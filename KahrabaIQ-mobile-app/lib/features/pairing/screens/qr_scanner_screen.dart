import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';

/// Premium QR pairing scanner.
class QrScannerScreen extends StatefulWidget {
  const QrScannerScreen({super.key});

  @override
  State<QrScannerScreen> createState() => _QrScannerScreenState();
}

class _QrScannerScreenState extends State<QrScannerScreen>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;
  final TextEditingController _manualController = TextEditingController();
  bool _handled = false;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 2),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    _manualController.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Stack(
          children: [
            MobileScanner(onDetect: _handleDetection),
            Container(color: ColorTokens.background.withValues(alpha: 0.62)),
            Center(
              child: SizedBox(
                width: 270,
                height: 270,
                child: AnimatedBuilder(
                  animation: _controller,
                  builder: (context, _) => CustomPaint(
                    painter: _ScannerPainter(progress: _controller.value),
                  ),
                ),
              ),
            ),
            Positioned(
              left: 20,
              right: 20,
              bottom: 38,
              child: Column(
                children: [
                  Text(
                    'Point camera at your device QR code',
                    style: AppTextStyles.h3,
                    textAlign: TextAlign.center,
                  ),
                  const SizedBox(height: 14),
                  OutlinedButton(
                    onPressed: _showManualEntry,
                    child: const Text('Enter code manually'),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _handleDetection(BarcodeCapture capture) {
    if (_handled) {
      return;
    }
    for (final barcode in capture.barcodes) {
      final value = barcode.rawValue;
      if (value != null && value.isNotEmpty) {
        _handled = true;
        Navigator.pop(context, value);
        return;
      }
    }
  }

  Future<void> _showManualEntry() async {
    final value = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: ColorTokens.surface,
        title: const Text('Enter pairing code'),
        content: TextField(
          controller: _manualController,
          autofocus: true,
          minLines: 1,
          maxLines: 3,
          decoration: const InputDecoration(
            hintText: 'kahrabaiq://pair?... or kahrabaiq://invite?...',
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, _manualController.text),
            child: const Text('Pair'),
          ),
        ],
      ),
    );
    final trimmed = value?.trim();
    if (trimmed != null && trimmed.isNotEmpty && mounted) {
      Navigator.pop(context, trimmed);
    }
  }
}

class _ScannerPainter extends CustomPainter {
  const _ScannerPainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final bracket = Paint()
      ..color = ColorTokens.primary
      ..strokeWidth = 4
      ..strokeCap = StrokeCap.round
      ..style = PaintingStyle.stroke;
    const length = 42.0;
    final rect = Offset.zero & size;
    for (final corner in [
      rect.topLeft,
      rect.topRight,
      rect.bottomLeft,
      rect.bottomRight,
    ]) {
      final xSign = corner.dx == 0 ? 1.0 : -1.0;
      final ySign = corner.dy == 0 ? 1.0 : -1.0;
      canvas.drawLine(corner, corner + Offset(length * xSign, 0), bracket);
      canvas.drawLine(corner, corner + Offset(0, length * ySign), bracket);
    }
    final y = size.height * progress;
    final line = Paint()
      ..color = ColorTokens.primary.withValues(alpha: 0.75)
      ..strokeWidth = 3;
    canvas.drawLine(Offset(18, y), Offset(size.width - 18, y), line);
  }

  @override
  bool shouldRepaint(covariant _ScannerPainter oldDelegate) =>
      oldDelegate.progress != progress;
}
