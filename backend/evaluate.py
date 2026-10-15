"""Measure the Study Buddy pipelines on a fixed dataset.

    python evaluate.py retrieval              # offline and free: BM25 hit rate / MRR
    python evaluate.py quiz --limit 6         # needs ANTHROPIC_API_KEY, makes API calls

`quiz` compares up to four configurations on the same queries:

    baseline             the production path: BM25 top-6 -> one Claude call
    baseline+reflection  the same, then verify_and_repair
    agent                the tool-using agent, no verification
    agent+reflection     the agent followed by verify_and_repair

Everything runs on a temporary SQLite file, never on the real notes.db.

How quiz quality is scored: every returned question is judged against the FULL text of
the note it should have come from (not against whatever was retrieved), so a retrieval
miss shows up as questions that cannot be answered from the right note. The judge is
the same reviewer prompt that the reflection step uses. If it runs on the same model as
the generator it is partly grading its own work: set STUDY_BUDDY_JUDGE_MODEL to a
different model, and spot-check some questions by hand before quoting the numbers.
"""
import argparse
import json
import os
import sys
import tempfile
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEFAULT_DATASET = HERE / "eval_data" / "dataset.json"
RESULTS_DIR = HERE / "eval_results"
CONFIGS = ("baseline", "baseline+reflection", "agent", "agent+reflection")
PRODUCTION_TOP_K = 6  # what /generate-quiz-from-topic uses


# ------------------------------------------------------------------ setup

def load_dataset(path) -> dict:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    titles = {n["title"] for n in data["notes"]}
    for item in data["queries"]:
        if item["expected_source"] not in titles:
            raise SystemExit(f"Query {item['query']!r} expects unknown note {item['expected_source']!r}.")
    return data


def build_app(dataset: dict):
    """Import the real app on an isolated database and load the dataset notes into it."""
    import database

    database.DB_PATH = os.path.join(tempfile.mkdtemp(prefix="study_buddy_eval_"), "eval.db")
    import main

    for note in dataset["notes"]:
        main.library.add_document(note["title"], note["text"])
    return main


def make_client():
    from anthropic import Anthropic

    return Anthropic()


class CountingClient:
    """Wraps an Anthropic client and counts calls and tokens."""

    def __init__(self, inner):
        self._inner = inner
        self.messages = self
        self.reset()

    def reset(self):
        self.calls = 0
        self.input_tokens = 0
        self.output_tokens = 0

    def create(self, **kwargs):
        response = self._inner.messages.create(**kwargs)
        self.calls += 1
        usage = getattr(response, "usage", None)
        if usage is not None:
            self.input_tokens += getattr(usage, "input_tokens", 0) or 0
            self.output_tokens += getattr(usage, "output_tokens", 0) or 0
        return response


def unique(items):
    return list(dict.fromkeys(items))


# --------------------------------------------------------------- retrieval

def retrieval_rows(main, dataset: dict, top_k: int) -> list[dict]:
    rows = []
    for item in dataset["queries"]:
        results = main.library.search(item["query"], top_k=top_k)
        sources = [r["source"] for r in results]
        rank = next((i for i, s in enumerate(sources, 1) if s == item["expected_source"]), None)
        rows.append(
            {
                "query": item["query"],
                "type": item.get("type", "other"),
                "expected": item["expected_source"],
                "rank": rank,
                "top_source": sources[0] if sources else None,
                "results": len(results),
            }
        )
    return rows


def retrieval_stats(rows: list[dict]) -> dict | None:
    n = len(rows)
    if n == 0:
        return None
    return {
        "n": n,
        "hit@1": sum(1 for r in rows if r["rank"] == 1) / n,
        "hit@3": sum(1 for r in rows if r["rank"] and r["rank"] <= 3) / n,
        "hit@k": sum(1 for r in rows if r["rank"]) / n,
        "mrr": sum(1 / r["rank"] for r in rows if r["rank"]) / n,
        "empty": sum(1 for r in rows if r["results"] == 0) / n,
    }


def run_retrieval(args) -> None:
    dataset = load_dataset(args.dataset)
    main = build_app(dataset)
    rows = retrieval_rows(main, dataset, args.top_k)

    groups = {"all": rows}
    for kind in sorted({r["type"] for r in rows}):
        groups[kind] = [r for r in rows if r["type"] == kind]
    summary = {name: retrieval_stats(group) for name, group in groups.items()}

    print(f"\nBM25 retrieval, top_k={args.top_k}, {len(dataset['notes'])} notes, {len(rows)} queries\n")
    print(f"{'queries':<12}{'n':>4}{'hit@1':>8}{'hit@3':>8}{'hit@k':>8}{'MRR':>8}{'empty':>8}")
    for name, s in summary.items():
        print(
            f"{name:<12}{s['n']:>4}{s['hit@1']:>8.0%}{s['hit@3']:>8.0%}"
            f"{s['hit@k']:>8.0%}{s['mrr']:>8.2f}{s['empty']:>8.0%}"
        )
    misses = [r for r in rows if r["rank"] != 1]
    if misses:
        print("\nNot ranked first:")
        for r in misses:
            where = f"rank {r['rank']}" if r["rank"] else "not retrieved"
            print(f"  [{r['type']}] {r['query']!r} -> {where} (top result: {r['top_source']})")

    save_results("retrieval", {"top_k": args.top_k, "summary": summary, "rows": rows})


# -------------------------------------------------------------------- quiz

def run_config(config: str, item: dict, ctx: dict):
    """Returns (questions, sources the pipeline retrieved)."""
    import agent
    import quality

    main, gen = ctx["main"], ctx["gen"]
    n, difficulty = ctx["num_questions"], ctx["difficulty"]
    verify = config.endswith("+reflection")

    if config.startswith("baseline"):
        chunks = main.library.search(item["query"], top_k=PRODUCTION_TOP_K)
        retrieved = unique(c["source"] for c in chunks)
        if not chunks:
            return [], retrieved
        notes = "\n\n".join(c["text"] for c in chunks)
        questions = main.call_claude_for_quiz(notes, n, difficulty)
        if verify:
            questions = quality.verify_and_repair(gen, notes, questions, difficulty)["questions"]
        return questions, retrieved

    result = agent.run_quiz_agent(
        gen, main.library, f"Make a quiz about: {item['query']}", n, difficulty, verify=verify
    )
    return result["questions"], result["retrieved_sources"]


def summarize_quiz(records: list[dict], num_questions: int) -> dict:
    by_config = defaultdict(list)
    for r in records:
        by_config[r["config"]].append(r)

    def mean(values):
        values = list(values)
        return sum(values) / len(values) if values else 0.0

    summary = {}
    for config, recs in by_config.items():
        returned = sum(r["returned"] for r in recs)
        passed = sum(r["passed"] for r in recs)
        summary[config] = {
            "queries": len(recs),
            "errors": sum(1 for r in recs if r["error"]),
            "retrieval_hit_rate": mean(1.0 if r["retrieval_hit"] else 0.0 for r in recs),
            "pass_rate": passed / returned if returned else 0.0,
            "effective_yield": passed / (len(recs) * num_questions),
            "avg_calls": mean(r["calls"] for r in recs),
            "avg_tokens": mean(r["tokens"] for r in recs),
            "avg_seconds": mean(r["seconds"] for r in recs),
        }
    return summary


def markdown_table(summary: dict) -> str:
    lines = [
        "| Configuration | Retrieval hit | Question pass rate | Valid questions / requested | API calls / quiz | Tokens / quiz | Seconds / quiz |",
        "|---|---|---|---|---|---|---|",
    ]
    for config, s in summary.items():
        lines.append(
            f"| {config} | {s['retrieval_hit_rate']:.0%} | {s['pass_rate']:.0%} | "
            f"{s['effective_yield']:.0%} | {s['avg_calls']:.1f} | {s['avg_tokens']:.0f} | {s['avg_seconds']:.1f} |"
        )
    return "\n".join(lines)


def run_quiz(args) -> None:
    import quality

    if not os.getenv("ANTHROPIC_API_KEY"):
        raise SystemExit("Set ANTHROPIC_API_KEY first: `quiz` makes real API calls.")
    configs = [c.strip() for c in args.configs.split(",") if c.strip()]
    unknown = [c for c in configs if c not in CONFIGS]
    if unknown:
        raise SystemExit(f"Unknown configuration(s) {unknown}. Choose from {list(CONFIGS)}.")

    dataset = load_dataset(args.dataset)
    queries = dataset["queries"][: args.limit] if args.limit else dataset["queries"]
    notes_by_title = {n["title"]: n["text"] for n in dataset["notes"]}
    main = build_app(dataset)

    inner = make_client()
    gen, judge = CountingClient(inner), CountingClient(inner)
    main.get_client = lambda: gen  # the baseline path builds its client through main.get_client
    ctx = {"main": main, "gen": gen, "num_questions": args.questions, "difficulty": args.difficulty}

    total = len(configs) * len(queries)
    print(f"\n{len(queries)} queries x {len(configs)} configurations = {total} runs\n")
    records = []
    for config in configs:
        for item in queries:
            gen.reset()
            started = time.time()
            error, questions, retrieved = None, [], []
            try:
                questions, retrieved = run_config(config, item, ctx)
            except Exception as exc:  # one failed run must not stop the evaluation
                error = f"{type(exc).__name__}: {exc}"
            seconds = time.time() - started
            calls, tokens = gen.calls, gen.input_tokens + gen.output_tokens

            passed = 0
            if questions:
                try:
                    verdicts = quality.verify_questions(
                        judge, notes_by_title[item["expected_source"]], questions, model=quality.JUDGE_MODEL
                    )
                    passed = sum(1 for v in verdicts if v["passed"])
                except Exception as exc:
                    error = error or f"judge failed: {type(exc).__name__}: {exc}"

            records.append(
                {
                    "config": config,
                    "query": item["query"],
                    "type": item.get("type", "other"),
                    "expected": item["expected_source"],
                    "retrieval_hit": item["expected_source"] in retrieved,
                    "retrieved": retrieved,
                    "returned": len(questions) if isinstance(questions, list) else 0,
                    "passed": passed,
                    "calls": calls,
                    "tokens": tokens,
                    "seconds": round(seconds, 2),
                    "error": error,
                }
            )
            flag = "ERR" if error else "ok "
            print(
                f"  {flag} {config:<20} {item['query'][:48]:<48} "
                f"{records[-1]['passed']}/{records[-1]['returned']} pass, {calls} calls"
            )

    summary = summarize_quiz(records, args.questions)
    print("\n" + markdown_table(summary))
    if quality.JUDGE_MODEL == quality.MODEL:
        print(
            "\nNote: the judge runs on the same model as the generator, so these numbers are "
            "optimistic. Set STUDY_BUDDY_JUDGE_MODEL to another model and spot-check by hand."
        )
    save_results(
        "quiz",
        {
            "num_questions": args.questions,
            "difficulty": args.difficulty,
            "generator_model": quality.MODEL,
            "judge_model": quality.JUDGE_MODEL,
            "summary": summary,
            "records": records,
        },
    )


# --------------------------------------------------------------------- cli

def save_results(kind: str, payload: dict) -> None:
    RESULTS_DIR.mkdir(exist_ok=True)
    path = RESULTS_DIR / f"{kind}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"\nSaved {path}")


def main(argv=None) -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)

    common = argparse.ArgumentParser(add_help=False)
    common.add_argument("--dataset", default=str(DEFAULT_DATASET))

    r = sub.add_parser("retrieval", parents=[common], help="BM25 hit rate and MRR (offline)")
    r.add_argument("--top-k", type=int, default=PRODUCTION_TOP_K)
    r.set_defaults(func=run_retrieval)

    q = sub.add_parser("quiz", parents=[common], help="compare quiz quality (uses the API)")
    q.add_argument("--limit", type=int, default=0, help="only the first N queries (0 = all)")
    q.add_argument("--questions", type=int, default=3, help="questions per quiz")
    q.add_argument("--difficulty", default="medium", choices=["easy", "medium", "hard"])
    q.add_argument("--configs", default="baseline,baseline+reflection,agent+reflection")
    q.set_defaults(func=run_quiz)

    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
