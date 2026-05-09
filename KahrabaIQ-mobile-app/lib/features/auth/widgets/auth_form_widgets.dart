import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';

/// Auth tab mode.
enum AuthMode { login, signup }

/// Sign-in/create-account tab selector.
class AuthModeTabs extends StatelessWidget {
  const AuthModeTabs({super.key, required this.mode, required this.onChanged});

  final AuthMode mode;
  final ValueChanged<AuthMode> onChanged;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: ColorTokens.surface,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          _tab('Sign in', AuthMode.login),
          _tab('Create account', AuthMode.signup),
        ],
      ),
    );
  }

  Widget _tab(String label, AuthMode value) {
    final selected = mode == value;
    return Expanded(
      child: GestureDetector(
        onTap: () => onChanged(value),
        child: AnimatedContainer(
          duration: const Duration(milliseconds: 200),
          padding: const EdgeInsets.symmetric(vertical: 12),
          decoration: BoxDecoration(
            color: selected ? ColorTokens.surfaceElevated : Colors.transparent,
            borderRadius: BorderRadius.circular(10),
          ),
          child: Text(
            label,
            style: AppTextStyles.bodyMedium,
            textAlign: TextAlign.center,
          ),
        ),
      ),
    );
  }
}

/// Tokenized auth form field.
class AuthField extends StatelessWidget {
  const AuthField({
    super.key,
    required this.controller,
    required this.label,
    required this.icon,
    this.obscureText = false,
    this.keyboardType,
  });

  final TextEditingController controller;
  final String label;
  final IconData icon;
  final bool obscureText;
  final TextInputType? keyboardType;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      obscureText: obscureText,
      keyboardType: keyboardType,
      decoration: InputDecoration(labelText: label, prefixIcon: Icon(icon)),
      validator: (value) =>
          (value ?? '').trim().isEmpty ? '$label is required.' : null,
    );
  }
}

/// Full-width gradient authentication action.
class AuthGradientButton extends StatelessWidget {
  const AuthGradientButton({
    super.key,
    required this.label,
    required this.isBusy,
    required this.onPressed,
  });

  final String label;
  final bool isBusy;
  final VoidCallback onPressed;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: isBusy ? null : onPressed,
      child: Container(
        height: 56,
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [ColorTokens.primary, ColorTokens.accent],
          ),
          borderRadius: BorderRadius.circular(12),
          boxShadow: const [
            BoxShadow(color: ColorTokens.primaryGlow, blurRadius: 20),
          ],
        ),
        child: Center(
          child: Text(
            isBusy ? 'Please wait...' : label,
            style: AppTextStyles.bodyMedium.copyWith(
              color: ColorTokens.background,
            ),
          ),
        ),
      ),
    );
  }
}

/// Animated KahrabaIQ lightning-ring logo.
class AuthAnimatedLogo extends StatelessWidget {
  const AuthAnimatedLogo({super.key, required this.controller});

  final AnimationController controller;

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => CustomPaint(
        painter: _LogoPainter(progress: controller.value),
        child: const SizedBox(
          height: 120,
          child: Center(
            child: Icon(Icons.bolt, color: ColorTokens.primary, size: 44),
          ),
        ),
      ),
    );
  }
}

class _LogoPainter extends CustomPainter {
  const _LogoPainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = math.min(size.width, size.height) / 2 - 10;
    final paint = Paint()
      ..shader = const LinearGradient(
        colors: [ColorTokens.primary, ColorTokens.accent],
      ).createShader(Rect.fromCircle(center: center, radius: radius))
      ..style = PaintingStyle.stroke
      ..strokeWidth = 5
      ..strokeCap = StrokeCap.round;
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      progress * math.pi * 2,
      math.pi * 1.45,
      false,
      paint,
    );
  }

  @override
  bool shouldRepaint(covariant _LogoPainter oldDelegate) =>
      oldDelegate.progress != progress;
}
