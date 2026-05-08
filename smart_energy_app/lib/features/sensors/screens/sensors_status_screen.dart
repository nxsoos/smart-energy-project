import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../core/widgets/app_state_widgets.dart';
import '../../../shared/models/sensor_data.dart';
import '../widgets/safety_status_bar.dart';
import '../widgets/sensor_card.dart';
import '../widgets/sensor_event_tile.dart';

/// Live sensor cockpit screen.
class SensorsStatusScreen extends StatelessWidget {
  const SensorsStatusScreen({
    super.key,
    required this.sensorData,
    this.isDemoMode = false,
  });

  final SensorData sensorData;
  final bool isDemoMode;

  @override
  Widget build(BuildContext context) {
    final sensors = _sensors();
    return Scaffold(
      body: SafeArea(
        child: sensors.isEmpty
            ? const AppEmptyState(
                icon: Icons.sensors_off,
                title: 'No sensor data',
                message:
                    'Sensor readings will appear once the Pi receives ESP32 telemetry.',
              )
            : ListView(
                padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
                children: [
                  _Header(isDemoMode: isDemoMode),
                  const SizedBox(height: 18),
                  SafetyStatusBar(isSafe: _isSafe),
                  const SizedBox(height: 18),
                  GridView.builder(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: sensors.length,
                    gridDelegate:
                        const SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 2,
                          mainAxisSpacing: 12,
                          crossAxisSpacing: 12,
                          childAspectRatio: 0.9,
                        ),
                    itemBuilder: (context, index) => sensors[index],
                  ),
                  const SizedBox(height: 24),
                  Text('Recent Events', style: AppTextStyles.h3),
                  const SizedBox(height: 14),
                  SensorEventTile(
                    title: 'Temperature and humidity heartbeat received',
                    time: 'now',
                    isHealthy: sensorData.ahtOk,
                  ),
                  SensorEventTile(
                    title:
                        'Smoke sensor reports ${sensorData.smokeStatus.toLowerCase()}',
                    time: '1m',
                    isHealthy: !sensorData.smokeStatus.toLowerCase().contains(
                      'alert',
                    ),
                  ),
                  SensorEventTile(
                    title: sensorData.isOccupied
                        ? 'Motion detected in living room'
                        : 'No motion detected',
                    time: '3m',
                    isHealthy: true,
                  ),
                ],
              ),
      ),
    );
  }

  bool get _isSafe => !sensorData.smokeStatus.toLowerCase().contains('alert');

  List<SensorCard> _sensors() => [
    SensorCard(
      icon: Icons.thermostat,
      label: 'Temperature',
      value: sensorData.temperature.toStringAsFixed(1),
      unit: '°C',
      isHealthy: sensorData.ahtOk,
      points: const [20, 21, 22, 23, 23.4],
    ),
    SensorCard(
      icon: Icons.water_drop_outlined,
      label: 'Humidity',
      value: sensorData.humidity.toStringAsFixed(0),
      unit: '%',
      isHealthy: sensorData.ahtOk,
      points: const [44, 45, 46, 46, 45],
    ),
    SensorCard(
      icon: Icons.motion_photos_on,
      label: 'Motion',
      value: sensorData.isOccupied ? 'Yes' : 'No',
      unit: '',
      isHealthy: true,
      points: const [0, 1, 1, 0, 1],
    ),
    SensorCard(
      icon: Icons.local_fire_department,
      label: 'Smoke',
      value: sensorData.smokeRaw.toString(),
      unit: 'raw',
      isHealthy: _isSafe,
      points: const [100, 110, 105, 120, 118],
    ),
    SensorCard(
      icon: Icons.bolt,
      label: 'Current',
      value: sensorData.soundRaw.toString(),
      unit: 'raw',
      isHealthy: true,
      points: const [18, 22, 19, 28, 24],
    ),
  ];
}

class _Header extends StatefulWidget {
  const _Header({required this.isDemoMode});

  final bool isDemoMode;

  @override
  State<_Header> createState() => _HeaderState();
}

class _HeaderState extends State<_Header> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1200),
    )..repeat(reverse: true);
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(child: Text('Sensor Status', style: AppTextStyles.h1)),
        AnimatedBuilder(
          animation: _controller,
          builder: (context, _) => Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(
              color: ColorTokens.success.withValues(
                alpha: 0.4 + _controller.value * 0.6,
              ),
              shape: BoxShape.circle,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Text(widget.isDemoMode ? 'Demo' : 'Live', style: AppTextStyles.caption),
      ],
    );
  }
}
