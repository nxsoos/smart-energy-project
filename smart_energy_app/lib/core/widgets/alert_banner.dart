import 'package:flutter/material.dart';

import '../../shared/models/alert.dart';
import '../utils/constants.dart';
import '../utils/helpers.dart';

/// High-contrast alert banner for dashboard safety states.
class AlertBanner extends StatelessWidget {
  const AlertBanner({super.key, required this.alert, this.onDismiss});

  final Alert alert;
  final VoidCallback? onDismiss;

  IconData _getAlertIcon() {
    switch (alert.type.toString().split('.').last) {
      case 'overload':
        return Icons.warning_amber_rounded;
      case 'fire':
        return Icons.local_fire_department;
      case 'highConsumption':
        return Icons.trending_up;
      case 'sensorFailure':
        return Icons.sensors_off;
      default:
        return Icons.info_outline;
    }
  }

  @override
  Widget build(BuildContext context) {
    final isDark = Theme.of(context).brightness == Brightness.dark;
    final textPrimary = isDark
        ? AppColors.textPrimary
        : const Color(0xFF17231D);
    final textSecondary = isDark
        ? AppColors.textSecondary
        : const Color(0xFF65766D);
    final textMuted = isDark ? AppColors.textMuted : const Color(0xFF849287);
    final color = Color(alert.color);
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 5),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.13),
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(9),
              decoration: BoxDecoration(
                color: color.withValues(alpha: 0.16),
                shape: BoxShape.circle,
              ),
              child: Icon(_getAlertIcon(), color: color, size: 21),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    alert.message,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w800,
                      color: textPrimary,
                    ),
                  ),
                  if (alert.affectedBranch != null) ...[
                    const SizedBox(height: 3),
                    Text(
                      alert.affectedBranch!,
                      style: TextStyle(fontSize: 12, color: textSecondary),
                    ),
                  ],
                  const SizedBox(height: 3),
                  Text(
                    formatTime(alert.timestamp),
                    style: TextStyle(fontSize: 11, color: textMuted),
                  ),
                ],
              ),
            ),
            if (onDismiss != null)
              IconButton(
                icon: const Icon(Icons.close, size: 20),
                onPressed: onDismiss,
                color: textSecondary,
              ),
          ],
        ),
      ),
    );
  }
}
