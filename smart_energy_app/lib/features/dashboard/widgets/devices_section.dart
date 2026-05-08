import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../core/widgets/app_state_widgets.dart';
import '../../../core/widgets/device_card.dart';
import '../../../shared/models/device.dart';

/// Horizontal smart-device carousel.
class DevicesSection extends StatelessWidget {
  const DevicesSection({
    super.key,
    required this.devices,
    required this.onToggle,
    this.pendingDeviceCommands = const {},
    this.deviceCommandErrors = const {},
  });

  final List<Device> devices;
  final void Function(Device device, bool value) onToggle;
  final Set<String> pendingDeviceCommands;
  final Map<String, String> deviceCommandErrors;

  @override
  Widget build(BuildContext context) {
    if (devices.isEmpty) {
      return const AppEmptyState(
        icon: Icons.power_settings_new,
        title: 'No devices paired',
        message:
            'Pair your Pi hub to start controlling breakers and Matter devices.',
      );
    }
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          children: [
            Text('Devices', style: AppTextStyles.h3),
            const Spacer(),
            Text(
              '${devices.where((item) => item.isOn).length} active',
              style: AppTextStyles.caption.copyWith(color: ColorTokens.primary),
            ),
          ],
        ),
        const SizedBox(height: 12),
        SizedBox(
          height: 200,
          child: ListView.separated(
            scrollDirection: Axis.horizontal,
            itemCount: devices.length,
            separatorBuilder: (context, index) => const SizedBox(width: 12),
            itemBuilder: (context, index) {
              final device = devices[index];
              return DeviceCard(
                device: device,
                onToggle: (value) => onToggle(device, value),
                onLongPress: () => _showDetails(context, device),
                isCommandPending:
                    pendingDeviceCommands.contains(device.id) ||
                    device.commandInProgress,
                commandError: deviceCommandErrors[device.id],
              );
            },
          ),
        ),
      ],
    );
  }

  void _showDetails(BuildContext context, Device device) {
    showModalBottomSheet<void>(
      context: context,
      backgroundColor: ColorTokens.surface,
      builder: (context) => Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(device.name, style: AppTextStyles.h2),
            const SizedBox(height: 8),
            Text(
              '${device.branch} · ${device.controlMethod ?? 'local control'}',
              style: AppTextStyles.caption,
            ),
          ],
        ),
      ),
    );
  }
}
