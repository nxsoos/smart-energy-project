import 'package:flutter/material.dart';
import '../models/device.dart';
import '../utils/constants.dart';
import '../utils/helpers.dart';

/// Device control card for the dashboard
class DeviceCard extends StatelessWidget {
  final Device device;
  final VoidCallback? onTap;
  final Function(bool)? onToggle;
  final bool isCommandPending;
  final String? commandError;

  const DeviceCard({
    super.key,
    required this.device,
    this.onTap,
    this.onToggle,
    this.isCommandPending = false,
    this.commandError,
  });

  IconData _getDeviceIcon() {
    switch (device.type) {
      case DeviceType.light:
        return Icons.lightbulb_outline;
      case DeviceType.socket:
        return Icons.power;
      case DeviceType.airConditioner:
        return Icons.ac_unit;
    }
  }

  Color _getDeviceColor() {
    if (!device.isOn) return Colors.grey;

    switch (device.type) {
      case DeviceType.light:
        return AppColors.accent;
      case DeviceType.socket:
        return AppColors.primary;
      case DeviceType.airConditioner:
        return Colors.blue;
    }
  }

  @override
  Widget build(BuildContext context) {
    final color = _getDeviceColor();

    return Card(
      elevation: 2,
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(8),
        child: Padding(
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(_getDeviceIcon(), color: color, size: 32),
                  const SizedBox(width: 12),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          device.name,
                          style: const TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.bold,
                          ),
                        ),
                        Text(
                          device.branch,
                          style: TextStyle(
                            fontSize: 12,
                            color: Colors.grey[600],
                          ),
                        ),
                      ],
                    ),
                  ),
                  if (isCommandPending) ...[
                    const SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(strokeWidth: 2.5),
                    ),
                    const SizedBox(width: 12),
                  ],
                  Switch(
                    value: device.isOn,
                    onChanged: isCommandPending ? null : onToggle,
                    activeThumbColor: color,
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 12,
                  vertical: 6,
                ),
                decoration: BoxDecoration(
                  color: device.isOn
                      ? color.withValues(alpha: 0.1)
                      : Colors.grey[100],
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Row(
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    Icon(
                      Icons.bolt,
                      size: 16,
                      color: device.isOn ? color : Colors.grey,
                    ),
                    const SizedBox(width: 4),
                    Text(
                      formatPower(device.currentPower),
                      style: TextStyle(
                        fontSize: 14,
                        fontWeight: FontWeight.w600,
                        color: device.isOn ? color : Colors.grey,
                      ),
                    ),
                  ],
                ),
              ),
              if (isCommandPending) ...[
                const SizedBox(height: 10),
                ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: const LinearProgressIndicator(minHeight: 3),
                ),
              ],
              if (commandError != null && commandError!.isNotEmpty) ...[
                const SizedBox(height: 10),
                Row(
                  children: [
                    const Icon(
                      Icons.error_outline,
                      color: AppColors.energyDanger,
                      size: 16,
                    ),
                    const SizedBox(width: 6),
                    Expanded(
                      child: Text(
                        commandError!,
                        style: const TextStyle(
                          color: AppColors.energyDanger,
                          fontSize: 12,
                          fontWeight: FontWeight.w600,
                        ),
                      ),
                    ),
                  ],
                ),
              ],
            ],
          ),
        ),
      ),
    );
  }
}
