import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

class StudyColors {
  static const paper = Color(0xFFFAFAF6);
  static const paperLine = Color(0xFFE4E1D6);
  static const ink = Color(0xFF1B2A4A);
  static const inkSoft = Color(0xFF4A4A45);
  static const highlighter = Color(0xFFFFD23F);
  static const correct = Color(0xFF2E7D4F);
  static const correctBg = Color(0xFFE8F5EC);
  static const incorrect = Color(0xFFB8442B);
  static const incorrectBg = Color(0xFFFBEAE5);
}

class StudyText {
  static TextStyle masthead = GoogleFonts.sourceSerif4(
    fontSize: 32,
    fontWeight: FontWeight.w700,
    color: StudyColors.ink,
    letterSpacing: -0.3,
  );

  static TextStyle questionText = GoogleFonts.sourceSerif4(
    fontSize: 19,
    fontWeight: FontWeight.w600,
    color: StudyColors.ink,
    height: 1.35,
  );

  static TextStyle body = GoogleFonts.ibmPlexSans(
    fontSize: 15,
    color: StudyColors.ink,
  );

  static TextStyle bodySoft = GoogleFonts.ibmPlexSans(
    fontSize: 14,
    color: StudyColors.inkSoft,
  );

  static TextStyle label = GoogleFonts.ibmPlexMono(
    fontSize: 11,
    fontWeight: FontWeight.w500,
    color: StudyColors.inkSoft,
    letterSpacing: 0.6,
  );

  static TextStyle mono = GoogleFonts.ibmPlexMono(
    fontSize: 14,
    color: StudyColors.ink,
  );

  static TextStyle score = GoogleFonts.sourceSerif4(
    fontSize: 44,
    fontWeight: FontWeight.w700,
    color: StudyColors.ink,
  );
}

class NotebookBackground extends StatelessWidget {
  final Widget child;

  const NotebookBackground({super.key, required this.child});

  @override
  Widget build(BuildContext context) {
    return Container(
      color: StudyColors.paper,
      child: CustomPaint(
        painter: _LinePainter(),
        child: child,
      ),
    );
  }
}

class _LinePainter extends CustomPainter {
  @override
  void paint(Canvas canvas, Size size) {
    final paint = Paint()
      ..color = StudyColors.paperLine
      ..strokeWidth = 1;

    const lineSpacing = 32.0;
    for (double y = lineSpacing; y < size.height; y += lineSpacing) {
      canvas.drawLine(Offset(0, y), Offset(size.width, y), paint);
    }
  }

  @override
  bool shouldRepaint(covariant CustomPainter oldDelegate) => false;
}

class HighlighterButton extends StatefulWidget {
  final String label;
  final VoidCallback? onPressed;
  final Widget? child;

  const HighlighterButton({
    super.key,
    required this.label,
    required this.onPressed,
    this.child,
  });

  @override
  State<HighlighterButton> createState() => _HighlighterButtonState();
}

class _HighlighterButtonState extends State<HighlighterButton> {
  bool _pressed = false;

  @override
  Widget build(BuildContext context) {
    final disabled = widget.onPressed == null;

    return GestureDetector(
      onTapDown: disabled ? null : (_) => setState(() => _pressed = true),
      onTapUp: disabled ? null : (_) => setState(() => _pressed = false),
      onTapCancel: disabled ? null : () => setState(() => _pressed = false),
      onTap: widget.onPressed,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 150),
        curve: Curves.easeOut,
        width: double.infinity,
        padding: const EdgeInsets.symmetric(vertical: 14),
        decoration: BoxDecoration(
          color: disabled
              ? StudyColors.paperLine
              : (_pressed ? StudyColors.highlighter : Colors.transparent),
          border: Border.all(
            color: disabled ? StudyColors.paperLine : StudyColors.ink,
            width: 2,
          ),
          borderRadius: BorderRadius.circular(2),
        ),
        alignment: Alignment.center,
        child: widget.child ??
            Text(
              widget.label,
              style: StudyText.body.copyWith(
                fontWeight: FontWeight.w600,
                color: disabled ? StudyColors.inkSoft : StudyColors.ink,
              ),
            ),
      ),
    );
  }
}
