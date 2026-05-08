import 'package:flutter/material.dart';

import '../../shared/models/device.dart';
import '../theme/app_text_styles.dart';
import '../theme/color_tokens.dart';
import '../utils/constants.dart';
import '../utils/helpers.dart';

/// Fixed-size smart device card with animated on/off styling.
class DeviceCard extends StatelessWidget {
  const DeviceCard({
    super.key,
    required this.device,
    this.onTap,
    this.onLongPress,
    this.onToggle,
    this.isCommandPending = false,
    this.commandError,
  });

  final Device device;
  final VoidCallback? onTap;
  final VoidCallback? onLongPress;
  final ValueChanged<bool>? onToggle;
  final bool isCommandPending;
  final String? commandError;

  bool get _isActive =>
      device.isOn &&
      device.online &&
      (device.localOnline || (NetworkConfig.useAwsIotLive && device.cloudOnline));

  @override
  Widget build(BuildContext context) {
    final color = _deviceColor();
    return AnimatedOpacity(
      duration: const Duration(milliseconds: 200),
      opacity: _isActive ? 1 : 0.5,
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: 160,
        height: 200,
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            begin: Alignment.topLeft,
            end: Alignment.bottomRight,
            colors: [ColorTokens.surfaceElevated, ColorTokens.surface],
          ),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(
            color: _isActive ? ColorTokens.primary : ColorTokens.border,
            width: _isActive ? 2 : 1,
          ),
          boxShadow: _isActive
              ? const [
                  BoxShadow(color: ColorTokens.primaryGlow, blurRadius: 20),
                ]
              : const [BoxShadow(color: ColorTokens.shadow, blurRadius: 12)],
        ),
        child: Material(
          color: Colors.transparent,
          child: InkWell(
            onTap: onTap,
            onLongPress: onLongPress,
            borderRadius: BorderRadius.circular(16),
            splashColor: ColorTokens.primaryGlow,
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Row(
                  children: [
                    Icon(
                      _deviceIcon(),
                      color: _isActive ? color : ColorTokens.textMuted,
                      size: 30,
                    ),
                    const Spacer(),
                    _DeviceSwitch(
                      value: _isActive,
                      onChanged: _canToggle ? onToggle : null,
                    ),
                  ],
                ),
                const Spacer(),
                Text(device.name, style: AppTextStyles.bodyMedium, maxLines: 2),
                const SizedBox(height: 6),
                Text(device.branch, style: AppTextStyles.caption, maxLines: 1),
                const SizedBox(height: 14),
                Text(
                  formatPower(device.currentPower),
                  style: AppTextStyles.mono.copyWith(color: color),
                ),
                if (isCommandPending || device.commandInProgress) ...[
                  const SizedBox(height: 8),
                  const LinearProgressIndicator(
                    minHeight: 2,
                    color: ColorTokens.primary,
                  ),
                ],
                if (commandError != null && commandError!.isNotEmpty) ...[
                  const SizedBox(height: 8),
                  Text(
                    commandError!,
                    style: AppTextStyles.caption.copyWith(
                      color: ColorTokens.danger,
                    ),
                    maxLines: 2,
                    overflow: TextOverflow.ellipsis,
                  ),
                ],
              ],
            ),
          ),
        ),
      ),
    );
  }

  bool get _canToggle {
    final hasCommandPath = NetworkConfig.useAwsIotLive
        ? true
        : device.localOnline || device.cloudOnline;
    return !isCommandPending && device.controllable && hasCommandPath;
  }

  Color _deviceColor() {
    switch (device.type) {
      case DeviceType.light:
        return ColorTokens.warning;
      case DeviceType.socket:
        return ColorTokens.primary;
      case DeviceType.airConditioner:
        return ColorTokens.info;
    }
  }

  IconData _deviceIcon() {
    switch (device.type) {
      case DeviceType.light:
        return Icons.lightbulb_outline;
      case DeviceType.socket:
        return Icons.power;
      case DeviceType.airConditioner:
        return Icons.ac_unit;
    }
  }
}

class _DeviceSwitch extends StatelessWidget {
  const _DeviceSwitch({required this.value, required this.onChanged});

  final bool value;
  final ValueChanged<bool>? onChanged;

  @override
  Widget build(BuildContext context) {
    return GestureDetector(
      onTap: onChanged == null ? null : () => onChanged!(!value),
      child: AnimatedContainer(
        duration: const Duration(milliseconds: 200),
        width: 42,
        height: 24,
        padding: const EdgeInsets.all(3),
        decoration: BoxDecoration(
          color: value ? ColorTokens.primary : ColorTokens.textMuted,
          borderRadius: BorderRadius.circular(999),
        ),
        child: AnimatedAlign(
          duration: const Duration(milliseconds: 200),
          alignment: value ? Alignment.centerRight : Alignment.centerLeft,
          child: Container(
            width: 18,
            height: 18,
            decoration: const BoxDecoration(
              color: ColorTokens.textPrimary,
              shape: BoxShape.circle,
            ),
          ),
        ),
      ),
    );
  }
}
