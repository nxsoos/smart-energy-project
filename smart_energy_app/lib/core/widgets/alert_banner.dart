import 'package:flutter/material.dart';

import '../../shared/models/alert.dart';
import '../theme/app_text_styles.dart';
import '../theme/color_tokens.dart';
import '../utils/constants.dart';
import '../utils/helpers.dart';

/// Swipe-dismissible alert banner with severity-driven styling.
class AlertBanner extends StatefulWidget {
  const AlertBanner({super.key, required this.alert, this.onDismiss});

  final Alert alert;
  final VoidCallback? onDismiss;

  @override
  State<AlertBanner> createState() => _AlertBannerState();
}

class _AlertBannerState extends State<AlertBanner>
    with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1500),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final color = _severityColor(widget.alert.severity);
    final content = AnimatedBuilder(
      animation: _controller,
      builder: (context, child) {
        final glow =
            widget.alert.severity == 'critical' ||
            widget.alert.severity == 'high';
        return Container(
          decoration: BoxDecoration(
            color: color.withValues(
              alpha: glow ? 0.10 + (_controller.value * 0.06) : 0.10,
            ),
            borderRadius: BorderRadius.circular(16),
            border: Border.all(color: color.withValues(alpha: 0.28)),
            boxShadow: glow
                ? [
                    BoxShadow(
                      color: color.withValues(
                        alpha: 0.22 + (_controller.value * 0.12),
                      ),
                      blurRadius: 24,
                    ),
                  ]
                : null,
          ),
          child: IntrinsicHeight(
            child: Row(
              children: [
                Container(
                  width: 4,
                  decoration: BoxDecoration(
                    color: color,
                    borderRadius: const BorderRadius.horizontal(
                      left: Radius.circular(16),
                    ),
                  ),
                ),
                Expanded(child: child!),
              ],
            ),
          ),
        );
      },
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(_alertIcon(), color: color, size: 24),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(widget.alert.message, style: AppTextStyles.bodyMedium),
                  const SizedBox(height: 4),
                  Text(
                    widget.alert.affectedBranch ??
                        formatTime(widget.alert.timestamp),
                    style: AppTextStyles.caption,
                  ),
                ],
              ),
            ),
            Icon(Icons.swipe_left, color: ColorTokens.textMuted, size: 18),
          ],
        ),
      ),
    );

    return Dismissible(
      key: ValueKey(widget.alert.id),
      direction: DismissDirection.endToStart,
      onDismissed: (_) => widget.onDismiss?.call(),
      child: content,
    );
  }

  Color _severityColor(String severity) {
    switch (severity.toLowerCase()) {
      case 'critical':
      case 'high':
        return ColorTokens.danger;
      case 'medium':
        return ColorTokens.warning;
      default:
        return ColorTokens.info;
    }
  }

  IconData _alertIcon() {
    switch (widget.alert.type) {
      case AlertType.fire:
        return Icons.local_fire_department;
      case AlertType.overload:
        return Icons.warning_amber_rounded;
      case AlertType.highConsumption:
        return Icons.trending_up;
      case AlertType.sensorFailure:
        return Icons.sensors_off;
    }
  }
}
