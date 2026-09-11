
import importlib
import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    test_db_path = str(tmp_path / "test_notes.db")

    import database
    database.DB_PATH = test_db_path

    import main
    importlib.reload(main)

    return TestClient(main.app)
