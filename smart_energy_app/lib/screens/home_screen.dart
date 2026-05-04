import 'dart:async';

import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:intl/intl.dart';
import '../utils/constants.dart';
import '../models/alert.dart';
import '../models/ai_insights.dart';
import '../models/device.dart';
import '../models/energy_reading.dart';
import '../models/sensor_data.dart';
import '../screens/ai_chatbot_screen.dart';
import '../screens/sensors_status_screen.dart';
import '../services/firebase_realtime_service.dart';
import '../widgets/metric_card.dart';
import '../widgets/device_card.dart';

class _HomeChoice {
  const _HomeChoice({
    required this.id,
    required this.label,
    required this.badge,
    required this.description,
    required this.isDemo,
  });

  final String id;
  final String label;
  final String badge;
  final String description;
  final bool isDemo;
}

class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.enableRealtimeSync = true});

  final bool enableRealtimeSync;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static const int _alertDedupCooldownMs = 5 * 60 * 1000;
  static const int _historicalAlertMaxAgeMs = 10 * 60 * 1000;
  static const int _sensorFeedStaleThresholdMs = 2 * 60 * 1000;

  final FirebaseRealtimeService _firebaseRealtimeService =
      FirebaseRealtimeService();

  late EnergyReading _currentReading;
  late SensorData _sensorData;
  late List<Device> _devices;
  String _selectedHomeId = NetworkConfig.firebaseHomeId;
  String? _selectedScenarioId;
  String? _activeScenarioName;
  String? _activeScenarioDescription;
  bool _deviceControlEnabled = true;
  bool _hasLiveData = false;
  List<DemoScenario> _demoScenarios = const [];
  AiDashboardSummary? _aiDashboard;
  AiDailySummary? _aiDailySummary;
  AiRecommendation? _aiRecommendation;
  AiAlertInsight? _aiAlert;
  ControlModeInfo _controlMode = const ControlModeInfo(
    mode: 'assist',
    label: 'Assist',
    description:
        'The system suggests actions and asks before controlling devices.',
  );
  List<ActionSuggestion> _actionSuggestions = const [];
  List<AutomationLog> _automationLogs = const [];
  Map<String, dynamic> _settingsSummary = const {};
  Map<String, dynamic> _occupancy = const {};
  Map<String, dynamic> _safety = const {};
  List<Map<String, dynamic>> _criticalAlerts = const [];
  String? _shownEmergencyAlertId;
  bool _smokeEmergencyDialogOpen = false;
  int? _smokeClearStartedAtMs;
  ScheduleInfo? _nextSchedule;
  bool _isUpdatingControlMode = false;
  final List<Alert> _alerts = [];
  final Set<String> _seenAlertIds = <String>{};
  final Map<String, int> _lastShownAlertBySignature = <String, int>{};
  final Set<String> _pendingDeviceCommands = <String>{};
  final Map<String, String> _deviceCommandErrors = <String, String>{};
  final Map<String, StreamSubscription<DeviceCommandState>>
  _commandStatusSubscriptions =
      <String, StreamSubscription<DeviceCommandState>>{};
  final Map<String, StreamSubscription<Device>> _deviceSubscriptions =
      <String, StreamSubscription<Device>>{};
  StreamSubscription<Alert>? _alertsSubscription;
  StreamSubscription<SensorData>? _liveSensorSubscription;
  Timer? _sensorFreshnessTimer;
  Timer? _dashboardRefreshTimer;
  late int _alertsListenerStartedAtMs;
  double _currentTariff = ElectricityPricing.costPerKWh;
  bool _isLoading = false;
  String? _loadError;
  CancelToken? _activeRequestToken;

  static const List<_HomeChoice> _homeChoices = [
    _HomeChoice(
      id: 'home_test',
      label: 'Home Test',
      badge: 'DEMO',
      description: 'Prepared demo scenarios',
      isDemo: true,
    ),
    _HomeChoice(
      id: NetworkConfig.firebaseHomeId,
      label: 'Home 1',
      badge: 'REAL',
      description: 'Live hardware data',
      isDemo: false,
    ),
  ];

  bool get _isDemoHome => _selectedHomeId == 'home_test';
  _HomeChoice get _selectedHome => _homeChoices.firstWhere(
    (home) => home.id == _selectedHomeId,
    orElse: () => _homeChoices.last,
  );
  String get _dataSourceLabel =>
      _isDemoHome ? 'Demo scenario data' : 'Live Firebase data';

  @override
  void initState() {
    super.initState();
    _initializeEmptyData();
    _sensorFreshnessTimer = Timer.periodic(const Duration(seconds: 3), (_) {
      if (!mounted) {
        return;
      }

      setState(() {});
    });
    _dashboardRefreshTimer = Timer.periodic(const Duration(seconds: 15), (_) {
      if (!mounted) {
        return;
      }

      if (widget.enableRealtimeSync && !_isDemoHome) {
        _refreshData(
          showErrorSnackBar: false,
          updateLoading: false,
          cancelActiveRequest: false,
        );
      }
    });
    if (widget.enableRealtimeSync) {
      _refreshData(showErrorSnackBar: false);
      _startLiveSensorListener();
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (!mounted) {
          return;
        }
        _startAlertsListener();
      });
    }
  }

  @override
  void dispose() {
    _activeRequestToken?.cancel('Screen disposed');
    _liveSensorSubscription?.cancel();
    _alertsSubscription?.cancel();
    for (final subscription in _commandStatusSubscriptions.values) {
      subscription.cancel();
    }
    for (final subscription in _deviceSubscriptions.values) {
      subscription.cancel();
    }
    _sensorFreshnessTimer?.cancel();
    _dashboardRefreshTimer?.cancel();
    super.dispose();
  }

  void _startLiveSensorListener() {
    _liveSensorSubscription?.cancel();
    if (_isDemoHome || !widget.enableRealtimeSync) {
      return;
    }

    _liveSensorSubscription = _firebaseRealtimeService
        .watchLiveSensorData(homeId: _selectedHomeId)
        .listen(
          (sensorData) {
            if (!mounted || _isDemoHome) {
              return;
            }

            setState(() {
              _sensorData = sensorData;
              _hasLiveData = true;
            });
          },
          onError: (_) {
            if (!mounted) {
              return;
            }
            setState(() {});
          },
        );
  }

  void _startAlertsListener() {
    try {
      _alertsSubscription?.cancel();
      if (_isDemoHome) {
        return;
      }
      _alertsListenerStartedAtMs = DateTime.now().millisecondsSinceEpoch;

      _alertsSubscription = _firebaseRealtimeService
          .watchAlerts(
            homeId: _selectedHomeId,
            sinceTimestampMs: _alertsListenerStartedAtMs,
          )
          .listen(
            (alert) {
              if (!mounted || _seenAlertIds.contains(alert.id)) {
                return;
              }

              final alertTimestampMs = alert.timestamp.millisecondsSinceEpoch;
              if (alertTimestampMs < _alertsListenerStartedAtMs) {
                return;
              }

              final nowMs = DateTime.now().millisecondsSinceEpoch;
              if ((nowMs - alertTimestampMs) > _historicalAlertMaxAgeMs) {
                return;
              }

              if (_isSensorFeedStale()) {
                return;
              }

              final signature = _alertSignature(alert);
              final lastShownMs = _lastShownAlertBySignature[signature];
              if (lastShownMs != null &&
                  (nowMs - lastShownMs) < _alertDedupCooldownMs) {
                return;
              }

              setState(() {
                _seenAlertIds.add(alert.id);
                _lastShownAlertBySignature[signature] = nowMs;
                _alerts.insert(0, alert);
                if (_alerts.length > 8) {
                  _alerts.removeLast();
                }
              });

              final backgroundColor = _severityColor(alert.severity);
              _showSnackBarDeferred(
                SnackBar(
                  backgroundColor: backgroundColor,
                  content: Text(alert.message),
                  duration: const Duration(seconds: 4),
                ),
              );
            },
            onError: (_) {
              if (!mounted) {
                return;
              }

              _showSnackBarDeferred(
                const SnackBar(
                  content: Text('Realtime alerts connection failed.'),
                ),
              );
            },
          );
    } catch (_) {
      if (!mounted) {
        return;
      }

      _showSnackBarDeferred(
        const SnackBar(
          content: Text('Realtime alerts are not configured on this build.'),
        ),
      );
    }
  }

  String _alertSignature(Alert alert) {
    final normalizedMessage = alert.message.toLowerCase().trim();
    return '${alert.backendType.toLowerCase()}|$normalizedMessage';
  }

  bool _isSensorFeedStale() {
    if (_isDemoHome) {
      return false;
    }

    final ageMs = DateTime.now()
        .difference(_sensorData.timestamp)
        .inMilliseconds;
    return ageMs > _sensorFeedStaleThresholdMs;
  }

  bool get _isSensorFeedWorking => !_isSensorFeedStale();

  void _showSnackBarDeferred(SnackBar snackBar) {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(snackBar);
    });
  }

  void _initializeEmptyData() {
    _currentReading = EnergyReading(
      timestamp: DateTime.fromMillisecondsSinceEpoch(0),
      voltage: 0,
      current: 0,
      power: 0,
      energyToday: 0,
      energyTotal: 0,
    );

    _sensorData = SensorData(
      timestamp: DateTime.fromMillisecondsSinceEpoch(0),
      temperature: 0,
      humidity: 0,
      isOccupied: false,
    );

    _devices = const [];

    _currentTariff = ElectricityPricing.costPerKWh;
  }

  bool _isControllableBreaker(String deviceId) {
    return deviceId == 'breaker_01' || deviceId == 'breaker_02';
  }

  Future<void> _toggleDevice(Device device, bool value) async {
    if (!_deviceControlEnabled || _isDemoHome) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Device control is disabled in Home Test mode.'),
        ),
      );
      return;
    }

    if (!_isControllableBreaker(device.id)) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${device.name} is not command-enabled.')),
      );
      return;
    }

    if (!device.online || !device.controllable) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Device is offline. Check power or Wi-Fi connection.'),
        ),
      );
      return;
    }

    if (!device.commandInProgress && device.isOn == value) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Already ${value ? 'on' : 'off'}.')),
      );
      return;
    }

    await _sendDeviceCommand(device.id, value ? 'turn_on' : 'turn_off');
  }

  Future<void> _sendDeviceCommand(String deviceId, String action) async {
    setState(() {
      _pendingDeviceCommands.add(deviceId);
      _deviceCommandErrors.remove(deviceId);
    });

    try {
      final result = await _firebaseRealtimeService.sendDeviceCommand(
        deviceId,
        action,
        homeId: _selectedHomeId,
      );
      if (!mounted) {
        return;
      }

      if (result.noAction) {
        setState(() {
          if (result.status == 'command_already_in_progress') {
            _pendingDeviceCommands.add(deviceId);
          } else {
            _pendingDeviceCommands.remove(deviceId);
          }
        });
        if (result.message.trim().isNotEmpty &&
            result.status != 'command_already_in_progress') {
          ScaffoldMessenger.of(
            context,
          ).showSnackBar(SnackBar(content: Text(result.message)));
        }
        return;
      }

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(result.message)));
    } catch (_) {
      if (!mounted) {
        return;
      }

      setState(() {
        _pendingDeviceCommands.remove(deviceId);
        _deviceCommandErrors[deviceId] =
            'Could not send command. Please try again.';
      });

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not send device command.')),
      );
    }
  }

  void _syncDeviceListeners(List<Device> devices) {
    if (!_deviceControlEnabled || _isDemoHome) {
      for (final subscription in _commandStatusSubscriptions.values) {
        subscription.cancel();
      }
      for (final subscription in _deviceSubscriptions.values) {
        subscription.cancel();
      }
      _commandStatusSubscriptions.clear();
      _deviceSubscriptions.clear();
      return;
    }

    final activeDeviceIds = devices
        .map((device) => device.id)
        .where(_isControllableBreaker)
        .toSet();

    for (final deviceId in _commandStatusSubscriptions.keys.toList()) {
      if (!activeDeviceIds.contains(deviceId)) {
        _commandStatusSubscriptions.remove(deviceId)?.cancel();
      }
    }

    for (final deviceId in _deviceSubscriptions.keys.toList()) {
      if (!activeDeviceIds.contains(deviceId)) {
        _deviceSubscriptions.remove(deviceId)?.cancel();
      }
    }

    for (final deviceId in activeDeviceIds) {
      _commandStatusSubscriptions.putIfAbsent(
        deviceId,
        () => _firebaseRealtimeService
            .watchLatestCommandStatusForHome(_selectedHomeId, deviceId)
            .listen(
              (state) => _handleCommandStateChanged(deviceId, state),
              onError: (_) {
                if (!mounted) {
                  return;
                }

                setState(() {
                  _pendingDeviceCommands.remove(deviceId);
                  _deviceCommandErrors[deviceId] =
                      'Command status listener failed.';
                });
              },
            ),
      );

      _deviceSubscriptions.putIfAbsent(
        deviceId,
        () => _firebaseRealtimeService
            .watchDeviceForHome(_selectedHomeId, deviceId)
            .listen((device) => _updateDeviceRealtimeState(device)),
      );
    }
  }

  void _handleCommandStateChanged(String deviceId, DeviceCommandState state) {
    if (!mounted || state.status.isEmpty) {
      return;
    }

    if (state.isPending) {
      setState(() {
        _pendingDeviceCommands.add(deviceId);
        _deviceCommandErrors.remove(deviceId);
      });
      return;
    }

    final wasPending = _pendingDeviceCommands.contains(deviceId);
    if (!wasPending) {
      return;
    }

    if (state.isDone) {
      setState(() {
        _pendingDeviceCommands.remove(deviceId);
        _deviceCommandErrors.remove(deviceId);
      });
      _refreshData(showErrorSnackBar: false, updateLoading: false);
      return;
    }

    if (state.isFailed) {
      final error = state.error?.trim().isNotEmpty == true
          ? state.error!.trim()
          : 'Device command failed.';

      setState(() {
        _pendingDeviceCommands.remove(deviceId);
        _deviceCommandErrors[deviceId] = error;
      });

      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(error)));
    }
  }

  void _updateDeviceRealtimeState(Device updatedDevice) {
    if (!mounted) {
      return;
    }

    final index = _devices.indexWhere(
      (device) => device.id == updatedDevice.id,
    );
    if (_pendingDeviceCommands.contains(updatedDevice.id) ||
        (index != -1 && _devices[index].commandInProgress)) {
      if (index != -1) {
        setState(() {
          if (!updatedDevice.online) {
            _pendingDeviceCommands.remove(updatedDevice.id);
            _deviceCommandErrors.remove(updatedDevice.id);
          }
          _devices[index] = _devices[index].copyWith(
            type: _stableDeviceType(updatedDevice.id, _devices[index].type),
            isOn: updatedDevice.online && updatedDevice.isOn,
            online: updatedDevice.online,
            controllable: updatedDevice.controllable,
            currentPower: updatedDevice.currentPower,
            commandInProgress:
                updatedDevice.online && updatedDevice.commandInProgress,
            lastCommandMessage: updatedDevice.lastCommandMessage,
          );
        });
      }
      return;
    }
    if (index == -1) {
      return;
    }

    setState(() {
      _devices[index] = updatedDevice.copyWith(
        type: _stableDeviceType(updatedDevice.id, _devices[index].type),
      );
    });
  }

  Future<void> _refreshData({
    bool showErrorSnackBar = true,
    bool updateLoading = true,
    bool cancelActiveRequest = true,
  }) async {
    if (_activeRequestToken != null) {
      if (!cancelActiveRequest) {
        return;
      }
      _activeRequestToken?.cancel('New refresh started');
    }

    if (mounted && updateLoading) {
      setState(() {
        _isLoading = true;
        _loadError = null;
      });
    }

    final cancelToken = CancelToken();
    _activeRequestToken = cancelToken;

    try {
      final dashboardData = await _firebaseRealtimeService.fetchDashboardData(
        homeId: _selectedHomeId,
        scenarioId: _isDemoHome ? _selectedScenarioId : null,
        cancelToken: cancelToken,
      );

      final demoScenarios = _isDemoHome
          ? await _firebaseRealtimeService.fetchDemoScenarios(
              cancelToken: cancelToken,
            )
          : const <DemoScenario>[];

      if (!mounted) {
        return;
      }

      final fallbackScenarioId = demoScenarios.isNotEmpty
          ? demoScenarios.first.id
          : dashboardData.scenarioId;

      final mergedDevices = _mergeRealtimeDevices(dashboardData.devices);

      setState(() {
        _currentReading = dashboardData.reading;
        _updateSmokeClearTimer(dashboardData.sensors);
        if (_isDemoHome || _isSensorFeedStale()) {
          _sensorData = dashboardData.sensors;
        }
        _devices = mergedDevices;
        _hasLiveData = true;
        _demoScenarios = demoScenarios;
        _selectedScenarioId = _isDemoHome
            ? (_selectedScenarioId ?? fallbackScenarioId)
            : null;
        _activeScenarioName = dashboardData.scenarioName;
        _activeScenarioDescription = dashboardData.scenarioDescription;
        _deviceControlEnabled =
            !_isDemoHome && dashboardData.deviceControlEnabled;
        _pendingDeviceCommands
          ..clear()
          ..addAll(dashboardData.pendingDeviceCommands);
        _deviceCommandErrors
          ..clear()
          ..addAll(dashboardData.deviceCommandErrors);
        _currentTariff = dashboardData.tariffBhdPerKwh;
        _aiDashboard = dashboardData.aiDashboard;
        _aiDailySummary = dashboardData.aiDailySummary;
        _aiRecommendation = dashboardData.aiRecommendation;
        _aiAlert = dashboardData.aiAlert;
        _controlMode = dashboardData.control;
        _actionSuggestions = _dedupeActionSuggestions(
          dashboardData.actionSuggestions,
        );
        _automationLogs = dashboardData.automationLogs;
        _settingsSummary = dashboardData.settingsSummary;
        _occupancy = dashboardData.occupancy;
        _safety = dashboardData.safety;
        _criticalAlerts = dashboardData.criticalAlerts;
        _nextSchedule = dashboardData.nextSchedule;
      });

      _showEmergencyPopupIfNeeded();

      try {
        _syncDeviceListeners(mergedDevices);
      } catch (_) {
        // The dashboard data is loaded through REST. Native Firebase listeners
        // can be unavailable on local/dev builds without breaking the dashboard.
      }
    } catch (error) {
      if (!mounted) {
        return;
      }

      if (_isRequestCancellation(error)) {
        return;
      }

      setState(() {
        _loadError = _friendlyLoadError(error);
        _hasLiveData = false;
        _devices = const [];
      });

      if (showErrorSnackBar) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text('Dashboard connection failed. Pull to retry.'),
          ),
        );
      }
    } finally {
      if (mounted && updateLoading) {
        setState(() {
          _isLoading = false;
        });
      }
      if (identical(_activeRequestToken, cancelToken)) {
        _activeRequestToken = null;
      }
    }
  }

  List<Device> _mergeRealtimeDevices(List<Device> refreshedDevices) {
    if (_isDemoHome || _devices.isEmpty || _deviceSubscriptions.isEmpty) {
      return refreshedDevices;
    }

    final currentById = {for (final device in _devices) device.id: device};

    return refreshedDevices.map((device) {
      final current = currentById[device.id];
      if (current == null) {
        return device;
      }
      return device.copyWith(
        type: _stableDeviceType(device.id, device.type),
        isOn: current.isOn,
        currentPower: current.currentPower,
        online: current.online,
        controllable: current.controllable,
        commandInProgress: current.commandInProgress,
        pendingTargetState: current.pendingTargetState,
        lastCommandMessage: current.lastCommandMessage,
      );
    }).toList();
  }

  DeviceType _stableDeviceType(String deviceId, DeviceType fallback) {
    if (deviceId == 'breaker_01') {
      return DeviceType.light;
    }
    if (deviceId == 'breaker_02') {
      return DeviceType.airConditioner;
    }
    return fallback;
  }

  bool _isRequestCancellation(Object error) {
    return error is DioException && error.type == DioExceptionType.cancel;
  }

  String _friendlyLoadError(Object error) {
    if (error is DioException) {
      final statusCode = error.response?.statusCode;
      final detail = error.response?.data?.toString();
      if (statusCode != null) {
        return 'Cloud Run API error $statusCode. ${detail ?? 'Pull to retry.'}';
      }
      return 'Cloud Run API connection failed: ${error.message ?? error.type.name}.';
    }

    final message = error.toString().replaceFirst('Exception: ', '');
    if (message.trim().isNotEmpty) {
      return message;
    }

    return 'Could not load dashboard data. Check the Cloud Run API connection and pull to retry.';
  }

  void _selectHome(String homeId) {
    if (homeId == _selectedHomeId) {
      return;
    }

    _alertsSubscription?.cancel();
    _liveSensorSubscription?.cancel();
    for (final subscription in _commandStatusSubscriptions.values) {
      subscription.cancel();
    }
    for (final subscription in _deviceSubscriptions.values) {
      subscription.cancel();
    }

    setState(() {
      _selectedHomeId = homeId;
      _selectedScenarioId = null;
      _activeScenarioName = null;
      _activeScenarioDescription = null;
      _demoScenarios = const [];
      _alerts.clear();
      _seenAlertIds.clear();
      _pendingDeviceCommands.clear();
      _deviceCommandErrors.clear();
      _commandStatusSubscriptions.clear();
      _deviceSubscriptions.clear();
      _loadError = null;
      _hasLiveData = false;
      _devices = const [];
    });

    _refreshData(showErrorSnackBar: false);
    _startLiveSensorListener();
    _startAlertsListener();
  }

  void _selectScenario(String? scenarioId) {
    if (scenarioId == null || scenarioId == _selectedScenarioId) {
      return;
    }

    setState(() {
      _selectedScenarioId = scenarioId;
      _loadError = null;
      _pendingDeviceCommands.clear();
      _deviceCommandErrors.clear();
      _hasLiveData = false;
      _devices = const [];
    });

    _refreshData(showErrorSnackBar: false);
  }

  Future<void> _showSettingsSheet() async {
    final results = await Future.wait<dynamic>([
      _firebaseRealtimeService.fetchControlModes(homeId: _selectedHomeId),
      _firebaseRealtimeService.fetchSettings(homeId: _selectedHomeId),
      _firebaseRealtimeService.fetchSchedules(homeId: _selectedHomeId),
    ]);
    final options = results[0] as List<ControlModeOption>;
    var settings = results[1] as HomeSettings;
    var schedules = results[2] as List<ScheduleInfo>;
    if (!mounted) {
      return;
    }

    final costController = TextEditingController(
      text: settings.costPerKwh.toStringAsFixed(3),
    );
    final comfortMinController = TextEditingController(
      text: settings.comfortMin.toStringAsFixed(0),
    );
    final comfortMaxController = TextEditingController(
      text: settings.comfortMax.toStringAsFixed(0),
    );
    final highTempController = TextEditingController(
      text: settings.highTempThreshold.toStringAsFixed(0),
    );
    final lightWasteController = TextEditingController(
      text: settings.lightWasteMinutes.toString(),
    );
    final motionRecentController = TextEditingController(
      text: settings.motionRecentSeconds.toString(),
    );
    final soundRecentController = TextEditingController(
      text: settings.soundRecentSeconds.toString(),
    );
    final occupancyController = TextEditingController(
      text: settings.occupancyEmptyMinutes.toString(),
    );
    final soundThresholdController = TextEditingController(
      text: settings.soundActivityThreshold.toStringAsFixed(0),
    );
    final occupancyConfidenceController = TextEditingController(
      text: settings.occupancyConfidenceThreshold.toStringAsFixed(2),
    );
    final offlineController = TextEditingController(
      text: settings.deviceOfflineMinutes.toString(),
    );
    var quietEnabled = settings.quietHoursEnabled;
    var aiEnabled = settings.aiRecommendationsEnabled;
    var autoEnabled = settings.autoControlEnabled;
    var notificationsEnabled = settings.notificationsEnabled;
    var schedulesEnabled = settings.schedulesEnabled;

    await showModalBottomSheet<void>(
      context: context,
      isScrollControlled: true,
      useSafeArea: true,
      builder: (context) => StatefulBuilder(
        builder: (context, setSheetState) {
          return SafeArea(
            child: SingleChildScrollView(
              padding: EdgeInsets.only(
                left: 16,
                right: 16,
                top: 14,
                bottom: MediaQuery.of(context).viewInsets.bottom + 20,
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Row(
                    children: [
                      const Icon(Icons.settings, color: AppColors.primary),
                      const SizedBox(width: 8),
                      const Expanded(
                        child: Text(
                          'Settings',
                          style: TextStyle(
                            fontSize: 20,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                      IconButton(
                        tooltip: 'Close settings',
                        constraints: const BoxConstraints(
                          minWidth: 48,
                          minHeight: 48,
                        ),
                        icon: const Icon(Icons.close),
                        onPressed: () => Navigator.of(context).pop(),
                      ),
                    ],
                  ),
                  const SizedBox(height: 10),
                  const Text(
                    'Control Mode',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 10),
                  ...options.map(
                    (option) => _buildModeOptionTile(
                      option: option,
                      isSelected: option.mode == _controlMode.mode,
                      isBusy: _isUpdatingControlMode,
                      onSelected: () async {
                        setSheetState(() {
                          _isUpdatingControlMode = true;
                        });
                        await _changeControlMode(option.mode);
                        if (!mounted) {
                          return;
                        }
                        setSheetState(() {
                          _isUpdatingControlMode = false;
                        });
                      },
                    ),
                  ),
                  const SizedBox(height: 18),
                  const Text(
                    'System Preferences',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800),
                  ),
                  const SizedBox(height: 10),
                  _buildNumberField(costController, 'Cost per kWh'),
                  _buildNumberField(
                    comfortMinController,
                    'Comfort temperature min',
                  ),
                  _buildNumberField(
                    comfortMaxController,
                    'Comfort temperature max',
                  ),
                  _buildNumberField(
                    highTempController,
                    'High temperature threshold',
                  ),
                  _buildNumberField(
                    lightWasteController,
                    'Light waste delay minutes',
                  ),
                  _buildNumberField(
                    motionRecentController,
                    'Motion recent seconds',
                  ),
                  _buildNumberField(
                    soundRecentController,
                    'Sound recent seconds',
                  ),
                  _buildNumberField(
                    occupancyController,
                    'Occupancy empty delay minutes',
                  ),
                  _buildNumberField(
                    soundThresholdController,
                    'Sound activity threshold',
                  ),
                  _buildNumberField(
                    occupancyConfidenceController,
                    'Occupancy confidence threshold',
                  ),
                  _buildNumberField(
                    offlineController,
                    'Device offline delay minutes',
                  ),
                  SwitchListTile(
                    value: quietEnabled,
                    onChanged: (value) =>
                        setSheetState(() => quietEnabled = value),
                    title: const Text('Quiet hours'),
                    subtitle: Text(
                      '${settings.quietHoursStart} - ${settings.quietHoursEnd}',
                    ),
                  ),
                  SwitchListTile(
                    value: aiEnabled,
                    onChanged: (value) =>
                        setSheetState(() => aiEnabled = value),
                    title: const Text('AI recommendations'),
                  ),
                  SwitchListTile(
                    value: autoEnabled,
                    onChanged: (value) =>
                        setSheetState(() => autoEnabled = value),
                    title: const Text('Auto control'),
                  ),
                  SwitchListTile(
                    value: notificationsEnabled,
                    onChanged: (value) =>
                        setSheetState(() => notificationsEnabled = value),
                    title: const Text('Notifications'),
                  ),
                  SwitchListTile(
                    value: schedulesEnabled,
                    onChanged: (value) =>
                        setSheetState(() => schedulesEnabled = value),
                    title: const Text('Schedules'),
                  ),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: () async {
                        final updated = await _saveSettings(
                          costController: costController,
                          comfortMinController: comfortMinController,
                          comfortMaxController: comfortMaxController,
                          highTempController: highTempController,
                          lightWasteController: lightWasteController,
                          motionRecentController: motionRecentController,
                          soundRecentController: soundRecentController,
                          occupancyController: occupancyController,
                          soundThresholdController: soundThresholdController,
                          occupancyConfidenceController:
                              occupancyConfidenceController,
                          offlineController: offlineController,
                          quietEnabled: quietEnabled,
                          aiEnabled: aiEnabled,
                          autoEnabled: autoEnabled,
                          notificationsEnabled: notificationsEnabled,
                          schedulesEnabled: schedulesEnabled,
                        );
                        if (updated != null) {
                          setSheetState(() {
                            settings = updated;
                          });
                        }
                      },
                      icon: const Icon(Icons.save_outlined),
                      label: const Text('Save Preferences'),
                    ),
                  ),
                  const SizedBox(height: 18),
                  Row(
                    children: [
                      const Expanded(
                        child: Text(
                          'Schedules',
                          style: TextStyle(
                            fontSize: 16,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                      ),
                      TextButton.icon(
                        onPressed: () async {
                          final created = await _showCreateScheduleDialog();
                          if (created == true) {
                            final next = await _firebaseRealtimeService
                                .fetchSchedules(homeId: _selectedHomeId);
                            setSheetState(() => schedules = next);
                            await _refreshData(
                              showErrorSnackBar: false,
                              updateLoading: false,
                            );
                          }
                        },
                        icon: const Icon(Icons.add),
                        label: const Text('Add'),
                      ),
                    ],
                  ),
                  ...schedules.map(
                    (schedule) => _buildScheduleTile(
                      schedule,
                      onChanged: (enabled) async {
                        await _firebaseRealtimeService.updateScheduleEnabled(
                          homeId: _selectedHomeId,
                          scheduleId: schedule.id,
                          enabled: enabled,
                        );
                        final next = await _firebaseRealtimeService
                            .fetchSchedules(homeId: _selectedHomeId);
                        setSheetState(() => schedules = next);
                        await _refreshData(
                          showErrorSnackBar: false,
                          updateLoading: false,
                        );
                      },
                      onRunNow: () async {
                        final message = await _firebaseRealtimeService
                            .runScheduleNow(
                              homeId: _selectedHomeId,
                              scheduleId: schedule.id,
                            );
                        if (!mounted) {
                          return;
                        }
                        _showSnackBarDeferred(SnackBar(content: Text(message)));
                      },
                      onDelete: () async {
                        await _firebaseRealtimeService.deleteSchedule(
                          homeId: _selectedHomeId,
                          scheduleId: schedule.id,
                        );
                        final next = await _firebaseRealtimeService
                            .fetchSchedules(homeId: _selectedHomeId);
                        setSheetState(() => schedules = next);
                        await _refreshData(
                          showErrorSnackBar: false,
                          updateLoading: false,
                        );
                      },
                    ),
                  ),
                ],
              ),
            ),
          );
        },
      ),
    );
  }

  Future<void> _changeControlMode(String mode) async {
    try {
      final message = await _firebaseRealtimeService.updateControlMode(
        homeId: _selectedHomeId,
        mode: mode,
        updatedBy: 'flutter_app',
      );
      await _refreshData(showErrorSnackBar: false, updateLoading: false);
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    } catch (_) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Could not update control mode.')),
      );
    }
  }

  Future<HomeSettings?> _saveSettings({
    required TextEditingController costController,
    required TextEditingController comfortMinController,
    required TextEditingController comfortMaxController,
    required TextEditingController highTempController,
    required TextEditingController lightWasteController,
    required TextEditingController motionRecentController,
    required TextEditingController soundRecentController,
    required TextEditingController occupancyController,
    required TextEditingController soundThresholdController,
    required TextEditingController occupancyConfidenceController,
    required TextEditingController offlineController,
    required bool quietEnabled,
    required bool aiEnabled,
    required bool autoEnabled,
    required bool notificationsEnabled,
    required bool schedulesEnabled,
  }) async {
    final comfortMin = double.tryParse(comfortMinController.text);
    final comfortMax = double.tryParse(comfortMaxController.text);
    final highTemp = double.tryParse(highTempController.text);
    if (comfortMin == null ||
        comfortMax == null ||
        highTemp == null ||
        comfortMin >= comfortMax ||
        highTemp <= comfortMax) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Check temperature preference values.')),
      );
      return null;
    }

    try {
      final updated = await _firebaseRealtimeService.updateSettings(
        homeId: _selectedHomeId,
        values: {
          'cost_per_kwh': double.tryParse(costController.text) ?? 0.029,
          'comfort_temperature_min': comfortMin,
          'comfort_temperature_max': comfortMax,
          'high_temperature_threshold': highTemp,
          'light_waste_minutes': int.tryParse(lightWasteController.text) ?? 5,
          'motion_recent_seconds':
              int.tryParse(motionRecentController.text) ?? 90,
          'sound_recent_seconds': int.tryParse(soundRecentController.text) ?? 120,
          'occupancy_empty_minutes':
              int.tryParse(occupancyController.text) ?? 10,
          'sound_activity_threshold':
              double.tryParse(soundThresholdController.text) ?? 45,
          'occupancy_confidence_threshold':
              double.tryParse(occupancyConfidenceController.text) ?? 0.65,
          'device_offline_minutes': int.tryParse(offlineController.text) ?? 2,
          'quiet_hours_enabled': quietEnabled,
          'ai_recommendations_enabled': aiEnabled,
          'auto_control_enabled': autoEnabled,
          'notifications_enabled': notificationsEnabled,
          'schedules_enabled': schedulesEnabled,
          'updated_by': 'flutter_app',
        },
      );
      await _refreshData(showErrorSnackBar: false, updateLoading: false);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(const SnackBar(content: Text('Preferences saved.')));
      }
      return updated;
    } catch (error) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('Could not save preferences: $error')),
        );
      }
      return null;
    }
  }

  Future<bool?> _showCreateScheduleDialog() async {
    final nameController = TextEditingController(text: 'Turn off at night');
    var deviceId = 'breaker_01';
    var command = 'turn_off';
    var time = const TimeOfDay(hour: 23, minute: 30);
    final selectedDays = <String>{
      'Sun',
      'Mon',
      'Tue',
      'Wed',
      'Thu',
      'Fri',
      'Sat',
    };

    return showDialog<bool>(
      context: context,
      builder: (context) => StatefulBuilder(
        builder: (context, setDialogState) {
          return AlertDialog(
            title: const Text('Add Schedule'),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  TextField(
                    controller: nameController,
                    decoration: const InputDecoration(
                      labelText: 'Schedule name',
                    ),
                  ),
                  DropdownButtonFormField<String>(
                    initialValue: deviceId,
                    decoration: const InputDecoration(labelText: 'Device'),
                    items: const [
                      DropdownMenuItem(
                        value: 'breaker_01',
                        child: Text('Switch Breaker'),
                      ),
                      DropdownMenuItem(
                        value: 'breaker_02',
                        child: Text('AC Breaker'),
                      ),
                    ],
                    onChanged: (value) {
                      if (value != null) {
                        setDialogState(() => deviceId = value);
                      }
                    },
                  ),
                  DropdownButtonFormField<String>(
                    initialValue: command,
                    decoration: const InputDecoration(labelText: 'Command'),
                    items: const [
                      DropdownMenuItem(
                        value: 'turn_on',
                        child: Text('Turn On'),
                      ),
                      DropdownMenuItem(
                        value: 'turn_off',
                        child: Text('Turn Off'),
                      ),
                    ],
                    onChanged: (value) {
                      if (value != null) {
                        setDialogState(() => command = value);
                      }
                    },
                  ),
                  ListTile(
                    contentPadding: EdgeInsets.zero,
                    title: const Text('Time'),
                    subtitle: Text(_formatTimeOfDay(time)),
                    trailing: const Icon(Icons.schedule),
                    onTap: () async {
                      final picked = await showTimePicker(
                        context: context,
                        initialTime: time,
                      );
                      if (picked != null) {
                        setDialogState(() => time = picked);
                      }
                    },
                  ),
                  Wrap(
                    spacing: 6,
                    children: ['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat']
                        .map(
                          (day) => FilterChip(
                            label: Text(day),
                            selected: selectedDays.contains(day),
                            onSelected: (selected) {
                              setDialogState(() {
                                if (selected) {
                                  selectedDays.add(day);
                                } else {
                                  selectedDays.remove(day);
                                }
                              });
                            },
                          ),
                        )
                        .toList(),
                  ),
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(context, false),
                child: const Text('Cancel'),
              ),
              ElevatedButton(
                onPressed: selectedDays.isEmpty
                    ? null
                    : () async {
                        await _firebaseRealtimeService.createSchedule(
                          homeId: _selectedHomeId,
                          values: {
                            'name': nameController.text.trim(),
                            'device_id': deviceId,
                            'command': command,
                            'time': _formatTimeOfDay(time),
                            'days': selectedDays.toList(),
                            'enabled': true,
                            'created_by': 'flutter_app',
                          },
                        );
                        if (context.mounted) {
                          Navigator.pop(context, true);
                        }
                      },
                child: const Text('Create'),
              ),
            ],
          );
        },
      ),
    );
  }

  String _formatTimeOfDay(TimeOfDay time) {
    return '${time.hour.toString().padLeft(2, '0')}:${time.minute.toString().padLeft(2, '0')}';
  }

  Future<void> _approveSuggestion(ActionSuggestion suggestion) async {
    _removeMatchingSuggestions(suggestion);
    try {
      final message = await _firebaseRealtimeService.approveActionSuggestion(
        homeId: _selectedHomeId,
        suggestionId: suggestion.id,
      );
      await _refreshData(showErrorSnackBar: false, updateLoading: false);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(message)));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not approve suggestion.')),
        );
      }
    }
  }

  Future<void> _dismissSuggestion(ActionSuggestion suggestion) async {
    _removeMatchingSuggestions(suggestion);
    try {
      final message = await _firebaseRealtimeService.dismissActionSuggestion(
        homeId: _selectedHomeId,
        suggestionId: suggestion.id,
      );
      await _refreshData(showErrorSnackBar: false, updateLoading: false);
      if (mounted) {
        ScaffoldMessenger.of(
          context,
        ).showSnackBar(SnackBar(content: Text(message)));
      }
    } catch (_) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('Could not dismiss suggestion.')),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final totalCost = _currentReading.calculateCost(_currentTariff);
    final isSensorFeedWorking = _isSensorFeedWorking;
    final averageCurrent = _currentReading.current > 0
        ? _currentReading.current
        : 0.0;

    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text(
          appName,
          style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
        ),
        backgroundColor: AppColors.primary,
        elevation: 0,
        actions: [
          IconButton(
            icon: const Icon(Icons.settings, color: Colors.white),
            onPressed: _showSettingsSheet,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: () async {
          await _refreshData();
        },
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16.0),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_isLoading) ...[
                const LinearProgressIndicator(),
                const SizedBox(height: 16),
              ],

              if (_loadError != null) ...[
                Card(
                  color: Colors.orange.shade50,
                  child: Padding(
                    padding: const EdgeInsets.all(12),
                    child: Row(
                      children: [
                        const Icon(
                          Icons.warning_amber_rounded,
                          color: Colors.orange,
                        ),
                        const SizedBox(width: 8),
                        Expanded(
                          child: Text(
                            _loadError!,
                            style: const TextStyle(color: Colors.black87),
                          ),
                        ),
                      ],
                    ),
                  ),
                ),
                const SizedBox(height: 12),
              ],

              _buildHomeSelectorCard(),
              const SizedBox(height: 16),

              _buildControlModeCard(),
              const SizedBox(height: 16),

              if (_nextSchedule != null) ...[
                _buildNextScheduleCard(_nextSchedule!),
                const SizedBox(height: 16),
              ],

              if (_controlMode.mode == 'assist' &&
                  _actionSuggestions.isNotEmpty) ...[
                _buildSectionTitle('Action Suggestions'),
                const SizedBox(height: 8),
                ..._actionSuggestions.map(_buildActionSuggestionCard),
                const SizedBox(height: 16),
              ],

              if (_controlMode.mode == 'auto' &&
                  _automationLogs.isNotEmpty) ...[
                _buildAutomationLogCard(_automationLogs.first),
                const SizedBox(height: 16),
              ],

              if (!_hasLiveData && !_isLoading) ...[
                _buildNoLiveDataCard(),
                const SizedBox(height: 16),
              ],

              if (_alerts.isNotEmpty) ...[
                _buildSectionTitle('Alerts'),
                const SizedBox(height: 8),
                ..._alerts.map(_buildAlertCard),
                const SizedBox(height: 16),
              ],

              // Energy Metrics
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _buildSectionTitle('Energy Overview'),
                  Text(
                    _dataSourceLabel,
                    style: TextStyle(
                      color: Colors.grey[600],
                      fontSize: 12,
                      fontWeight: FontWeight.w600,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: MetricCard(
                      title: 'Current Power',
                      value: _hasLiveData
                          ? (_currentReading.power / 1000).toStringAsFixed(2)
                          : '--',
                      unit: 'kW',
                      icon: Icons.bolt,
                      color: AppColors.primary,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: MetricCard(
                      title: 'Energy Today',
                      value: _hasLiveData
                          ? _currentReading.energyToday.toStringAsFixed(2)
                          : '--',
                      unit: 'kWh',
                      icon: Icons.calendar_today,
                      color: AppColors.accent,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: MetricCard(
                      title: 'Cost Today',
                      value: _hasLiveData ? totalCost.toStringAsFixed(3) : '--',
                      unit: 'BD',
                      icon: Icons.attach_money,
                      color: Colors.orange,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: MetricCard(
                      title: 'Tariff',
                      value: _hasLiveData
                          ? _currentTariff.toStringAsFixed(3)
                          : '--',
                      unit: 'BD/kWh',
                      icon: Icons.price_change,
                      color: Colors.indigo,
                    ),
                  ),
                ],
              ),

              const SizedBox(height: 12),
              Row(
                children: [
                  Expanded(
                    child: MetricCard(
                      title: 'Voltage',
                      value: _hasLiveData
                          ? _currentReading.voltage.toStringAsFixed(1)
                          : '--',
                      unit: 'V',
                      icon: Icons.electrical_services,
                      color: Colors.blue,
                    ),
                  ),
                  const SizedBox(width: 12),
                  Expanded(
                    child: MetricCard(
                      title: 'Current',
                      value: _hasLiveData
                          ? averageCurrent.toStringAsFixed(2)
                          : '--',
                      unit: 'A',
                      icon: Icons.cable,
                      color: Colors.teal,
                    ),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              MetricCard(
                title: 'Total Energy',
                value: _hasLiveData
                    ? _currentReading.energyTotal.toStringAsFixed(2)
                    : '--',
                unit: 'kWh',
                icon: Icons.stacked_line_chart,
                color: Colors.deepPurple,
              ),

              const SizedBox(height: 24),

              _buildSectionTitle('Smart Energy AI'),
              const SizedBox(height: 12),
              if (_isDemoHome) ...[
                _buildModeNotice(
                  icon: Icons.science_outlined,
                  message:
                      'Home Test Mode: AI analysis is based on demo/test scenario data.',
                  color: Colors.indigo,
                ),
                const SizedBox(height: 12),
              ],
              _buildAiDashboardCard(),
              const SizedBox(height: 12),
              _buildAiDailySummaryCard(),
              if (_aiRecommendation?.isActive ?? false) ...[
                const SizedBox(height: 12),
                _buildAiRecommendationCard(_aiRecommendation!),
              ],
              const SizedBox(height: 12),
              _buildAiAlertCard(),

              const SizedBox(height: 24),

              // Environment Sensors
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _buildSectionTitle('Environment'),
                  _buildStatusChip(
                    icon: _isDemoHome
                        ? Icons.science_outlined
                        : Icons.sensors_outlined,
                    label: _isDemoHome
                        ? 'Simulated sensors'
                        : 'Live sensor data',
                    color: _isDemoHome ? Colors.indigo : AppColors.primary,
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (_isDemoHome) ...[
                _buildModeNotice(
                  icon: Icons.info_outline,
                  message:
                      'Test Home Mode: Showing the latest simulated environment sensor record for demonstration.',
                  color: Colors.indigo,
                ),
                const SizedBox(height: 12),
              ],
              Card(
                elevation: 2,
                child: Padding(
                  padding: const EdgeInsets.all(16.0),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          Text(
                            _isDemoHome
                                ? 'Simulated sensor record'
                                : 'Live sensor feed',
                            style: TextStyle(
                              fontSize: 15,
                              fontWeight: FontWeight.w700,
                              color: Colors.grey[800],
                            ),
                          ),
                          TextButton.icon(
                            onPressed: () {
                              Navigator.of(context).push(
                                MaterialPageRoute(
                                  builder: (_) => SensorsStatusScreen(
                                    sensorData: _sensorData,
                                    isDemoMode: _isDemoHome,
                                  ),
                                ),
                              );
                            },
                            icon: const Icon(Icons.sensors, size: 16),
                            label: const Text('Sensors'),
                          ),
                        ],
                      ),
                      Text(
                        DateFormat(
                          'MMM d, HH:mm:ss',
                        ).format(_sensorData.timestamp),
                        style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                      ),
                      const SizedBox(height: 12),
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.symmetric(
                          horizontal: 12,
                          vertical: 10,
                        ),
                        decoration: BoxDecoration(
                          color: _roomComfortColor().withValues(alpha: 0.12),
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(
                            color: _roomComfortColor().withValues(alpha: 0.25),
                          ),
                        ),
                        child: Row(
                          children: [
                            Icon(
                              _roomComfortIcon(),
                              size: 18,
                              color: _roomComfortColor(),
                            ),
                            const SizedBox(width: 8),
                            Expanded(
                              child: Text(
                                _roomComfortMessage(),
                                style: TextStyle(
                                  fontSize: 13,
                                  fontWeight: FontWeight.w600,
                                  color: _roomComfortColor(),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 12),
                      _buildOccupancySummary(),
                      const SizedBox(height: 12),
                      if (!isSensorFeedWorking) ...[
                        Container(
                          width: double.infinity,
                          padding: const EdgeInsets.symmetric(
                            horizontal: 12,
                            vertical: 10,
                          ),
                          decoration: BoxDecoration(
                            color: AppColors.energyDanger.withValues(
                              alpha: 0.10,
                            ),
                            borderRadius: BorderRadius.circular(10),
                            border: Border.all(
                              color: AppColors.energyDanger.withValues(
                                alpha: 0.25,
                              ),
                            ),
                          ),
                          child: const Row(
                            children: [
                              Icon(
                                Icons.sensors_off_outlined,
                                size: 18,
                                color: AppColors.energyDanger,
                              ),
                              SizedBox(width: 8),
                              Expanded(
                                child: Text(
                                  'Sensor feed is offline. Waiting for a new ESP32 update.',
                                  style: TextStyle(
                                    fontSize: 13,
                                    fontWeight: FontWeight.w600,
                                    color: AppColors.energyDanger,
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 12),
                      ],
                      Wrap(
                        spacing: 8,
                        runSpacing: 8,
                        children: [
                          _buildStatusChip(
                            icon: !isSensorFeedWorking
                                ? Icons.sensors_off_outlined
                                : _sensorData.isOccupied
                                ? Icons.person
                                : Icons.person_outline,
                            label: !isSensorFeedWorking
                                ? 'Feed offline'
                                : _sensorData.isOccupied
                                ? 'Occupied'
                                : 'Not occupied',
                            color: !isSensorFeedWorking
                                ? AppColors.energyDanger
                                : _sensorData.isOccupied
                                ? AppColors.primary
                                : Colors.blueGrey,
                          ),
                          _buildStatusChip(
                            icon: isSensorFeedWorking && _sensorData.ahtOk
                                ? Icons.check_circle
                                : Icons.error_outline,
                            label: isSensorFeedWorking && _sensorData.ahtOk
                                ? 'AHT sensor OK'
                                : 'AHT sensor issue',
                            color: isSensorFeedWorking && _sensorData.ahtOk
                                ? AppColors.energySafe
                                : AppColors.energyDanger,
                          ),
                          _buildStatusChip(
                            icon: isSensorFeedWorking && _sensorData.ens160Ok
                                ? Icons.check_circle
                                : Icons.error_outline,
                            label: isSensorFeedWorking && _sensorData.ens160Ok
                                ? 'ENS160 OK'
                                : 'ENS160 issue',
                            color: isSensorFeedWorking && _sensorData.ens160Ok
                                ? AppColors.energySafe
                                : AppColors.energyDanger,
                          ),
                          _buildStatusChip(
                            icon: Icons.wb_sunny_outlined,
                            label: isSensorFeedWorking
                                ? _sensorData.lightStatus
                                : 'Light sensor issue',
                            color: isSensorFeedWorking
                                ? Colors.amber
                                : AppColors.energyDanger,
                          ),
                          _buildStatusChip(
                            icon: Icons.local_fire_department_outlined,
                            label: !isSensorFeedWorking
                                ? 'Smoke sensor issue'
                                : _sensorData.smokeStatus.toLowerCase() ==
                                      'clear'
                                ? 'Air clear'
                                : _sensorData.smokeStatus,
                            color:
                                isSensorFeedWorking &&
                                    _sensorData.smokeStatus.toLowerCase() ==
                                        'clear'
                                ? AppColors.energySafe
                                : AppColors.energyDanger,
                          ),
                          _buildStatusChip(
                            icon: Icons.graphic_eq,
                            label: isSensorFeedWorking
                                ? _noiseLabel()
                                : 'Noise sensor issue',
                            color: !isSensorFeedWorking
                                ? AppColors.energyDanger
                                : _sensorData.noise == 1
                                ? AppColors.energyWarning
                                : Colors.blueGrey,
                          ),
                        ],
                      ),
                      const SizedBox(height: 16),
                      GridView.count(
                        crossAxisCount: 2,
                        crossAxisSpacing: 10,
                        mainAxisSpacing: 10,
                        childAspectRatio: 1.25,
                        shrinkWrap: true,
                        physics: const NeverScrollableScrollPhysics(),
                        children: [
                          _buildSensorStatCard(
                            icon: Icons.thermostat,
                            title: 'Temperature',
                            value: isSensorFeedWorking
                                ? '${_sensorData.temperature.toStringAsFixed(1)} C'
                                : 'Offline',
                            color:
                                isSensorFeedWorking &&
                                    _sensorData.isComfortableTemp
                                ? AppColors.energySafe
                                : AppColors.energyDanger,
                          ),
                          _buildSensorStatCard(
                            icon: Icons.water_drop,
                            title: 'Humidity',
                            value: isSensorFeedWorking
                                ? '${_sensorData.humidity.toStringAsFixed(1)}%'
                                : 'Offline',
                            color:
                                isSensorFeedWorking &&
                                    _sensorData.isComfortableHumidity
                                ? AppColors.energySafe
                                : AppColors.energyDanger,
                          ),
                          _buildSensorStatCard(
                            icon: Icons.air,
                            title: 'Air Quality',
                            value: isSensorFeedWorking
                                ? _airQualityLabel()
                                : 'Offline',
                            color: isSensorFeedWorking
                                ? _airQualityStatusColor()
                                : AppColors.energyDanger,
                          ),
                          _buildSensorStatCard(
                            icon: Icons.wb_incandescent_outlined,
                            title: 'Room Light',
                            value: isSensorFeedWorking
                                ? _sensorData.lightStatus
                                : 'Offline',
                            color:
                                isSensorFeedWorking &&
                                    _sensorData.lightStatus.toLowerCase() ==
                                        'bright'
                                ? Colors.amber.shade700
                                : isSensorFeedWorking
                                ? Colors.blueGrey
                                : AppColors.energyDanger,
                          ),
                          _buildSensorStatCard(
                            icon: Icons.graphic_eq,
                            title: 'Noise',
                            value: isSensorFeedWorking
                                ? '${_noiseLabel()} (${_sensorData.soundRaw})'
                                : 'Offline',
                            color: !isSensorFeedWorking
                                ? AppColors.energyDanger
                                : _sensorData.noise == 1
                                ? AppColors.energyWarning
                                : Colors.blueGrey,
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ),

              const SizedBox(height: 24),

              // Devices Section
              Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  _buildSectionTitle('Devices'),
                  TextButton.icon(
                    onPressed: () {
                      // TODO: Navigate to all devices
                    },
                    icon: const Icon(Icons.arrow_forward, size: 16),
                    label: const Text('View All'),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              if (_isDemoHome) ...[
                _buildModeNotice(
                  icon: Icons.lock_outline,
                  message:
                      'Test Home Mode: Device control is disabled because this home uses demo data.',
                  color: AppColors.energyWarning,
                ),
                const SizedBox(height: 12),
              ],
              if (_devices.isEmpty)
                _buildNoDevicesCard()
              else
                ..._devices.map(
                  (device) => Padding(
                    padding: const EdgeInsets.only(bottom: 12.0),
                    child: DeviceCard(
                      device: device,
                      onToggle: _deviceControlEnabled
                          ? (value) => _toggleDevice(device, value)
                          : null,
                      isCommandPending:
                          _pendingDeviceCommands.contains(device.id) ||
                          device.commandInProgress,
                      commandError: _deviceCommandErrors[device.id],
                      onTap: () {
                        // TODO: Navigate to device details
                      },
                    ),
                  ),
                ),

              const SizedBox(height: 24),

              // Emergency Button
              SizedBox(
                width: double.infinity,
                height: 56,
                child: ElevatedButton.icon(
                  onPressed: _deviceControlEnabled
                      ? _showEmergencyDialog
                      : null,
                  icon: const Icon(Icons.power_off, size: 24),
                  label: const Text(
                    'EMERGENCY SHUTDOWN',
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: AppColors.energyDanger,
                    foregroundColor: Colors.white,
                    shape: RoundedRectangleBorder(
                      borderRadius: BorderRadius.circular(12),
                    ),
                  ),
                ),
              ),

              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildNoLiveDataCard() {
    return Card(
      color: Colors.orange.shade50,
      child: const Padding(
        padding: EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.cloud_off_outlined, color: Colors.orange),
            SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Waiting for live Firebase data',
                    style: TextStyle(
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  SizedBox(height: 4),
                  Text(
                    'No local demo values are being shown. Pull to retry or check the Firebase connection.',
                    style: TextStyle(color: AppColors.textSecondary),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildControlModeCard() {
    final color = _controlMode.mode == 'auto'
        ? Colors.teal
        : _controlMode.mode == 'manual'
        ? Colors.blueGrey
        : AppColors.primary;

    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(Icons.tune, color: color),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    'Mode: ${_controlMode.label}',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                      color: color,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _controlMode.description,
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                  if (_settingsSummary.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text(
                      'Tariff ${_settingsSummary['cost_per_kwh'] ?? '--'} ${_settingsSummary['currency'] ?? 'BHD'}/kWh',
                      style: const TextStyle(
                        fontSize: 11,
                        color: AppColors.textSecondary,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                  ],
                ],
              ),
            ),
            IconButton(
              icon: const Icon(Icons.settings),
              onPressed: _showSettingsSheet,
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNextScheduleCard(ScheduleInfo schedule) {
    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            const Icon(
              Icons.event_available_outlined,
              color: AppColors.primary,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Next schedule: ${schedule.name} at ${schedule.time}',
                style: const TextStyle(
                  fontWeight: FontWeight.w800,
                  color: AppColors.textPrimary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildOccupancySummary() {
    final state = (_occupancy['state'] ?? 'unknown').toString();
    final label = state
        .split('_')
        .map((part) => part.isEmpty
            ? part
            : '${part[0].toUpperCase()}${part.substring(1)}')
        .join(' ');
    final confidence = _occupancy['confidence'] is num
        ? ((_occupancy['confidence'] as num).toDouble() * 100).round()
        : null;
    final reason = (_occupancy['reason'] ?? 'Waiting for occupancy analysis.')
        .toString();
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.primary.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.18)),
      ),
      child: Row(
        children: [
          const Icon(Icons.meeting_room_outlined, color: AppColors.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  confidence == null
                      ? 'Room Status: $label'
                      : 'Room Status: $label ($confidence%)',
                  style: const TextStyle(fontWeight: FontWeight.w800),
                ),
                const SizedBox(height: 3),
                Text(
                  reason,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildNumberField(TextEditingController controller, String label) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: TextField(
        controller: controller,
        keyboardType: const TextInputType.numberWithOptions(decimal: true),
        decoration: InputDecoration(
          labelText: label,
          border: const OutlineInputBorder(),
          isDense: true,
        ),
      ),
    );
  }

  Widget _buildScheduleTile(
    ScheduleInfo schedule, {
    required ValueChanged<bool> onChanged,
    required VoidCallback onRunNow,
    required VoidCallback onDelete,
  }) {
    final commandLabel = schedule.command == 'turn_on' ? 'On' : 'Off';
    return Card(
      elevation: 0,
      child: ListTile(
        leading: const Icon(Icons.schedule),
        title: Text(
          schedule.name,
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        subtitle: Text(
          '${schedule.deviceName} - $commandLabel at ${schedule.time} - ${schedule.days.join(', ')}',
        ),
        trailing: Wrap(
          spacing: 4,
          children: [
            IconButton(
              icon: const Icon(Icons.play_arrow),
              onPressed: onRunNow,
              tooltip: 'Run now',
            ),
            Switch(value: schedule.enabled, onChanged: onChanged),
            IconButton(
              icon: const Icon(Icons.delete_outline),
              onPressed: onDelete,
              tooltip: 'Delete',
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildModeOptionTile({
    required ControlModeOption option,
    required bool isSelected,
    required bool isBusy,
    required VoidCallback onSelected,
  }) {
    return Card(
      elevation: isSelected ? 2 : 0,
      color: isSelected
          ? AppColors.primary.withValues(alpha: 0.08)
          : Colors.white,
      child: ListTile(
        enabled: !isBusy,
        onTap: isBusy ? null : onSelected,
        leading: Icon(
          isSelected ? Icons.radio_button_checked : Icons.radio_button_off,
          color: isSelected ? AppColors.primary : AppColors.textSecondary,
        ),
        title: Row(
          children: [
            Text(
              option.label,
              style: const TextStyle(fontWeight: FontWeight.w800),
            ),
            if (option.mode == 'assist') ...[
              const SizedBox(width: 8),
              _buildInsightPill(
                icon: Icons.recommend_outlined,
                label: 'Recommended',
                color: AppColors.primary,
              ),
            ],
          ],
        ),
        subtitle: Text(option.description),
      ),
    );
  }

  Widget _buildActionSuggestionCard(ActionSuggestion suggestion) {
    final actionText = suggestion.suggestedCommand == 'turn_off'
        ? 'Turn Off'
        : 'Turn On';
    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Icon(
                  Icons.auto_awesome_outlined,
                  color: AppColors.primary,
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    '${suggestion.deviceName} may be wasting energy.',
                    style: const TextStyle(
                      fontSize: 15,
                      fontWeight: FontWeight.w800,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Text(suggestion.reason),
            const SizedBox(height: 12),
            Row(
              children: [
                ElevatedButton(
                  onPressed: () => _approveSuggestion(suggestion),
                  child: Text(actionText),
                ),
                const SizedBox(width: 10),
                OutlinedButton(
                  onPressed: () => _dismissSuggestion(suggestion),
                  child: const Text('Dismiss'),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAutomationLogCard(AutomationLog log) {
    final actionText = log.command == 'turn_off' ? 'turned off' : 'turned on';
    return Card(
      color: Colors.teal.shade50,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.bolt_outlined, color: Colors.teal),
            const SizedBox(width: 10),
            Expanded(
              child: Text(
                'Auto Mode $actionText ${log.deviceName} because ${log.reason.toLowerCase()}',
                style: const TextStyle(
                  fontWeight: FontWeight.w700,
                  color: AppColors.textPrimary,
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildNoDevicesCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(
              Icons.power_settings_new,
              color: AppColors.textSecondary,
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'No live devices loaded',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    _loadError == null
                        ? 'Waiting for breaker data from Firebase.'
                        : 'Breaker cards will appear after Firebase loads successfully.',
                    style: const TextStyle(color: AppColors.textSecondary),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSectionTitle(String title) {
    return Text(
      title,
      style: const TextStyle(
        fontSize: 20,
        fontWeight: FontWeight.bold,
        color: AppColors.textPrimary,
      ),
    );
  }

  Widget _buildHomeSelectorCard() {
    final selectedHome = _selectedHome;
    final selectedScenario = _demoScenarios.where(
      (scenario) => scenario.id == _selectedScenarioId,
    );

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Expanded(
                  child: SegmentedButton<String>(
                    segments: _homeChoices
                        .map(
                          (home) => ButtonSegment<String>(
                            value: home.id,
                            label: Text(home.label),
                            icon: Icon(
                              home.isDemo
                                  ? Icons.science_outlined
                                  : Icons.home_outlined,
                            ),
                          ),
                        )
                        .toList(),
                    selected: {_selectedHomeId},
                    onSelectionChanged: (selection) {
                      _selectHome(selection.first);
                    },
                  ),
                ),
                const SizedBox(width: 10),
                _buildStatusChip(
                  icon: selectedHome.isDemo
                      ? Icons.science_outlined
                      : Icons.verified_outlined,
                  label: selectedHome.badge,
                  color: selectedHome.isDemo
                      ? Colors.indigo
                      : AppColors.primary,
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              selectedHome.description,
              style: const TextStyle(
                fontSize: 12,
                color: AppColors.textSecondary,
                fontWeight: FontWeight.w600,
              ),
            ),
            if (_isDemoHome) ...[
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                key: ValueKey(_selectedScenarioId ?? 'scenario_none'),
                initialValue: _selectedScenarioId,
                isExpanded: true,
                decoration: const InputDecoration(
                  labelText: 'Demo scenario',
                  border: OutlineInputBorder(),
                  isDense: true,
                ),
                items: _demoScenarios
                    .map(
                      (scenario) => DropdownMenuItem<String>(
                        value: scenario.id,
                        child: Text(scenario.name),
                      ),
                    )
                    .toList(),
                onChanged: _demoScenarios.isEmpty ? null : _selectScenario,
              ),
              if (selectedScenario.isNotEmpty ||
                  (_activeScenarioName?.isNotEmpty ?? false)) ...[
                const SizedBox(height: 8),
                Text(
                  selectedScenario.isNotEmpty
                      ? selectedScenario.first.description
                      : _activeScenarioDescription ?? _activeScenarioName!,
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ],
            const SizedBox(height: 12),
            FilledButton.icon(
              icon: const Icon(Icons.chat_bubble_outline),
              label: const Text('Smart Energy Chatbot'),
              onPressed: () {
                Navigator.of(context).push(
                  MaterialPageRoute(
                    builder: (_) => AiChatbotScreen(
                      homeId: _selectedHomeId,
                      homeName: selectedHome.label,
                      scenarioId: _isDemoHome ? _selectedScenarioId : null,
                      scenarioName: _isDemoHome ? _activeScenarioName : null,
                    ),
                  ),
                );
              },
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildModeNotice({
    required IconData icon,
    required String message,
    required Color color,
  }) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.09),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        children: [
          Icon(icon, color: color, size: 18),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              message,
              style: TextStyle(
                color: color,
                fontWeight: FontWeight.w700,
                fontSize: 12,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAiDashboardCard() {
    final ai = _aiDashboard;
    if (ai == null) {
      return _buildAiPendingCard(
        icon: Icons.auto_awesome_outlined,
        title: 'AI analysis pending',
        message: 'Cloud AI has not published a dashboard summary yet.',
      );
    }

    final scoreColor = _efficiencyColor(ai.efficiencyScore);
    final statusColor = _aiStatusColor(ai.statusTone, ai.statusCode);

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: scoreColor.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(Icons.psychology_alt_outlined, color: scoreColor),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'AI Status: ${ai.statusLabel}',
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          color: statusColor,
                        ),
                      ),
                      Text(
                        'Updated ${DateFormat('MMM d, HH:mm').format(ai.updatedAt)}',
                        style: const TextStyle(
                          fontSize: 12,
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                _buildInsightPill(
                  icon: Icons.auto_awesome_outlined,
                  label: _prettyLabel(ai.statusCode),
                  color: statusColor,
                ),
              ],
            ),
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: statusColor.withValues(alpha: 0.08),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: statusColor.withValues(alpha: 0.20)),
              ),
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Icon(Icons.insights_outlined, color: statusColor),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          ai.statusSummary,
                          style: TextStyle(
                            fontSize: 13,
                            fontWeight: FontWeight.w800,
                            color: statusColor,
                          ),
                        ),
                        const SizedBox(height: 5),
                        Text(
                          ai.explanation,
                          style: const TextStyle(
                            fontSize: 13,
                            height: 1.35,
                            color: AppColors.textPrimary,
                          ),
                        ),
                      ],
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: _buildAiMetricTile(
                    title: 'Efficiency',
                    value: ai.efficiencyScore.toStringAsFixed(0),
                    unit: '/100',
                    icon: Icons.speed_outlined,
                    color: scoreColor,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: _buildAiMetricTile(
                    title: 'Next Hour',
                    value: ai.nextHourEnergyKwh.toStringAsFixed(2),
                    unit: 'kWh',
                    icon: Icons.bolt_outlined,
                    color: AppColors.primary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _buildInsightPill(
                  icon: ai.energyWaste
                      ? Icons.warning_amber_rounded
                      : Icons.check_circle_outline,
                  label: ai.energyWaste
                      ? 'Energy waste detected (${_asPercent(ai.wasteConfidence)})'
                      : 'No energy waste',
                  color: ai.energyWaste
                      ? AppColors.energyWarning
                      : AppColors.energySafe,
                ),
                _buildInsightPill(
                  icon: Icons.payments_outlined,
                  label: '${ai.nextHourCostBhd.toStringAsFixed(3)} BD next hour',
                  color: Colors.indigo,
                ),
                _buildInsightPill(
                  icon: Icons.tips_and_updates_outlined,
                  label: ai.actionTitle,
                  color: statusColor,
                ),
              ],
            ),
            if (ai.controlSuggestion.isNotEmpty) ...[
              const SizedBox(height: 10),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: AppColors.primary.withValues(alpha: 0.08),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(
                    color: AppColors.primary.withValues(alpha: 0.20),
                  ),
                ),
                child: Text(
                  ai.controlSuggestion,
                  style: const TextStyle(
                    fontSize: 13,
                    fontWeight: FontWeight.w600,
                    color: AppColors.primaryDark,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  Widget _buildAiDailySummaryCard() {
    final summary = _aiDailySummary;
    if (summary == null) {
      return _buildAiPendingCard(
        icon: Icons.today_outlined,
        title: 'Daily AI summary pending',
        message: 'Today has no AI summary yet.',
      );
    }

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                const Expanded(
                  child: Text(
                    'AI Daily Summary',
                    style: TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ),
                Text(
                  DateFormat('MMM d').format(summary.updatedAt),
                  style: const TextStyle(
                    fontSize: 12,
                    color: AppColors.textSecondary,
                  ),
                ),
              ],
            ),
            const SizedBox(height: 10),
            Text(
              summary.summary,
              style: const TextStyle(
                fontSize: 14,
                height: 1.35,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _buildInsightPill(
                  icon: Icons.fact_check_outlined,
                  label: '${summary.predictionCount} AI checks today',
                  color: AppColors.primary,
                ),
                _buildInsightPill(
                  icon: Icons.flash_on_outlined,
                  label: '${summary.wastePredictionCount} waste moments',
                  color: AppColors.energyWarning,
                ),
                _buildInsightPill(
                  icon: Icons.timeline_outlined,
                  label:
                      '${summary.abnormalPredictionCount} unusual moments',
                  color: Colors.deepOrange,
                ),
                _buildInsightPill(
                  icon: Icons.speed_outlined,
                  label:
                      '${summary.averageEfficiencyScore.toStringAsFixed(0)} average score',
                  color: _efficiencyColor(summary.averageEfficiencyScore),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAiRecommendationCard(AiRecommendation recommendation) {
    final color = _priorityColor(recommendation.priority);
    final isDataCheck =
        recommendation.type.toLowerCase() == 'device_health' ||
        recommendation.recommendationType.toLowerCase().contains('check_');
    final title = isDataCheck ? 'AI Data Check' : 'Recommended Action';

    return Card(
      elevation: 2,
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: color.withValues(alpha: 0.10),
                    borderRadius: BorderRadius.circular(10),
                  ),
                  child: Icon(
                    isDataCheck
                        ? Icons.sensors_outlined
                        : Icons.tips_and_updates_outlined,
                    color: color,
                  ),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        title,
                        style: TextStyle(
                          fontSize: 16,
                          fontWeight: FontWeight.w800,
                          color: color,
                        ),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        recommendation.title,
                        style: const TextStyle(
                          fontSize: 12,
                          fontWeight: FontWeight.w700,
                          color: AppColors.textSecondary,
                        ),
                      ),
                    ],
                  ),
                ),
                _buildInsightPill(
                  icon: Icons.flag_outlined,
                  label: _prettyLabel(recommendation.priority),
                  color: color,
                ),
              ],
            ),
            const SizedBox(height: 12),
            Text(
              recommendation.message,
              style: const TextStyle(
                fontSize: 14,
                height: 1.35,
                color: AppColors.textPrimary,
              ),
            ),
            const SizedBox(height: 12),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                _buildSourceChip('Smart Energy AI'),
                _buildInsightPill(
                  icon: isDataCheck
                      ? Icons.sync_problem_outlined
                      : Icons.offline_bolt_outlined,
                  label: isDataCheck
                      ? 'Data quality'
                      : _prettyLabel(recommendation.recommendationType),
                  color: color,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAiAlertCard() {
    final alert = _aiAlert;
    if (alert == null) {
      return Container(
        width: double.infinity,
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: AppColors.energySafe.withValues(alpha: 0.10),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(
            color: AppColors.energySafe.withValues(alpha: 0.25),
          ),
        ),
        child: const Row(
          children: [
            Icon(Icons.check_circle_outline, color: AppColors.energySafe),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                'AI abnormal usage state is normal.',
                style: TextStyle(
                  fontSize: 13,
                  fontWeight: FontWeight.w600,
                  color: AppColors.energySafe,
                ),
              ),
            ),
          ],
        ),
      );
    }

    final color = _priorityColor(alert.priority);
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.30)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.online_prediction_outlined, color: color),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  alert.title,
                  style: TextStyle(
                    fontSize: 15,
                    fontWeight: FontWeight.w800,
                    color: color,
                  ),
                ),
                const SizedBox(height: 4),
                const Text(
                  'AI-detected abnormal usage. Safety and device-health alerts still come from the rule-based backend.',
                  style: TextStyle(
                    fontSize: 12,
                    color: AppColors.textSecondary,
                  ),
                ),
                const SizedBox(height: 8),
                Text(
                  alert.message,
                  style: const TextStyle(
                    fontSize: 13,
                    height: 1.35,
                    color: AppColors.textPrimary,
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAiPendingCard({
    required IconData icon,
    required String title,
    required String message,
  }) {
    return Card(
      elevation: 1,
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(icon, color: AppColors.textSecondary),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 2),
                  Text(
                    message,
                    style: const TextStyle(
                      fontSize: 12,
                      color: AppColors.textSecondary,
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildAiMetricTile({
    required IconData icon,
    required String title,
    required String value,
    required String unit,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.09),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: color.withValues(alpha: 0.18)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, size: 19, color: color),
          const SizedBox(height: 7),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: Text.rich(
              TextSpan(
                text: value,
                children: [
                  if (unit.isNotEmpty)
                    TextSpan(
                      text: ' $unit',
                      style: const TextStyle(
                        fontSize: 12,
                        fontWeight: FontWeight.w600,
                      ),
                    ),
                ],
              ),
              maxLines: 1,
              style: TextStyle(
                fontSize: 16,
                fontWeight: FontWeight.w800,
                color: color,
              ),
            ),
          ),
          const SizedBox(height: 2),
          Text(
            title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: const TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w600,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSourceChip(String label) {
    return _buildInsightPill(
      icon: Icons.auto_awesome_outlined,
      label: label,
      color: Colors.teal,
    );
  }

  Widget _buildInsightPill({
    required IconData icon,
    required String label,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.11),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.24)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 13, color: color),
          const SizedBox(width: 5),
          Text(
            label,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.w700,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatusChip({
    required IconData icon,
    required String label,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.25)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 14, color: color),
          const SizedBox(width: 6),
          Text(
            label,
            style: TextStyle(
              fontSize: 12,
              fontWeight: FontWeight.w600,
              color: color,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSensorStatCard({
    required IconData icon,
    required String title,
    required String value,
    required Color color,
  }) {
    return Container(
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.10),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.20)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          Icon(icon, color: color, size: 20),
          const SizedBox(height: 8),
          FittedBox(
            fit: BoxFit.scaleDown,
            alignment: Alignment.centerLeft,
            child: ConstrainedBox(
              constraints: const BoxConstraints(minWidth: 1),
              child: Text(
                value,
                maxLines: 2,
                style: TextStyle(
                  fontSize: 15,
                  fontWeight: FontWeight.bold,
                  color: color,
                ),
              ),
            ),
          ),
          const SizedBox(height: 2),
          Text(
            title,
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 12,
              color: Colors.grey[700],
              fontWeight: FontWeight.w500,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildAlertCard(Alert alert) {
    final color = _severityColor(alert.severity);

    return Container(
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: color.withValues(alpha: 0.35)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Icon(Icons.notification_important_outlined, color: color),
              const SizedBox(width: 8),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      alert.message,
                      style: TextStyle(
                        fontWeight: FontWeight.w700,
                        color: color,
                        fontSize: 15,
                      ),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      DateFormat('HH:mm').format(alert.timestamp),
                      style: TextStyle(color: Colors.grey[700], fontSize: 12),
                    ),
                  ],
                ),
              ),
              IconButton(
                icon: const Icon(Icons.close),
                color: Colors.grey[700],
                onPressed: () {
                  setState(() {
                    _alerts.removeWhere((item) => item.id == alert.id);
                  });
                },
              ),
            ],
          ),
          if (_controlMode.mode == 'assist' && _isLightWasteAlert(alert)) ...[
            const SizedBox(height: 10),
            const Text(
              'No one is in the room. Do you want to turn off the lights?',
              style: TextStyle(fontWeight: FontWeight.w600),
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                OutlinedButton(
                  onPressed: () {
                    // TODO: Implement lights off control.
                  },
                  child: const Text('Yes'),
                ),
                const SizedBox(width: 10),
                TextButton(
                  onPressed: () {
                    // TODO: Implement dismiss/ignore action.
                  },
                  child: const Text('No'),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }

  bool _isLightWasteAlert(Alert alert) {
    final type = alert.backendType.toLowerCase();
    final text = alert.message.toLowerCase();
    return type == 'energy_waste' ||
        (text.contains('lights') && text.contains('empty'));
  }

  Color _efficiencyColor(double score) {
    if (score >= 80) {
      return AppColors.energySafe;
    }
    if (score >= 55) {
      return AppColors.energyWarning;
    }
    return AppColors.energyDanger;
  }

  Color _priorityColor(String priority) {
    switch (priority.toLowerCase()) {
      case 'critical':
      case 'high':
        return Colors.deepOrange;
      case 'medium':
        return AppColors.energyWarning;
      case 'low':
        return Colors.blue;
      default:
        return Colors.teal;
    }
  }

  List<ActionSuggestion> _dedupeActionSuggestions(
    List<ActionSuggestion> suggestions,
  ) {
    final seen = <String>{};
    final deduped = <ActionSuggestion>[];
    for (final suggestion in suggestions) {
      final key =
          '${suggestion.deviceId}|${suggestion.suggestedCommand}|${suggestion.reason}';
      if (seen.add(key)) {
        deduped.add(suggestion);
      }
    }
    return deduped;
  }

  void _removeMatchingSuggestions(ActionSuggestion suggestion) {
    setState(() {
      _actionSuggestions = _actionSuggestions.where((item) {
        final sameDevice = item.deviceId == suggestion.deviceId;
        final sameCommand = item.suggestedCommand == suggestion.suggestedCommand;
        final sameReason = item.reason == suggestion.reason;
        return item.id != suggestion.id &&
            !(sameDevice && sameCommand && sameReason);
      }).toList();
    });
  }

  Future<void> _sendEmergencyDeviceCommand(String deviceId) async {
    try {
      final result = await _firebaseRealtimeService.sendDeviceCommand(
        deviceId,
        'turn_off',
        homeId: _selectedHomeId,
        emergency: true,
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(result.message)));
      await _refreshData(showErrorSnackBar: false);
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Emergency command failed: $error')),
      );
    }
  }

  Map<String, dynamic>? _activeSmokeCriticalAlert() {
    if (_smokeClearedForPopup()) {
      return null;
    }
    for (final alert in _criticalAlerts) {
      final alertType =
          (alert['alert_type'] ?? alert['subtype'] ?? alert['type'] ?? '')
              .toString()
              .toLowerCase();
      final status = (alert['status'] ?? 'active').toString().toLowerCase();
      if (status == 'active' && alertType.contains('smoke')) {
        return alert;
      }
    }
    final emergency = (_safety['emergency_mode'] is Map)
        ? Map<String, dynamic>.from(_safety['emergency_mode'] as Map)
        : const <String, dynamic>{};
    if (emergency['active'] == true && emergency['reason'] == 'smoke_detected') {
      return {
        'alert_id': 'smoke_detected_room1',
        'title': 'Smoke/Gas Detected',
        'message':
            emergency['message'] ??
            'Smoke or gas was detected in Room 1. Check immediately.',
      };
    }
    return null;
  }

  bool _smokeClearedForPopup() {
    final clearStartedAt = _smokeClearStartedAtMs;
    if (clearStartedAt != null &&
        DateTime.now().millisecondsSinceEpoch - clearStartedAt >= 15000) {
      return true;
    }
    final currentSmokeStatus = _sensorData.smokeStatus.toLowerCase();
    final currentSmokeClear = currentSmokeStatus.contains('clear');
    if (currentSmokeClear &&
        DateTime.now().millisecondsSinceEpoch -
                _sensorData.timestamp.millisecondsSinceEpoch >=
            15000) {
      return true;
    }
    final smokeState = (_safety['smoke_state'] is Map)
        ? Map<String, dynamic>.from(_safety['smoke_state'] as Map)
        : const <String, dynamic>{};
    final status = (smokeState['status'] ?? '').toString().toLowerCase();
    if (status != 'clear') {
      return false;
    }
    final clearAt = _asIntValue(smokeState['last_clear_at_ms']);
    if (clearAt == null) {
      return false;
    }
    return DateTime.now().millisecondsSinceEpoch - clearAt >= 15000;
  }

  void _updateSmokeClearTimer(SensorData sensors) {
    final status = sensors.smokeStatus.toLowerCase();
    final smokeDetected =
        status.contains('detect') ||
        status.contains('smoke') ||
        status.contains('gas');
    if (smokeDetected) {
      _smokeClearStartedAtMs = null;
      return;
    }
    if (status.contains('clear') && _smokeClearStartedAtMs == null) {
      final sensorAgeMs =
          DateTime.now().millisecondsSinceEpoch -
          sensors.timestamp.millisecondsSinceEpoch;
      _smokeClearStartedAtMs = sensorAgeMs >= 15000
          ? sensors.timestamp.millisecondsSinceEpoch
          : DateTime.now().millisecondsSinceEpoch;
    }
  }

  int? _asIntValue(dynamic value) {
    if (value is int) {
      return value;
    }
    if (value is double) {
      return value.round();
    }
    return int.tryParse(value?.toString() ?? '');
  }

  void _showEmergencyPopupIfNeeded() {
    final alert = _activeSmokeCriticalAlert();
    if (alert == null || !mounted) {
      _shownEmergencyAlertId = null;
      if (_smokeEmergencyDialogOpen && mounted) {
        Navigator.of(context, rootNavigator: true).pop();
        _smokeEmergencyDialogOpen = false;
      }
      return;
    }
    final alertId = (alert['alert_id'] ?? alert['id'] ?? 'smoke_detected_room1')
        .toString();
    if (_shownEmergencyAlertId == alertId) {
      return;
    }
    _shownEmergencyAlertId = alertId;
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!mounted) {
        return;
      }
      _showSmokeEmergencyDialog(alert);
    });
  }

  Future<void> _showSmokeEmergencyDialog(Map<String, dynamic> alert) async {
    if (_smokeEmergencyDialogOpen) {
      return;
    }
    _smokeEmergencyDialogOpen = true;
    await showDialog<void>(
      context: context,
      barrierDismissible: false,
      builder: (dialogContext) {
        final title = (alert['title'] ?? 'Smoke/Gas Detected').toString();
        final message =
            (alert['message'] ??
                    'Smoke or gas was detected in Room 1. Check immediately.')
                .toString();
        return AlertDialog(
          backgroundColor: Colors.red.shade50,
          title: Row(
            children: [
              Icon(Icons.warning_amber_rounded, color: Colors.red.shade700),
              const SizedBox(width: 8),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(
                    color: Colors.red.shade700,
                    fontWeight: FontWeight.w900,
                  ),
                ),
              ),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.stretch,
            children: [
              Text(message),
              const SizedBox(height: 12),
              const Text(
                'Normal automation and schedules are paused. Use emergency actions only if it is safe.',
                style: TextStyle(fontWeight: FontWeight.w700),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                await _sendEmergencyDeviceCommand('breaker_01');
              },
              child: const Text('Turn Off Switch Breaker'),
            ),
            TextButton(
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                await _sendEmergencyDeviceCommand('breaker_02');
              },
              child: const Text('Turn Off AC Breaker'),
            ),
            ElevatedButton.icon(
              style: ElevatedButton.styleFrom(
                backgroundColor: Colors.red.shade700,
                foregroundColor: Colors.white,
              ),
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                final result = await _firebaseRealtimeService.turnOffSafeDevices(
                  homeId: _selectedHomeId,
                );
                if (!mounted) {
                  return;
                }
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(
                      (result['message'] ??
                              'Emergency shutdown commands requested.')
                          .toString(),
                    ),
                  ),
                );
                await _refreshData(showErrorSnackBar: false);
              },
              icon: const Icon(Icons.power_settings_new),
              label: const Text('Turn Off All Safe Devices'),
            ),
            OutlinedButton(
              onPressed: () async {
                Navigator.of(dialogContext).pop();
                final result = await _firebaseRealtimeService.markSmokeSafe(
                  homeId: _selectedHomeId,
                );
                if (!mounted) {
                  return;
                }
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(result['message'].toString())),
                );
                await _refreshData(showErrorSnackBar: false);
              },
              child: const Text('I Checked - Mark Safe'),
            ),
          ],
        );
      },
    );
    _smokeEmergencyDialogOpen = false;
  }

  Color _aiStatusColor(String tone, String code) {
    switch (tone.toLowerCase()) {
      case 'safe':
        return AppColors.energySafe;
      case 'warning':
        return AppColors.energyWarning;
      case 'danger':
        return AppColors.energyDanger;
    }
    switch (code.toLowerCase()) {
      case 'normal':
        return AppColors.energySafe;
      case 'needs_data':
      case 'possible_waste':
        return AppColors.energyWarning;
      case 'likely_waste':
        return AppColors.energyDanger;
      default:
        return AppColors.primary;
    }
  }

  String _asPercent(double value) {
    final normalized = value <= 1 ? value * 100 : value;
    return '${normalized.clamp(0, 100).toStringAsFixed(0)}%';
  }

  String _prettyLabel(String value) {
    final normalized = value.trim();
    if (normalized.isEmpty) {
      return 'General';
    }
    return normalized
        .replaceAll('_', ' ')
        .split(' ')
        .where((part) => part.isNotEmpty)
        .map((part) => '${part[0].toUpperCase()}${part.substring(1)}')
        .join(' ');
  }

  Color _severityColor(String severity) {
    switch (severity.toLowerCase()) {
      case 'critical':
        return AppColors.energyDanger;
      case 'high':
        return Colors.deepOrange;
      case 'medium':
        return AppColors.energyWarning;
      case 'low':
        return Colors.blue;
      default:
        return Colors.grey;
    }
  }

  Color _airQualityColor(double eco2) {
    if (eco2 <= 800) {
      return AppColors.energySafe;
    }
    if (eco2 <= 1200) {
      return AppColors.energyWarning;
    }
    return AppColors.energyDanger;
  }

  Color _tvocColor(double tvoc) {
    if (tvoc <= 65) {
      return AppColors.energySafe;
    }
    if (tvoc <= 220) {
      return AppColors.energyWarning;
    }
    return AppColors.energyDanger;
  }

  Color _aqiColor(int aqi) {
    if (aqi <= 1) {
      return AppColors.energySafe;
    }
    if (aqi <= 3) {
      return AppColors.energyWarning;
    }
    return AppColors.energyDanger;
  }

  String _airQualityLabel() {
    final eco2Status = _airQualityColor(_sensorData.eco2);
    final tvocStatus = _tvocColor(_sensorData.tvoc);
    final aqiStatus = _aqiColor(_sensorData.aqi);

    if (eco2Status == AppColors.energyDanger ||
        tvocStatus == AppColors.energyDanger ||
        aqiStatus == AppColors.energyDanger) {
      return 'Poor';
    }

    if (eco2Status == AppColors.energyWarning ||
        tvocStatus == AppColors.energyWarning ||
        aqiStatus == AppColors.energyWarning) {
      return 'Moderate';
    }

    return 'Good';
  }

  String _noiseLabel() {
    final status = _sensorData.noiseStatus.trim();
    if (status.isNotEmpty && status.toLowerCase() != 'unknown') {
      return status;
    }
    return _sensorData.noise == 1 ? 'Noise' : 'Quiet';
  }

  Color _airQualityStatusColor() {
    switch (_airQualityLabel()) {
      case 'Poor':
        return AppColors.energyDanger;
      case 'Moderate':
        return AppColors.energyWarning;
      default:
        return AppColors.energySafe;
    }
  }

  String _roomComfortMessage() {
    if (_isSensorFeedStale()) {
      return 'Sensor feed is offline. Room conditions are not current.';
    }

    if (_sensorData.smokeStatus.toLowerCase() != 'clear') {
      return 'Attention: smoke condition should be checked.';
    }

    if (!_sensorData.isComfortableTemp || !_sensorData.isComfortableHumidity) {
      return 'Room needs adjustment for better comfort.';
    }

    return 'Room conditions look good.';
  }

  Color _roomComfortColor() {
    if (_isSensorFeedStale()) {
      return AppColors.energyDanger;
    }

    if (_sensorData.smokeStatus.toLowerCase() != 'clear') {
      return AppColors.energyDanger;
    }

    if (!_sensorData.isComfortableTemp || !_sensorData.isComfortableHumidity) {
      return AppColors.energyWarning;
    }

    return AppColors.energySafe;
  }

  IconData _roomComfortIcon() {
    if (_isSensorFeedStale()) {
      return Icons.sensors_off_outlined;
    }

    if (_sensorData.smokeStatus.toLowerCase() != 'clear') {
      return Icons.report_problem_outlined;
    }

    if (!_sensorData.isComfortableTemp || !_sensorData.isComfortableHumidity) {
      return Icons.tune;
    }

    return Icons.check_circle_outline;
  }

  void _showEmergencyDialog() {
    showDialog(
      context: context,
      builder: (context) => AlertDialog(
        title: const Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: AppColors.energyDanger),
            SizedBox(width: 8),
            Text('Emergency Shutdown'),
          ],
        ),
        content: const Text(
          'This will immediately shut down all electrical branches. '
          'Are you sure you want to proceed?',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(context);
              _performEmergencyShutdown();
            },
            style: ElevatedButton.styleFrom(
              backgroundColor: AppColors.energyDanger,
              foregroundColor: Colors.white,
            ),
            child: const Text('Shutdown'),
          ),
        ],
      ),
    );
  }

  Future<void> _performEmergencyShutdown() async {
    if (!_deviceControlEnabled || _isDemoHome) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Emergency shutdown is disabled in Home Test mode.'),
        ),
      );
      return;
    }

    final controllableDevices = _devices.where(
      (device) => _isControllableBreaker(device.id),
    );

    for (final device in controllableDevices) {
      await _sendDeviceCommand(device.id, 'turn_off');
    }

    if (!mounted) {
      return;
    }

    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(
        content: Text('Emergency shutdown commands sent.'),
        backgroundColor: AppColors.energyDanger,
        duration: Duration(seconds: 3),
      ),
    );
  }
}
