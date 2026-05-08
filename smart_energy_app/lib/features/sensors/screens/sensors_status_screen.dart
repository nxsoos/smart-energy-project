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
    final offline = _isOffline;
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
                  _Header(
                    isDemoMode: isDemoMode,
                    isOffline: offline,
                    lastUpdated: sensorData.timestamp,
                  ),
                  const SizedBox(height: 18),
                  SafetyStatusBar(isSafe: _isSafe, isOffline: offline),
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
                  if (offline)
                    const SensorEventTile(
                      title: 'ESP32 sensor feed has not updated recently',
                      time: 'offline',
                      isHealthy: false,
                    )
                  else ...[
                    SensorEventTile(
                      title: 'Temperature and humidity updated',
                      time: 'now',
                      isHealthy: sensorData.ahtOk,
                    ),
                    SensorEventTile(
                      title:
                          'Smoke sensor reports ${sensorData.smokeStatus.toLowerCase()}',
                      time: 'now',
                      isHealthy: _isSafe,
                    ),
                    SensorEventTile(
                      title: sensorData.isOccupied
                          ? 'Motion detected'
                          : 'No motion detected',
                      time: 'now',
                      isHealthy: true,
                    ),
                  ],
                ],
              ),
      ),
    );
  }

  bool get _isSafe => !sensorData.smokeStatus.toLowerCase().contains('alert');

  bool get _isOffline {
    if (!sensorData.online) {
      return true;
    }
    if (sensorData.timestamp.year < 2024) {
      return true;
    }
    return DateTime.now().difference(sensorData.timestamp).inSeconds > 45;
  }

  List<SensorCard> _sensors() => [
    SensorCard(
      icon: Icons.thermostat,
      label: 'Temperature',
      value: _isOffline ? '--' : sensorData.temperature.toStringAsFixed(1),
      unit: 'C',
      isHealthy: sensorData.ahtOk && !_isOffline,
      points: _spark(sensorData.temperature),
      statusLabel: _isOffline ? 'Offline' : null,
    ),
    SensorCard(
      icon: Icons.water_drop_outlined,
      label: 'Humidity',
      value: _isOffline ? '--' : sensorData.humidity.toStringAsFixed(0),
      unit: '%',
      isHealthy: sensorData.ahtOk && !_isOffline,
      points: _spark(sensorData.humidity),
      statusLabel: _isOffline ? 'Offline' : null,
    ),
    SensorCard(
      icon: Icons.motion_photos_on,
      label: 'Motion',
      value: _isOffline
          ? 'Offline'
          : sensorData.isOccupied
          ? 'Occupied'
          : 'Clear',
      unit: '',
      isHealthy: !_isOffline,
      points: sensorData.isOccupied
          ? const [0, 1, 1, 1, 1]
          : const [0, 0, 0, 0, 0],
      statusLabel: _isOffline ? 'Offline' : 'Normal',
      showChart: false,
    ),
    SensorCard(
      icon: Icons.local_fire_department,
      label: 'Smoke/Gas',
      value: _isOffline ? 'Offline' : sensorData.smokeStatus,
      unit: '',
      isHealthy: _isSafe && !_isOffline,
      points: _spark(sensorData.smokeRaw.toDouble()),
      statusLabel: _isOffline ? 'Offline' : (_isSafe ? 'Clear' : 'Alert'),
      showChart: false,
    ),
    SensorCard(
      icon: Icons.graphic_eq,
      label: 'Noise',
      value: _isOffline ? 'Offline' : _noiseLabel,
      unit: '',
      isHealthy: !_isOffline,
      points: _spark(sensorData.soundRaw.toDouble()),
      statusLabel: _isOffline ? 'Offline' : _noiseLabel,
      showChart: false,
    ),
    SensorCard(
      icon: Icons.air,
      label: 'Air Quality',
      value: _isOffline ? 'Offline' : _airQualityLabel,
      unit: '',
      isHealthy: sensorData.ens160Ok && !_isOffline,
      points: _spark(sensorData.aqi.toDouble()),
      statusLabel: _isOffline ? 'Offline' : _airQualityLabel,
      showChart: false,
    ),
    SensorCard(
      icon: Icons.light_mode_outlined,
      label: 'Room Light',
      value: _isOffline ? 'Offline' : _lightLabel,
      unit: '',
      isHealthy: !_isOffline,
      points: _spark(sensorData.lightRaw.toDouble()),
      statusLabel: _isOffline ? 'Offline' : _lightLabel,
      showChart: false,
    ),
  ];

  String get _noiseLabel {
    final label = sensorData.noiseStatus.trim();
    if (label.isNotEmpty && label.toLowerCase() != 'unknown') {
      return label;
    }
    return sensorData.soundRaw > 700 ? 'Loud' : 'Quiet';
  }

  String get _lightLabel {
    final label = sensorData.lightStatus.trim();
    if (label.isNotEmpty && label.toLowerCase() != 'unknown') {
      return label;
    }
    return sensorData.lightRaw > 500 ? 'Bright' : 'Dark';
  }

  String get _airQualityLabel {
    if (!sensorData.ens160Ok) {
      return 'Sensor issue';
    }
    if (sensorData.aqi <= 1) {
      return 'Good';
    }
    if (sensorData.aqi == 2) {
      return 'Moderate';
    }
    return 'Poor';
  }

  List<double> _spark(double value) {
    if (value <= 0) {
      return const [0, 0, 0, 0, 0];
    }
    return [value * 0.92, value * 0.96, value, value * 0.98, value];
  }
}

class _Header extends StatefulWidget {
  const _Header({
    required this.isDemoMode,
    required this.isOffline,
    required this.lastUpdated,
  });

  final bool isDemoMode;
  final bool isOffline;
  final DateTime lastUpdated;

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
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Sensor Status', style: AppTextStyles.h1),
              const SizedBox(height: 6),
              Text(
                'Last updated ${_formatLastUpdated(widget.lastUpdated)}',
                style: AppTextStyles.caption,
              ),
            ],
          ),
        ),
        AnimatedBuilder(
          animation: _controller,
          builder: (context, _) => Container(
            width: 12,
            height: 12,
            decoration: BoxDecoration(
              color: (widget.isOffline
                      ? ColorTokens.textMuted
                      : ColorTokens.success)
                  .withValues(alpha: 0.4 + _controller.value * 0.6),
              shape: BoxShape.circle,
            ),
          ),
        ),
        const SizedBox(width: 8),
        Text(
          widget.isOffline
              ? 'Offline'
              : widget.isDemoMode
              ? 'Demo'
              : 'Live',
          style: AppTextStyles.caption,
        ),
      ],
    );
  }

  String _formatLastUpdated(DateTime value) {
    if (value.year < 2024) {
      return '--';
    }
    final local = value.toLocal();
    final hour = local.hour.toString().padLeft(2, '0');
    final minute = local.minute.toString().padLeft(2, '0');
    final second = local.second.toString().padLeft(2, '0');
    return '$hour:$minute:$second';
  }
}
