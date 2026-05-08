import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';

/// Full-width safety status bar for live or stale sensor feeds.
class SafetyStatusBar extends StatelessWidget {
  const SafetyStatusBar({
    super.key,
    required this.isSafe,
    this.isOffline = false,
  });

  final bool isSafe;
  final bool isOffline;

  @override
  Widget build(BuildContext context) {
    final color = isOffline
        ? ColorTokens.textMuted
        : isSafe
        ? ColorTokens.success
        : ColorTokens.danger;
    return AnimatedContainer(
      duration: const Duration(milliseconds: 250),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.3)),
      ),
      child: Row(
        children: [
          Icon(
            isOffline
                ? Icons.sensors_off
                : isSafe
                ? Icons.verified
                : Icons.warning_amber_rounded,
            color: color,
          ),
          const SizedBox(width: 12),
          Text(
            isOffline
                ? 'Sensor feed offline'
                : isSafe
                ? 'All Systems Normal'
                : 'Safety Alert Detected',
            style: AppTextStyles.bodyMedium.copyWith(color: color),
          ),
        ],
      ),
    );
  }
}
