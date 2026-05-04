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
  final ControlModeInfo control;
  final List<ActionSuggestion> actionSuggestions;
  final List<AutomationLog> automationLogs;
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
    this.control = const ControlModeInfo(
      mode: 'assist',
      label: 'Assist',
      description:
          'The system suggests actions and asks before controlling devices.',
    ),
    this.actionSuggestions = const [],
    this.automationLogs = const [],
    this.scenarioId,
    this.scenarioName,
    this.scenarioDescription,
    this.deviceControlEnabled = true,
  });
}

class ControlModeInfo {
  const ControlModeInfo({
    required this.mode,
    required this.label,
    required this.description,
  });

  final String mode;
  final String label;
  final String description;
}

class ControlModeOption extends ControlModeInfo {
  const ControlModeOption({
    required super.mode,
    required super.label,
    required super.description,
  });
}

class ActionSuggestion {
  const ActionSuggestion({
    required this.id,
    required this.deviceName,
    required this.deviceId,
    required this.suggestedCommand,
    required this.reason,
    required this.status,
  });

  final String id;
  final String deviceName;
  final String deviceId;
  final String suggestedCommand;
  final String reason;
  final String status;
}

class AutomationLog {
  const AutomationLog({
    required this.id,
    required this.deviceName,
    required this.command,
    required this.reason,
    required this.createdAt,
  });

  final String id;
  final String deviceName;
  final String command;
  final String reason;
  final DateTime createdAt;
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

  bool get isPending => status == 'pending' || status == 'sent';
  bool get isDone => status == 'done' || status == 'confirmed';
  bool get isFailed => status == 'failed' || status == 'timeout';

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

class DeviceCommandResult {
  const DeviceCommandResult({
    required this.success,
    required this.noAction,
    required this.status,
    required this.message,
    this.commandId,
  });

  final bool success;
  final bool noAction;
  final String status;
  final String message;
  final String? commandId;
}

class FirebaseRealtimeService {
  FirebaseRealtimeService()
    : _dio = Dio(
        BaseOptions(
          baseUrl: NetworkConfig.apiBaseUrl,
          connectTimeout: const Duration(seconds: 30),
          receiveTimeout: const Duration(seconds: 30),
        ),
      ),
      _firebaseDio = Dio(
        BaseOptions(
          baseUrl: NetworkConfig.firebaseRealtimeDatabaseUrl,
          connectTimeout: const Duration(seconds: 10),
          receiveTimeout: const Duration(seconds: 10),
        ),
      );

  final Dio _dio;
  final Dio _firebaseDio;
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

  Stream<SensorData> watchLiveSensorData({required String homeId}) {
    final sensorRef = _firebaseRef('homes/$homeId/devices/esp32_01');

    return sensorRef.onValue.map((event) {
      final raw = _asMap(event.snapshot.value);
      if (raw.isEmpty) {
        throw StateError('No live sensor data found for $homeId.');
      }
      return _parseLiveSensorDevice(raw);
    });
  }

  SensorData _parseLiveSensorDevice(Map<String, dynamic> raw) {
    final sensors = _asMap(raw['sensors']);
    final status = _asMap(raw['status']);
    final source = {...sensors, ...status};

    return SensorData(
      timestamp: _asDateTime(
        _pick(source, [
          'timestamp_ms',
          'lastSeenMs',
          'last_seen_ms',
          'readable_time',
          'readableTime',
          'timestamp',
        ]),
      ),
      temperature: _asDouble(
        _pick(source, ['temperature', 'latest_temperature']),
      ),
      humidity: _asDouble(_pick(source, ['humidity', 'latest_humidity'])),
      isOccupied: _asBool(_pick(source, ['motion', 'motion_text'])),
      eco2: _asDouble(_pick(source, ['eco2', 'eCO2'])),
      tvoc: _asDouble(_pick(source, ['tvoc'])),
      aqi: _asInt(_pick(source, ['aqi'])),
      smokeRaw: _asInt(_pick(source, ['smoke_raw', 'smokeRaw'])),
      lightRaw: _asInt(_pick(source, ['light_raw', 'lightRaw'])),
      soundRaw: _asInt(_pick(source, ['sound_raw', 'soundRaw'])),
      noise: _asInt(_pick(source, ['noise'])),
      noiseStatus: _asString(
        _pick(source, ['noise_text', 'noiseText']),
        fallback: 'Unknown',
      ),
      lightStatus: _asString(
        _pick(source, ['light_status', 'lightStatus']),
        fallback: 'Unknown',
      ),
      smokeStatus: _asSmokeStatus(
        _pick(source, ['smoke_text', 'smokeStatus', 'smoke_status']),
        _pick(source, ['smoke']),
        _asInt(_pick(source, ['smoke_raw', 'smokeRaw'])),
      ),
      ahtOk: _asBool(_pick(source, ['aht_ok', 'ahtOk']), fallback: true),
      ens160Ok: _asBool(
        _pick(source, ['ens160_ok', 'ens160Ok']),
        fallback: true,
      ),
    );
  }

  Future<DashboardData> fetchDashboardData({
    required String homeId,
    String? scenarioId,
    CancelToken? cancelToken,
  }) async {
    if (scenarioId != null) {
      return _fetchDashboardDataFromFirebase(
        homeId: homeId,
        scenarioId: scenarioId,
        cancelToken: cancelToken,
      );
    }

    try {
      final response = await _dio.get(
        '/api/home/$homeId/dashboard',
        cancelToken: cancelToken,
      );
      final data = _asMap(response.data);

      if (data.isEmpty) {
        throw Exception('No data found for $homeId.');
      }

      return _parseApiDashboardData(data, homeId: homeId);
    } catch (_) {
      return _fetchDashboardDataFromFirebase(
        homeId: homeId,
        cancelToken: cancelToken,
      );
    }
  }

  DashboardData _parseApiDashboardData(
    Map<String, dynamic> data, {
    required String homeId,
  }) {
    final room = _asMap(data['room']);
    final energy = _asMap(data['energy']);
    final devicesMap = _asMap(data['devices']);
    final alerts = _asList(data['alerts']);
    final recommendations = _asList(data['recommendations']);
    final actionSuggestions = _asList(data['action_suggestions']);
    final automationLogs = _asList(data['automation_logs']);
    final ai = _asMap(data['ai']);
    final aiDailySummary = _asMap(data['ai_daily_summary']);

    final parsedDevices = devicesMap.entries
        .map((entry) => _parseApiDevice(entry.key, _asMap(entry.value)))
        .where(
          (device) =>
              device.type != DeviceType.socket ||
              device.id.startsWith('breaker_'),
        )
        .toList();

    final pendingCommands = <String>{};
    for (final entry in devicesMap.entries) {
      final device = _asMap(entry.value);
      final commandState = _asString(
        _pick(device, ['last_command_status', 'command_status']),
      ).toLowerCase();
      if (_asBool(_pick(device, ['command_in_progress'])) ||
          commandState == 'pending' ||
          commandState == 'sent') {
        pendingCommands.add(entry.key);
      }
    }

    return DashboardData(
      reading: EnergyReading(
        timestamp: _asDateTime(
          _pick(data, ['updated_at_ms', 'updated_at_iso']),
        ),
        voltage: _asDouble(
          _pick(energy, ['voltage', 'voltage_v', 'voltage_V']),
        ),
        current: _asDouble(
          _pick(energy, ['current', 'current_a', 'current_A']),
        ),
        power: _asDouble(_pick(energy, ['current_power_w', 'total_power_W'])),
        energyToday: _asDouble(
          _pick(energy, ['today_kwh', 'total_energy_kWh']),
        ),
        energyTotal: _asDouble(
          _pick(energy, ['today_kwh', 'total_energy_kWh']),
        ),
        costToday: _asDouble(
          _pick(energy, ['today_cost_bhd', 'total_cost_BHD']),
        ),
      ),
      sensors: SensorData(
        timestamp: _asDateTime(
          _pick(room, ['sensor_timestamp_ms', 'sensor_timestamp_iso']) ??
              _pick(data, ['updated_at_ms', 'updated_at_iso']),
        ),
        temperature: _asDouble(_pick(room, ['temperature'])),
        humidity: _asDouble(_pick(room, ['humidity'])),
        isOccupied: _asBool(_pick(room, ['motion'])),
        eco2: _asDouble(_pick(room, ['eco2'])),
        tvoc: _asDouble(_pick(room, ['tvoc'])),
        aqi: _asInt(_pick(room, ['aqi'])),
        smokeRaw: _asInt(_pick(room, ['smoke_raw'])),
        lightRaw: _asInt(_pick(room, ['light_raw'])),
        soundRaw: _asInt(_pick(room, ['sound_level'])),
        noiseStatus: _asString(
          _pick(room, ['noise_text']),
          fallback: 'Unknown',
        ),
        lightStatus: _asString(
          _pick(room, ['light_status']),
          fallback: 'Unknown',
        ),
        smokeStatus: _asString(
          _pick(room, ['smoke_text']),
          fallback: 'Unknown',
        ),
        ahtOk: _asBool(_pick(room, ['aht_ok'])),
        ens160Ok: _asBool(_pick(room, ['ens160_ok'])),
      ),
      devices: parsedDevices,
      alerts: alerts
          .map(
            (item) => _alertFromBackend(
              _asString(_pick(item, ['id', 'alert_key', 'alert_id'])),
              item,
            ),
          )
          .toList(),
      tariffBhdPerKwh: ElectricityPricing.costPerKWh,
      pendingDeviceCommands: pendingCommands,
      deviceCommandErrors: const {},
      aiDashboard: ai.isEmpty ? null : _parseApiAiDashboard(ai, data),
      aiDailySummary: _parseAiDailySummary(aiDailySummary),
      aiRecommendation: recommendations.isEmpty
          ? null
          : _parseAiRecommendation(recommendations.first),
      aiAlert: null,
      control: _parseControl(_asMap(data['control'])),
      actionSuggestions: actionSuggestions.map(_parseActionSuggestion).toList(),
      automationLogs: automationLogs.map(_parseAutomationLog).toList()
        ..sort((a, b) => b.createdAt.compareTo(a.createdAt)),
      scenarioId: null,
      scenarioName: null,
      scenarioDescription: null,
      deviceControlEnabled: homeId != 'home_test',
    );
  }

  Device _parseApiDevice(String deviceId, Map<String, dynamic> data) {
    final displayState = _asString(
      _pick(data, ['display_state', 'state']),
    ).toLowerCase();
    final rawType = _asString(_pick(data, ['type']));
    final name = _asString(_pick(data, ['name']), fallback: deviceId);
    final lastCommand = _asMap(data['last_command']);
    final online = _asBool(_pick(data, ['online']), fallback: true);
    final visualIsOn =
        online &&
        (displayState == 'on' || _asBool(_pick(data, ['is_on', 'switch'])));
    return Device(
      id: _asString(_pick(data, ['device_id', 'id']), fallback: deviceId),
      name: name,
      type: _parseApiDeviceType(deviceId, name, rawType),
      isOn: visualIsOn,
      currentPower: online
          ? _asDouble(_pick(data, ['power_w', 'currentPower']))
          : 0.0,
      branch: _branchFromDeviceId(deviceId),
      online: online,
      controllable: _asBool(_pick(data, ['controllable']), fallback: true),
      commandInProgress: _asBool(_pick(data, ['command_in_progress'])),
      pendingTargetState: _asNullableString(
        _pick(data, ['pending_target_state']),
      ),
      lastCommandMessage: _asNullableString(
        _pick(lastCommand, ['user_message']) ??
            _pick(data, ['last_command_message']),
      ),
    );
  }

  DeviceType _parseApiDeviceType(String deviceId, String name, String rawType) {
    final text = '$deviceId $name $rawType'.toLowerCase();
    if (text.contains('ac') || text.contains('air')) {
      return DeviceType.airConditioner;
    }
    if (text.contains('light') || text.contains('switch')) {
      return DeviceType.light;
    }
    return _parseDeviceType(rawType);
  }

  AiDashboardSummary _parseApiAiDashboard(
    Map<String, dynamic> ai,
    Map<String, dynamic> root,
  ) {
    final status = _asString(
      _pick(ai, ['prediction_status', 'status']),
      fallback: 'unknown',
    );
    final abnormalUsage = _pick(ai, ['abnormal_usage']);
    final energyWaste = _pick(ai, ['energy_waste']);
    return AiDashboardSummary(
      updatedAt: _asDateTime(
        _pick(ai, ['updated_at']) ??
            _pick(root, ['updated_at_ms', 'updated_at_iso']),
      ),
      source: 'Smart Energy API',
      modelName: '',
      modelVersion: '',
      inputSource: 'backend_api',
      energyWaste: energyWaste != null
          ? _asBool(energyWaste)
          : status != 'normal' && status != 'unknown',
      wasteConfidence: _asDouble(_pick(ai, ['waste_confidence', 'confidence'])),
      abnormalUsage: abnormalUsage != null
          ? _asString(abnormalUsage).toLowerCase() != 'normal' &&
                _asString(abnormalUsage).isNotEmpty
          : status != 'normal' && status != 'unknown',
      abnormalUsageConfidence: _asDouble(
        _pick(ai, ['abnormal_usage_confidence', 'confidence']),
      ),
      recommendationType: _asString(
        _pick(ai, ['recommendation_type', 'recommended_action']),
      ),
      nextHourEnergyKwh: _asDouble(
        _pick(ai, ['next_hour_energy_kWh', 'next_hour_energy']),
      ),
      nextHourCostBhd: _asDouble(
        _pick(ai, ['next_hour_cost_BHD', 'next_hour_cost']),
      ),
      efficiencyScore: _asDouble(_pick(ai, ['efficiency_score'])),
      explanation: _asString(
        _pick(ai, ['summary']),
        fallback: 'AI analysis is not available yet.',
      ),
      controlSuggestion: _asString(_pick(ai, ['recommended_action'])),
    );
  }

  Future<DashboardData> _fetchDashboardDataFromFirebase({
    required String homeId,
    String? scenarioId,
    CancelToken? cancelToken,
  }) async {
    final response = await _firebaseDio.get(
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
    final actionSuggestions = _asMap(sourceHome['action_suggestions']);
    final activeSuggestions = _asMap(actionSuggestions['active']);
    final automationLogs = _asMap(sourceHome['automation_logs']);

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
      control: _parseControl(_asMap(sourceHome['control'])),
      actionSuggestions: _asList(
        activeSuggestions,
      ).map(_parseActionSuggestion).toList(),
      automationLogs: _asList(automationLogs).map(_parseAutomationLog).toList()
        ..sort((a, b) => b.createdAt.compareTo(a.createdAt)),
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
    final response = await _firebaseDio.get(
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

  Future<List<ControlModeOption>> fetchControlModes({
    required String homeId,
    CancelToken? cancelToken,
  }) async {
    final response = await _dio.get(
      '/api/home/$homeId/control',
      cancelToken: cancelToken,
    );
    final data = _asMap(response.data);
    return _asList(data['available_modes'])
        .map(
          (item) => ControlModeOption(
            mode: _asString(_pick(item, ['value', 'mode']), fallback: 'assist'),
            label: _asString(_pick(item, ['label']), fallback: 'Assist'),
            description: _asString(
              _pick(item, ['description']),
              fallback:
                  'The system suggests actions and asks before controlling devices.',
            ),
          ),
        )
        .toList();
  }

  Future<String> updateControlMode({
    required String homeId,
    required String mode,
    required String updatedBy,
  }) async {
    final response = await _dio.put(
      '/api/home/$homeId/control/mode',
      data: {'mode': mode, 'updated_by': updatedBy},
    );
    final data = _asMap(response.data);
    return _asString(
      _pick(data, ['message']),
      fallback: 'Control mode changed to ${_prettyMode(mode)} Mode.',
    );
  }

  Future<String> approveActionSuggestion({
    required String homeId,
    required String suggestionId,
  }) async {
    final response = await _dio.post(
      '/api/home/$homeId/action-suggestions/$suggestionId/approve',
    );
    final data = _asMap(response.data);
    return _asString(
      _pick(data, ['message']),
      fallback: 'Action suggestion approved.',
    );
  }

  Future<String> dismissActionSuggestion({
    required String homeId,
    required String suggestionId,
  }) async {
    final response = await _dio.post(
      '/api/home/$homeId/action-suggestions/$suggestionId/dismiss',
    );
    final data = _asMap(response.data);
    return _asString(
      _pick(data, ['message']),
      fallback: 'Action suggestion dismissed.',
    );
  }

  Future<DeviceCommandResult> sendDeviceCommand(
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

    try {
      final response = await _dio.post(
        '/api/home/$homeId/devices/$deviceId/command',
        data: {'command': action, 'requested_by': 'flutter_app'},
      );
      final data = _asMap(response.data);
      return DeviceCommandResult(
        success: _asBool(_pick(data, ['success']), fallback: true),
        noAction: _asBool(_pick(data, ['no_action'])),
        status: _asString(_pick(data, ['status'])),
        message: _asString(_pick(data, ['message'])),
        commandId: _asNullableString(_pick(data, ['command_id'])),
      );
    } catch (error) {
      if (error is DioException && error.response != null) {
        final data = _asMap(error.response?.data);
        final detail = _asMap(data['detail']);
        final message = _asString(
          _pick(detail, ['message']) ?? _pick(data, ['message', 'detail']),
          fallback: 'Could not send command. Please try again.',
        );
        throw Exception(message);
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
        'command': action,
        'target_state': action == 'turn_on' ? 'on' : 'off',
        'status': 'pending',
        'requested_by': 'mobile_app',
        'created_at': timestampMs,
      });
      return DeviceCommandResult(
        success: true,
        noAction: false,
        status: 'pending',
        message: 'Command accepted.',
        commandId: 'cmd_$timestampMs',
      );
    }
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
        action: _asString(_pick(command, ['action', 'command'])).toLowerCase(),
        error: _asNullableString(
          _pick(command, ['error']) ??
              _pick(_asMap(command['result']), ['user_message']),
        ),
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

  Stream<Device> watchDeviceForHome(String homeId, String deviceId) {
    return _firebaseRef('homes/$homeId/devices/$deviceId').onValue.map((event) {
      final raw = _asMap(event.snapshot.value);
      if (raw.isEmpty) {
        throw StateError('No device data found for $deviceId.');
      }
      return _parseRealtimeDevice(deviceId, raw);
    });
  }

  Device _parseRealtimeDevice(String deviceId, Map<String, dynamic> data) {
    final metering = _asMap(data['metering']);
    final status = _asMap(data['status']);
    final pendingTargetState = _asNullableString(
      _pick(data, ['pending_target_state']),
    );
    final commandInProgress = _asBool(_pick(data, ['command_in_progress']));
    final pendingSwitchState = pendingTargetState == 'on'
        ? true
        : pendingTargetState == 'off'
        ? false
        : null;
    final actualSwitchState = _asBool(
      _pick(status, ['switch', 'on', 'relay_status']) ??
          _pick(data, ['isOn', 'on', 'switch', 'relay_status']),
    );
    final rawType = _pick(data, ['type', 'deviceType'])?.toString();
    final name =
        _pick(data, ['name', 'label', 'deviceName'])?.toString() ?? deviceId;
    final online = _asBool(_pick(status, ['online']), fallback: true);
    final visualIsOn = online && (pendingSwitchState ?? actualSwitchState);
    final rawPower = _asDouble(
      _pick(data, ['currentPower', 'power', 'wattage']) ??
          _pick(metering, ['power_W', 'power_w', 'power']),
    );

    return Device(
      id: (_pick(data, ['id']) ?? deviceId).toString(),
      name: name,
      type: _parseApiDeviceType(deviceId, name, rawType ?? ''),
      isOn: visualIsOn,
      currentPower: visualIsOn ? rawPower : 0.0,
      branch:
          _pick(data, ['branch', 'zone'])?.toString() ??
          _branchFromDeviceId(deviceId),
      online: online,
      controllable: _asBool(_pick(data, ['controllable']), fallback: true),
      commandInProgress: commandInProgress,
      pendingTargetState: pendingTargetState,
      lastCommandMessage: _asNullableString(
        _pick(data, ['last_command_message']),
      ),
    );
  }

  String _prettyScenarioName(String value) {
    return value
        .replaceAll('_', ' ')
        .split(' ')
        .where((part) => part.isNotEmpty)
        .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
        .join(' ');
  }

  String _prettyMode(String value) {
    switch (value.toLowerCase()) {
      case 'manual':
        return 'Manual';
      case 'auto':
        return 'Auto';
      case 'assist':
      default:
        return 'Assist';
    }
  }

  ControlModeInfo _parseControl(Map<String, dynamic> data) {
    final mode = _asString(
      _pick(data, ['mode']),
      fallback: 'assist',
    ).toLowerCase();
    final label = _asString(
      _pick(data, ['label']),
      fallback: _prettyMode(mode),
    );
    return ControlModeInfo(
      mode: mode,
      label: label,
      description: _asString(
        _pick(data, ['description']),
        fallback: mode == 'manual'
            ? 'You control all devices. The system only monitors and recommends.'
            : mode == 'auto'
            ? 'The system can automatically control allowed devices to save energy.'
            : 'The system suggests actions and asks before controlling devices.',
      ),
    );
  }

  ActionSuggestion _parseActionSuggestion(Map<String, dynamic> data) {
    return ActionSuggestion(
      id: _asString(
        _pick(data, ['suggestion_id', 'id']),
        fallback: DateTime.now().millisecondsSinceEpoch.toString(),
      ),
      deviceName: _asString(_pick(data, ['device_name']), fallback: 'Device'),
      deviceId: _asString(_pick(data, ['device_id'])),
      suggestedCommand: _asString(
        _pick(data, ['suggested_command', 'command']),
      ),
      reason: _asString(
        _pick(data, ['reason']),
        fallback: 'Energy-saving action suggested.',
      ),
      status: _asString(_pick(data, ['status']), fallback: 'waiting_for_user'),
    );
  }

  AutomationLog _parseAutomationLog(Map<String, dynamic> data) {
    return AutomationLog(
      id: _asString(_pick(data, ['log_id', 'id'])),
      deviceName: _asString(_pick(data, ['device_name']), fallback: 'Device'),
      command: _asString(_pick(data, ['command'])),
      reason: _asString(_pick(data, ['reason']), fallback: 'Automatic action.'),
      createdAt: _asDateTime(
        _pick(data, ['created_at_ms', 'created_at_iso', 'created_at']),
      ),
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
      final pendingTargetState = _asNullableString(
        _pick(data, ['pending_target_state']),
      );
      final commandInProgress =
          _asBool(_pick(data, ['command_in_progress'])) ||
          commandState?.isPending == true;
      final desiredSwitchState = pendingTargetState == 'on'
          ? true
          : pendingTargetState == 'off'
          ? false
          : commandState?.desiredSwitchState;
      final actualSwitchState = _asBool(
        _pick(status, ['switch', 'on', 'relay_status']) ??
            _pick(data, ['isOn', 'on', 'switch', 'relay_status']),
      );
      final currentPower = _asDouble(
        _pick(data, ['currentPower', 'power', 'wattage']) ??
            _pick(metering, ['power_W', 'power_w', 'power']),
      );
      final online = _asBool(_pick(status, ['online']), fallback: true);
      final visualIsOn = online && (desiredSwitchState ?? actualSwitchState);

      devices.add(
        Device(
          id: (_pick(data, ['id']) ?? entry.key).toString(),
          name:
              _pick(data, ['name', 'label', 'deviceName'])?.toString() ??
              entry.key,
          type: _parseDeviceType(rawType),
          isOn: visualIsOn,
          currentPower: visualIsOn ? currentPower : 0.0,
          branch:
              _pick(data, ['branch', 'zone'])?.toString() ??
              _branchFromDeviceId(entry.key),
          online: online,
          controllable: _asBool(_pick(data, ['controllable']), fallback: true),
          commandInProgress: commandInProgress,
          pendingTargetState: pendingTargetState,
          lastCommandMessage:
              _asNullableString(_pick(data, ['last_command_message'])) ??
              commandState?.error,
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
        action: _asString(_pick(command, ['action', 'command'])).toLowerCase(),
        error: _asNullableString(
          _pick(command, ['error']) ??
              _pick(_asMap(command['result']), ['user_message']),
        ),
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

  List<Map<String, dynamic>> _asList(dynamic value) {
    if (value is List) {
      return value.whereType<Map>().map(_asMap).toList();
    }
    if (value is Map) {
      return value.entries
          .map((entry) => {'id': entry.key.toString(), ..._asMap(entry.value)})
          .toList();
    }
    return const [];
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
