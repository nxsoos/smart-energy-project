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
    if (!device.online || !device.isOn) return Colors.grey;

    switch (device.type) {
      case DeviceType.light:
        return AppColors.accent;
      case DeviceType.socket:
        return AppColors.primary;
      case DeviceType.airConditioner:
        return Colors.blue;
    }
  }

  Widget _metricChip({
    required IconData icon,
    required String label,
    required String value,
    required Color color,
    bool active = true,
  }) {
    final effectiveColor = active ? color : Colors.grey;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
      decoration: BoxDecoration(
        color: active ? color.withValues(alpha: 0.1) : Colors.grey[100],
        borderRadius: BorderRadius.circular(12),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: effectiveColor),
          const SizedBox(width: 4),
          Text(
            label.isEmpty ? value : '$label $value',
            style: TextStyle(
              fontSize: 13,
              fontWeight: FontWeight.w600,
              color: effectiveColor,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final color = _getDeviceColor();
    final controlsDisabled =
        isCommandPending ||
        !device.online ||
        !device.localOnline ||
        !device.controllable;
    final switchValue = device.online && device.localOnline && device.isOn;
    final visibleCommandError = device.online && device.localOnline
        ? commandError
        : null;
    final isLocalControl = device.controlMethod == 'home_assistant';

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
                  if (isCommandPending || device.commandInProgress) ...[
                    const SizedBox(
                      width: 24,
                      height: 24,
                      child: CircularProgressIndicator(strokeWidth: 2.5),
                    ),
                    const SizedBox(width: 12),
                  ],
                  Switch(
                    value: switchValue,
                    onChanged: controlsDisabled ? null : onToggle,
                    activeThumbColor: color,
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  if (device.energySupported)
                    _metricChip(
                      icon: Icons.bolt,
                      label: '',
                      value: formatPower(device.currentPower),
                      color: color,
                      active: switchValue,
                    ),
                  if (device.energySupported)
                    _metricChip(
                      icon: Icons.electrical_services,
                      label: 'V',
                      value: device.voltage > 0
                          ? device.voltage.toStringAsFixed(1)
                          : '--',
                      color: AppColors.primary,
                      active: device.online,
                    ),
                  if (device.energySupported)
                    _metricChip(
                      icon: Icons.speed,
                      label: 'A',
                      value: device.current.toStringAsFixed(3),
                      color: AppColors.primary,
                      active: device.online,
                    ),
                  if (device.energySupported)
                    _metricChip(
                      icon: Icons.timeline,
                      label: '',
                      value: formatEnergy(device.energyToday),
                      color: AppColors.primary,
                      active: device.online,
                    ),
                  if (isLocalControl)
                    Container(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 12,
                        vertical: 6,
                      ),
                      decoration: BoxDecoration(
                        color: Colors.teal.withValues(alpha: 0.1),
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: const Text(
                        'Local control',
                        style: TextStyle(
                          fontSize: 14,
                          fontWeight: FontWeight.w600,
                          color: Colors.teal,
                        ),
                      ),
                    ),
                ],
              ),
              if (isCommandPending || device.commandInProgress) ...[
                const SizedBox(height: 10),
                ClipRRect(
                  borderRadius: BorderRadius.circular(999),
                  child: const LinearProgressIndicator(minHeight: 3),
                ),
              ],
              if (!device.online ||
                  !device.localOnline ||
                  !device.controllable) ...[
                const SizedBox(height: 10),
                Text(
                  (!device.online || !device.localOnline)
                      ? 'Offline'
                      : 'Control disabled',
                  style: const TextStyle(
                    color: AppColors.textSecondary,
                    fontSize: 12,
                    fontWeight: FontWeight.w600,
                  ),
                ),
              ],
              if (visibleCommandError != null &&
                  visibleCommandError.isNotEmpty) ...[
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
                        visibleCommandError,
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
