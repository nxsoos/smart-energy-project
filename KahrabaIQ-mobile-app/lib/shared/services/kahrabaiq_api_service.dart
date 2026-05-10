// ignore_for_file: unused_element, unused_element_parameter

import 'dart:async';
import 'dart:convert';
import 'dart:io';

import 'package:dio/dio.dart';

import '../models/alert.dart';
import '../models/app_notification.dart';
import '../models/ai_insights.dart';
import '../models/device.dart';
import '../models/energy_reading.dart';
import '../models/sensor_data.dart';
import 'auth_service.dart';
import '../../core/utils/constants.dart';

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
  final Map<String, dynamic> settingsSummary;
  final Map<String, dynamic> occupancy;
  final Map<String, dynamic> safety;
  final List<Map<String, dynamic>> criticalAlerts;
  final ScheduleInfo? nextSchedule;
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
    this.settingsSummary = const {},
    this.occupancy = const {},
    this.safety = const {},
    this.criticalAlerts = const [],
    this.nextSchedule,
    this.scenarioId,
    this.scenarioName,
    this.scenarioDescription,
    this.deviceControlEnabled = true,
  });
}

class HomeSettings {
  const HomeSettings(this.values);

  final Map<String, dynamic> values;

  double get costPerKwh => _asDoubleValue(values['cost_per_kwh'], 0.029);
  double get comfortMin =>
      _asDoubleValue(values['comfort_temperature_min'], 22);
  double get comfortMax =>
      _asDoubleValue(values['comfort_temperature_max'], 25);
  double get highTempThreshold =>
      _asDoubleValue(values['high_temperature_threshold'], 28);
  int get lightWasteMinutes => _asIntValue(values['light_waste_minutes'], 5);
  int get motionRecentSeconds =>
      _asIntValue(values['motion_recent_seconds'], 90);
  int get soundRecentSeconds =>
      _asIntValue(values['sound_recent_seconds'], 120);
  int get occupancyEmptyMinutes =>
      _asIntValue(values['occupancy_empty_minutes'], 10);
  double get soundActivityThreshold =>
      _asDoubleValue(values['sound_activity_threshold'], 45);
  double get occupancyConfidenceThreshold =>
      _asDoubleValue(values['occupancy_confidence_threshold'], 0.65);
  int get deviceOfflineMinutes =>
      _asIntValue(values['device_offline_minutes'], 2);
  bool get quietHoursEnabled =>
      _asBoolValue(values['quiet_hours_enabled'], true);
  String get quietHoursStart =>
      values['quiet_hours_start']?.toString() ?? '23:00';
  String get quietHoursEnd => values['quiet_hours_end']?.toString() ?? '06:00';
  bool get aiRecommendationsEnabled =>
      _asBoolValue(values['ai_recommendations_enabled'], true);
  bool get autoControlEnabled =>
      _asBoolValue(values['auto_control_enabled'], true);
  bool get notificationsEnabled =>
      _asBoolValue(values['notifications_enabled'], true);
  bool get schedulesEnabled => _asBoolValue(values['schedules_enabled'], true);

  static double _asDoubleValue(dynamic value, double fallback) {
    if (value is num) {
      return value.toDouble();
    }
    return double.tryParse(value?.toString() ?? '') ?? fallback;
  }

  static int _asIntValue(dynamic value, int fallback) {
    if (value is num) {
      return value.toInt();
    }
    return int.tryParse(value?.toString() ?? '') ?? fallback;
  }

  static bool _asBoolValue(dynamic value, bool fallback) {
    if (value is bool) {
      return value;
    }
    return fallback;
  }
}

class ScheduleInfo {
  const ScheduleInfo({
    required this.id,
    required this.name,
    required this.deviceId,
    required this.deviceName,
    required this.command,
    required this.time,
    required this.days,
    required this.enabled,
    this.nextRunAt,
  });

  final String id;
  final String name;
  final String deviceId;
  final String deviceName;
  final String command;
  final String time;
  final List<String> days;
  final bool enabled;
  final DateTime? nextRunAt;
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

class HomeMember {
  const HomeMember({
    required this.uid,
    required this.email,
    required this.displayName,
    required this.role,
  });

  final String uid;
  final String email;
  final String displayName;
  final String role;
}

class HomeInvite {
  const HomeInvite({
    required this.inviteId,
    required this.token,
    required this.qrPayload,
    required this.expiresAtMs,
  });

  final String inviteId;
  final String token;
  final String qrPayload;
  final int expiresAtMs;
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

class KahrabaIqApiService {
  KahrabaIqApiService()
    : _dio = Dio(
        BaseOptions(
          baseUrl: NetworkConfig.apiBaseUrl,
          connectTimeout: Duration(seconds: NetworkConfig.piApiTimeoutSeconds),
          receiveTimeout: Duration(seconds: NetworkConfig.piApiTimeoutSeconds),
        ),
      ) {
    _dio.interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final token = await AuthService().getIdToken();
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (error, handler) async {
          if (error.response?.statusCode == 401) {
            await AuthService().signOut();
          }
          if (error.response?.statusCode == 403) {
            handler.reject(
              DioException(
                requestOptions: error.requestOptions,
                response: error.response,
                type: error.type,
                error: 'You do not have permission to perform this action.',
              ),
            );
            return;
          }
          handler.next(error);
        },
      ),
    );
  }

  final Dio _dio;

  bool get usesLocalPiApi => NetworkConfig.useLocalPiApi;

  Future<Map<String, dynamic>> runAiPrediction({required String homeId}) async {
    final response = await _dio.post('/api/homes/$homeId/ai/predict');
    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> fetchAiLatest({required String homeId}) async {
    final response = await _dio.get('/api/homes/$homeId/ai/latest');
    return _asMap(response.data);
  }

  Future<List<Map<String, dynamic>>> fetchAiNotifications({
    required String homeId,
    int limit = 50,
  }) async {
    final response = await _dio.get(
      '/api/homes/$homeId/ai/notifications',
      queryParameters: {'limit': limit},
    );
    return _asList(_asMap(response.data)['notifications'])
        .map(_asMap)
        .toList();
  }

  Future<List<Map<String, dynamic>>> fetchAiHistory({
    required String homeId,
    int limit = 24,
  }) async {
    final response = await _dio.get(
      '/api/homes/$homeId/ai/history',
      queryParameters: {'limit': limit},
    );
    return _asList(_asMap(response.data)['history']).map(_asMap).toList();
  }

  Stream<Alert> watchAlerts({
    required String homeId,
    required int sinceTimestampMs,
  }) {
    return const Stream<Alert>.empty();
  }

  Stream<SensorData> watchLiveSensorData({required String homeId}) {
    if (!NetworkConfig.useAwsIotLive || homeId != NetworkConfig.defaultHomeId) {
      return const Stream<SensorData>.empty();
    }
    return _watchAwsIotLivePayloads(homeId: homeId).map((data) {
      final room = _asMap(data['room']);
      if (room.isEmpty) {
        throw const FormatException('AWS IoT live message has no room data.');
      }
      return _parseAwsIotLiveSensor(room);
    });
  }

  Stream<DashboardData> watchLiveDashboardData({required String homeId}) {
    if (!NetworkConfig.useAwsIotLive || homeId != NetworkConfig.defaultHomeId) {
      return const Stream<DashboardData>.empty();
    }
    return _watchAwsIotLivePayloads(
      homeId: homeId,
    ).map((data) => _parseAwsIotLiveDashboard(data, homeId: homeId));
  }

  Stream<Map<String, dynamic>> _watchAwsIotLivePayloads({
    required String homeId,
  }) {
    final controller = StreamController<Map<String, dynamic>>();
    WebSocket? socket;
    StreamSubscription<dynamic>? subscription;
    Timer? firstMessageTimer;
    Timer? pingTimer;

    Future<void> connect() async {
      try {
        final config = await AuthService()
            .createAwsIotConnectionConfig(homeId: homeId)
            .timeout(
              const Duration(seconds: 25),
              onTimeout: () => throw TimeoutException(
                'Timed out while preparing AWS IoT connection config. '
                'Check Cognito Identity Pool and IoT policy permissions.',
              ),
            );

        final connack = Completer<void>();
        socket =
            await WebSocket.connect(
              config.signedUrl,
              protocols: const ['mqtt'],
            ).timeout(
              const Duration(seconds: 15),
              onTimeout: () => throw TimeoutException(
                'Timed out while opening the AWS IoT WebSocket. '
                'Check the IoT endpoint, client policy, and phone internet.',
              ),
            );

        subscription = socket!.listen(
          (event) {
            try {
              final bytes = _webSocketEventBytes(event);
              if (bytes.isEmpty) {
                return;
              }
              final packetType = bytes.first >> 4;
              if (packetType == 2) {
                if (bytes.length < 4 || bytes[3] != 0) {
                  final code = bytes.length >= 4 ? bytes[3] : -1;
                  throw Exception('AWS IoT MQTT CONNACK failed: code=$code');
                }
                if (!connack.isCompleted) {
                  connack.complete();
                }
                return;
              }
              if (packetType == 3) {
                final publish = _decodeMqttPublishPacket(bytes);
                if (publish.packetId != null) {
                  socket?.add(_buildMqttPubackPacket(publish.packetId!));
                }
                if (publish.topic != config.topic) {
                  return;
                }
                final decoded = jsonDecode(publish.payload);
                final data = _asMap(decoded);
                if (data.isNotEmpty && !controller.isClosed) {
                  firstMessageTimer?.cancel();
                  controller.add(data);
                }
                return;
              }
              if (packetType == 9 || packetType == 13) {
                return;
              }
            } catch (error, stackTrace) {
              if (!connack.isCompleted) {
                connack.completeError(error, stackTrace);
              }
              if (!controller.isClosed) {
                controller.addError(error, stackTrace);
              }
            }
          },
          onError: (Object error, StackTrace stackTrace) {
            if (!connack.isCompleted) {
              connack.completeError(error, stackTrace);
            }
            if (!controller.isClosed) {
              controller.addError(error, stackTrace);
            }
          },
          onDone: () {
            if (!connack.isCompleted) {
              connack.completeError(
                StateError('AWS IoT WebSocket closed before MQTT connected.'),
              );
            }
            if (!controller.isClosed) {
              controller.addError('AWS IoT live connection closed.');
            }
          },
        );

        socket!.add(_buildMqttConnectPacket(config.clientId));
        await connack.future.timeout(
          const Duration(seconds: 10),
          onTimeout: () => throw TimeoutException(
            'Timed out waiting for AWS IoT MQTT CONNACK.',
          ),
        );

        socket!.add(_buildMqttSubscribePacket(config.topic, 1));
        pingTimer = Timer.periodic(const Duration(seconds: 20), (_) {
          try {
            socket?.add(const [0xC0, 0x00]);
          } catch (_) {
            // The stream listener will surface the connection failure.
          }
        });
        firstMessageTimer = Timer(const Duration(seconds: 35), () {
          if (!controller.isClosed) {
            controller.addError(
              'Connected to AWS IoT, but no live message arrived yet. '
              'Check that the Pi publisher is publishing to ${config.topic}.',
            );
          }
        });
      } catch (error, stackTrace) {
        if (!controller.isClosed) {
          controller.addError(_friendlyAwsIotError(error), stackTrace);
        }
      }
    }

    controller.onListen = connect;
    controller.onCancel = () async {
      firstMessageTimer?.cancel();
      pingTimer?.cancel();
      await subscription?.cancel();
      await socket?.close();
    };
    return controller.stream;
  }

  List<int> _webSocketEventBytes(dynamic event) {
    if (event is List<int>) {
      return event;
    }
    if (event is String) {
      return utf8.encode(event);
    }
    throw FormatException('Unexpected AWS IoT WebSocket message type.');
  }

  List<int> _buildMqttConnectPacket(String clientId) {
    final variableHeader = <int>[
      ..._encodeMqttString('MQTT'),
      0x04,
      0x02,
      0x00,
      0x1E,
    ];
    final payload = _encodeMqttString(clientId);
    return [
      0x10,
      ..._encodeMqttRemainingLength(variableHeader.length + payload.length),
      ...variableHeader,
      ...payload,
    ];
  }

  List<int> _buildMqttSubscribePacket(String topic, int packetId) {
    final variableHeader = [(packetId >> 8) & 0xFF, packetId & 0xFF];
    final payload = [..._encodeMqttString(topic), 0x00];
    return [
      0x82,
      ..._encodeMqttRemainingLength(variableHeader.length + payload.length),
      ...variableHeader,
      ...payload,
    ];
  }

  List<int> _buildMqttPubackPacket(int packetId) {
    return [0x40, 0x02, (packetId >> 8) & 0xFF, packetId & 0xFF];
  }

  List<int> _encodeMqttString(String value) {
    final bytes = utf8.encode(value);
    if (bytes.length > 65535) {
      throw ArgumentError.value(value, 'value', 'MQTT string is too long.');
    }
    return [(bytes.length >> 8) & 0xFF, bytes.length & 0xFF, ...bytes];
  }

  List<int> _encodeMqttRemainingLength(int length) {
    var value = length;
    final encoded = <int>[];
    do {
      var digit = value % 128;
      value = value ~/ 128;
      if (value > 0) {
        digit |= 0x80;
      }
      encoded.add(digit);
    } while (value > 0);
    return encoded;
  }

  ({int value, int nextIndex}) _decodeMqttRemainingLength(
    List<int> bytes,
    int startIndex,
  ) {
    var multiplier = 1;
    var value = 0;
    var index = startIndex;
    while (index < bytes.length) {
      final digit = bytes[index++];
      value += (digit & 127) * multiplier;
      if ((digit & 128) == 0) {
        return (value: value, nextIndex: index);
      }
      multiplier *= 128;
      if (multiplier > 128 * 128 * 128) {
        break;
      }
    }
    throw const FormatException('Invalid MQTT remaining length.');
  }

  ({String topic, String payload, int? packetId}) _decodeMqttPublishPacket(
    List<int> bytes,
  ) {
    if (bytes.length < 4) {
      throw const FormatException('Invalid MQTT publish packet.');
    }
    final qos = (bytes.first & 0x06) >> 1;
    final remaining = _decodeMqttRemainingLength(bytes, 1);
    var index = remaining.nextIndex;
    final packetEnd = index + remaining.value;
    if (packetEnd > bytes.length || index + 2 > packetEnd) {
      throw const FormatException('Invalid MQTT publish length.');
    }

    final topicLength = (bytes[index] << 8) | bytes[index + 1];
    index += 2;
    if (index + topicLength > packetEnd) {
      throw const FormatException('Invalid MQTT publish topic.');
    }
    final topic = utf8.decode(bytes.sublist(index, index + topicLength));
    index += topicLength;

    int? packetId;
    if (qos > 0) {
      if (index + 2 > packetEnd) {
        throw const FormatException('Invalid MQTT publish packet id.');
      }
      packetId = (bytes[index] << 8) | bytes[index + 1];
      index += 2;
    }

    final payload = utf8.decode(bytes.sublist(index, packetEnd));
    return (topic: topic, payload: payload, packetId: packetId);
  }

  String _friendlyAwsIotError(Object error) {
    final text = error.toString();
    if (text.contains('HTTP status code: 403')) {
      return 'AWS IoT rejected the app credentials (HTTP 403). '
          'Rebuild the app with the latest AWS IoT signer, then sign out and '
          'sign in again so Cognito gets fresh AWS credentials.';
    }
    if (text.contains('was not upgraded to websocket')) {
      return 'AWS IoT WebSocket upgrade failed. Check the Cognito role, IoT '
          'policy, and signed WebSocket URL.';
    }
    return text.replaceFirst('Exception: ', '');
  }

  DashboardData _parseAwsIotLiveDashboard(
    Map<String, dynamic> data, {
    required String homeId,
  }) {
    final room = _asMap(data['room']);
    final energy = _asMap(data['energy']);
    final safety = _asMap(data['safety']);
    final devicesMap = _asMap(data['devices']);
    final devices =
        devicesMap.entries
            .map(
              (entry) => _parseAwsIotLiveDevice(entry.key, _asMap(entry.value)),
            )
            .where(
              (device) =>
                  _isDisplayDevice(device) &&
                  (device.controllable ||
                      device.id.startsWith('breaker_') ||
                      device.id.startsWith('matter_')),
            )
            .toList()
          ..sort(_compareDevices);
    final totalDevicePower = devices.fold<double>(
      0,
      (sum, device) => sum + device.currentPower,
    );
    final voltageValues = devices
        .map((device) => device.voltage)
        .where((value) => value > 0)
        .toList();
    final currentValues = devices
        .map((device) => device.current)
        .where((value) => value > 0)
        .toList();
    final energyToday = _asDouble(
      _pick(energy, [
        'energyToday',
        'energyTodayKwh',
        'todayKwh',
        'today_kwh',
        'totalEnergyKwh',
      ]),
      fallback: devices.fold<double>(
        0,
        (sum, device) => sum + device.energyToday,
      ),
    );
    final parsedAlerts = _dedupeAlerts(
      _asList(data['alerts'])
          .map((alert) => _alertFromBackend(_asString(alert['id']), alert))
          .toList(),
    );
    final parsedSensors = _sensorWithSmokeOverride(
      _parseAwsIotLiveSensor(room),
      safety: safety,
      alerts: parsedAlerts,
    );

    return DashboardData(
      reading: EnergyReading(
        timestamp: _asDateTime(
          _pick(data, ['timestampMs', 'timestampIso']) ??
              _pick(energy, ['timestampMs', 'timestampIso']),
        ),
        voltage: _asDouble(
          _pick(energy, ['voltage', 'voltageV', 'voltage_v']),
          fallback: voltageValues.isEmpty
              ? 0
              : voltageValues.reduce((a, b) => a + b) / voltageValues.length,
        ),
        current: _asDouble(
          _pick(energy, ['current', 'currentA', 'current_a']),
          fallback: currentValues.isEmpty
              ? 0
              : currentValues.reduce((a, b) => a + b) / currentValues.length,
        ),
        power: _asDouble(
          _pick(energy, ['currentPowerW', 'powerW', 'power_w', 'power']),
          fallback: totalDevicePower,
        ),
        energyToday: energyToday,
        energyTotal: _asDouble(
          _pick(energy, ['energyTotal', 'totalEnergyKwh', 'energyTotalKwh']),
          fallback: energyToday,
        ),
        costToday: _asDouble(_pick(energy, ['costToday', 'costTodayBhd'])),
      ),
      sensors: parsedSensors,
      devices: devices,
      alerts: parsedAlerts,
      tariffBhdPerKwh: ElectricityPricing.costPerKWh,
      control: _parseControl(_asMap(data['control'])),
      safety: safety,
      deviceControlEnabled: homeId != 'home_test',
    );
  }

  Device _parseAwsIotLiveDevice(String deviceId, Map<String, dynamic> data) {
    final metering = _asMap(data['metering']);
    final state = _asString(
      _pick(data, ['state', 'displayState']),
    ).toLowerCase();
    final name = _asString(_pick(data, ['name']), fallback: deviceId);
    final rawType = _asString(_pick(data, ['type']));
    final online = _asBool(_pick(data, ['online']), fallback: true);
    final localOnline = _asBool(
      _pick(data, ['localOnline', 'local_online']),
      fallback: online,
    );
    final isOn =
        online &&
        localOnline &&
        (state == 'on' ||
            _asBool(_pick(data, ['switch', 'isOn']), fallback: false));
    return Device(
      id: _asString(
        _pick(data, ['deviceId', 'device_id', 'id']),
        fallback: deviceId,
      ),
      name: name,
      type: _parseApiDeviceType(deviceId, name, rawType),
      isOn: isOn,
      currentPower: online
          ? _asDouble(
              _pick(data, ['powerW', 'power_w', 'power_W', 'currentPower']) ??
                  _pick(metering, ['power_W', 'power_w', 'power']),
            )
          : 0,
      branch: _asString(
        _pick(data, ['branch', 'zone']),
        fallback: _branchFromDeviceId(deviceId),
      ),
      online: online,
      localOnline: localOnline,
      cloudOnline: _asBool(
        _pick(data, ['cloudOnline', 'cloud_online']),
        fallback: true,
      ),
      controllable: _asBool(_pick(data, ['controllable']), fallback: true),
      commandInProgress: _asBool(
        _pick(data, ['commandInProgress', 'command_in_progress']),
      ),
      energySupported: _asBool(
        _pick(data, ['energySupported', 'energy_supported']),
        fallback: true,
      ),
      voltage: _asDouble(
        _pick(data, ['voltageV', 'voltage_v', 'voltage_V', 'voltage']) ??
            _pick(metering, ['voltage_V', 'voltage_v', 'voltage']),
      ),
      current: _asDouble(
        _pick(data, ['currentA', 'current_a', 'current_A', 'current']) ??
            _pick(metering, ['current_A', 'current_a', 'current']),
      ),
      energyToday: _asDouble(
        _pick(data, [
              'energyKwh',
              'energy_kwh',
              'energy_kWh',
              'energyToday',
              'today_kwh',
            ]) ??
            _pick(metering, ['energy_kWh', 'energy_kwh', 'energyToday']),
      ),
      controlMethod: _asNullableString(
        _pick(data, ['controlMethod', 'control_method']),
      ),
      pendingTargetState: _asNullableString(
        _pick(data, ['pendingTargetState', 'pending_target_state']),
      ),
      lastCommandMessage: _asNullableString(
        _pick(data, ['lastCommandMessage', 'last_command_message']),
      ),
    );
  }

  SensorData _parseAwsIotLiveSensor(Map<String, dynamic> room) {
    final timestampValue = _pick(room, [
      'timestampMs',
      'timestamp_ms',
      'timestampIso',
      'timestamp_iso',
      'readable_time',
      'timestamp',
      'updatedAt',
      'updated_at',
    ]);
    final sensorOnline = _asBool(
      _pick(room, [
        'sensorOnline',
        'sensor_online',
        'online',
        'ahtOk',
        'aht_ok',
      ]),
      fallback: timestampValue != null,
    );

    return SensorData(
      timestamp: timestampValue == null
          ? DateTime.fromMillisecondsSinceEpoch(0)
          : _asDateTime(timestampValue),
      temperature: _asDouble(_pick(room, ['temperature'])),
      humidity: _asDouble(_pick(room, ['humidity'])),
      isOccupied: _asBool(_pick(room, ['motion', 'motionText'])),
      eco2: _asDouble(_pick(room, ['eco2'])),
      tvoc: _asDouble(_pick(room, ['tvoc'])),
      aqi: _asInt(_pick(room, ['aqi'])),
      smokeRaw: _asInt(_pick(room, ['smokeRaw'])),
      lightRaw: _asInt(_pick(room, ['lightRaw'])),
      soundRaw: _asInt(_pick(room, ['soundRaw'])),
      noise: _asInt(_pick(room, ['noise'])),
      noiseStatus: _asString(_pick(room, ['noiseText']), fallback: 'Unknown'),
      lightStatus: _asString(_pick(room, ['lightStatus']), fallback: 'Unknown'),
      smokeStatus: _asString(
        _pick(room, ['smokeText']),
        fallback: _asBool(_pick(room, ['smoke'])) ? 'Smoke/Gas' : 'Clear',
      ),
      ahtOk: _asBool(_pick(room, ['ahtOk']), fallback: true),
      ens160Ok: _asBool(_pick(room, ['ens160Ok']), fallback: true),
      online: sensorOnline && !_asBool(_pick(room, ['stale'])),
    );
  }

  SensorData _parseLiveSensorDevice(Map<String, dynamic> raw) {
    final sensors = _asMap(raw['sensors']);
    final status = _asMap(raw['status']);
    final source = {...sensors, ...status};
    final timestampValue =
        _pick(sensors, [
          'timestamp_ms',
          'timestamp_iso',
          'readable_time',
          'timestamp',
        ]) ??
        _pick(status, ['lastSeenMs', 'last_seen_ms', 'readableTime']);

    return SensorData(
      timestamp: timestampValue == null
          ? DateTime.fromMillisecondsSinceEpoch(0)
          : _asDateTime(timestampValue),
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
      online: _asBool(
        _pick(source, ['sensor_online', 'sensorOnline', 'online']),
        fallback: true,
      ),
    );
  }

  Future<DashboardData> fetchDashboardData({
    required String homeId,
    String? scenarioId,
    CancelToken? cancelToken,
  }) async {
    if (usesLocalPiApi && homeId == NetworkConfig.defaultHomeId) {
      final response = await _dio.get('/api/latest', cancelToken: cancelToken);
      final data = _asMap(response.data);
      final dashboard = _asMap(data['dashboard']).isNotEmpty
          ? _asMap(data['dashboard'])
          : data;

      if (dashboard.isEmpty) {
        throw Exception('No local dashboard data found for $homeId.');
      }

      return _parseApiDashboardData(dashboard, homeId: homeId);
    }

    if (scenarioId != null) {
      throw Exception('Demo scenarios are not available in local Pi mode.');
    }

    final response = await _dio.get(
      '/api/home/$homeId/dashboard',
      cancelToken: cancelToken,
    );
    final data = _asMap(response.data);

    if (data.isEmpty) {
      throw Exception('No data found for $homeId.');
    }

    return _parseApiDashboardData(data, homeId: homeId);
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
    final latestRecommendation = recommendations.isEmpty
        ? const <String, dynamic>{}
        : _asMap(recommendations.first);
    final effectiveAi = ai.isNotEmpty
        ? ai
        : _buildFallbackAiDashboard(
            aiDailySummary: aiDailySummary,
            recommendation: latestRecommendation,
            root: data,
          );

    final parsedDevices =
        devicesMap.entries
            .map((entry) => _parseApiDevice(entry.key, _asMap(entry.value)))
            .where(
              (device) =>
                  _isDisplayDevice(device) &&
                  (device.controllable ||
                      device.id.startsWith('breaker_') ||
                      device.id.startsWith('matter_')),
            )
            .toList()
          ..sort(_compareDevices);

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
    final parsedAlerts = _dedupeAlerts(
      alerts
          .map(
            (item) => _alertFromBackend(
              _asString(_pick(item, ['id', 'alert_key', 'alert_id'])),
              item,
            ),
          )
          .toList(),
    );

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
      sensors: _sensorWithSmokeOverride(
        SensorData(
          timestamp:
              (_pick(room, ['sensor_timestamp_ms', 'sensor_timestamp_iso']) ??
                      _pick(data, ['updated_at_ms', 'updated_at_iso'])) ==
                  null
              ? DateTime.fromMillisecondsSinceEpoch(0)
              : _asDateTime(
                  _pick(room, [
                        'sensor_timestamp_ms',
                        'sensor_timestamp_iso',
                      ]) ??
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
          online: _asBool(
            _pick(room, ['sensor_online', 'sensorOnline', 'online']),
            fallback:
                _pick(room, ['sensor_timestamp_ms', 'sensor_timestamp_iso']) !=
                null,
          ),
        ),
        safety: _asMap(data['safety']),
        alerts: parsedAlerts,
      ),
      devices: parsedDevices,
      alerts: parsedAlerts,
      tariffBhdPerKwh: ElectricityPricing.costPerKWh,
      pendingDeviceCommands: pendingCommands,
      deviceCommandErrors: const {},
      aiDashboard: effectiveAi.isEmpty
          ? null
          : _parseApiAiDashboard(effectiveAi, data),
      aiDailySummary: _parseAiDailySummary(aiDailySummary),
      aiRecommendation: latestRecommendation.isEmpty
          ? null
          : _parseAiRecommendation(latestRecommendation),
      aiAlert: null,
      control: _parseControl(_asMap(data['control'])),
      actionSuggestions: actionSuggestions.map(_parseActionSuggestion).toList(),
      automationLogs: automationLogs.map(_parseAutomationLog).toList()
        ..sort((a, b) => b.createdAt.compareTo(a.createdAt)),
      settingsSummary: _asMap(data['settings_summary']),
      occupancy: _asMap(data['occupancy']),
      safety: _asMap(data['safety']),
      criticalAlerts: _asList(
        data['critical_alerts'],
      ).map((item) => _asMap(item)).toList(),
      nextSchedule: _parseOptionalSchedule(_asMap(data['next_schedule'])),
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
    final localOnline = _asBool(
      _pick(data, ['local_online', 'localOnline']),
      fallback: online,
    );
    final energySupported = _asBool(
      _pick(data, ['energy_supported', 'energySupported']),
      fallback: true,
    );
    final visualIsOn =
        online &&
        localOnline &&
        (displayState == 'on' || _asBool(_pick(data, ['is_on', 'switch'])));
    return Device(
      id: _asString(_pick(data, ['device_id', 'id']), fallback: deviceId),
      name: name,
      type: _parseApiDeviceType(deviceId, name, rawType),
      isOn: visualIsOn,
      currentPower: online
          ? _asDouble(
              _pick(data, ['power_w', 'currentPower', 'power_W', 'powerW']),
            )
          : 0.0,
      branch: _asString(
        _pick(data, ['branch', 'zone']),
        fallback: _branchFromDeviceId(deviceId),
      ),
      online: online,
      localOnline: localOnline,
      cloudOnline: _asBool(
        _pick(data, ['cloud_online', 'cloudOnline']),
        fallback: true,
      ),
      controllable: _asBool(_pick(data, ['controllable']), fallback: true),
      commandInProgress: _asBool(_pick(data, ['command_in_progress'])),
      energySupported: energySupported,
      voltage: _asDouble(_pick(data, ['voltage_v', 'voltage_V', 'voltageV'])),
      current: _asDouble(_pick(data, ['current_a', 'current_A', 'currentA'])),
      energyToday: _asDouble(
        _pick(data, ['energy_kwh', 'energy_kWh', 'energyKwh', 'today_kwh']),
      ),
      controlMethod: _asNullableString(
        _pick(data, ['control_method', 'controlMethod']),
      ),
      pendingTargetState: _asNullableString(
        _pick(data, ['pending_target_state']),
      ),
      lastCommandMessage: _asNullableString(
        _pick(lastCommand, ['user_message']) ??
            _pick(data, ['last_command_message']),
      ),
    );
  }

  bool _isDisplayDevice(Device device) {
    final id = device.id.toLowerCase();
    final name = device.name.toLowerCase();
    return !id.startsWith('esp32') &&
        !id.contains('_sensor') &&
        !id.contains('sensor_') &&
        !name.contains('esp32') &&
        !name.contains('sensor receiver');
  }

  DeviceType _parseApiDeviceType(String deviceId, String name, String rawType) {
    if (deviceId == 'breaker_01' || deviceId == 'matter_ac_switch') {
      return DeviceType.airConditioner;
    }
    if (deviceId == 'breaker_02' || deviceId == 'matter_socket_switch') {
      return DeviceType.socket;
    }
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
      source: 'KahrabaIQ API',
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
      statusCode: _asString(_pick(ai, ['ai_status_code']), fallback: status),
      statusLabel: _asString(
        _pick(ai, ['ai_status_label']),
        fallback: _friendlyAiStatus(status),
      ),
      statusTone: _asString(_pick(ai, ['ai_status_tone']), fallback: 'info'),
      statusSummary: _asString(
        _pick(ai, ['ai_status_summary']),
        fallback: 'AI is reviewing current energy use.',
      ),
      actionTitle: _asString(
        _pick(ai, ['ai_action_title']),
        fallback: 'Review insight',
      ),
      nextHourEnergyKwh: _asDouble(
        _pick(ai, ['next_hour_energy_kWh', 'next_hour_energy']),
      ),
      nextHourCostBhd: _asDouble(
        _pick(ai, ['next_hour_cost_BHD', 'next_hour_cost']),
      ),
      efficiencyScore: _asDouble(_pick(ai, ['efficiency_score'])),
      explanation: _asString(
        _pick(ai, ['explanation', 'summary']),
        fallback: 'AI analysis is not available yet.',
      ),
      controlSuggestion: _asString(_pick(ai, ['recommended_action'])),
    );
  }

  Future<DashboardData> _fetchDashboardDataFromLegacyStore({
    required String homeId,
    String? scenarioId,
    CancelToken? cancelToken,
  }) async {
    throw Exception('Legacy realtime database fallback is disabled.');
  }

  Future<List<DemoScenario>> fetchDemoScenarios({
    CancelToken? cancelToken,
  }) async {
    return const <DemoScenario>[];
  }

  Future<List<ControlModeOption>> fetchControlModes({
    required String homeId,
    CancelToken? cancelToken,
  }) async {
    if (usesLocalPiApi) {
      return const [
        ControlModeOption(
          mode: 'assist',
          label: 'Assist',
          description:
              'The system suggests actions and asks before controlling devices.',
        ),
        ControlModeOption(
          mode: 'auto',
          label: 'Auto',
          description: 'The Pi can run approved local automation rules.',
        ),
        ControlModeOption(
          mode: 'manual',
          label: 'Manual',
          description: 'The system only shows data; users control devices.',
        ),
      ];
    }

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

  Future<HomeSettings> fetchSettings({
    required String homeId,
    CancelToken? cancelToken,
  }) async {
    if (usesLocalPiApi) {
      final response = await _dio.get(
        '/api/settings',
        cancelToken: cancelToken,
      );
      return HomeSettings(_asMap(_asMap(response.data)['settings']));
    }

    final response = await _dio.get(
      '/api/home/$homeId/settings',
      cancelToken: cancelToken,
    );
    return HomeSettings(_asMap(_asMap(response.data)['settings']));
  }

  Future<HomeSettings> updateSettings({
    required String homeId,
    required Map<String, dynamic> values,
  }) async {
    if (usesLocalPiApi) {
      final response = await _dio.put('/api/settings', data: values);
      return HomeSettings(_asMap(_asMap(response.data)['settings']));
    }

    final response = await _dio.put('/api/home/$homeId/settings', data: values);
    return HomeSettings(_asMap(_asMap(response.data)['settings']));
  }

  Future<List<ScheduleInfo>> fetchSchedules({
    required String homeId,
    CancelToken? cancelToken,
  }) async {
    if (usesLocalPiApi) {
      final response = await _dio.get(
        '/api/schedules',
        cancelToken: cancelToken,
      );
      return _asList(
        _asMap(response.data)['schedules'],
      ).map(_parseSchedule).toList();
    }

    final response = await _dio.get(
      '/api/home/$homeId/schedules',
      cancelToken: cancelToken,
    );
    return _asList(
      _asMap(response.data)['schedules'],
    ).map(_parseSchedule).toList();
  }

  Future<ScheduleInfo> createSchedule({
    required String homeId,
    required Map<String, dynamic> values,
  }) async {
    if (usesLocalPiApi) {
      final response = await _dio.post('/api/schedules', data: values);
      return _parseSchedule(_asMap(_asMap(response.data)['schedule']));
    }

    final response = await _dio.post(
      '/api/home/$homeId/schedules',
      data: values,
    );
    return _parseSchedule(_asMap(_asMap(response.data)['schedule']));
  }

  Future<ScheduleInfo> updateScheduleEnabled({
    required String homeId,
    required String scheduleId,
    required bool enabled,
  }) async {
    if (usesLocalPiApi) {
      final response = await _dio.patch(
        '/api/schedules/$scheduleId/enabled',
        data: {'enabled': enabled, 'updated_by': 'flutter_app'},
      );
      return _parseSchedule(_asMap(_asMap(response.data)['schedule']));
    }

    final response = await _dio.patch(
      '/api/home/$homeId/schedules/$scheduleId/enabled',
      data: {'enabled': enabled, 'updated_by': 'flutter_app'},
    );
    return _parseSchedule(_asMap(_asMap(response.data)['schedule']));
  }

  Future<void> deleteSchedule({
    required String homeId,
    required String scheduleId,
  }) async {
    if (usesLocalPiApi) {
      await _dio.delete(
        '/api/schedules/$scheduleId',
        queryParameters: {'deleted_by': 'flutter_app'},
      );
      return;
    }

    await _dio.delete(
      '/api/home/$homeId/schedules/$scheduleId',
      queryParameters: {'deleted_by': 'flutter_app'},
    );
  }

  Future<String> runScheduleNow({
    required String homeId,
    required String scheduleId,
  }) async {
    if (usesLocalPiApi) {
      final response = await _dio.post('/api/schedules/$scheduleId/run-now');
      final data = _asMap(response.data);
      final log = _asMap(data['log']);
      return _asString(
        _pick(log, ['message']) ?? _pick(data, ['message']),
        fallback: 'Schedule run requested.',
      );
    }

    final response = await _dio.post(
      '/api/home/$homeId/schedules/$scheduleId/run-now',
    );
    final data = _asMap(response.data);
    final log = _asMap(data['log']);
    return _asString(
      _pick(log, ['message']) ?? _pick(data, ['message']),
      fallback: 'Schedule run requested.',
    );
  }

  Future<List<HomeMember>> fetchMembers({required String homeId}) async {
    final response = await _dio.get('/api/home/$homeId/members');
    return _asList(_asMap(response.data)['members']).map(_parseMember).toList();
  }

  Future<void> addMember({
    required String homeId,
    required String email,
    required String role,
  }) async {
    await _dio.post(
      '/api/home/$homeId/members',
      data: {'email': email, 'role': role},
    );
  }

  Future<void> updateMemberRole({
    required String homeId,
    required String uid,
    required String role,
  }) async {
    await _dio.put('/api/home/$homeId/members/$uid/role', data: {'role': role});
  }

  Future<void> removeMember({
    required String homeId,
    required String uid,
  }) async {
    await _dio.delete('/api/home/$homeId/members/$uid');
  }

  Future<Map<String, dynamic>> claimPi({
    required String piId,
    required String token,
    String? homeName,
  }) async {
    final response = await _dio.post(
      '/api/pairing/claim-pi',
      data: {
        'pi_id': piId,
        'token': token,
        if (homeName != null && homeName.trim().isNotEmpty)
          'home_name': homeName.trim(),
      },
    );
    return _asMap(response.data);
  }

  Future<HomeInvite> createHomeInvite({
    required String homeId,
    String role = 'member',
  }) async {
    final response = await _dio.post(
      '/api/home/$homeId/invites',
      data: {'role': role, 'max_uses': 1},
    );
    final data = _asMap(response.data);
    return HomeInvite(
      inviteId: _asString(data['invite_id']),
      token: _asString(data['token']),
      qrPayload: _asString(data['qr_payload']),
      expiresAtMs: _asInt(data['expires_at_ms']),
    );
  }

  Future<Map<String, dynamic>> claimHomeInvite({
    required String inviteId,
    required String token,
  }) async {
    final response = await _dio.post(
      '/api/home-invites/claim',
      data: {'invite_id': inviteId, 'token': token},
    );
    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> fetchPlatformAdminSummary() async {
    final responses = await Future.wait([
      _dio.get('/api/admin/users'),
      _dio.get('/api/admin/homes'),
      _dio.get('/api/admin/pis'),
    ]);
    return {
      'users': _asList(_asMap(responses[0].data)['users']),
      'homes': _asList(_asMap(responses[1].data)['homes']),
      'pis': _asList(_asMap(responses[2].data)['pis']),
    };
  }

  Future<Map<String, dynamic>> turnOffSafeDevices({
    required String homeId,
  }) async {
    if (usesLocalPiApi) {
      final response = await _dio.post(
        '/api/safety/smoke/actions/turn-off-safe-devices',
      );
      return _asMap(response.data);
    }

    final response = await _dio.post(
      '/api/home/$homeId/safety/smoke/actions/turn-off-safe-devices',
    );
    return _asMap(response.data);
  }

  Future<Map<String, dynamic>> markSmokeSafe({required String homeId}) async {
    if (usesLocalPiApi) {
      final response = await _dio.post('/api/safety/smoke/actions/mark-safe');
      return _asMap(response.data);
    }

    final response = await _dio.post(
      '/api/home/$homeId/safety/smoke/actions/mark-safe',
    );
    return _asMap(response.data);
  }

  Future<void> registerNotificationToken({
    required String homeId,
    required String token,
    String userId = 'user_001',
    String platform = 'android',
    String? installationId,
  }) async {
    if (usesLocalPiApi) {
      return;
    }

    await _dio.post(
      '/api/home/$homeId/notifications/register-token',
      data: {
        'user_id': userId,
        'token': token,
        'platform': platform,
        if (installationId != null) ...{'installation_id': installationId},
      },
    );
  }

  Future<List<AppNotification>> fetchNotifications({
    required String homeId,
    int limit = 50,
    bool unreadOnly = false,
    CancelToken? cancelToken,
  }) async {
    if (usesLocalPiApi) {
      return const [];
    }

    final response = await _dio.get(
      '/api/users/me/notifications',
      queryParameters: {'limit': limit, 'unread_only': unreadOnly},
      cancelToken: cancelToken,
    );
    final data = _asMap(response.data);
    return _asList(data['notifications'])
        .map((item) => AppNotification.fromJson(_asMap(item)))
        .where((item) => item.id.isNotEmpty)
        .toList();
  }

  Future<void> markNotificationRead({
    required String homeId,
    required String notificationId,
  }) async {
    if (usesLocalPiApi) {
      return;
    }

    await _dio.post('/api/users/me/notifications/$notificationId/read');
  }

  Future<void> markAllNotificationsRead() async {
    if (usesLocalPiApi) {
      return;
    }

    await _dio.post('/api/users/me/notifications/read-all');
  }

  Future<String> updateControlMode({
    required String homeId,
    required String mode,
    required String updatedBy,
  }) async {
    if (usesLocalPiApi) {
      final response = await _dio.put(
        '/api/control/mode',
        data: {'mode': mode, 'updated_by': updatedBy},
      );
      final data = _asMap(response.data);
      return _asString(
        _pick(data, ['message']),
        fallback: 'Control mode changed to ${_prettyMode(mode)} Mode.',
      );
    }

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
    final encodedSuggestionId = Uri.encodeComponent(suggestionId);
    if (usesLocalPiApi) {
      final response = await _dio.post(
        '/api/action-suggestions/$encodedSuggestionId/approve',
      );
      final data = _asMap(response.data);
      return _asString(
        _pick(data, ['message']),
        fallback: 'Action suggestion approved.',
      );
    }

    final response = await _dio.post(
      '/api/home/$homeId/action-suggestions/$encodedSuggestionId/approve',
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
    final encodedSuggestionId = Uri.encodeComponent(suggestionId);
    try {
      if (usesLocalPiApi) {
        final response = await _dio.post(
          '/api/action-suggestions/$encodedSuggestionId/dismiss',
        );
        final data = _asMap(response.data);
        return _asString(
          _pick(data, ['message']),
          fallback: 'Action suggestion dismissed.',
        );
      }

      final response = await _dio.post(
        '/api/home/$homeId/action-suggestions/$encodedSuggestionId/dismiss',
      );
      final data = _asMap(response.data);
      return _asString(
        _pick(data, ['message']),
        fallback: 'Action suggestion dismissed.',
      );
    } catch (_) {
      await _dismissActionSuggestionInLegacyStore(
        homeId: homeId,
        suggestionId: suggestionId,
      );
      return 'Action suggestion dismissed.';
    }
  }

  Future<void> _dismissActionSuggestionInLegacyStore({
    required String homeId,
    required String suggestionId,
  }) async {
    throw Exception('Legacy realtime database fallback is disabled.');
  }

  Future<DeviceCommandResult> sendDeviceCommand(
    String deviceId,
    String action, {
    required String homeId,
    bool emergency = false,
  }) async {
    if (homeId != NetworkConfig.defaultHomeId) {
      throw ArgumentError.value(
        homeId,
        'homeId',
        'Device control is only enabled for the real home',
      );
    }

    if (!_isCommandEnabledDeviceId(deviceId)) {
      throw ArgumentError.value(deviceId, 'deviceId', 'Unsupported device ID');
    }

    if (action != 'turn_on' && action != 'turn_off') {
      throw ArgumentError.value(action, 'action', 'Unsupported command action');
    }

    try {
      if (NetworkConfig.remoteLiveOnly && NetworkConfig.useAwsIotLive) {
        return _sendCloudDeviceCommand(
          deviceId,
          action,
          homeId: homeId,
          emergency: emergency,
        );
      }

      if (usesLocalPiApi) {
        final response = await _dio.post(
          '/api/command',
          data: {
            'device_id': deviceId,
            'action': action,
            if (emergency) 'emergency': true,
          },
        );
        final data = _asMap(response.data);
        return DeviceCommandResult(
          success: _asBool(_pick(data, ['success']), fallback: true),
          noAction: _asBool(_pick(data, ['no_action'])),
          status: _asString(_pick(data, ['status'])),
          message: _asString(_pick(data, ['message'])),
          commandId: _asNullableString(_pick(data, ['command_id'])),
        );
      }

      final response = await _dio.post(
        '/api/home/$homeId/devices/$deviceId/command',
        data: {
          'command': action,
          'requested_by': emergency ? 'user_emergency_action' : 'flutter_app',
          if (emergency) ...{
            'source': 'smoke_emergency',
            'emergency': true,
            'alert_id': 'smoke_detected_room1',
            'reason': 'User emergency action from smoke/gas popup.',
          },
        },
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

      if (usesLocalPiApi) {
        if (NetworkConfig.useAwsIotLive) {
          return _sendCloudDeviceCommand(
            deviceId,
            action,
            homeId: homeId,
            emergency: emergency,
          );
        }
        throw Exception('Local Pi API command failed.');
      }

      if (deviceId.startsWith('matter_')) {
        throw Exception('Local controller command requires the backend API.');
      }

      throw Exception('Backend API command failed.');
    }
  }

  Future<DeviceCommandResult> _sendCloudDeviceCommand(
    String deviceId,
    String action, {
    required String homeId,
    bool emergency = false,
  }) async {
    try {
      final response = await _dio.post(
        '/api/home/$homeId/cloud/commands',
        data: {
          'device_id': deviceId,
          'command': action,
          'requested_by': emergency ? 'user_emergency_action' : 'flutter_app',
          'source': emergency ? 'smoke_emergency' : 'flutter_app',
          'emergency': emergency,
          if (emergency) 'alert_id': 'smoke_detected_room1',
          if (emergency)
            'reason': 'User emergency action from smoke/gas popup.',
        },
      );
      final data = _asMap(response.data);
      return DeviceCommandResult(
        success: _asBool(_pick(data, ['success']), fallback: true),
        noAction: false,
        status: _asString(_pick(data, ['status']), fallback: 'pending'),
        message: _asString(
          _pick(data, ['message']),
          fallback: 'Command queued for the Raspberry Pi.',
        ),
        commandId: _asNullableString(_pick(data, ['command_id', 'commandId'])),
      );
    } catch (error) {
      if (error is DioException && error.response != null) {
        final body = error.response?.data;
        throw Exception(
          'Cloud command queue failed (${error.response?.statusCode}): $body',
        );
      }
      throw Exception('Cloud command queue failed: $error');
    }
  }

  Stream<DeviceCommandState> watchLatestCommandStatus(String deviceId) {
    return watchLatestCommandStatusForHome(
      NetworkConfig.defaultHomeId,
      deviceId,
    );
  }

  Stream<DeviceCommandState> watchLatestCommandStatusForHome(
    String homeId,
    String deviceId,
  ) {
    return const Stream<DeviceCommandState>.empty();
  }

  Stream<bool?> watchDeviceSwitchStatus(String deviceId) {
    return watchDeviceSwitchStatusForHome(
      NetworkConfig.defaultHomeId,
      deviceId,
    );
  }

  Stream<bool?> watchDeviceSwitchStatusForHome(String homeId, String deviceId) {
    return const Stream<bool?>.empty();
  }

  Stream<Device> watchDeviceForHome(String homeId, String deviceId) {
    return const Stream<Device>.empty();
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
    final online = _asBool(
      _pick(status, ['online']) ?? _pick(data, ['online']),
      fallback: true,
    );
    final localOnline = _asBool(
      _pick(data, ['local_online', 'localOnline']),
      fallback: online,
    );
    final energySupported = _asBool(
      _pick(data, ['energy_supported', 'energySupported']),
      fallback: true,
    );
    final visualIsOn =
        online && localOnline && (pendingSwitchState ?? actualSwitchState);
    final rawPower = _asDouble(
      _pick(data, ['currentPower', 'power', 'wattage']) ??
          _pick(metering, ['power_W', 'power_w', 'power']),
    );

    return Device(
      id: (_pick(data, ['id']) ?? deviceId).toString(),
      name: name,
      type: _parseApiDeviceType(deviceId, name, rawType ?? ''),
      isOn: visualIsOn,
      currentPower: online ? rawPower : 0.0,
      branch:
          _pick(data, ['branch', 'zone'])?.toString() ??
          _branchFromDeviceId(deviceId),
      online: online,
      localOnline: localOnline,
      cloudOnline: _asBool(
        _pick(data, ['cloud_online', 'cloudOnline']),
        fallback: true,
      ),
      controllable: _asBool(_pick(data, ['controllable']), fallback: true),
      commandInProgress: commandInProgress,
      energySupported: energySupported,
      voltage: _asDouble(_pick(metering, ['voltage_V', 'voltage'])),
      current: _asDouble(_pick(metering, ['current_A', 'current'])),
      energyToday: _asDouble(_pick(metering, ['energy_kWh', 'energy_kwh'])),
      controlMethod: _asNullableString(
        _pick(data, ['control_method', 'controlMethod']),
      ),
      pendingTargetState: pendingTargetState,
      lastCommandMessage: _asNullableString(
        _pick(data, ['last_command_message']),
      ),
    );
  }

  Map<String, dynamic> _buildFallbackAiDashboard({
    required Map<String, dynamic> aiDailySummary,
    required Map<String, dynamic> recommendation,
    required Map<String, dynamic> root,
  }) {
    if (aiDailySummary.isEmpty && recommendation.isEmpty) {
      return const {};
    }

    final recommendationType = _asString(
      _pick(recommendation, ['recommendation_type', 'recommendationType']),
    );
    final recommendationPriority = _asString(
      _pick(recommendation, ['priority']),
      fallback: 'low',
    ).toLowerCase();
    final hasActiveRecommendation =
        recommendation.isNotEmpty &&
        _asString(
              _pick(recommendation, ['status']),
              fallback: 'active',
            ).toLowerCase() ==
            'active';
    final needsData =
        recommendationType.contains('check_') ||
        _asString(_pick(recommendation, ['type'])).toLowerCase() ==
            'device_health';
    final possibleWaste =
        hasActiveRecommendation &&
        !needsData &&
        (recommendationPriority == 'high' ||
            recommendationPriority == 'medium' ||
            recommendationType.contains('turn_off') ||
            recommendationType.contains('energy'));
    final statusCode = needsData
        ? 'needs_data'
        : possibleWaste
        ? 'possible_waste'
        : 'watching';
    final statusLabel = _friendlyAiStatus(statusCode);
    final statusTone = needsData
        ? 'warning'
        : possibleWaste
        ? 'warning'
        : 'info';
    final message = _asString(
      _pick(recommendation, ['message']),
      fallback: _asString(
        _pick(aiDailySummary, ['latest_explanation', 'summary']),
        fallback: 'AI is reviewing current energy use.',
      ),
    );

    return {
      'updated_at':
          _pick(recommendation, ['updated_at_ms', 'updated_at_iso']) ??
          _pick(aiDailySummary, ['updated_at_ms', 'updated_at_iso']) ??
          _pick(root, ['updated_at_ms', 'updated_at_iso']),
      'source': 'KahrabaIQ Intelligence',
      'prediction_status': statusCode,
      'ai_status_code': statusCode,
      'ai_status_label': statusLabel,
      'ai_status_tone': statusTone,
      'ai_status_summary': needsData
          ? 'AI needs fresh data before judging waste.'
          : possibleWaste
          ? 'AI found a possible energy-saving opportunity.'
          : 'AI is monitoring recent energy patterns.',
      'ai_action_title': needsData
          ? 'Check data'
          : possibleWaste
          ? 'Review action'
          : 'Keep monitoring',
      'energy_waste': possibleWaste,
      'waste_confidence': possibleWaste ? 0.65 : 0.0,
      'abnormal_usage': possibleWaste || needsData,
      'abnormal_usage_confidence': possibleWaste || needsData ? 0.65 : 0.0,
      'recommendation_type': recommendationType.isEmpty
          ? 'none'
          : recommendationType,
      'next_hour_energy_kWh': _pick(aiDailySummary, [
        'predicted_next_hour_energy_total_kWh',
        'predicted_next_hour_energy_total_kwh',
      ]),
      'next_hour_cost_BHD': _pick(aiDailySummary, [
        'predicted_next_hour_cost_total_BHD',
        'predicted_next_hour_cost_total_bhd',
      ]),
      'efficiency_score': _pick(aiDailySummary, [
        'average_efficiency_score',
        'averageEfficiencyScore',
      ]),
      'explanation': message,
    };
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

  String _friendlyAiStatus(String value) {
    switch (value.toLowerCase()) {
      case 'normal':
      case 'normal_low_power':
        return 'Normal';
      case 'needs_data':
      case 'needs_fresh_sensor_data':
      case 'needs_fresh_breaker_data':
      case 'insufficient_data':
        return 'Needs Data';
      case 'likely_waste':
        return 'Likely Waste';
      case 'possible_waste':
        return 'Possible Waste';
      default:
        return 'Watching';
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

  ScheduleInfo? _parseOptionalSchedule(Map<String, dynamic> data) {
    if (data.isEmpty) {
      return null;
    }
    return _parseSchedule(data);
  }

  ScheduleInfo _parseSchedule(Map<String, dynamic> data) {
    return ScheduleInfo(
      id: _asString(_pick(data, ['schedule_id', 'id'])),
      name: _asString(_pick(data, ['name']), fallback: 'Device schedule'),
      deviceId: _asString(_pick(data, ['device_id'])),
      deviceName: _asString(_pick(data, ['device_name']), fallback: 'Device'),
      command: _asString(_pick(data, ['command']), fallback: 'turn_off'),
      time: _asString(_pick(data, ['time']), fallback: '23:30'),
      days: _asListOfStrings(_pick(data, ['days'])),
      enabled: _asBool(_pick(data, ['enabled']), fallback: true),
      nextRunAt: _parseOptionalDateTime(
        _pick(data, ['next_run_at_ms', 'next_run_at_iso']),
      ),
    );
  }

  HomeMember _parseMember(Map<String, dynamic> data) {
    return HomeMember(
      uid: _asString(_pick(data, ['uid', 'id'])),
      email: _asString(_pick(data, ['email'])),
      displayName: _asString(
        _pick(data, ['display_name', 'displayName']),
        fallback: 'User',
      ),
      role: _asString(_pick(data, ['role']), fallback: 'viewer'),
    );
  }

  AiDashboardSummary? _parseAiDashboard(Map<String, dynamic> data) {
    if (data.isEmpty) {
      return null;
    }

    return AiDashboardSummary(
      updatedAt: _asDateTime(_pick(data, ['updated_at', 'updatedAt'])),
      source: _asString(
        _pick(data, ['source']),
        fallback: 'KahrabaIQ Intelligence',
      ),
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
      statusCode: _asString(
        _pick(data, ['ai_status_code', 'status_code', 'statusCode']),
        fallback: _asString(
          _pick(data, ['prediction_status']),
          fallback: 'watching',
        ),
      ),
      statusLabel: _asString(
        _pick(data, ['ai_status_label', 'status_label', 'statusLabel']),
        fallback: _friendlyAiStatus(
          _asString(_pick(data, ['prediction_status']), fallback: 'watching'),
        ),
      ),
      statusTone: _asString(
        _pick(data, ['ai_status_tone', 'status_tone', 'statusTone']),
        fallback: 'info',
      ),
      statusSummary: _asString(
        _pick(data, ['ai_status_summary', 'status_summary', 'statusSummary']),
        fallback: 'AI is reviewing current energy use.',
      ),
      actionTitle: _asString(
        _pick(data, ['ai_action_title', 'action_title', 'actionTitle']),
        fallback: 'Review insight',
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
      source: _asString(
        _pick(data, ['source']),
        fallback: 'KahrabaIQ Intelligence',
      ),
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
        fallback: 'KahrabaIQ Intelligence insight',
      ),
      message: _asString(_pick(data, ['message'])),
      source: _asString(
        _pick(data, ['source']),
        fallback: 'KahrabaIQ Intelligence',
      ),
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
        fallback: 'KahrabaIQ Intelligence detected unusual energy behavior.',
      ),
      source: _asString(
        _pick(data, ['source']),
        fallback: 'KahrabaIQ Intelligence',
      ),
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
    final timestampValue = _pick(source, [
      'readable_time',
      'sensorTimestamp',
      'timestamp',
      'timestamp_ms',
      'updatedAt',
      'updated_at',
      'last_processed_at',
    ]);

    return SensorData(
      timestamp: timestampValue == null
          ? DateTime.fromMillisecondsSinceEpoch(0)
          : _asDateTime(timestampValue),
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
      online: _asBool(
        _pick(source, ['sensor_online', 'sensorOnline', 'online']),
        fallback: timestampValue != null,
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
      final online = _asBool(
        _pick(status, ['online']) ?? _pick(data, ['online']),
        fallback: true,
      );
      final localOnline = _asBool(
        _pick(data, ['local_online', 'localOnline']),
        fallback: online,
      );
      final energySupported = _asBool(
        _pick(data, ['energy_supported', 'energySupported']),
        fallback: true,
      );
      final visualIsOn =
          online && localOnline && (desiredSwitchState ?? actualSwitchState);

      devices.add(
        Device(
          id: (_pick(data, ['id']) ?? entry.key).toString(),
          name:
              _pick(data, ['name', 'label', 'deviceName'])?.toString() ??
              entry.key,
          type: _parseApiDeviceType(
            entry.key,
            _pick(data, ['name', 'label', 'deviceName'])?.toString() ??
                entry.key,
            rawType ?? '',
          ),
          isOn: visualIsOn,
          currentPower: online ? currentPower : 0.0,
          branch:
              _pick(data, ['branch', 'zone'])?.toString() ??
              _branchFromDeviceId(entry.key),
          online: online,
          localOnline: localOnline,
          cloudOnline: _asBool(
            _pick(data, ['cloud_online', 'cloudOnline']),
            fallback: true,
          ),
          controllable: _asBool(_pick(data, ['controllable']), fallback: true),
          commandInProgress: commandInProgress,
          energySupported: energySupported,
          voltage: _asDouble(
            _pick(data, ['voltage_v', 'voltage_V']) ??
                _pick(metering, ['voltage_V', 'voltage']),
          ),
          current: _asDouble(
            _pick(data, ['current_a', 'current_A']) ??
                _pick(metering, ['current_A', 'current']),
          ),
          energyToday: _asDouble(
            _pick(data, ['energy_kwh', 'energy_kWh', 'today_kwh']) ??
                _pick(metering, ['energy_kWh', 'energy_kwh']),
          ),
          controlMethod: _asNullableString(
            _pick(data, ['control_method', 'controlMethod']),
          ),
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
        normalizedType == 'matter_switch' ||
        deviceId.toLowerCase().startsWith('breaker_') ||
        deviceId.toLowerCase().startsWith('matter_');
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

  int _compareDevices(Device left, Device right) {
    final leftRank = _deviceSortRank(left.id);
    final rightRank = _deviceSortRank(right.id);
    if (leftRank != rightRank) {
      return leftRank.compareTo(rightRank);
    }
    return left.name.toLowerCase().compareTo(right.name.toLowerCase());
  }

  int _deviceSortRank(String deviceId) {
    switch (deviceId) {
      case 'matter_socket_switch':
        return 10;
      case 'matter_ac_switch':
        return 20;
      case 'breaker_01':
        return 30;
      case 'breaker_02':
        return 40;
      default:
        return 100;
    }
  }

  bool _isCommandEnabledDeviceId(String deviceId) {
    return deviceId == 'breaker_01' ||
        deviceId == 'breaker_02' ||
        deviceId == 'matter_socket_switch' ||
        deviceId == 'matter_ac_switch';
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

  List<String> _asListOfStrings(dynamic value) {
    if (value is List) {
      return value.map((item) => item.toString()).toList();
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
      if (normalized == 'true' ||
          normalized == '1' ||
          normalized == 'on' ||
          normalized == 'yes' ||
          normalized == 'detected' ||
          normalized == 'smoke' ||
          normalized == 'gas' ||
          normalized.contains('detected')) {
        return true;
      }
      if (normalized == 'false' ||
          normalized == '0' ||
          normalized == 'off' ||
          normalized == 'no' ||
          normalized == 'clear' ||
          normalized.contains('no smoke') ||
          normalized.contains('no gas')) {
        return false;
      }
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
      final normalized = text.toLowerCase();
      if (normalized.contains('clear') ||
          normalized.contains('no smoke') ||
          normalized.contains('no gas')) {
        return 'Clear';
      }
      if (normalized.contains('detect') ||
          normalized.contains('smoke') ||
          normalized.contains('gas') ||
          normalized.contains('alert')) {
        return 'Detected';
      }
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

  bool _isSmokeAlert(Alert alert) {
    final id = alert.id.toLowerCase();
    final type = alert.backendType.toLowerCase();
    final message = alert.message.toLowerCase();
    return alert.isActive &&
        (id == 'smoke_detected_room1' ||
            type.contains('smoke') ||
            type.contains('gas') ||
            message.contains('smoke') ||
            message.contains('gas'));
  }

  SensorData _sensorWithSmokeOverride(
    SensorData sensors, {
    required Map<String, dynamic> safety,
    required List<Alert> alerts,
  }) {
    final smokeState = _asMap(safety['smoke_state']);
    final emergency = _asMap(safety['emergency_mode']);
    final smokeStatus = _asString(_pick(smokeState, ['status'])).toLowerCase();
    final emergencyReason = _asString(
      _pick(emergency, ['reason']),
    ).toLowerCase();
    final smokeActive =
        alerts.any(_isSmokeAlert) ||
        smokeStatus == 'confirmed' ||
        smokeStatus == 'pending' ||
        (_asBool(_pick(emergency, ['active'])) &&
            (emergencyReason.contains('smoke') ||
                emergencyReason.contains('gas')));

    if (!smokeActive) {
      return sensors;
    }

    return sensors.copyWith(
      smokeStatus: 'Detected',
      smokeRaw: sensors.smokeRaw > 0 ? sensors.smokeRaw : 1,
      online: true,
    );
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
    final alertId = _asString(
      _pick(data, ['alert_id', 'id', 'alertId', 'alert_key']),
      fallback: id,
    );
    final alertType = _asString(
      _pick(data, ['alert_type', 'category', 'type']),
      fallback: 'sensorfailure',
    );
    final isSmokeAlert =
        alertId == 'smoke_detected_room1' ||
        alertType.toLowerCase().contains('smoke') ||
        alertType.toLowerCase().contains('gas');
    final payload = <String, dynamic>{
      ...data,
      'id': alertId,
      'alert_id': alertId,
      'severity':
          _pick(data, ['severity', 'level']) ??
          (isSmokeAlert ? 'critical' : 'medium'),
      'timestamp': _pick(data, [
        'created_at_ms',
        'created_at_iso',
        'createdAt',
        'created_at',
        'first_detected_at_ms',
        'started_at_ms',
        'timestamp_ms',
        'timestamp',
        'updated_at_ms',
      ]),
      'isActive': _pick(data, ['isActive', 'active']) ?? true,
      'type': alertType,
      'alert_type': alertType,
      'message':
          _pick(data, ['message', 'body', 'title']) ??
          (isSmokeAlert
              ? 'Smoke or gas was detected in Room 1. Check immediately.'
              : 'System alert'),
    };

    return Alert.fromJson(payload);
  }

  List<Alert> _dedupeAlerts(List<Alert> alerts) {
    final byId = <String, Alert>{};
    for (final alert in alerts) {
      if (!_isMeaningfulAlert(alert)) {
        continue;
      }
      final key = _alertDedupeKey(alert);
      final existing = byId[key];
      if (existing == null ||
          existing.message == 'System alert' &&
              alert.message != 'System alert') {
        byId[key] = alert;
      }
    }
    final result = byId.values.toList()
      ..sort((a, b) => b.timestamp.compareTo(a.timestamp));
    return result;
  }

  String _alertDedupeKey(Alert alert) {
    if (_isSmokeAlert(alert)) {
      return 'smoke_detected_room1';
    }
    if (alert.id.isNotEmpty) {
      return alert.id;
    }
    final message = alert.message.toLowerCase().trim();
    return '${alert.backendType.toLowerCase()}_$message';
  }

  bool _isMeaningfulAlert(Alert alert) {
    if (_isSmokeAlert(alert)) {
      return true;
    }
    final message = alert.message.trim().toLowerCase();
    final type = alert.backendType.trim().toLowerCase();
    if (message.isEmpty || message == 'system alert') {
      return type.isNotEmpty &&
          type != 'sensorfailure' &&
          type != 'sensor_failure';
    }
    return true;
  }
}
