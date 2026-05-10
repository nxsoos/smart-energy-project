import 'dart:math' as math;

import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../core/utils/helpers.dart';
import '../../../shared/models/energy_reading.dart';

/// Full-width live power hero with animated energy ring.
class EnergyHeroCard extends StatelessWidget {
  const EnergyHeroCard({
    super.key,
    required this.reading,
    required this.costMonth,
  });

  final EnergyReading reading;
  final double costMonth;

  @override
  Widget build(BuildContext context) {
    final powerKw = reading.power / 1000;
    final progress = (powerKw / 4).clamp(0.05, 1.0);
    final hasMonth = reading.monthDataAvailable;
    return RepaintBoundary(
      child: Container(
        padding: const EdgeInsets.all(22),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [ColorTokens.primary, ColorTokens.accent],
          ),
          borderRadius: BorderRadius.circular(24),
          boxShadow: const [
            BoxShadow(color: ColorTokens.primaryGlow, blurRadius: 28),
          ],
        ),
        child: Row(
          children: [
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Live Power',
                    style: AppTextStyles.caption.copyWith(
                      color: ColorTokens.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 10),
                  TweenAnimationBuilder<double>(
                    tween: Tween(begin: 0, end: powerKw),
                    duration: const Duration(milliseconds: 500),
                    builder: (context, value, _) => Text(
                      '${value.toStringAsFixed(2)} kW',
                      style: AppTextStyles.mono.copyWith(fontSize: 36),
                    ),
                  ),
                  const SizedBox(height: 14),
                  Text(
                    hasMonth
                        ? 'This month ${formatCost(costMonth)}'
                        : 'No monthly data yet',
                    style: AppTextStyles.bodyMedium,
                  ),
                  const SizedBox(height: 4),
                  Text(
                    hasMonth
                        ? '${reading.energyMonth.toStringAsFixed(1)} kWh this month'
                        : 'Waiting for cloud summaries',
                    style: AppTextStyles.caption.copyWith(
                      color: ColorTokens.textPrimary,
                    ),
                  ),
                ],
              ),
            ),
            SizedBox(
              width: 118,
              height: 118,
              child: CustomPaint(
                painter: _PowerRingPainter(progress: progress),
                child: const Icon(
                  Icons.bolt,
                  color: ColorTokens.textPrimary,
                  size: 38,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _PowerRingPainter extends CustomPainter {
  const _PowerRingPainter({required this.progress});

  final double progress;

  @override
  void paint(Canvas canvas, Size size) {
    final center = size.center(Offset.zero);
    final radius = size.shortestSide / 2 - 8;
    final base = Paint()
      ..color = ColorTokens.textPrimary.withValues(alpha: 0.18)
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round;
    final active = Paint()
      ..color = ColorTokens.textPrimary
      ..style = PaintingStyle.stroke
      ..strokeWidth = 10
      ..strokeCap = StrokeCap.round;
    canvas.drawCircle(center, radius, base);
    canvas.drawArc(
      Rect.fromCircle(center: center, radius: radius),
      -math.pi / 2,
      math.pi * 2 * progress,
      false,
      active,
    );
  }

  @override
  bool shouldRepaint(covariant _PowerRingPainter oldDelegate) =>
      oldDelegate.progress != progress;
}
