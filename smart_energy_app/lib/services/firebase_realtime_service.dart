import 'package:dio/dio.dart';
import 'package:firebase_database/firebase_database.dart';

import '../models/alert.dart';
import '../models/ai_insights.dart';
import '../models/device.dart';
import '../models/energy_reading.dart';
import '../models/sensor_data.dart';
import '../utils/constants.dart';

class DashboardData {
  final EnergyReading reading;
  final SensorData sensors;
  final List<Device> devices;
  final List<Alert> alerts;
  final double tariffBhdPerKwh;
  final AiDashboardSummary? aiDashboard;
  final AiDailySummary? aiDailySummary;
  final AiRecommendation? aiRecommendation;
  final AiAlertInsight? aiAlert;

  const DashboardData({
    required this.reading,
    required this.sensors,
    required this.devices,
    required this.alerts,
    required this.tariffBhdPerKwh,
    this.aiDashboard,
    this.aiDailySummary,
    this.aiRecommendation,
    this.aiAlert,
  });
}

class FirebaseRealtimeService {
  FirebaseRealtimeService()
    : _dio = Dio(
        BaseOptions(
          baseUrl: NetworkConfig.firebaseRealtimeDatabaseUrl,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        ),
      );

  final Dio _dio;

  Stream<Alert> watchAlerts({required int sinceTimestampMs}) {
    final database = FirebaseDatabase.instanceFor(
      app: FirebaseDatabase.instance.app,
      databaseURL: NetworkConfig.firebaseRealtimeDatabaseUrl,
    );

    final alertsRef = database.ref(
      'homes/${NetworkConfig.firebaseHomeId}/backend/alerts',
    );

    final alertsQuery = alertsRef
        .orderByChild('timestamp')
        .startAt(sinceTimestampMs);

    return alertsQuery.onChildAdded.map((event) {
      final raw = event.snapshot.value;
      final data = _asMap(raw);
      return _alertFromBackend(
        event.snapshot.key ?? DateTime.now().millisecondsSinceEpoch.toString(),
        data,
      );
    });
  }

  Future<DashboardData> fetchDashboardData({CancelToken? cancelToken}) async {
    final response = await _dio.get(
      '/homes/${NetworkConfig.firebaseHomeId}.json',
      cancelToken: cancelToken,
    );
    final home = _asMap(response.data);

    if (home.isEmpty) {
      throw Exception('No data found for ${NetworkConfig.firebaseHomeId}.');
    }

    final devices = _asMap(home['devices']);
    final history = _asMap(home['history']);
    final sensors = _asMap(home['sensors']);
    final backend = _asMap(home['backend']);
    final backendAi = _asMap(backend['ai']);
    final backendDashboard = _asMap(backend['dashboard']);
    final recommendations = _asMap(backend['recommendations']);
    final activeAlerts = _asMap(backend['active_alerts']);

    final parsedDevices = _parseDevices(devices);
    final meteringSummary = _collectMeteringSummary(devices);

    return DashboardData(
      reading: _parseReading(history, parsedDevices, meteringSummary),
      sensors: _parseSensors(sensors, devices),
      devices: parsedDevices,
      alerts: const [],
      tariffBhdPerKwh: _asDouble(
        _pick(home, ['tariff_BHD_per_kWh', 'tariffBhdPerKwh', 'tariff']),
        fallback: ElectricityPricing.costPerKWh,
      ),
      aiDashboard: _parseAiDashboard(_asMap(backendDashboard['ai'])),
      aiDailySummary: _parseAiDailySummary(_asMap(backendAi['daily_summary'])),
      aiRecommendation: _parseAiRecommendation(
        _asMap(recommendations['ai_energy_insight']),
      ),
      aiAlert: _parseAiAlert(_asMap(activeAlerts['ai_abnormal_usage'])),
    );
  }

  AiDashboardSummary? _parseAiDashboard(Map<String, dynamic> data) {
    if (data.isEmpty) {
      return null;
    }

    return AiDashboardSummary(
      updatedAt: _asDateTime(_pick(data, ['updated_at', 'updatedAt'])),
      source: _asString(_pick(data, ['source']), fallback: 'Smart Energy AI'),
      modelName: _asString(_pick(data, ['model_name', 'modelName'])),
      modelVersion: _asString(_pick(data, ['model_version', 'modelVersion'])),
      inputSource: _asString(_pick(data, ['input_source', 'inputSource'])),
      energyWaste: _asBool(_pick(data, ['energy_waste', 'energyWaste'])),
      wasteConfidence: _asDouble(
        _pick(data, ['waste_confidence', 'wasteConfidence']),
      ),
      abnormalUsage: _asBool(_pick(data, ['abnormal_usage', 'abnormalUsage'])),
      abnormalUsageConfidence: _asDouble(
        _pick(data, ['abnormal_usage_confidence', 'abnormalUsageConfidence']),
      ),
      recommendationType: _asString(
        _pick(data, ['recommendation_type', 'recommendationType']),
        fallback: 'general',
      ),
      nextHourEnergyKwh: _asDouble(
        _pick(data, ['next_hour_energy_kWh', 'next_hour_energy_kwh']),
      ),
      nextHourCostBhd: _asDouble(
        _pick(data, ['next_hour_cost_BHD', 'next_hour_cost_bhd']),
      ),
      efficiencyScore: _asDouble(
        _pick(data, ['efficiency_score', 'efficiencyScore']),
      ),
      explanation: _asString(
        _pick(data, ['explanation']),
        fallback: 'AI analysis is available.',
      ),
      controlSuggestion: _asString(
        _pick(data, ['control_suggestion', 'controlSuggestion']),
      ),
    );
  }

  AiDailySummary? _parseAiDailySummary(Map<String, dynamic> data) {
    if (data.isEmpty) {
      return null;
    }

    return AiDailySummary(
      dayId: _asString(_pick(data, ['day_id', 'dayId'])),
      updatedAt: _asDateTime(_pick(data, ['updated_at', 'updatedAt'])),
      source: _asString(_pick(data, ['source']), fallback: 'Smart Energy AI'),
      predictionCount: _asInt(
        _pick(data, ['prediction_count', 'predictionCount']),
      ),
      wastePredictionCount: _asInt(
        _pick(data, ['waste_prediction_count', 'wastePredictionCount']),
      ),
      abnormalPredictionCount: _asInt(
        _pick(data, ['abnormal_prediction_count', 'abnormalPredictionCount']),
      ),
      averageEfficiencyScore: _asDouble(
        _pick(data, ['average_efficiency_score', 'averageEfficiencyScore']),
      ),
      predictedNextHourEnergyTotalKwh: _asDouble(
        _pick(data, [
          'predicted_next_hour_energy_total_kWh',
          'predicted_next_hour_energy_total_kwh',
        ]),
      ),
      predictedNextHourCostTotalBhd: _asDouble(
        _pick(data, [
          'predicted_next_hour_cost_total_BHD',
          'predicted_next_hour_cost_total_bhd',
        ]),
      ),
      latestExplanation: _asString(
        _pick(data, ['latest_explanation', 'latestExplanation']),
      ),
      summary: _asString(
        _pick(data, ['summary']),
        fallback: 'AI daily summary is pending.',
      ),
    );
  }

  AiRecommendation? _parseAiRecommendation(Map<String, dynamic> data) {
    if (data.isEmpty) {
      return null;
    }

    return AiRecommendation(
      recommendationId: _asString(
        _pick(data, ['recommendation_id', 'recommendationId']),
        fallback: 'ai_energy_insight',
      ),
      type: _asString(_pick(data, ['type'])),
      priority: _asString(_pick(data, ['priority']), fallback: 'medium'),
      title: _asString(
        _pick(data, ['title']),
        fallback: 'Smart Energy AI insight',
      ),
      message: _asString(_pick(data, ['message'])),
      source: _asString(_pick(data, ['source']), fallback: 'Smart Energy AI'),
      relatedDeviceId: _asNullableString(
        _pick(data, ['related_device_id', 'relatedDeviceId']),
      ),
      relatedAlertKey: _asNullableString(
        _pick(data, ['related_alert_key', 'relatedAlertKey']),
      ),
      aiPredictionId: _asNullableString(
        _pick(data, ['ai_prediction_id', 'aiPredictionId']),
      ),
      recommendationType: _asString(
        _pick(data, ['recommendation_type', 'recommendationType']),
      ),
      status: _asString(_pick(data, ['status']), fallback: 'active'),
      createdAt: _asDateTime(_pick(data, ['created_at', 'createdAt'])),
      updatedAt: _asDateTime(_pick(data, ['updated_at', 'updatedAt'])),
      resolvedAt: _parseOptionalDateTime(
        _pick(data, ['resolved_at', 'resolvedAt']),
      ),
    );
  }

  AiAlertInsight? _parseAiAlert(Map<String, dynamic> data) {
    if (data.isEmpty) {
      return null;
    }

    return AiAlertInsight(
      id: _asString(
        _pick(data, ['id', 'alert_id']),
        fallback: 'ai_abnormal_usage',
      ),
      type: _asString(_pick(data, ['type']), fallback: 'ai_abnormal_usage'),
      priority: _asString(
        _pick(data, ['priority', 'severity']),
        fallback: 'medium',
      ),
      title: _asString(
        _pick(data, ['title']),
        fallback: 'AI-detected abnormal usage',
      ),
      message: _asString(
        _pick(data, ['message']),
        fallback: 'Smart Energy AI detected unusual energy behavior.',
      ),
      source: _asString(_pick(data, ['source']), fallback: 'Smart Energy AI'),
      createdAt: _asDateTime(
        _pick(data, ['created_at', 'createdAt', 'timestamp']),
      ),
      updatedAt: _asDateTime(
        _pick(data, ['updated_at', 'updatedAt', 'timestamp']),
      ),
      energyWaste: _asBool(_pick(data, ['energy_waste', 'energyWaste'])),
      abnormalUsage: _asBool(_pick(data, ['abnormal_usage', 'abnormalUsage'])),
    );
  }

  EnergyReading _parseReading(
    Map<String, dynamic> history,
    List<Device> devices,
    Map<String, dynamic> meteringSummary,
  ) {
    final latestHistory = _asMap(history['latest']);

    final totalPowerFromDevices = devices.fold<double>(
      0,
      (sum, device) => sum + device.currentPower,
    );

    final source = {...latestHistory, ...history, ...meteringSummary};

    return EnergyReading(
      timestamp: _asDateTime(
        _pick(source, ['timestamp', 'updatedAt', 'updated_at', 'time']),
      ),
      voltage: _asDouble(_pick(source, ['voltage', 'voltage_V', 'v'])),
      current: _asDouble(
        _pick(source, ['current', 'current_A', 'i', 'ampere']),
      ),
      power: _asDouble(
        _pick(source, ['power', 'power_W', 'wattage']),
        fallback: totalPowerFromDevices,
      ),
      energyToday: _asDouble(
        _pick(source, [
          'energyToday',
          'energy_today',
          'todayKwh',
          'today_kwh',
          'energy_kWh',
          'energy_kwh',
        ]),
      ),
      energyTotal: _asDouble(
        _pick(source, [
          'energyTotal',
          'energy_total',
          'totalKwh',
          'total_kwh',
          'energy_total_kWh',
          'energy_total_kwh',
        ]),
      ),
    );
  }

  SensorData _parseSensors(
    Map<String, dynamic> sensors,
    Map<String, dynamic> devices,
  ) {
    final source = sensors.isNotEmpty
        ? sensors
        : _firstNonEmptyMap([_extractSensorsFromDevices(devices)]);

    return SensorData(
      timestamp: _asDateTime(
        _pick(source, [
          'readable_time',
          'sensorTimestamp',
          'timestamp',
          'timestamp_ms',
          'updatedAt',
        ]),
      ),
      temperature: _asDouble(_pick(source, ['temperature', 'temp'])),
      humidity: _asDouble(_pick(source, ['humidity', 'humid'])),
      isOccupied: _asBool(
        _pick(source, [
          'isOccupied',
          'is_occupied',
          'occupied',
          'motion',
          'motion_text',
        ]),
      ),
      eco2: _asDouble(_pick(source, ['eco2', 'co2'])),
      tvoc: _asDouble(_pick(source, ['tvoc'])),
      aqi: _asInt(_pick(source, ['aqi'])),
      smokeRaw: _asInt(_pick(source, ['smoke_raw', 'smokeRaw', 'smoke'])),
      lightRaw: _asInt(_pick(source, ['light_raw', 'lightRaw'])),
      lightStatus:
          _pick(source, ['light_status', 'lightStatus'])?.toString() ??
          'Unknown',
      smokeStatus:
          _pick(source, ['smoke_text', 'smokeStatus'])?.toString() ?? 'Unknown',
      ahtOk: _asBool(_pick(source, ['aht_ok', 'ahtOk']), fallback: true),
      ens160Ok: _asBool(
        _pick(source, ['ens160_ok', 'ens160Ok']),
        fallback: true,
      ),
    );
  }

  List<Device> _parseDevices(Map<String, dynamic> devicesMap) {
    if (devicesMap.isEmpty) {
      return const [];
    }

    final devices = <Device>[];
    for (final entry in devicesMap.entries) {
      final data = _asMap(entry.value);
      if (data.isEmpty) {
        continue;
      }

      final metering = _asMap(data['metering']);
      final status = _asMap(data['status']);

      devices.add(
        Device(
          id: (_pick(data, ['id']) ?? entry.key).toString(),
          name:
              _pick(data, ['name', 'label', 'deviceName'])?.toString() ??
              entry.key,
          type: _parseDeviceType(
            _pick(data, ['type', 'deviceType'])?.toString(),
          ),
          isOn: _asBool(
            _pick(data, ['isOn', 'status', 'on']) ??
                _pick(status, ['on', 'switch']),
          ),
          currentPower: _asDouble(
            _pick(data, ['currentPower', 'power', 'wattage']) ??
                _pick(metering, ['power_W', 'power_w', 'power']),
          ),
          branch:
              _pick(data, ['branch', 'zone'])?.toString() ??
              _branchFromDeviceId(entry.key),
        ),
      );
    }

    return devices;
  }

  Map<String, dynamic> _collectMeteringSummary(
    Map<String, dynamic> devicesMap,
  ) {
    var totalPower = 0.0;
    var totalEnergyToday = 0.0;
    var voltageSum = 0.0;
    var currentSum = 0.0;
    var voltageCount = 0;
    var currentCount = 0;

    for (final entry in devicesMap.entries) {
      final data = _asMap(entry.value);
      final metering = _asMap(data['metering']);
      if (metering.isEmpty) {
        continue;
      }

      totalPower += _asDouble(_pick(metering, ['power_W', 'power_w', 'power']));
      totalEnergyToday += _asDouble(
        _pick(metering, ['energy_kWh', 'energy_kwh', 'energy_today']),
      );

      final voltage = _asDouble(_pick(metering, ['voltage_V', 'voltage']));
      if (voltage > 0) {
        voltageSum += voltage;
        voltageCount++;
      }

      final current = _asDouble(
        _pick(metering, ['current_A', 'current', 'ampere']),
      );
      if (current > 0) {
        currentSum += current;
        currentCount++;
      }
    }

    return {
      'power_W': totalPower,
      'energy_kWh': totalEnergyToday,
      'voltage_V': voltageCount > 0 ? (voltageSum / voltageCount) : 0,
      'current_A': currentCount > 0 ? (currentSum / currentCount) : 0,
    };
  }

  Map<String, dynamic> _extractSensorsFromDevices(
    Map<String, dynamic> devicesMap,
  ) {
    for (final entry in devicesMap.entries) {
      final data = _asMap(entry.value);
      final directSensors = _asMap(data['sensors']);
      if (directSensors.isNotEmpty) {
        return directSensors;
      }

      final raw = _asMap(data['raw']);
      final rawSensors = _asMap(raw['sensors']);
      if (rawSensors.isNotEmpty) {
        return rawSensors;
      }
    }

    return const {};
  }

  Map<String, dynamic> _firstNonEmptyMap(
    List<Map<String, dynamic>> candidates,
  ) {
    for (final candidate in candidates) {
      if (candidate.isNotEmpty) {
        return candidate;
      }
    }
    return const {};
  }

  String _branchFromDeviceId(String deviceId) {
    final normalized = deviceId.toLowerCase();
    if (normalized.contains('01') || normalized.contains('1')) {
      return 'Branch 1';
    }
    if (normalized.contains('02') || normalized.contains('2')) {
      return 'Branch 2';
    }
    if (normalized.contains('03') || normalized.contains('3')) {
      return 'Branch 3';
    }
    return 'Main';
  }

  dynamic _pick(Map<String, dynamic> source, List<String> keys) {
    for (final key in keys) {
      if (source.containsKey(key) && source[key] != null) {
        return source[key];
      }
    }
    return null;
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map) {
      return value.map((key, val) => MapEntry(key.toString(), val));
    }
    return const {};
  }

  double _asDouble(dynamic value, {double fallback = 0.0}) {
    if (value is num) {
      return value.toDouble();
    }
    if (value is String) {
      return double.tryParse(value) ?? fallback;
    }
    return fallback;
  }

  int _asInt(dynamic value, {int fallback = 0}) {
    if (value is int) {
      return value;
    }
    if (value is num) {
      return value.toInt();
    }
    if (value is String) {
      return int.tryParse(value) ?? fallback;
    }
    return fallback;
  }

  bool _asBool(dynamic value, {bool fallback = false}) {
    if (value is bool) {
      return value;
    }
    if (value is num) {
      return value != 0;
    }
    if (value is String) {
      final normalized = value.toLowerCase();
      return normalized == 'true' || normalized == '1' || normalized == 'on';
    }
    return fallback;
  }

  String _asString(dynamic value, {String fallback = ''}) {
    if (value == null) {
      return fallback;
    }
    final text = value.toString().trim();
    return text.isEmpty ? fallback : text;
  }

  String? _asNullableString(dynamic value) {
    if (value == null) {
      return null;
    }
    final text = value.toString().trim();
    return text.isEmpty ? null : text;
  }

  DateTime? _parseOptionalDateTime(dynamic value) {
    if (value == null) {
      return null;
    }
    return _asDateTime(value);
  }

  DateTime _asDateTime(dynamic value) {
    if (value is int) {
      final dateTime = value > 1000000000000
          ? DateTime.fromMillisecondsSinceEpoch(value)
          : DateTime.fromMillisecondsSinceEpoch(value * 1000);
      return dateTime;
    }

    if (value is num) {
      final integerValue = value.toInt();
      final dateTime = integerValue > 1000000000000
          ? DateTime.fromMillisecondsSinceEpoch(integerValue)
          : DateTime.fromMillisecondsSinceEpoch(integerValue * 1000);
      return dateTime;
    }

    if (value is String) {
      final maybeInt = int.tryParse(value);
      if (maybeInt != null) {
        final dateTime = maybeInt > 1000000000000
            ? DateTime.fromMillisecondsSinceEpoch(maybeInt)
            : DateTime.fromMillisecondsSinceEpoch(maybeInt * 1000);
        return dateTime;
      }

      return DateTime.tryParse(value) ?? DateTime.now();
    }
    return DateTime.now();
  }

  DeviceType _parseDeviceType(String? type) {
    switch (type?.toLowerCase()) {
      case 'light':
      case 'led':
      case 'ledstrip':
      case 'led_strip':
        return DeviceType.light;
      case 'airconditioner':
      case 'air_conditioner':
      case 'ac':
        return DeviceType.airConditioner;
      case 'socket':
      default:
        return DeviceType.socket;
    }
  }

  Alert _alertFromBackend(String id, Map<String, dynamic> data) {
    final payload = <String, dynamic>{
      ...data,
      'id': id,
      'severity': _pick(data, ['severity', 'level']) ?? 'medium',
      'timestamp': _pick(data, ['timestamp', 'createdAt', 'created_at']),
      'isActive': _pick(data, ['isActive', 'active']) ?? true,
      'type': _pick(data, ['type']) ?? 'sensorfailure',
    };

    return Alert.fromJson(payload);
  }
}
