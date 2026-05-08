import 'package:flutter/material.dart';

import '../../shared/models/device.dart';
import '../utils/constants.dart';
import '../utils/helpers.dart';

/// Device command surface with explicit online, pending, and local-control states.
class DeviceCard extends StatelessWidget {
  const DeviceCard({
    super.key,
    required this.device,
    this.onTap,
    this.onToggle,
    this.isCommandPending = false,
    this.commandError,
  });

  final Device device;
  final VoidCallback? onTap;
  final Function(bool)? onToggle;
  final bool isCommandPending;
  final String? commandError;

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
    if (!device.online || !device.localOnline || !device.isOn) {
      return AppColors.textMuted;
    }
    switch (device.type) {
      case DeviceType.light:
        return AppColors.accent;
      case DeviceType.socket:
        return AppColors.primary;
      case DeviceType.airConditioner:
        return const Color(0xFF65B7FF);
    }
  }

  Widget _metricChip({
    required IconData icon,
    required String label,
    required String value,
    required Color color,
    bool active = true,
  }) {
    final effectiveColor = active ? color : AppColors.textMuted;
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
      decoration: BoxDecoration(
        color: effectiveColor.withValues(alpha: active ? 0.13 : 0.08),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: effectiveColor.withValues(alpha: 0.20)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 15, color: effectiveColor),
          const SizedBox(width: 5),
          Text(
            label.isEmpty ? value : '$label $value',
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w800,
              color: effectiveColor,
            ),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final theme = Theme.of(context);
    final isDark = theme.brightness == Brightness.dark;
    final textPrimary = isDark
        ? AppColors.textPrimary
        : const Color(0xFF17231D);
    final textSecondary = isDark
        ? AppColors.textSecondary
        : const Color(0xFF65766D);
    final outline = isDark ? AppColors.outline : const Color(0xFFD8CFBE);
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

    return Container(
      decoration: BoxDecoration(
        color: theme.colorScheme.surface,
        borderRadius: BorderRadius.circular(UIConstants.cardBorderRadius),
        border: Border.all(
          color: switchValue ? color.withValues(alpha: 0.34) : outline,
        ),
      ),
      child: Material(
        color: Colors.transparent,
        child: InkWell(
          onTap: onTap,
          borderRadius: BorderRadius.circular(UIConstants.cardBorderRadius),
          child: Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: color.withValues(alpha: 0.14),
                        borderRadius: BorderRadius.circular(16),
                      ),
                      child: Icon(_getDeviceIcon(), color: color, size: 26),
                    ),
                    const SizedBox(width: 13),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            device.name,
                            style: TextStyle(
                              fontSize: 16,
                              fontWeight: FontWeight.w900,
                              color: textPrimary,
                            ),
                          ),
                          const SizedBox(height: 3),
                          Text(
                            device.branch,
                            style: TextStyle(
                              fontSize: 12,
                              color: textSecondary,
                              fontWeight: FontWeight.w600,
                            ),
                          ),
                        ],
                      ),
                    ),
                    if (isCommandPending || device.commandInProgress) ...[
                      const SizedBox(
                        width: 22,
                        height: 22,
                        child: CircularProgressIndicator(strokeWidth: 2.5),
                      ),
                      const SizedBox(width: 10),
                    ],
                    Switch(
                      value: switchValue,
                      onChanged: controlsDisabled ? null : onToggle,
                      activeThumbColor: color,
                      activeTrackColor: color.withValues(alpha: 0.28),
                    ),
                  ],
                ),
                const SizedBox(height: 14),
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
                      _metricChip(
                        icon: Icons.home_work_outlined,
                        label: '',
                        value: 'Local',
                        color: AppColors.energySafe,
                      ),
                  ],
                ),
                if (isCommandPending || device.commandInProgress) ...[
                  const SizedBox(height: 12),
                  ClipRRect(
                    borderRadius: BorderRadius.circular(999),
                    child: LinearProgressIndicator(
                      minHeight: 3,
                      color: color,
                      backgroundColor: color.withValues(alpha: 0.12),
                    ),
                  ),
                ],
                if (!device.online ||
                    !device.localOnline ||
                    !device.controllable) ...[
                  const SizedBox(height: 12),
                  Text(
                    (!device.online || !device.localOnline)
                        ? 'Offline'
                        : 'Control disabled',
                    style: TextStyle(
                      color: textSecondary,
                      fontSize: 12,
                      fontWeight: FontWeight.w700,
                    ),
                  ),
                ],
                if (visibleCommandError != null &&
                    visibleCommandError.isNotEmpty) ...[
                  const SizedBox(height: 12),
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
                            fontWeight: FontWeight.w700,
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
      ),
    );
  }
}
