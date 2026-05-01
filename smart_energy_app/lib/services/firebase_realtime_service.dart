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
  final Set<String> pendingDeviceCommands;
  final Map<String, String> deviceCommandErrors;
  final AiDashboardSummary? aiDashboard;
  final AiDailySummary? aiDailySummary;
  final AiRecommendation? aiRecommendation;
  final AiAlertInsight? aiAlert;
  final String? scenarioId;
  final String? scenarioName;
  final String? scenarioDescription;
  final bool deviceControlEnabled;

  const DashboardData({
    required this.reading,
    required this.sensors,
    required this.devices,
    required this.alerts,
    required this.tariffBhdPerKwh,
    this.pendingDeviceCommands = const {},
    this.deviceCommandErrors = const {},
    this.aiDashboard,
    this.aiDailySummary,
    this.aiRecommendation,
    this.aiAlert,
    this.scenarioId,
    this.scenarioName,
    this.scenarioDescription,
    this.deviceControlEnabled = true,
  });
}

class DemoScenario {
  const DemoScenario({
    required this.id,
    required this.name,
    required this.description,
  });

  final String id;
  final String name;
  final String description;
}

class DeviceCommandState {
  const DeviceCommandState({
    required this.status,
    this.action = '',
    this.error,
  });

  final String status;
  final String action;
  final String? error;

  bool get isPending => status == 'pending';
  bool get isDone => status == 'done';
  bool get isFailed => status == 'failed';

  bool? get desiredSwitchState {
    if (!isPending) {
      return null;
    }
    if (action == 'turn_on') {
      return true;
    }
    if (action == 'turn_off') {
      return false;
    }
    return null;
  }
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
  int _lastCommandTimestampMs = 0;

  DatabaseReference _firebaseRef(String path) {
    final database = FirebaseDatabase.instanceFor(
      app: FirebaseDatabase.instance.app,
      databaseURL: NetworkConfig.firebaseRealtimeDatabaseUrl,
    );

    return database.ref(path);
  }

  Stream<Alert> watchAlerts({
    required String homeId,
    required int sinceTimestampMs,
  }) {
    final alertsRef = _firebaseRef('homes/$homeId/backend/alerts');

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

  Future<DashboardData> fetchDashboardData({
    required String homeId,
    String? scenarioId,
    CancelToken? cancelToken,
  }) async {
    final response = await _dio.get(
      '/homes/$homeId.json',
      cancelToken: cancelToken,
    );
    final home = _asMap(response.data);

    if (home.isEmpty) {
      throw Exception('No data found for $homeId.');
    }

    final selectedScenario = scenarioId == null
        ? const <String, dynamic>{}
        : _asMap(_asMap(home['demo_scenarios'])[scenarioId]);
    final sourceHome = selectedScenario.isEmpty ? home : selectedScenario;
    final sourceBackend = _asMap(sourceHome['backend']);
    final rootBackend = _asMap(home['backend']);
    final rootAiMetadata = _asMap(_asMap(rootBackend['ai'])['test_metadata']);
    final metadata = {
      ...rootAiMetadata,
      ..._asMap(_asMap(sourceBackend['ai'])['test_metadata']),
      ..._asMap(sourceHome['scenario']),
    };

    final devices = _asMap(sourceHome['devices']);
    final history = _asMap(sourceHome['history']);
    final sensors = _asMap(sourceHome['sensors']);
    final commands = _asMap(sourceHome['commands']);
    final backend = _asMap(sourceHome['backend']);
    final backendAi = _asMap(backend['ai']);
    final backendDashboard = _asMap(backend['dashboard']);
    final dashboardEnergy = {
      ...sourceHome,
      ..._asMap(backendDashboard['energy']),
    };
    final dashboardEnvironment = {
      ...sourceHome,
      ..._asMap(backendDashboard['environment']),
    };
    final backendEnergy = _asMap(backend['energy']);
    final backendCurrentTotal = _asMap(backendEnergy['current_total']);
    final recommendations = _asMap(backend['recommendations']);
    final activeAlerts = _asMap(backend['active_alerts']);

    final commandStates = _parseDeviceCommandStates(commands);
    final parsedDevices = _parseDevices(devices, commandStates);
    final meteringSummary = _collectMeteringSummary(devices);

    return DashboardData(
      reading: _parseReading(
        history,
        dashboardEnergy,
        backendCurrentTotal,
        parsedDevices,
        meteringSummary,
      ),
      sensors: _parseSensors(sensors, devices, dashboardEnvironment),
      devices: parsedDevices,
      alerts: const [],
      tariffBhdPerKwh: _asDouble(
        _pick(dashboardEnergy, [
              'tariff_BHD_per_kWh',
              'tariffBhdPerKwh',
              'tariff',
            ]) ??
            _pick(backendCurrentTotal, [
              'tariff_BHD_per_kWh',
              'tariffBhdPerKwh',
              'tariff',
            ]) ??
            _pick(home, ['tariff_BHD_per_kWh', 'tariffBhdPerKwh', 'tariff']),
        fallback: ElectricityPricing.costPerKWh,
      ),
      pendingDeviceCommands: commandStates.entries
          .where((entry) => entry.value.isPending)
          .map((entry) => entry.key)
          .toSet(),
      deviceCommandErrors: const {},
      aiDashboard: _parseAiDashboard(_asMap(backendDashboard['ai'])),
      aiDailySummary: _parseAiDailySummary(_asMap(backendAi['daily_summary'])),
      aiRecommendation: _parseAiRecommendation(
        _asMap(recommendations['ai_energy_insight']),
      ),
      aiAlert: _parseAiAlert(_asMap(activeAlerts['ai_abnormal_usage'])),
      scenarioId: _asNullableString(
        _pick(metadata, ['scenario_id', 'active_scenario', 'scenario_name']),
      ),
      scenarioName: _asNullableString(
        _pick(metadata, ['scenario_name', 'name', 'active_scenario']),
      ),
      scenarioDescription: _asNullableString(
        _pick(metadata, ['scenario_description', 'description', 'notes']),
      ),
      deviceControlEnabled: _asBool(
        _pick(sourceHome, ['device_control_enabled', 'deviceControlEnabled']) ??
            _pick(metadata, ['device_control_enabled', 'deviceControlEnabled']),
        fallback: homeId != 'home_test',
      ),
    );
  }

  Future<List<DemoScenario>> fetchDemoScenarios({
    CancelToken? cancelToken,
  }) async {
    final response = await _dio.get(
      '/homes/home_test.json',
      cancelToken: cancelToken,
    );
    final home = _asMap(response.data);
    final scenarios = _asMap(home['demo_scenarios']);

    if (scenarios.isNotEmpty) {
      return scenarios.entries.map((entry) {
        final data = _asMap(entry.value);
        final scenarioAiMetadata = _asMap(
          _asMap(_asMap(data['backend'])['ai'])['test_metadata'],
        );
        final metadata = {..._asMap(data['scenario']), ...scenarioAiMetadata};
        return DemoScenario(
          id: entry.key,
          name:
              _asNullableString(
                _pick(metadata, ['scenario_name', 'name', 'active_scenario']),
              ) ??
              _prettyScenarioName(entry.key),
          description:
              _asNullableString(
                _pick(metadata, ['scenario_description', 'description']),
              ) ??
              'Demo scenario data.',
        );
      }).toList()..sort((a, b) => a.name.compareTo(b.name));
    }

    final metadata = _asMap(_asMap(home['backend'])['ai'])['test_metadata'];
    final activeScenario =
        _asNullableString(_pick(metadata, ['active_scenario'])) ??
        'current_home_test';
    return [
      DemoScenario(
        id: activeScenario,
        name: _prettyScenarioName(activeScenario),
        description:
            _asNullableString(_pick(metadata, ['notes'])) ??
            'Current Home Test scenario.',
      ),
    ];
  }

  Future<void> sendDeviceCommand(
    String deviceId,
    String action, {
    required String homeId,
  }) async {
    if (homeId != NetworkConfig.firebaseHomeId) {
      throw ArgumentError.value(
        homeId,
        'homeId',
        'Device control is only enabled for the real home',
      );
    }

    if (deviceId != 'breaker_01' && deviceId != 'breaker_02') {
      throw ArgumentError.value(deviceId, 'deviceId', 'Unsupported device ID');
    }

    if (action != 'turn_on' && action != 'turn_off') {
      throw ArgumentError.value(action, 'action', 'Unsupported command action');
    }

    final nowMs = DateTime.now().millisecondsSinceEpoch;
    final timestampMs = nowMs <= _lastCommandTimestampMs
        ? _lastCommandTimestampMs + 1
        : nowMs;
    _lastCommandTimestampMs = timestampMs;

    await _firebaseRef('homes/$homeId/commands/$deviceId/latest').set({
      'command_id': 'cmd_$timestampMs',
      'device_id': deviceId,
      'action': action,
      'status': 'pending',
      'requested_by': 'mobile_app',
      'created_at': timestampMs,
    });
  }

  Stream<DeviceCommandState> watchLatestCommandStatus(String deviceId) {
    return watchLatestCommandStatusForHome(
      NetworkConfig.firebaseHomeId,
      deviceId,
    );
  }

  Stream<DeviceCommandState> watchLatestCommandStatusForHome(
    String homeId,
    String deviceId,
  ) {
    final commandRef = _firebaseRef('homes/$homeId/commands/$deviceId/latest');

    return commandRef.onValue.map((event) {
      final command = _asMap(event.snapshot.value);
      return DeviceCommandState(
        status: _asString(_pick(command, ['status'])).toLowerCase(),
        action: _asString(_pick(command, ['action'])).toLowerCase(),
        error: _asNullableString(_pick(command, ['error'])),
      );
    });
  }

  Stream<bool?> watchDeviceSwitchStatus(String deviceId) {
    return watchDeviceSwitchStatusForHome(
      NetworkConfig.firebaseHomeId,
      deviceId,
    );
  }

  Stream<bool?> watchDeviceSwitchStatusForHome(String homeId, String deviceId) {
    return _firebaseRef(
      'homes/$homeId/devices/$deviceId/status/switch',
    ).onValue.map((event) {
      final value = event.snapshot.value;
      if (value == null) {
        return null;
      }
      return _asBool(value);
    });
  }

  String _prettyScenarioName(String value) {
    return value
        .replaceAll('_', ' ')
        .split(' ')
        .where((part) => part.isNotEmpty)
        .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
        .join(' ');
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
    Map<String, dynamic> dashboardEnergy,
    Map<String, dynamic> backendCurrentTotal,
    List<Device> devices,
    Map<String, dynamic> meteringSummary,
  ) {
    final latestHistory = _asMap(history['latest']);

    final totalPowerFromDevices = devices.fold<double>(
      0,
      (sum, device) => sum + device.currentPower,
    );

    final source = {
      ...meteringSummary,
      ...history,
      ...latestHistory,
      ...dashboardEnergy,
      ...backendCurrentTotal,
    };

    return EnergyReading(
      timestamp: _asDateTime(
        _pick(source, [
          'updated_at',
          'updatedAt',
          'timestamp',
          'created_at',
          'time',
        ]),
      ),
      voltage: _asDouble(
        _pick(source, ['voltage', 'voltage_v', 'voltage_V', 'v']),
      ),
      current: _asDouble(
        _pick(source, ['current', 'current_a', 'current_A', 'i', 'ampere']),
      ),
      power: _asDouble(
        _pick(source, [
          'total_power_W',
          'total_avg_power_W',
          'current_power_w',
          'currentPowerW',
          'power',
          'power_W',
          'wattage',
        ]),
        fallback: totalPowerFromDevices,
      ),
      energyToday: _asDouble(
        _pick(source, [
          'total_estimated_energy_kWh',
          'total_energy_kWh',
          'energy_today_kwh',
          'energy_today_kWh',
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
          'total_energy_kWh',
          'total_estimated_energy_kWh',
          'total_energy_kwh',
          'energyTotal',
          'energy_total',
          'totalKwh',
          'total_kwh',
          'energy_total_kWh',
          'energy_total_kwh',
        ]),
      ),
      costToday: _asDouble(
        _pick(source, [
          'total_estimated_cost_BHD',
          'total_cost_BHD',
          'cost_today_bd',
          'cost_today_BD',
          'costToday',
          'cost_today',
          'todayCost',
          'today_cost',
        ]),
      ),
    );
  }

  SensorData _parseSensors(
    Map<String, dynamic> sensors,
    Map<String, dynamic> devices,
    Map<String, dynamic> dashboardEnvironment,
  ) {
    final source = <String, dynamic>{
      ...dashboardEnvironment,
      ..._extractSensorsFromDevices(devices),
      ...sensors,
    };
    final smokeRaw = _asInt(
      _pick(source, ['smoke_raw', 'smokeRaw', 'mq2_raw', 'mq2Raw']),
    );
    final smokeDigital = _pick(source, ['smoke']);
    final smokeStatus = _asSmokeStatus(
      _pick(source, ['smoke_text', 'smokeStatus', 'smoke_status']),
      smokeDigital,
      smokeRaw,
    );

    return SensorData(
      timestamp: _asDateTime(
        _pick(source, [
          'readable_time',
          'sensorTimestamp',
          'timestamp',
          'timestamp_ms',
          'updatedAt',
          'updated_at',
          'last_processed_at',
        ]),
      ),
      temperature: _asDouble(
        _pick(source, [
          'temperature',
          'temperature_c',
          'temperature_C',
          'temp',
        ]),
      ),
      humidity: _asDouble(
        _pick(source, ['humidity', 'humidity_percent', 'humid']),
      ),
      isOccupied: _asBool(
        _pick(source, [
          'isOccupied',
          'is_occupied',
          'occupied',
          'motion',
          'motion_text',
        ]),
      ),
      eco2: _asDouble(_pick(source, ['eco2', 'eCO2', 'co2'])),
      tvoc: _asDouble(_pick(source, ['tvoc'])),
      aqi: _asInt(_pick(source, ['aqi'])),
      smokeRaw: smokeRaw,
      lightRaw: _asInt(_pick(source, ['light_raw', 'lightRaw'])),
      soundRaw: _asInt(
        _pick(source, [
          'sound_raw',
          'soundRaw',
          'latest_sound_raw',
          'noise_level',
        ]),
      ),
      noise: _asInt(_pick(source, ['noise'])),
      noiseStatus:
          _pick(source, [
            'noise_text',
            'noiseText',
            'noise_status',
            'noiseStatus',
          ])?.toString() ??
          'Unknown',
      lightStatus:
          _pick(source, ['light_status', 'lightStatus'])?.toString() ??
          'Unknown',
      smokeStatus: smokeStatus,
      ahtOk: _asBool(_pick(source, ['aht_ok', 'ahtOk']), fallback: true),
      ens160Ok: _asBool(
        _pick(source, ['ens160_ok', 'ens160Ok']),
        fallback: true,
      ),
    );
  }

  List<Device> _parseDevices(
    Map<String, dynamic> devicesMap,
    Map<String, DeviceCommandState> commandStates,
  ) {
    if (devicesMap.isEmpty) {
      return const [];
    }

    final devices = <Device>[];
    for (final entry in devicesMap.entries) {
      final data = _asMap(entry.value);
      if (data.isEmpty) {
        continue;
      }

      final rawType = _pick(data, ['type', 'deviceType'])?.toString();
      if (!_isControllableDevice(rawType, entry.key)) {
        continue;
      }

      final metering = _asMap(data['metering']);
      final status = _asMap(data['status']);
      final commandState = commandStates[entry.key];
      final desiredSwitchState = commandState?.desiredSwitchState;
      final actualSwitchState = _asBool(
        _pick(status, ['switch', 'on', 'relay_status']) ??
            _pick(data, ['isOn', 'on', 'switch', 'relay_status']),
      );
      final currentPower = _asDouble(
        _pick(data, ['currentPower', 'power', 'wattage']) ??
            _pick(metering, ['power_W', 'power_w', 'power']),
      );

      devices.add(
        Device(
          id: (_pick(data, ['id']) ?? entry.key).toString(),
          name:
              _pick(data, ['name', 'label', 'deviceName'])?.toString() ??
              entry.key,
          type: _parseDeviceType(rawType),
          isOn: desiredSwitchState ?? actualSwitchState,
          currentPower: desiredSwitchState == false ? 0.0 : currentPower,
          branch:
              _pick(data, ['branch', 'zone'])?.toString() ??
              _branchFromDeviceId(entry.key),
        ),
      );
    }

    return devices;
  }

  Map<String, DeviceCommandState> _parseDeviceCommandStates(
    Map<String, dynamic> commandsMap,
  ) {
    final result = <String, DeviceCommandState>{};

    for (final entry in commandsMap.entries) {
      final command = _asMap(_asMap(entry.value)['latest']);
      if (command.isEmpty) {
        continue;
      }

      result[entry.key] = DeviceCommandState(
        status: _asString(_pick(command, ['status'])).toLowerCase(),
        action: _asString(_pick(command, ['action'])).toLowerCase(),
        error: _asNullableString(_pick(command, ['error'])),
      );
    }

    return result;
  }

  bool _isControllableDevice(String? type, String deviceId) {
    final normalizedType = type?.toLowerCase();
    if (normalizedType == 'sensor_node' || normalizedType == 'sensor') {
      return false;
    }

    return normalizedType == 'smart_breaker' ||
        normalizedType == 'breaker' ||
        deviceId.toLowerCase().startsWith('breaker_');
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

  String _asSmokeStatus(dynamic textValue, dynamic digitalValue, int rawValue) {
    final text = _asString(textValue);
    if (text.isNotEmpty) {
      return text;
    }

    if (digitalValue != null) {
      return _asBool(digitalValue) ? 'Smoke/Gas' : 'Clear';
    }

    if (rawValue > 0) {
      return 'Clear';
    }

    return 'Unknown';
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
