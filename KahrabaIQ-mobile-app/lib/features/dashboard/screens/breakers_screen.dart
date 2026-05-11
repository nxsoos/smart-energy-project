import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../shared/models/device.dart';

class BreakersScreen extends StatelessWidget {
  const BreakersScreen({super.key, required this.devices});

  final List<Device> devices;

  @override
  Widget build(BuildContext context) {
    final breakers = devices
        .where((device) => device.id.startsWith('breaker_'))
        .toList();
    final totalPower = breakers.fold<double>(
      0,
      (sum, device) => sum + device.currentPower,
    );
    final totalEnergy = breakers.fold<double>(
      0,
      (sum, device) => sum + device.energyToday,
    );

    return Scaffold(
      appBar: AppBar(
        title: const Text('Breakers'),
        backgroundColor: ColorTokens.background,
        foregroundColor: ColorTokens.textPrimary,
        elevation: 0,
      ),
      body: ListView(
        padding: const EdgeInsets.fromLTRB(20, 12, 20, 28),
        children: [
          _SummaryBand(
            active: breakers.where((device) => device.isOn).length,
            total: breakers.length,
            power: totalPower,
            energy: totalEnergy,
          ),
          const SizedBox(height: 18),
          if (breakers.isEmpty)
            const _EmptyBreakers()
          else
            ...breakers.map(
              (device) => Padding(
                padding: const EdgeInsets.only(bottom: 12),
                child: _BreakerCard(device: device),
              ),
            ),
        ],
      ),
    );
  }
}

class _SummaryBand extends StatelessWidget {
  const _SummaryBand({
    required this.active,
    required this.total,
    required this.power,
    required this.energy,
  });

  final int active;
  final int total;
  final double power;
  final double energy;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: ColorTokens.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: ColorTokens.primary.withValues(alpha: 0.18)),
      ),
      child: Row(
        children: [
          _SummaryMetric(label: 'Active', value: '$active/$total'),
          _SummaryMetric(
            label: 'Power',
            value: '${power.toStringAsFixed(0)} W',
          ),
          _SummaryMetric(
            label: 'Today',
            value: '${energy.toStringAsFixed(2)} kWh',
          ),
        ],
      ),
    );
  }
}

class _SummaryMetric extends StatelessWidget {
  const _SummaryMetric({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Expanded(
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: AppTextStyles.caption),
          const SizedBox(height: 6),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(value, style: AppTextStyles.h3),
          ),
        ],
      ),
    );
  }
}

class _BreakerCard extends StatelessWidget {
  const _BreakerCard({required this.device});

  final Device device;

  @override
  Widget build(BuildContext context) {
    final online = device.online && (device.localOnline || device.cloudOnline);
    final stale = device.stale;
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: ColorTokens.surfaceElevated,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: device.isOn
              ? ColorTokens.primary.withValues(alpha: 0.32)
              : ColorTokens.textMuted.withValues(alpha: 0.18),
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                Icons.electrical_services,
                color: device.isOn
                    ? ColorTokens.primary
                    : ColorTokens.textMuted,
              ),
              const SizedBox(width: 10),
              Expanded(child: Text(device.name, style: AppTextStyles.h3)),
              _StatusPill(
                label: !online ? 'Offline' : stale ? 'Stale' : device.isOn ? 'On' : 'Off',
                color: !online
                    ? ColorTokens.danger
                    : stale
                    ? ColorTokens.warning
                    : device.isOn
                    ? ColorTokens.success
                    : ColorTokens.textMuted,
              ),
            ],
          ),
          if (!online || stale) ...[
            const SizedBox(height: 8),
            Text(
              _lastSeenText(device),
              style: AppTextStyles.caption.copyWith(color: ColorTokens.textMuted),
            ),
          ],
          const SizedBox(height: 16),
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: [
              _DataChip(
                label: 'Power',
                value: '${device.currentPower.toStringAsFixed(0)} W',
              ),
              _DataChip(
                label: 'Voltage',
                value: '${device.voltage.toStringAsFixed(1)} V',
              ),
              _DataChip(
                label: 'Current',
                value: '${device.current.toStringAsFixed(2)} A',
              ),
              _DataChip(
                label: 'Energy',
                value: '${device.energyToday.toStringAsFixed(2)} kWh',
              ),
              _DataChip(label: 'Branch', value: device.branch),
              _DataChip(
                label: 'Control',
                value: device.controlMethod ?? 'local',
              ),
            ],
          ),
        ],
      ),
    );
  }

  String _lastSeenText(Device device) {
    final lastSeen = device.lastSeen;
    if (lastSeen == null) {
      return 'Last seen unknown';
    }
    final age = DateTime.now().difference(lastSeen);
    if (age.inMinutes < 1) {
      return 'Last seen just now';
    }
    if (age.inHours < 1) {
      return 'Last seen ${age.inMinutes} min ago';
    }
    return 'Last seen ${age.inHours} hr ago';
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(label, style: AppTextStyles.caption.copyWith(color: color)),
    );
  }
}

class _DataChip extends StatelessWidget {
  const _DataChip({required this.label, required this.value});

  final String label;
  final String value;

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 132,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: ColorTokens.surface,
        borderRadius: BorderRadius.circular(14),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(label, style: AppTextStyles.caption),
          const SizedBox(height: 6),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text(value, style: AppTextStyles.mono),
          ),
        ],
      ),
    );
  }
}

class _EmptyBreakers extends StatelessWidget {
  const _EmptyBreakers();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(24),
      decoration: BoxDecoration(
        color: ColorTokens.surface,
        borderRadius: BorderRadius.circular(18),
      ),
      child: Column(
        children: [
          const Icon(
            Icons.electrical_services_outlined,
            color: ColorTokens.primary,
            size: 42,
          ),
          const SizedBox(height: 12),
          Text('No breaker data yet', style: AppTextStyles.h3),
          const SizedBox(height: 8),
          Text(
            'When the Pi publishes breaker readings, they will appear here.',
            style: AppTextStyles.caption,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}
