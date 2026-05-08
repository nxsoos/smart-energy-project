import 'package:flutter/material.dart';

import '../../../core/theme/color_tokens.dart';
import '../../../core/widgets/metric_card.dart';
import '../../../shared/models/energy_reading.dart';
import '../../../shared/models/sensor_data.dart';

/// Three-card row for key daily status metrics.
class QuickStatsRow extends StatelessWidget {
  const QuickStatsRow({
    super.key,
    required this.reading,
    required this.sensorData,
  });

  final EnergyReading reading;
  final SensorData sensorData;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: MetricCard(
            title: 'Today',
            value: reading.energyToday.toStringAsFixed(1),
            unit: 'kWh',
            icon: Icons.bolt,
            color: ColorTokens.primary,
            trendLabel: 'live',
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: MetricCard(
            title: 'Room',
            value: sensorData.temperature.toStringAsFixed(0),
            unit: '°C',
            icon: Icons.thermostat,
            color: ColorTokens.warning,
            trendLabel: 'stable',
          ),
        ),
        const SizedBox(width: 10),
        Expanded(
          child: MetricCard(
            title: 'Occupancy',
            value: sensorData.isOccupied ? 'ON' : 'OFF',
            unit: '',
            icon: Icons.motion_photos_on,
            color: sensorData.isOccupied
                ? ColorTokens.success
                : ColorTokens.textMuted,
            trendLabel: sensorData.isOccupied ? 'active' : 'clear',
          ),
        ),
      ],
    );
  }
}
