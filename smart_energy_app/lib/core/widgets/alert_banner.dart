import 'package:flutter/material.dart';
import '../../shared/models/alert.dart';
import '../utils/helpers.dart';

/// Alert banner widget for displaying system alerts
class AlertBanner extends StatelessWidget {
  final Alert alert;
  final VoidCallback? onDismiss;

  const AlertBanner({super.key, required this.alert, this.onDismiss});

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
    return Container(
      margin: const EdgeInsets.symmetric(vertical: 4),
      decoration: BoxDecoration(
        color: Color(alert.color).withValues(alpha: 0.1),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: Color(alert.color), width: 1),
      ),
      child: Padding(
        padding: const EdgeInsets.all(12.0),
        child: Row(
          children: [
            Icon(_getAlertIcon(), color: Color(alert.color), size: 24),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    alert.message,
                    style: TextStyle(
                      fontSize: 14,
                      fontWeight: FontWeight.w600,
                      color: Color(alert.color),
                    ),
                  ),
                  if (alert.affectedBranch != null) ...[
                    const SizedBox(height: 2),
                    Text(
                      alert.affectedBranch!,
                      style: TextStyle(fontSize: 12, color: Colors.grey[700]),
                    ),
                  ],
                  Text(
                    formatTime(alert.timestamp),
                    style: TextStyle(fontSize: 11, color: Colors.grey[600]),
                  ),
                ],
              ),
            ),
            if (onDismiss != null)
              IconButton(
                icon: const Icon(Icons.close, size: 20),
                onPressed: onDismiss,
                color: Colors.grey[600],
              ),
          ],
        ),
      ),
    );
  }
}
