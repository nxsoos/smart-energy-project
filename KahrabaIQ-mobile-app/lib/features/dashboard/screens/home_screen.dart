import 'dart:async';
import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../core/utils/app_routes.dart';
import '../../../core/utils/constants.dart';
import '../../../core/widgets/alert_banner.dart';
import '../../../core/widgets/app_state_widgets.dart';
import '../../../shared/models/alert.dart';
import '../../../shared/models/device.dart';
import '../../../shared/models/energy_reading.dart';
import '../../../shared/models/sensor_data.dart';
import '../../../shared/services/auth_service.dart';
import '../../../shared/services/kahrabaiq_api_service.dart';
import '../../../shared/services/notification_service.dart';
import '../../ai_chat/screens/ai_chatbot_screen.dart';
import '../../demo/demo_scenarios.dart';
import '../../demo/widgets/demo_scenario_selector.dart';
import '../../pairing/screens/qr_scanner_screen.dart';
import '../../sensors/screens/sensors_status_screen.dart';
import 'breakers_screen.dart';
import 'global_admin_screen.dart';
import 'home_admin_panel_screen.dart';
import 'home_settings_screen.dart';
import 'notifications_screen.dart';
import '../widgets/ai_insights_banner.dart';
import '../widgets/dashboard_header.dart';
import '../widgets/devices_section.dart';
import '../widgets/energy_hero_card.dart';
import '../widgets/quick_stats_row.dart';

/// Premium KahrabaIQ dashboard experience.
class HomeScreen extends StatefulWidget {
  const HomeScreen({super.key, this.enableRealtimeSync = true});

  final bool enableRealtimeSync;

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  static const String _dashboardCachePrefix = 'kahrabaiq.dashboard.cache.';
  static const Duration _optimisticCommandHold = Duration(seconds: 12);

  final KahrabaIqApiService _api = KahrabaIqApiService();
  String? _homeId;
  String? _currentUserUid;
  UserHomeAccess? _currentHomeAccess;
  bool _isPlatformAdmin = false;
  DashboardData? _dashboard;
  StreamSubscription<DashboardData>? _liveSubscription;
  bool _isLoading = true;
  bool _isPairing = false;
  String? _error;
  String? _dashboardNotice;
  DemoScenarioData? _selectedDemoScenario;
  bool _scenarioAiBusy = false;
  final Set<String> _localPendingCommands = {};
  final Map<String, String> _localCommandErrors = {};
  final Map<String, bool> _localOptimisticDeviceStates = {};
  final Map<String, DateTime> _localOptimisticDeviceStartedAt = {};
  final Set<String> _dismissedAlertIds = {};
  final Set<String> _notifiedSmokeAlertIds = {};
  bool _smokeDialogVisible = false;

  @override
  void initState() {
    super.initState();
    _loadDashboard();
  }

  @override
  void dispose() {
    _liveSubscription?.cancel();
    super.dispose();
  }

  Future<void> _loadDashboard() async {
    if (_selectedDemoScenario != null) {
      setState(() {
        _dashboard = _selectedDemoScenario!.dashboard;
        _isLoading = false;
        _error = null;
        _dashboardNotice =
            'Simulation Mode is active. Live home data and device control are paused.';
      });
      return;
    }
    await _liveSubscription?.cancel();
    if (_dashboard == null) {
      final cached = await _loadCachedDashboard();
      if (mounted && cached != null) {
        final cachedForDisplay = _dashboardForCacheRestore(cached);
        debugPrint(
          '[KahrabaIQ DASHBOARD CACHE] restored cached dashboard '
          'home=${_homeId ?? NetworkConfig.defaultHomeId} '
          'power=${cached.reading.power} devices=${cached.devices.length}',
        );
        setState(() {
          _dashboard = cachedForDisplay;
          _isLoading = false;
          _dashboardNotice = _feedPauseNotice(cachedForDisplay);
        });
      }
    }
    setState(() {
      _isLoading = _dashboard == null;
      _error = null;
      _dashboardNotice = _dashboard == null
          ? 'Loading latest dashboard...'
          : _feedPauseNotice(_dashboard!);
    });

    String? pairedHomeId;
    if (!NetworkConfig.useCognitoAuth) {
      pairedHomeId = NetworkConfig.defaultHomeId;
      setState(() {
        _homeId = pairedHomeId;
        _currentUserUid = null;
        _currentHomeAccess = null;
        _isPlatformAdmin = false;
      });
    } else {
      try {
        final profile = await AuthService().loadCurrentUserProfile();
        final selectedHome = _selectPairedHome(profile);
        pairedHomeId = selectedHome?.homeId;
        if (!mounted) {
          return;
        }
        setState(() {
          _homeId = pairedHomeId;
          _currentUserUid = profile.uid;
          _currentHomeAccess = selectedHome;
          _isPlatformAdmin = profile.isPlatformAdmin;
        });
        if (pairedHomeId == null || pairedHomeId.isEmpty) {
          setState(() {
            _dashboard = null;
            _isLoading = false;
            _error = null;
          });
          return;
        }
      } catch (error) {
        debugPrint('[KahrabaIQ PROFILE ERROR] $error');
        if (!mounted) {
          return;
        }
        setState(() {
          _isLoading = false;
          _error =
              'Could not load your home pairing. Please sign in again or check the backend connection.';
        });
        return;
      }
    }

    try {
      debugPrint(
        '[KahrabaIQ DASHBOARD API] fetching snapshot home=$pairedHomeId',
      );
      final dashboard = await _api.fetchDashboardData(homeId: pairedHomeId);
      debugPrint(
        '[KahrabaIQ DASHBOARD API] snapshot received '
        'power=${dashboard.reading.power} month=${dashboard.reading.energyMonth} '
        'devices=${dashboard.devices.length}',
      );
      _applyDashboardData(dashboard);
    } catch (error) {
      debugPrint('[KahrabaIQ DASHBOARD API FALLBACK ERROR] $error');
      if (!mounted) {
        return;
      }
      if (_dashboard != null) {
        setState(() {
          _isLoading = false;
          _dashboardNotice =
              'Could not refresh from EC2. Showing the latest saved dashboard data.';
        });
        return;
      }
      setState(() {
        _isLoading = false;
        _error =
            'Could not load the latest dashboard. Please check the backend connection and try again.';
      });
    }

    if (widget.enableRealtimeSync && NetworkConfig.useAwsIotLive) {
      debugPrint('[KahrabaIQ IOT LIVE] subscribing after EC2 snapshot');
      _liveSubscription = _api
          .watchLiveDashboardData(homeId: pairedHomeId)
          .listen(_applyDashboardData, onError: _handleLiveError);
    }
  }

  void _applyDashboardData(DashboardData dashboard) {
    if (!mounted) {
      return;
    }
    if (_selectedDemoScenario != null) {
      return;
    }
    final mergedDashboard = _mergeLiveDashboardData(dashboard);
    debugPrint(
      '[KahrabaIQ DASHBOARD DISPLAY] '
      'power=${mergedDashboard.reading.power} '
      'month=${mergedDashboard.reading.energyMonth} '
      'monthAvailable=${mergedDashboard.reading.monthDataAvailable} '
      'devices=${mergedDashboard.devices.length}',
    );
    unawaited(
      _cacheDashboard(_homeId ?? NetworkConfig.defaultHomeId, mergedDashboard),
    );
    final liveDeviceIds = mergedDashboard.devices
        .map((device) => device.id)
        .toSet();
    setState(() {
      _dashboard = mergedDashboard;
      _syncSafetyPopup(mergedDashboard.alerts);
      _localPendingCommands.removeWhere((deviceId) {
        Device? device;
        for (final item in mergedDashboard.devices) {
          if (item.id == deviceId) {
            device = item;
            break;
          }
        }
        return device == null || !device.commandInProgress;
      });
      _localCommandErrors.removeWhere(
        (deviceId, _) => liveDeviceIds.contains(deviceId),
      );
      _isLoading = false;
      _error = null;
      _dashboardNotice = NetworkConfig.useAwsIotLive
          ? _feedPauseNotice(mergedDashboard)
          : null;
    });
  }

  DashboardData _mergeLiveDashboardData(DashboardData incoming) {
    final previous = _dashboard;
    if (previous == null) {
      return _applyOptimisticCommandState(incoming);
    }
    if (previous.scenarioId != incoming.scenarioId) {
      return _applyOptimisticCommandState(incoming);
    }

    final hasIntelligence =
        incoming.aiDashboard != null ||
        incoming.aiDailySummary != null ||
        incoming.aiRecommendation != null ||
        incoming.aiAlert != null ||
        incoming.aiNotifications.isNotEmpty ||
        incoming.actionSuggestions.isNotEmpty ||
        incoming.automationLogs.isNotEmpty ||
        incoming.nextSchedule != null ||
        incoming.settingsSummary.isNotEmpty;
    final degradedOperationalSnapshot =
        hasIntelligence && _isOperationalDowngrade(previous, incoming);
    if (degradedOperationalSnapshot) {
      debugPrint(
        '[KahrabaIQ DASHBOARD MERGE] preserved live operational state; '
        'snapshot looked stale/partial '
        'previousPower=${previous.reading.power} incomingPower=${incoming.reading.power} '
        'previousOnline=${_onlineControlDeviceCount(previous.devices)} '
        'incomingOnline=${_onlineControlDeviceCount(incoming.devices)}',
      );
    } else if (hasIntelligence) {
      return _applyOptimisticCommandState(incoming);
    }

    final operationalReading = degradedOperationalSnapshot
        ? _readingWithPreviousLiveValues(
            incoming: incoming.reading,
            previous: previous.reading,
          )
        : incoming.reading;
    final reading =
        !operationalReading.monthDataAvailable &&
            previous.reading.monthDataAvailable
        ? EnergyReading(
            timestamp: operationalReading.timestamp,
            voltage: operationalReading.voltage,
            current: operationalReading.current,
            power: operationalReading.power,
            energyToday: operationalReading.energyToday,
            energyMonth: previous.reading.energyMonth,
            energyTotal: operationalReading.energyTotal,
            costToday: operationalReading.costToday,
            costMonth: previous.reading.costMonth,
            monthDataAvailable: true,
            monthSource: previous.reading.monthSource,
          )
        : operationalReading;
    if (!incoming.reading.monthDataAvailable &&
        previous.reading.monthDataAvailable) {
      debugPrint(
        '[KahrabaIQ DASHBOARD MERGE] preserved monthly summary from '
        '${previous.reading.monthSource}; live update had no month data',
      );
    }

    return _applyOptimisticCommandState(
      DashboardData(
        reading: reading,
        sensors: degradedOperationalSnapshot
            ? previous.sensors
            : incoming.sensors,
        devices: degradedOperationalSnapshot
            ? previous.devices
            : incoming.devices.isNotEmpty
            ? incoming.devices
            : previous.devices,
        alerts: incoming.alerts,
        tariffBhdPerKwh: incoming.tariffBhdPerKwh,
        pendingDeviceCommands: incoming.pendingDeviceCommands,
        deviceCommandErrors: incoming.deviceCommandErrors,
        aiDashboard: incoming.aiDashboard ?? previous.aiDashboard,
        aiDailySummary: incoming.aiDailySummary ?? previous.aiDailySummary,
        aiRecommendation:
            incoming.aiRecommendation ?? previous.aiRecommendation,
        aiAlert: incoming.aiAlert ?? previous.aiAlert,
        aiNotifications: incoming.aiNotifications.isNotEmpty
            ? incoming.aiNotifications
            : previous.aiNotifications,
        control: incoming.control,
        actionSuggestions: incoming.actionSuggestions.isNotEmpty
            ? incoming.actionSuggestions
            : previous.actionSuggestions,
        automationLogs: incoming.automationLogs.isNotEmpty
            ? incoming.automationLogs
            : previous.automationLogs,
        settingsSummary: incoming.settingsSummary.isNotEmpty
            ? incoming.settingsSummary
            : previous.settingsSummary,
        occupancy: incoming.occupancy.isNotEmpty
            ? incoming.occupancy
            : previous.occupancy,
        safety: incoming.safety.isNotEmpty ? incoming.safety : previous.safety,
        hubStatus: incoming.hubStatus.isNotEmpty
            ? incoming.hubStatus
            : previous.hubStatus,
        criticalAlerts: incoming.criticalAlerts.isNotEmpty
            ? incoming.criticalAlerts
            : previous.criticalAlerts,
        nextSchedule: previous.nextSchedule,
        scenarioId: previous.scenarioId,
        scenarioName: previous.scenarioName,
        scenarioDescription: previous.scenarioDescription,
        deviceControlEnabled: incoming.deviceControlEnabled,
      ),
    );
  }

  DashboardData _applyOptimisticCommandState(DashboardData dashboard) {
    if (_localOptimisticDeviceStates.isEmpty) {
      return dashboard;
    }

    final now = DateTime.now();
    var changed = false;
    final devices = dashboard.devices.map((device) {
      final targetIsOn = _localOptimisticDeviceStates[device.id];
      final startedAt = _localOptimisticDeviceStartedAt[device.id];
      if (targetIsOn == null || startedAt == null) {
        return device;
      }

      final expired = now.difference(startedAt) > _optimisticCommandHold;
      final message = (device.lastCommandMessage ?? '').toLowerCase();
      final failed =
          message.contains('failed') ||
          message.contains('could not') ||
          message.contains('unavailable');
      final confirmed = device.isOn == targetIsOn && !device.commandInProgress;

      if (confirmed || failed || expired) {
        _localOptimisticDeviceStates.remove(device.id);
        _localOptimisticDeviceStartedAt.remove(device.id);
        return device;
      }

      if (device.isOn != targetIsOn || !device.commandInProgress) {
        changed = true;
        debugPrint(
          '[KahrabaIQ COMMAND MERGE] protected optimistic state '
          'device=${device.id} target=${targetIsOn ? 'on' : 'off'} '
          'incoming=${device.isOn ? 'on' : 'off'}',
        );
      }

      return device.copyWith(
        isOn: targetIsOn,
        commandInProgress: true,
        pendingTargetState: targetIsOn ? 'on' : 'off',
        statusLabel: device.online && !device.stale
            ? 'online'
            : device.statusLabel,
      );
    }).toList();

    return changed ? dashboard.copyWith(devices: devices) : dashboard;
  }

  bool _isOperationalDowngrade(DashboardData previous, DashboardData incoming) {
    if (incoming.hubStatus['online'] == false) {
      return false;
    }
    final previousOnline = _onlineControlDeviceCount(previous.devices);
    final incomingOnline = _onlineControlDeviceCount(incoming.devices);
    final previousPower = _effectivePower(previous);
    final incomingPower = _effectivePower(incoming);
    final previousHasFreshOperationalState =
        previousOnline > 0 || previousPower > 0.5;
    final incomingLooksEmpty =
        incoming.devices.isEmpty ||
        incomingOnline < previousOnline ||
        (previousPower > 0.5 && incomingPower <= 0.1);
    return previousHasFreshOperationalState && incomingLooksEmpty;
  }

  int _onlineControlDeviceCount(List<Device> devices) {
    return devices
        .where(
          (device) =>
              (device.id.startsWith('breaker_') ||
                  device.id.startsWith('matter_') ||
                  device.id == 'light_switch') &&
              device.online &&
              !device.stale,
        )
        .length;
  }

  double _effectivePower(DashboardData dashboard) {
    final devicePower = dashboard.devices.fold<double>(
      0,
      (sum, device) => sum + device.currentPower,
    );
    return dashboard.reading.power > 0 ? dashboard.reading.power : devicePower;
  }

  DashboardData _dashboardForCacheRestore(DashboardData dashboard) {
    if (dashboard.scenarioId != null) {
      return dashboard;
    }
    return dashboard.copyWith(
      reading: EnergyReading(
        timestamp: dashboard.reading.timestamp,
        voltage: 0,
        current: 0,
        power: 0,
        energyToday: dashboard.reading.energyToday,
        energyMonth: dashboard.reading.energyMonth,
        energyTotal: dashboard.reading.energyTotal,
        costToday: dashboard.reading.costToday,
        costMonth: dashboard.reading.costMonth,
        monthDataAvailable: dashboard.reading.monthDataAvailable,
        monthSource: dashboard.reading.monthSource,
      ),
      sensors: dashboard.sensors.copyWith(online: false),
      devices: dashboard.devices
          .map(
            (device) => device.copyWith(
              online: false,
              localOnline: false,
              stale: true,
              commandInProgress: false,
              statusLabel: 'cached',
            ),
          )
          .toList(),
      hubStatus: {
        ...dashboard.hubStatus,
        'online': false,
        'stale': true,
        'status_label': 'cached',
      },
    );
  }

  EnergyReading _readingWithPreviousLiveValues({
    required EnergyReading incoming,
    required EnergyReading previous,
  }) {
    return EnergyReading(
      timestamp: previous.timestamp.isAfter(incoming.timestamp)
          ? previous.timestamp
          : incoming.timestamp,
      voltage: previous.voltage > 0 ? previous.voltage : incoming.voltage,
      current: previous.current > 0 ? previous.current : incoming.current,
      power: previous.power > 0 ? previous.power : incoming.power,
      energyToday: previous.energyToday > 0
          ? previous.energyToday
          : incoming.energyToday,
      energyMonth: incoming.monthDataAvailable
          ? incoming.energyMonth
          : previous.energyMonth,
      energyTotal: previous.energyTotal > 0
          ? previous.energyTotal
          : incoming.energyTotal,
      costToday: previous.costToday > 0
          ? previous.costToday
          : incoming.costToday,
      costMonth: incoming.monthDataAvailable
          ? incoming.costMonth
          : previous.costMonth,
      monthDataAvailable:
          incoming.monthDataAvailable || previous.monthDataAvailable,
      monthSource: incoming.monthDataAvailable
          ? incoming.monthSource
          : previous.monthSource,
    );
  }

  void _syncSafetyPopup(List<Alert> alerts) {
    if (_selectedDemoScenario != null) {
      if (_smokeDialogVisible) {
        _smokeDialogVisible = false;
        Navigator.of(context, rootNavigator: true).maybePop();
      }
      return;
    }
    final smokeAlert = _activeSmokeAlert(alerts);
    if (smokeAlert == null) {
      if (_smokeDialogVisible) {
        _smokeDialogVisible = false;
        Navigator.of(context, rootNavigator: true).maybePop();
      }
      return;
    }
    if (_selectedDemoScenario == null &&
        _notifiedSmokeAlertIds.add(smokeAlert.id)) {
      unawaited(
        NotificationService.showSmokeAlert(
          alertId: smokeAlert.id,
          message: smokeAlert.message,
        ),
      );
    }
    if (_smokeDialogVisible) {
      return;
    }
    _smokeDialogVisible = true;
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      if (!mounted ||
          _activeSmokeAlert(_dashboard?.alerts ?? const []) == null) {
        _smokeDialogVisible = false;
        return;
      }
      await showDialog<void>(
        context: context,
        barrierDismissible: false,
        builder: (context) => _SmokeAlertDialog(alert: smokeAlert),
      );
      _smokeDialogVisible = false;
    });
  }

  Alert? _activeSmokeAlert(List<Alert> alerts) {
    for (final alert in alerts) {
      final type = alert.backendType.toLowerCase();
      if (alert.isActive &&
          (alert.id == 'smoke_detected_room1' ||
              type.contains('smoke') ||
              type.contains('gas'))) {
        return alert;
      }
    }
    return null;
  }

  void _handleLiveError(Object error) {
    if (!mounted) {
      return;
    }
    if (_selectedDemoScenario != null) {
      return;
    }
    if (_dashboard == null) {
      setState(() {
        _isLoading = false;
        _dashboardNotice = 'Waiting for the latest dashboard snapshot.';
      });
      return;
    }
    setState(() {
      _dashboardNotice = _feedPauseNotice(_dashboard!);
    });
  }

  String? _feedPauseNotice(DashboardData dashboard) {
    if (dashboard.scenarioId != null) {
      return null;
    }
    final breakersPaused = dashboard.devices
        .where((device) => device.id.startsWith('breaker_'))
        .any((device) => !device.online || device.stale);
    final sensorsPaused = !dashboard.sensors.online;
    final paused = <String>[
      if (breakersPaused) 'breakers',
      if (sensorsPaused) 'sensors',
    ];
    if (paused.isEmpty) {
      return null;
    }
    final label = paused.join(' and ');
    return '${label[0].toUpperCase()}${label.substring(1)} data updates are paused. Showing the latest available dashboard data.';
  }

  Future<DashboardData?> _loadCachedDashboard() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final preferredHomeId = _homeId ?? NetworkConfig.defaultHomeId;
      final raw =
          prefs.getString('$_dashboardCachePrefix$preferredHomeId') ??
          prefs.getString('${_dashboardCachePrefix}last');
      if (raw == null || raw.isEmpty) {
        debugPrint('[KahrabaIQ DASHBOARD CACHE] no cached dashboard found');
        return null;
      }
      final data = jsonDecode(raw);
      if (data is! Map<String, dynamic>) {
        return null;
      }
      final dashboard = _dashboardFromCache(data);
      final cachedAt = DateTime.tryParse(data['cachedAt']?.toString() ?? '');
      final ageSeconds = cachedAt == null
          ? null
          : DateTime.now().difference(cachedAt).inSeconds;
      debugPrint(
        '[KahrabaIQ DASHBOARD CACHE] loaded cached dashboard '
        'ageSeconds=${ageSeconds ?? 'unknown'}',
      );
      return dashboard;
    } catch (error) {
      debugPrint('[KahrabaIQ DASHBOARD CACHE] restore failed: $error');
      return null;
    }
  }

  Future<void> _cacheDashboard(String homeId, DashboardData dashboard) async {
    if (dashboard.scenarioId != null || dashboard.devices.isEmpty) {
      return;
    }
    try {
      final prefs = await SharedPreferences.getInstance();
      final raw = jsonEncode(_dashboardToCache(dashboard));
      await prefs.setString('$_dashboardCachePrefix$homeId', raw);
      await prefs.setString('${_dashboardCachePrefix}last', raw);
      debugPrint(
        '[KahrabaIQ DASHBOARD CACHE] saved dashboard '
        'home=$homeId power=${dashboard.reading.power} devices=${dashboard.devices.length}',
      );
    } catch (error) {
      debugPrint('[KahrabaIQ DASHBOARD CACHE] save failed: $error');
    }
  }

  Map<String, dynamic> _dashboardToCache(DashboardData dashboard) {
    return {
      'cachedAt': DateTime.now().toIso8601String(),
      'reading': dashboard.reading.toJson(),
      'sensors': dashboard.sensors.toJson(),
      'devices': dashboard.devices.map((device) => device.toJson()).toList(),
      'alerts': dashboard.alerts.map((alert) => alert.toJson()).toList(),
      'tariffBhdPerKwh': dashboard.tariffBhdPerKwh,
      'hubStatus': dashboard.hubStatus,
      'occupancy': dashboard.occupancy,
      'safety': dashboard.safety,
      'criticalAlerts': dashboard.criticalAlerts,
      'deviceControlEnabled': dashboard.deviceControlEnabled,
    };
  }

  DashboardData _dashboardFromCache(Map<String, dynamic> data) {
    final devices = (data['devices'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(Device.fromJson)
        .toList();
    final alerts = (data['alerts'] as List<dynamic>? ?? const [])
        .whereType<Map<String, dynamic>>()
        .map(Alert.fromJson)
        .toList();
    return DashboardData(
      reading: EnergyReading.fromJson(
        Map<String, dynamic>.from(data['reading'] as Map? ?? const {}),
      ),
      sensors: SensorData.fromJson(
        Map<String, dynamic>.from(data['sensors'] as Map? ?? const {}),
      ),
      devices: devices,
      alerts: alerts,
      tariffBhdPerKwh:
          (data['tariffBhdPerKwh'] as num?)?.toDouble() ??
          ElectricityPricing.costPerKWh,
      hubStatus: Map<String, dynamic>.from(
        data['hubStatus'] as Map? ?? const {},
      ),
      occupancy: Map<String, dynamic>.from(
        data['occupancy'] as Map? ?? const {},
      ),
      safety: Map<String, dynamic>.from(data['safety'] as Map? ?? const {}),
      criticalAlerts: (data['criticalAlerts'] as List<dynamic>? ?? const [])
          .whereType<Map<String, dynamic>>()
          .toList(),
      deviceControlEnabled: data['deviceControlEnabled'] as bool? ?? true,
    );
  }

  @override
  Widget build(BuildContext context) {
    final dashboard = _dashboard;
    final isPaired = _homeId != null && _homeId!.isNotEmpty;
    final canOpenAdminPanel =
        _currentHomeAccess?.permissions.canGenerateInvites == true ||
        _currentHomeAccess?.role == 'home_admin';
    final canEditSettings =
        _currentHomeAccess?.permissions.canChangeSettings == true ||
        _currentHomeAccess?.role == 'home_admin' ||
        _isPlatformAdmin;
    return Scaffold(
      body: SafeArea(
        child: _isLoading
            ? _DashboardLoading(onRetry: () => _loadDashboard())
            : _error != null
            ? AppErrorState(message: _error!, onRetry: () => _loadDashboard())
            : !isPaired
            ? _UnpairedHomeState(
                name: _displayName(),
                onPair: _openQrScanner,
                onLogout: _logout,
                onGlobalAdmin: _isPlatformAdmin ? _openGlobalAdmin : null,
                isPairing: _isPairing,
              )
            : dashboard == null
            ? AppEmptyState(
                icon: Icons.dashboard_outlined,
                title: 'No dashboard data yet',
                message:
                    _dashboardNotice ??
                    'Could not receive dashboard data. Pull to retry.',
              )
            : RefreshIndicator(
                color: ColorTokens.primary,
                onRefresh: _loadDashboard,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
                  children: [
                    DashboardHeader(
                      name: _displayName(),
                      alertCount: dashboard.alerts.length,
                      onNotifications: () => _openNotifications(dashboard),
                      onLogout: NetworkConfig.useCognitoAuth ? _logout : null,
                    ),
                    if (_dashboardNotice != null) ...[
                      const SizedBox(height: 16),
                      _DashboardNotice(message: _dashboardNotice!),
                    ],
                    if (_hubOfflineNotice(dashboard) != null) ...[
                      const SizedBox(height: 16),
                      _DashboardNotice(message: _hubOfflineNotice(dashboard)!),
                    ],
                    if (NetworkConfig.enableDemoScenarios) ...[
                      const SizedBox(height: 16),
                      DemoScenarioSelector(
                        scenarios: demoScenarios,
                        selectedScenario: _selectedDemoScenario,
                        isGeneratingAi: _scenarioAiBusy,
                        onSelect: _activateDemoScenario,
                        onReturnToLive: _returnToLiveData,
                      ),
                    ],
                    const SizedBox(height: 24),
                    EnergyHeroCard(
                      reading: dashboard.reading,
                      costMonth: dashboard.reading.costMonth > 0
                          ? dashboard.reading.costMonth
                          : dashboard.reading.calculateMonthCost(
                              dashboard.tariffBhdPerKwh,
                            ),
                    ),
                    const SizedBox(height: 16),
                    QuickStatsRow(
                      reading: dashboard.reading,
                      devices: dashboard.devices,
                      onBreakersTap: () => _openBreakers(dashboard.devices),
                    ),
                    const SizedBox(height: 16),
                    if (dashboard.alerts
                        .where(
                          (alert) => !_dismissedAlertIds.contains(alert.id),
                        )
                        .isNotEmpty)
                      AlertBanner(
                        alert: dashboard.alerts.firstWhere(
                          (alert) => !_dismissedAlertIds.contains(alert.id),
                        ),
                        onDismiss: () {
                          setState(() {
                            _dismissedAlertIds.add(
                              dashboard.alerts
                                  .firstWhere(
                                    (alert) =>
                                        !_dismissedAlertIds.contains(alert.id),
                                  )
                                  .id,
                            );
                          });
                        },
                      ),
                    const SizedBox(height: 16),
                    AiInsightsBanner(
                      text: _aiInsightText(dashboard),
                      onTap: _openChat,
                    ),
                    const SizedBox(height: 16),
                    _AiAnalysisSection(
                      dashboard: dashboard,
                      onOpenChat: _openChat,
                    ),
                    const SizedBox(height: 22),
                    DevicesSection(
                      devices: dashboard.devices,
                      onToggle: _toggleDevice,
                      pendingDeviceCommands: {
                        ...dashboard.pendingDeviceCommands,
                        ..._localPendingCommands,
                      },
                      deviceCommandErrors: {
                        ...dashboard.deviceCommandErrors,
                        ..._localCommandErrors,
                      },
                    ),
                    const SizedBox(height: 22),
                    _DashboardActions(
                      onSensors: _openSensors,
                      onSettings: () => _openSettings(canEditSettings),
                      onPair: _openQrScanner,
                      onAdmin: canOpenAdminPanel ? _openAdminPanel : null,
                      onGlobalAdmin: _isPlatformAdmin ? _openGlobalAdmin : null,
                      isPairing: _isPairing,
                      showPair: false,
                    ),
                  ],
                ),
              ),
      ),
    );
  }

  Future<void> _toggleDevice(Device device, bool value) async {
    if (_dashboard?.scenarioId != null ||
        _dashboard?.deviceControlEnabled == false) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text('Device control is disabled in Demo Mode.'),
        ),
      );
      return;
    }
    if (!device.online || device.stale) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            device.stale
                ? '${device.name} data is stale. Wait for fresh data before controlling it.'
                : '${device.name} is offline. Control is disabled.',
          ),
        ),
      );
      return;
    }
    final action = value ? 'turn_on' : 'turn_off';
    debugPrint(
      '[KahrabaIQ COMMAND TAP] device=${device.id} '
      'name=${device.name} action=$action '
      'control=${device.controlMethod ?? 'unknown'} '
      'home=${_homeId ?? NetworkConfig.defaultHomeId} '
      'online=${device.online} local=${device.localOnline} cloud=${device.cloudOnline}',
    );
    setState(() {
      _localPendingCommands.add(device.id);
      _localOptimisticDeviceStates[device.id] = value;
      _localOptimisticDeviceStartedAt[device.id] = DateTime.now();
      _localCommandErrors.remove(device.id);
      _dashboard = _dashboardWithOptimisticDeviceState(
        device.id,
        value,
        commandInProgress: true,
      );
    });
    try {
      final result = await _api.sendDeviceCommand(
        device.id,
        action,
        homeId: _homeId ?? NetworkConfig.defaultHomeId,
      );
      if (!mounted) {
        return;
      }
      debugPrint(
        '[KahrabaIQ COMMAND QUEUED] device=${device.id} action=$action '
        'success=${result.success} status=${result.status} '
        'commandId=${result.commandId} message=${result.message}',
      );
      if (!result.success) {
        setState(() {
          _localCommandErrors[device.id] = result.message;
          _localOptimisticDeviceStates.remove(device.id);
          _localOptimisticDeviceStartedAt.remove(device.id);
          _dashboard = _dashboardWithOptimisticDeviceState(
            device.id,
            device.isOn,
            commandInProgress: false,
          );
        });
      } else {
        setState(() {
          _dashboard = _dashboardWithOptimisticDeviceState(
            device.id,
            value,
            commandInProgress: true,
          );
        });
      }
    } catch (error) {
      debugPrint(
        '[KahrabaIQ COMMAND ERROR] device=${device.id} action=$action error=$error',
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _localCommandErrors[device.id] = error.toString().replaceFirst(
          'Exception: ',
          '',
        );
        _localOptimisticDeviceStates.remove(device.id);
        _localOptimisticDeviceStartedAt.remove(device.id);
        _dashboard = _dashboardWithOptimisticDeviceState(
          device.id,
          device.isOn,
          commandInProgress: false,
        );
      });
    } finally {
      if (mounted) {
        setState(() => _localPendingCommands.remove(device.id));
      }
    }
  }

  DashboardData? _dashboardWithOptimisticDeviceState(
    String deviceId,
    bool isOn, {
    required bool commandInProgress,
  }) {
    final dashboard = _dashboard;
    if (dashboard == null) {
      return null;
    }
    final devices = dashboard.devices
        .map(
          (item) => item.id == deviceId
              ? item.copyWith(
                  isOn: isOn,
                  commandInProgress: commandInProgress,
                  pendingTargetState: commandInProgress
                      ? (isOn ? 'on' : 'off')
                      : null,
                  statusLabel: item.online && !item.stale
                      ? 'online'
                      : item.statusLabel,
                )
              : item,
        )
        .toList();
    return dashboard.copyWith(devices: devices);
  }

  void _openChat() => Navigator.of(context).push(
    fadeSlideRoute(
      AiChatbotScreen(
        homeId: _homeId ?? NetworkConfig.defaultHomeId,
        scenarioId: _selectedDemoScenario?.id,
        scenarioName: _selectedDemoScenario?.name,
        dashboard: _dashboard,
      ),
    ),
  );

  String? _hubOfflineNotice(DashboardData dashboard) {
    if (dashboard.scenarioId != null) {
      return null;
    }
    final online = dashboard.hubStatus['online'];
    if (online == false) {
      return 'Hub offline. Showing latest cloud data.';
    }
    return null;
  }

  Future<void> _activateDemoScenario(DemoScenarioData scenario) async {
    await _liveSubscription?.cancel();
    _liveSubscription = null;
    if (!mounted) {
      return;
    }
    setState(() {
      _selectedDemoScenario = scenario;
      _dashboard = scenario.dashboard;
      _scenarioAiBusy = NetworkConfig.useBackendScenarioAi;
      _isLoading = false;
      _error = null;
      _dashboardNotice = NetworkConfig.useBackendScenarioAi
          ? 'Simulation Mode is active. Generating AI insight from EC2 using simulated scenario data...'
          : 'Simulation Mode is active. Using local demo AI fallback. No real devices will be controlled.';
      _localPendingCommands.clear();
      _localOptimisticDeviceStates.clear();
      _localOptimisticDeviceStartedAt.clear();
      _localCommandErrors.clear();
      _dismissedAlertIds.clear();
      _notifiedSmokeAlertIds.clear();
    });
    _syncSafetyPopup(scenario.dashboard.alerts);
    if (!NetworkConfig.useBackendScenarioAi) {
      return;
    }
    try {
      final response = await _api.runScenarioAiPrediction(
        homeId: _homeId ?? NetworkConfig.defaultHomeId,
        scenarioPayload: scenario.toBackendPayload(),
      );
      if (!mounted || _selectedDemoScenario?.id != scenario.id) {
        return;
      }
      final generatedDashboard = _api.applyScenarioAiResponse(
        scenario.dashboard,
        response,
      );
      setState(() {
        _dashboard = generatedDashboard;
        _scenarioAiBusy = false;
        _dashboardNotice =
            'Simulation Mode is active. AI was generated by EC2 from simulated scenario data. No real devices are controlled.';
      });
      _syncSafetyPopup(generatedDashboard.alerts);
    } catch (error) {
      debugPrint('[KahrabaIQ SCENARIO AI FALLBACK] $error');
      if (!mounted || _selectedDemoScenario?.id != scenario.id) {
        return;
      }
      setState(() {
        _scenarioAiBusy = false;
        _dashboardNotice =
            'Simulation Mode is active. Backend scenario AI failed, so local demo fallback is shown.';
      });
    }
  }

  Future<void> _returnToLiveData() async {
    if (!mounted) {
      return;
    }
    setState(() {
      _selectedDemoScenario = null;
      _scenarioAiBusy = false;
      _dashboardNotice = 'Returning to live home data...';
      _dismissedAlertIds.clear();
      _notifiedSmokeAlertIds.clear();
    });
    await _loadDashboard();
  }

  void _openBreakers(List<Device> devices) {
    Navigator.of(
      context,
    ).push(fadeSlideRoute(BreakersScreen(devices: devices)));
  }

  void _openNotifications(DashboardData dashboard) {
    Navigator.of(context).push(
      fadeSlideRoute(
        NotificationsScreen(
          homeId: _homeId ?? NetworkConfig.defaultHomeId,
          alerts: dashboard.alerts,
        ),
      ),
    );
  }

  void _openSensors() => Navigator.of(context).push(
    fadeSlideRoute(
      SensorsStatusScreen(
        sensorData: _dashboard!.sensors,
        isDemoMode: _dashboard?.scenarioId != null,
      ),
    ),
  );

  Future<void> _logout() async {
    if (!NetworkConfig.useCognitoAuth) {
      return;
    }
    await _liveSubscription?.cancel();
    _liveSubscription = null;
    if (mounted) {
      setState(() {
        _dashboard = null;
        _homeId = null;
        _currentUserUid = null;
        _currentHomeAccess = null;
        _localPendingCommands.clear();
        _localCommandErrors.clear();
      });
    }
    await AuthService().signOut();
  }

  Future<void> _openQrScanner() async {
    final value = await Navigator.of(
      context,
    ).push<String>(fadeSlideRoute(const QrScannerScreen()));
    final payload = value?.trim();
    if (payload == null || payload.isEmpty) {
      return;
    }
    final parsed = _parseScannedQrPayload(payload);
    if (parsed == null) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Invalid pairing code.')));
      return;
    }
    setState(() => _isPairing = true);
    try {
      final Map<String, dynamic> result;
      final String successMessage;
      if (parsed is _PiPairingPayload) {
        result = await _api.claimPi(
          piId: parsed.piId,
          token: parsed.token,
          homeName: 'KahrabaIQ Home',
        );
        successMessage =
            'Paired ${result['pi_id'] ?? parsed.piId} successfully.';
      } else if (parsed is _HomeInvitePayload) {
        result = await _api.claimHomeInvite(
          inviteId: parsed.inviteId,
          token: parsed.token,
        );
        successMessage = 'Joined home as ${result['role'] ?? 'member'}.';
      } else {
        throw Exception('Unsupported QR code.');
      }
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(successMessage)));
      await _loadDashboard();
    } catch (error) {
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Pairing failed: ${error.toString().replaceFirst('Exception: ', '')}',
          ),
        ),
      );
    } finally {
      if (mounted) {
        setState(() => _isPairing = false);
      }
    }
  }

  UserHomeAccess? _selectPairedHome(CurrentUserProfile profile) {
    final activeHomes = profile.homes
        .where((home) => home.status.toLowerCase() != 'unpaired')
        .toList();
    if (activeHomes.isEmpty) {
      return null;
    }
    final defaultHomeId = profile.defaultHomeId;
    if (defaultHomeId != null && defaultHomeId.isNotEmpty) {
      for (final home in activeHomes) {
        if (home.homeId == defaultHomeId) {
          return home;
        }
      }
    }
    return activeHomes.first;
  }

  _ScannedQrPayload? _parseScannedQrPayload(String payload) {
    final uri = Uri.tryParse(payload);
    if (uri != null && uri.scheme == 'kahrabaiq' && uri.host == 'pair') {
      final piId = uri.queryParameters['pi_id']?.trim();
      final token = uri.queryParameters['token']?.trim();
      if (piId != null &&
          piId.isNotEmpty &&
          token != null &&
          token.isNotEmpty) {
        return _PiPairingPayload(piId: piId, token: token);
      }
    }
    if (uri != null && uri.scheme == 'kahrabaiq' && uri.host == 'invite') {
      final inviteId = uri.queryParameters['invite_id']?.trim();
      final token = uri.queryParameters['token']?.trim();
      if (inviteId != null &&
          inviteId.isNotEmpty &&
          token != null &&
          token.isNotEmpty) {
        return _HomeInvitePayload(inviteId: inviteId, token: token);
      }
    }
    final parts = payload.split(RegExp(r'\s+'));
    if (parts.length >= 2) {
      return _PiPairingPayload(
        piId: parts.first.trim(),
        token: parts.last.trim(),
      );
    }
    return _PiPairingPayload(
      piId: NetworkConfig.defaultHomePiId,
      token: payload,
    );
  }

  Future<void> _openAdminPanel() async {
    final homeId = _homeId;
    final userUid = _currentUserUid;
    if (homeId == null ||
        homeId.isEmpty ||
        userUid == null ||
        userUid.isEmpty) {
      return;
    }
    await Navigator.of(context).push(
      fadeSlideRoute(
        HomeAdminPanelScreen(homeId: homeId, currentUserUid: userUid),
      ),
    );
    await _loadDashboard();
  }

  Future<void> _openSettings(bool canEdit) async {
    final homeId = _homeId;
    if (homeId == null || homeId.isEmpty) {
      return;
    }
    final changed = await Navigator.of(context).push<bool>(
      fadeSlideRoute(
        HomeSettingsScreen(
          homeId: homeId,
          canEdit: canEdit,
          scenarioMode: _dashboard?.scenarioId != null,
        ),
      ),
    );
    if (changed == true) {
      await _loadDashboard();
    }
  }

  Future<void> _openGlobalAdmin() async {
    await Navigator.of(context).push(fadeSlideRoute(const GlobalAdminScreen()));
    await _loadDashboard();
  }

  String _displayName() {
    if (!NetworkConfig.useCognitoAuth) {
      return 'Guest';
    }
    final user = AuthService().currentUser;
    final name = user?.displayName?.trim();
    if (name != null && name.isNotEmpty) {
      return name.split(' ').first;
    }
    final email = user?.email ?? '';
    if (email.contains('@')) {
      return email.split('@').first;
    }
    return 'there';
  }

  String _aiInsightText(DashboardData dashboard) {
    final recommendation = dashboard.aiRecommendation;
    if (recommendation != null && recommendation.message.trim().isNotEmpty) {
      return recommendation.message;
    }
    final aiDashboard = dashboard.aiDashboard;
    if (aiDashboard != null && aiDashboard.statusSummary.trim().isNotEmpty) {
      return aiDashboard.statusSummary;
    }
    final dailySummary = dashboard.aiDailySummary;
    if (dailySummary != null && dailySummary.summary.trim().isNotEmpty) {
      return dailySummary.summary;
    }
    if (dashboard.reading.power > 0) {
      return 'Live energy data is active. AI recommendations will appear when a useful action is detected.';
    }
    return 'AI analysis is waiting for enough live energy data.';
  }
}

class _DashboardLoading extends StatelessWidget {
  const _DashboardLoading({required this.onRetry});

  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
      children: const [
        AppShimmer(height: 48),
        SizedBox(height: 24),
        AppShimmer(height: 190, radius: 24),
        SizedBox(height: 16),
        Row(
          children: [
            Expanded(child: AppShimmer(height: 148)),
            SizedBox(width: 10),
            Expanded(child: AppShimmer(height: 148)),
          ],
        ),
      ],
    );
  }
}

class _UnpairedHomeState extends StatelessWidget {
  const _UnpairedHomeState({
    required this.name,
    required this.onPair,
    required this.onLogout,
    required this.isPairing,
    this.onGlobalAdmin,
  });

  final String name;
  final VoidCallback onPair;
  final VoidCallback onLogout;
  final VoidCallback? onGlobalAdmin;
  final bool isPairing;

  @override
  Widget build(BuildContext context) {
    return ListView(
      padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
      children: [
        DashboardHeader(name: name, alertCount: 0, onLogout: onLogout),
        const SizedBox(height: 28),
        AppEmptyState(
          icon: Icons.home_work_outlined,
          title: 'Join or pair a home',
          message: 'Scan a Pi pairing QR or a home invite QR to continue.',
        ),
        const SizedBox(height: 12),
        OutlinedButton.icon(
          onPressed: isPairing ? null : onPair,
          icon: isPairing
              ? const SizedBox(
                  width: 18,
                  height: 18,
                  child: CircularProgressIndicator(strokeWidth: 2),
                )
              : const Icon(Icons.qr_code_scanner),
          label: Text(isPairing ? 'Pairing' : 'Scan QR'),
        ),
        if (onGlobalAdmin != null) ...[
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: onGlobalAdmin,
            icon: const Icon(Icons.shield_outlined),
            label: const Text('Global Admin'),
          ),
        ],
      ],
    );
  }
}

class _AiAnalysisSection extends StatelessWidget {
  const _AiAnalysisSection({required this.dashboard, required this.onOpenChat});

  final DashboardData dashboard;
  final VoidCallback onOpenChat;

  Color get _toneColor {
    final tone = dashboard.aiDashboard?.statusTone.toLowerCase() ?? '';
    if (tone == 'warning') return ColorTokens.warning;
    if (tone == 'danger' || tone == 'critical') return ColorTokens.danger;
    if (tone == 'success') return ColorTokens.success;
    return ColorTokens.primary;
  }

  String get _statusLabel {
    final label = dashboard.aiDashboard?.statusLabel.trim() ?? '';
    return label.isEmpty ? 'Learning' : label;
  }

  String get _summary {
    if (dashboard.scenarioId != null && dashboard.aiDashboard == null) {
      return 'Demo scenario AI result is being prepared.';
    }
    final ai = dashboard.aiDashboard;
    if (ai != null && ai.statusSummary.trim().isNotEmpty) {
      return ai.statusSummary;
    }
    if (dashboard.aiRecommendation?.message.trim().isNotEmpty ?? false) {
      return dashboard.aiRecommendation!.message;
    }
    return 'AI analysis will appear here after the backend runs a prediction.';
  }

  String get _explanation {
    final ai = dashboard.aiDashboard;
    if (ai != null && ai.explanation.trim().isNotEmpty) {
      return ai.explanation;
    }
    return 'KahrabaIQ compares live breaker, sensor, occupancy, and recent usage data to suggest useful actions.';
  }

  String get _actionText {
    final ai = dashboard.aiDashboard;
    if (ai != null && ai.actionTitle.trim().isNotEmpty) {
      return ai.actionTitle;
    }
    final recommendation = dashboard.aiRecommendation;
    if (recommendation != null && recommendation.title.trim().isNotEmpty) {
      return recommendation.title;
    }
    return 'Waiting for prediction';
  }

  String get _notificationText {
    if (dashboard.aiNotifications.isEmpty) {
      return '';
    }
    final item = dashboard.aiNotifications.first;
    final confidence = item.confidence == null
        ? ''
        : ' Confidence ${(item.confidence! * 100).round()}%.';
    return '${item.title}: ${item.message}$confidence';
  }

  String get _scenarioSourceLabel {
    if (dashboard.scenarioId == null) {
      return '';
    }
    final label = dashboard.settingsSummary['scenario_ai_source_label'];
    if (label is String && label.trim().isNotEmpty) {
      return label;
    }
    return 'Using local demo fallback';
  }

  @override
  Widget build(BuildContext context) {
    final ai = dashboard.aiDashboard;
    final suggestion = dashboard.actionSuggestions.isNotEmpty
        ? dashboard.actionSuggestions.first.reason
        : dashboard.aiRecommendation?.message ?? _explanation;

    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ColorTokens.surfaceElevated,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: _toneColor.withValues(alpha: 0.35)),
        boxShadow: const [BoxShadow(color: ColorTokens.shadow, blurRadius: 18)],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: _toneColor.withValues(alpha: 0.16),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: Icon(Icons.psychology_alt, color: _toneColor, size: 22),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text('AI Energy Analysis', style: AppTextStyles.h3),
                    const SizedBox(height: 2),
                    Text(
                      _statusLabel,
                      style: AppTextStyles.caption.copyWith(color: _toneColor),
                    ),
                  ],
                ),
              ),
              TextButton.icon(
                onPressed: onOpenChat,
                icon: const Icon(Icons.chat_bubble_outline, size: 18),
                label: const Text('Ask AI'),
              ),
            ],
          ),
          if (dashboard.scenarioId != null) ...[
            const SizedBox(height: 10),
            Wrap(
              spacing: 8,
              runSpacing: 8,
              children: [
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: ColorTokens.warning.withValues(alpha: 0.14),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(
                      color: ColorTokens.warning.withValues(alpha: 0.45),
                    ),
                  ),
                  child: Text(
                    'Simulation Mode: ${dashboard.scenarioName ?? 'Demo Scenario'}',
                    style: AppTextStyles.caption.copyWith(
                      color: ColorTokens.warning,
                    ),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(
                    horizontal: 10,
                    vertical: 6,
                  ),
                  decoration: BoxDecoration(
                    color: ColorTokens.primary.withValues(alpha: 0.12),
                    borderRadius: BorderRadius.circular(999),
                    border: Border.all(
                      color: ColorTokens.primary.withValues(alpha: 0.35),
                    ),
                  ),
                  child: Text(
                    _scenarioSourceLabel,
                    style: AppTextStyles.caption.copyWith(
                      color: ColorTokens.primary,
                    ),
                  ),
                ),
              ],
            ),
          ],
          const SizedBox(height: 14),
          Text(_summary, style: AppTextStyles.bodyMedium),
          const SizedBox(height: 10),
          Text(_explanation, style: AppTextStyles.caption),
          const SizedBox(height: 14),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              _AiMetricChip(
                icon: Icons.bolt,
                label: ai == null
                    ? 'No prediction yet'
                    : '${ai.nextHourEnergyKwh.toStringAsFixed(3)} kWh next hour',
              ),
              _AiMetricChip(
                icon: Icons.savings_outlined,
                label: ai == null
                    ? 'Cost pending'
                    : '${ai.nextHourCostBhd.toStringAsFixed(3)} BHD',
              ),
              _AiMetricChip(
                icon: Icons.tips_and_updates_outlined,
                label: _actionText,
              ),
            ],
          ),
          const SizedBox(height: 14),
          if (_notificationText.isNotEmpty) ...[
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: _toneColor.withValues(alpha: 0.10),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: _toneColor.withValues(alpha: 0.28)),
              ),
              child: Text(
                _notificationText,
                style: AppTextStyles.caption.copyWith(
                  color: ColorTokens.textPrimary,
                ),
              ),
            ),
            const SizedBox(height: 14),
          ],
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: ColorTokens.surface,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: ColorTokens.border),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Icon(
                  Icons.lightbulb_outline,
                  color: ColorTokens.warning,
                  size: 20,
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: Text(
                    suggestion.trim().isEmpty
                        ? 'No suggestion yet.'
                        : suggestion,
                    style: AppTextStyles.caption.copyWith(
                      color: ColorTokens.textPrimary,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _AiMetricChip extends StatelessWidget {
  const _AiMetricChip({required this.icon, required this.label});

  final IconData icon;
  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
      decoration: BoxDecoration(
        color: ColorTokens.primaryGlow,
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: ColorTokens.primary.withValues(alpha: 0.25)),
      ),
      child: Row(
        mainAxisSize: MainAxisSize.min,
        children: [
          Icon(icon, size: 16, color: ColorTokens.primary),
          const SizedBox(width: 6),
          Text(
            label,
            style: AppTextStyles.caption.copyWith(
              color: ColorTokens.textPrimary,
            ),
          ),
        ],
      ),
    );
  }
}

class _DashboardActions extends StatelessWidget {
  const _DashboardActions({
    required this.onSensors,
    required this.onSettings,
    required this.onPair,
    required this.isPairing,
    this.onAdmin,
    this.onGlobalAdmin,
    this.showPair = true,
  });

  final VoidCallback onSensors;
  final VoidCallback onSettings;
  final VoidCallback onPair;
  final VoidCallback? onAdmin;
  final VoidCallback? onGlobalAdmin;
  final bool isPairing;
  final bool showPair;

  @override
  Widget build(BuildContext context) {
    return LayoutBuilder(
      builder: (context, constraints) {
        final itemWidth = (constraints.maxWidth - 12) / 2;
        Widget action(Widget child) => SizedBox(width: itemWidth, child: child);
        return Wrap(
          spacing: 12,
          runSpacing: 12,
          children: [
            action(
              OutlinedButton.icon(
                onPressed: onSensors,
                icon: const Icon(Icons.sensors),
                label: const Text('Sensors'),
              ),
            ),
            action(
              OutlinedButton.icon(
                onPressed: onSettings,
                icon: const Icon(Icons.settings_outlined),
                label: const Text('Settings'),
              ),
            ),
            if (onAdmin != null)
              action(
                OutlinedButton.icon(
                  onPressed: onAdmin,
                  icon: const Icon(Icons.admin_panel_settings),
                  label: const Text('Admin Panel'),
                ),
              ),
            if (onGlobalAdmin != null)
              action(
                OutlinedButton.icon(
                  onPressed: onGlobalAdmin,
                  icon: const Icon(Icons.shield_outlined),
                  label: const Text('Global Admin'),
                ),
              ),
            if (showPair)
              action(
                OutlinedButton.icon(
                  onPressed: isPairing ? null : onPair,
                  icon: isPairing
                      ? const SizedBox(
                          width: 18,
                          height: 18,
                          child: CircularProgressIndicator(strokeWidth: 2),
                        )
                      : const Icon(Icons.qr_code_scanner),
                  label: Text(isPairing ? 'Pairing' : 'Pair'),
                ),
              ),
          ],
        );
      },
    );
  }
}

class _DashboardNotice extends StatelessWidget {
  const _DashboardNotice({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: ColorTokens.warning.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: ColorTokens.warning.withValues(alpha: 0.35)),
      ),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Icon(
            Icons.wifi_off_rounded,
            color: ColorTokens.warning,
            size: 20,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              message,
              style: AppTextStyles.caption.copyWith(
                color: ColorTokens.textPrimary,
              ),
            ),
          ),
        ],
      ),
    );
  }
}

class _SmokeAlertDialog extends StatelessWidget {
  const _SmokeAlertDialog({required this.alert});

  final Alert alert;

  @override
  Widget build(BuildContext context) {
    return AlertDialog(
      backgroundColor: ColorTokens.surfaceElevated,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(20)),
      icon: const Icon(
        Icons.local_fire_department,
        color: ColorTokens.danger,
        size: 42,
      ),
      title: Text('Smoke/Gas Detected', style: AppTextStyles.h2),
      content: Text(
        alert.message.isEmpty
            ? 'Smoke or gas was detected in Room 1. Check immediately.'
            : alert.message,
        style: AppTextStyles.body,
        textAlign: TextAlign.center,
      ),
      actionsAlignment: MainAxisAlignment.center,
      actions: [
        FilledButton.icon(
          style: FilledButton.styleFrom(
            backgroundColor: ColorTokens.danger,
            foregroundColor: ColorTokens.textPrimary,
          ),
          onPressed: () => Navigator.of(context).pop(),
          icon: const Icon(Icons.check_circle_outline),
          label: const Text('I understand'),
        ),
      ],
    );
  }
}

sealed class _ScannedQrPayload {
  const _ScannedQrPayload();
}

class _PiPairingPayload extends _ScannedQrPayload {
  const _PiPairingPayload({required this.piId, required this.token});

  final String piId;
  final String token;
}

class _HomeInvitePayload extends _ScannedQrPayload {
  const _HomeInvitePayload({required this.inviteId, required this.token});

  final String inviteId;
  final String token;
}
