import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';

/// Auth tab mode.
enum AuthMode { login, signup, verifySignup }

/// Sign-in/create-account tab selector.
class AuthModeTabs extends StatelessWidget {
  const AuthModeTabs({super.key, required this.mode, required this.onChanged});

  final AuthMode mode;
  final ValueChanged<AuthMode> onChanged;

  @override
  Widget build(BuildContext context) {
    final selectedMode = mode == AuthMode.verifySignup ? AuthMode.signup : mode;
    return Container(
      padding: const EdgeInsets.all(4),
      decoration: BoxDecoration(
        color: ColorTokens.surface,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Row(
        children: [
          _tab('Sign in', AuthMode.login, selectedMode),
          _tab('Create account', AuthMode.signup, selectedMode),
        ],
      ),
    );
  }

  Widget _tab(String label, AuthMode value, AuthMode selectedMode) {
    final selected = selectedMode == value;
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
    this.focusNode,
    this.textInputAction,
    this.autofillHints,
    this.onFieldSubmitted,
  });

  final TextEditingController controller;
  final String label;
  final IconData icon;
  final bool obscureText;
  final TextInputType? keyboardType;
  final FocusNode? focusNode;
  final TextInputAction? textInputAction;
  final Iterable<String>? autofillHints;
  final ValueChanged<String>? onFieldSubmitted;

  @override
  Widget build(BuildContext context) {
    return TextFormField(
      controller: controller,
      focusNode: focusNode,
      obscureText: obscureText,
      keyboardType: keyboardType,
      textInputAction: textInputAction,
      autofillHints: autofillHints,
      onFieldSubmitted: onFieldSubmitted,
      onTap: () => Scrollable.ensureVisible(
        context,
        duration: const Duration(milliseconds: 240),
        curve: Curves.easeOutCubic,
        alignmentPolicy: ScrollPositionAlignmentPolicy.keepVisibleAtEnd,
      ),
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

/// Top KahrabaIQ brand mark.
class AuthHeader extends StatelessWidget {
  const AuthHeader({super.key, required this.screenHeight});

  final double screenHeight;

  @override
  Widget build(BuildContext context) {
    final logoHeight = screenHeight < 720
        ? 98.0
        : screenHeight < 860
        ? 118.0
        : 138.0;
    return SizedBox(
      height: logoHeight,
      child: Center(
        child: Image.asset(
          'assets/brand/kahrabaiq-brand-identity.png',
          height: logoHeight,
          fit: BoxFit.contain,
          filterQuality: FilterQuality.high,
        ),
      ),
    );
  }
}

/// Animated electricity gauge.
class ElectricityAnimation extends StatelessWidget {
  const ElectricityAnimation({
    super.key,
    required this.controller,
    required this.screenHeight,
  });

  final AnimationController controller;
  final double screenHeight;

  @override
  Widget build(BuildContext context) {
    final animationSize = screenHeight < 720
        ? 82.0
        : screenHeight < 860
        ? 96.0
        : 110.0;
    final iconSize = screenHeight < 720 ? 34.0 : 42.0;
    return AnimatedBuilder(
      animation: controller,
      builder: (context, _) => Center(
        child: CustomPaint(
          painter: _LogoPainter(progress: controller.value),
          child: SizedBox.square(
            dimension: animationSize,
            child: Center(
              child: Icon(
                Icons.bolt,
                color: ColorTokens.primary,
                size: iconSize,
              ),
            ),
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
    final rect = Rect.fromCircle(center: center, radius: radius);
    final paint = Paint()
      ..shader = const LinearGradient(
        colors: [ColorTokens.primary, ColorTokens.accent],
      ).createShader(rect)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 5
      ..strokeCap = StrokeCap.round;
    final glowPaint = Paint()
      ..color = ColorTokens.primaryGlow
      ..style = PaintingStyle.stroke
      ..strokeWidth = 12
      ..maskFilter = const MaskFilter.blur(BlurStyle.normal, 10);
    canvas.drawArc(
      rect,
      progress * math.pi * 2,
      math.pi * 1.45,
      false,
      glowPaint,
    );
    canvas.drawArc(rect, progress * math.pi * 2, math.pi * 1.45, false, paint);
  }

  @override
  bool shouldRepaint(covariant _LogoPainter oldDelegate) =>
      oldDelegate.progress != progress;
}
