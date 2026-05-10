import 'package:flutter/material.dart';

import '../../../core/theme/color_tokens.dart';
import '../../../core/widgets/metric_card.dart';
import '../../../shared/models/device.dart';
import '../../../shared/models/energy_reading.dart';

/// Three-card row for live breaker and energy KPIs.
class QuickStatsRow extends StatelessWidget {
  const QuickStatsRow({
    super.key,
    required this.reading,
    required this.devices,
    this.onBreakersTap,
  });

  final EnergyReading reading;
  final List<Device> devices;
  final VoidCallback? onBreakersTap;

  @override
  Widget build(BuildContext context) {
    final breakerDevices = devices
        .where((device) => device.id.startsWith('breaker_'))
        .toList();
    final activeBreakers = breakerDevices.where((device) => device.isOn).length;
    final totalBreakers = breakerDevices.length;
    final activePower = devices.fold<double>(
      0,
      (sum, device) => sum + device.currentPower,
    );
    final breakerEnergy = breakerDevices.fold<double>(
      0,
      (sum, device) => sum + device.energyToday,
    );
    final energyMonth = reading.energyMonth > 0
        ? reading.energyMonth
        : breakerEnergy > 0
        ? breakerEnergy
        : reading.energyToday;

    return Row(
      children: [
        Expanded(
          child: InkWell(
            onTap: onBreakersTap,
            borderRadius: BorderRadius.circular(16),
            child: MetricCard(
              title: 'Breakers',
              value: '$activeBreakers/$totalBreakers',
              unit: 'on',
              icon: Icons.electrical_services,
              color: ColorTokens.primary,
              trendLabel: totalBreakers > 0 ? 'details' : 'waiting',
              isTrendPositive: totalBreakers > 0,
            ),
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: MetricCard(
            title: 'Power',
            value: (reading.power > 0 ? reading.power : activePower)
                .toStringAsFixed(0),
            unit: 'W',
            icon: Icons.bolt,
            color: ColorTokens.warning,
            trendLabel: 'live',
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: MetricCard(
            title: 'Energy',
            value: reading.monthDataAvailable
                ? energyMonth.toStringAsFixed(1)
                : '--',
            unit: reading.monthDataAvailable ? 'kWh' : '',
            icon: Icons.speed,
            color: ColorTokens.success,
            trendLabel: reading.monthDataAvailable ? 'month' : 'no data',
          ),
        ),
      ],
    );
  }
}
