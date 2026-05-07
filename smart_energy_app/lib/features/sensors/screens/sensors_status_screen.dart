import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../shared/models/sensor_data.dart';
import '../../../core/utils/constants.dart';

class SensorsStatusScreen extends StatelessWidget {
  const SensorsStatusScreen({
    super.key,
    required this.sensorData,
    this.isDemoMode = false,
  });

  final SensorData sensorData;
  final bool isDemoMode;

  static const int _sensorFeedStaleThresholdMs = 2 * 60 * 1000;

  @override
  Widget build(BuildContext context) {
    final feedAge = DateTime.now().difference(sensorData.timestamp);
    final isFeedFresh =
        isDemoMode || feedAge.inMilliseconds <= _sensorFeedStaleThresholdMs;
    final isAhtWorking = isFeedFresh && sensorData.ahtOk;
    final isEns160Working = isFeedFresh && sensorData.ens160Ok;
    final isSmokeWorking = isFeedFresh && _isSmokeSensorWorking(sensorData);
    final isLightWorking = isFeedFresh && _isLightSensorWorking(sensorData);
    final isNoiseWorking = isFeedFresh && _isNoiseSensorWorking(sensorData);
    final isPirWorking = isFeedFresh;

    return Scaffold(
      appBar: AppBar(
        title: const Text(
          'Sensors Status',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.w700),
        ),
        backgroundColor: AppColors.primary,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      backgroundColor: AppColors.background,
      body: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            _buildStatusCard(
              title: 'Sensor Feed',
              subtitle: isDemoMode
                  ? 'Demo scenario uses a simulated sensor record.'
                  : isFeedFresh
                  ? 'Live updates are recent.'
                  : 'No recent sensor update detected.',
              trailingText: isFeedFresh ? 'Working' : 'Not working',
              isHealthy: isFeedFresh,
            ),
            const SizedBox(height: 12),
            _buildStatusCard(
              title: 'AHT20 (Temperature / Humidity)',
              subtitle: _sensorSubtitle(isAhtWorking, isFeedFresh),
              trailingText: isAhtWorking ? 'Working' : 'Not working',
              isHealthy: isAhtWorking,
            ),
            const SizedBox(height: 12),
            _buildStatusCard(
              title: 'ENS160 (Air Quality)',
              subtitle: _sensorSubtitle(isEns160Working, isFeedFresh),
              trailingText: isEns160Working ? 'Working' : 'Not working',
              isHealthy: isEns160Working,
            ),
            const SizedBox(height: 12),
            _buildStatusCard(
              title: 'Smoke Sensor',
              subtitle: isSmokeWorking
                  ? 'MQ2 raw: ${sensorData.smokeRaw} (${sensorData.smokeStatus}).'
                  : _sensorSubtitle(isSmokeWorking, isFeedFresh),
              trailingText: isSmokeWorking ? 'Working' : 'Not working',
              isHealthy: isSmokeWorking,
            ),
            const SizedBox(height: 12),
            _buildStatusCard(
              title: 'Light Sensor',
              subtitle: _sensorSubtitle(isLightWorking, isFeedFresh),
              trailingText: isLightWorking ? 'Working' : 'Not working',
              isHealthy: isLightWorking,
            ),
            const SizedBox(height: 12),
            _buildStatusCard(
              title: 'Noise Sensor',
              subtitle: isNoiseWorking
                  ? 'Sound level: ${sensorData.soundRaw} raw units (${_noiseLabel(sensorData)}).'
                  : _sensorSubtitle(isNoiseWorking, isFeedFresh),
              trailingText: isNoiseWorking ? 'Working' : 'Not working',
              isHealthy: isNoiseWorking,
            ),
            const SizedBox(height: 12),
            _buildStatusCard(
              title: 'PIR Motion Sensor',
              subtitle: isPirWorking
                  ? 'Motion state: ${sensorData.isOccupied ? 'motion detected' : 'no motion'}.'
                  : _sensorSubtitle(isPirWorking, isFeedFresh),
              trailingText: isPirWorking ? 'Working' : 'Not working',
              isHealthy: isPirWorking,
            ),
            const SizedBox(height: 24),
            Text(
              'Last sensor timestamp: ${DateFormat('MMM d, HH:mm:ss').format(sensorData.timestamp)}',
              style: TextStyle(color: Colors.grey[700], fontSize: 13),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildStatusCard({
    required String title,
    required String subtitle,
    required String trailingText,
    required bool isHealthy,
  }) {
    final color = isHealthy ? AppColors.energySafe : AppColors.energyDanger;

    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Icon(
            isHealthy ? Icons.check_circle_outline : Icons.error_outline,
            color: color,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(fontWeight: FontWeight.w700),
                ),
                const SizedBox(height: 4),
                Text(
                  subtitle,
                  style: TextStyle(fontSize: 12, color: Colors.grey[700]),
                ),
              ],
            ),
          ),
          const SizedBox(width: 10),
          Text(
            trailingText,
            style: TextStyle(fontWeight: FontWeight.w700, color: color),
          ),
        ],
      ),
    );
  }

  String _sensorSubtitle(bool working, bool isFeedFresh) {
    if (isDemoMode) {
      return working
          ? 'Simulated value is present for this demo scenario.'
          : 'No simulated value is available for this demo scenario.';
    }

    if (!isFeedFresh) {
      return 'Sensor feed is offline, so this sensor is not trusted.';
    }

    return working
        ? 'Sensor heartbeat and values look valid.'
        : 'No valid signal detected from this sensor.';
  }

  bool _isSmokeSensorWorking(SensorData data) {
    final status = data.smokeStatus.toLowerCase();
    return status != 'unknown' || data.smokeRaw > 0;
  }

  bool _isLightSensorWorking(SensorData data) {
    return data.lightStatus.toLowerCase() != 'unknown';
  }

  bool _isNoiseSensorWorking(SensorData data) {
    return data.soundRaw > 0 ||
        data.noiseStatus.toLowerCase() != 'unknown' ||
        data.noise == 0 ||
        data.noise == 1;
  }

  String _noiseLabel(SensorData data) {
    final status = data.noiseStatus.trim();
    if (status.isNotEmpty && status.toLowerCase() != 'unknown') {
      return status;
    }
    return data.noise == 1 ? 'Noise' : 'Quiet';
  }
}
