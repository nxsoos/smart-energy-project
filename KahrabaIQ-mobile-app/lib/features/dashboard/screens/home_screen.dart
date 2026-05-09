import 'dart:async';

import 'package:flutter/material.dart';

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
import '../../pairing/screens/qr_scanner_screen.dart';
import '../../sensors/screens/sensors_status_screen.dart';
import 'breakers_screen.dart';
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
  final KahrabaIqApiService _api = KahrabaIqApiService();
  String? _homeId;
  DashboardData? _dashboard;
  StreamSubscription<DashboardData>? _liveSubscription;
  bool _isLoading = true;
  bool _isPairing = false;
  String? _error;
  String? _dashboardNotice;
  final Set<String> _localPendingCommands = {};
  final Map<String, String> _localCommandErrors = {};
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
    await _liveSubscription?.cancel();
    setState(() {
      _isLoading = _dashboard == null;
      _error = null;
      _dashboardNotice = null;
    });

    String? pairedHomeId;
    if (!NetworkConfig.useCognitoAuth) {
      pairedHomeId = NetworkConfig.defaultHomeId;
      setState(() {
        _homeId = pairedHomeId;
      });
    } else {
      try {
        final profile = await AuthService().loadCurrentUserProfile();
        pairedHomeId = _selectPairedHome(profile)?.homeId;
        if (!mounted) {
          return;
        }
        setState(() {
          _homeId = pairedHomeId;
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

    if (widget.enableRealtimeSync && NetworkConfig.useAwsIotLive) {
      _liveSubscription = _api
          .watchLiveDashboardData(homeId: pairedHomeId)
          .listen(_applyDashboardData, onError: _handleLiveError);
    }

    try {
      final dashboard = await _api.fetchDashboardData(homeId: pairedHomeId);
      _applyDashboardData(dashboard);
    } catch (error) {
      debugPrint('[KahrabaIQ DASHBOARD API FALLBACK ERROR] $error');
      if (!mounted) {
        return;
      }
      if (_dashboard != null) {
        return;
      }
      setState(() {
        _dashboard = _offlineDashboard();
        _isLoading = false;
        _dashboardNotice =
            'The Pi is offline or frozen. Showing the dashboard shell until live data returns.';
      });
    }
  }

  void _applyDashboardData(DashboardData dashboard) {
    if (!mounted) {
      return;
    }
    final liveDeviceIds = dashboard.devices.map((device) => device.id).toSet();
    setState(() {
      _dashboard = dashboard;
      _syncSafetyPopup(dashboard.alerts);
      _localPendingCommands.removeWhere((deviceId) {
        Device? device;
        for (final item in dashboard.devices) {
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
      _dashboardNotice = null;
    });
  }

  void _syncSafetyPopup(List<Alert> alerts) {
    final smokeAlert = _activeSmokeAlert(alerts);
    if (smokeAlert == null) {
      if (_smokeDialogVisible) {
        _smokeDialogVisible = false;
        Navigator.of(context, rootNavigator: true).maybePop();
      }
      return;
    }
    if (_notifiedSmokeAlertIds.add(smokeAlert.id)) {
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
      final message = alert.message.toLowerCase();
      if (alert.isActive &&
          (alert.id == 'smoke_detected_room1' ||
              type.contains('smoke') ||
              type.contains('gas') ||
              message.contains('smoke') ||
              message.contains('gas'))) {
        return alert;
      }
    }
    return null;
  }

  void _handleLiveError(Object error) {
    if (!mounted) {
      return;
    }
    if (_dashboard == null) {
      setState(() {
        _dashboard = _offlineDashboard();
        _isLoading = false;
        _dashboardNotice =
            'The Pi is offline or frozen. Showing the dashboard shell until live data returns.';
      });
      return;
    }
    setState(() {
      _dashboardNotice =
          'Live updates are paused. Showing the latest available dashboard data.';
    });
  }

  DashboardData _offlineDashboard() {
    final now = DateTime.now();
    return DashboardData(
      reading: EnergyReading(
        timestamp: now,
        voltage: 0,
        current: 0,
        power: 0,
        energyToday: 0,
        energyTotal: 0,
      ),
      sensors: SensorData(
        timestamp: DateTime.fromMillisecondsSinceEpoch(0),
        temperature: 0,
        humidity: 0,
        isOccupied: false,
        smokeStatus: 'Unknown',
        noiseStatus: 'Unknown',
        lightStatus: 'Unknown',
        online: false,
      ),
      devices: [
        Device(
          id: 'matter_socket_switch',
          name: 'Socket Switch',
          type: DeviceType.socket,
          isOn: false,
          currentPower: 0,
          branch: 'Main',
          online: false,
          localOnline: false,
          cloudOnline: false,
          controlMethod: 'home_assistant',
        ),
        Device(
          id: 'matter_ac_switch',
          name: 'AC Switch',
          type: DeviceType.airConditioner,
          isOn: false,
          currentPower: 0,
          branch: 'Main',
          online: false,
          localOnline: false,
          cloudOnline: false,
          controlMethod: 'home_assistant',
        ),
        Device(
          id: 'breaker_01',
          name: 'Switch Breaker',
          type: DeviceType.light,
          isOn: false,
          currentPower: 0,
          branch: 'Branch 1',
          online: false,
          localOnline: false,
          cloudOnline: false,
          controlMethod: 'tuya_cloud',
        ),
        Device(
          id: 'breaker_02',
          name: 'AC Breaker',
          type: DeviceType.airConditioner,
          isOn: false,
          currentPower: 0,
          branch: 'Branch 2',
          online: false,
          localOnline: false,
          cloudOnline: false,
          controlMethod: 'tuya_cloud',
        ),
      ],
      alerts: const [],
      tariffBhdPerKwh: ElectricityPricing.costPerKWh,
      deviceControlEnabled: false,
    );
  }

  @override
  Widget build(BuildContext context) {
    final dashboard = _dashboard;
    final isPaired = _homeId != null && _homeId!.isNotEmpty;
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
                      onLogout: _logout,
                    ),
                    if (_dashboardNotice != null) ...[
                      const SizedBox(height: 16),
                      _DashboardNotice(message: _dashboardNotice!),
                    ],
                    const SizedBox(height: 24),
                    EnergyHeroCard(
                      reading: dashboard.reading,
                      costToday: dashboard.reading.costToday > 0
                          ? dashboard.reading.costToday
                          : dashboard.reading.calculateCost(
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
                      onPair: _openQrScanner,
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
      _localCommandErrors.remove(device.id);
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
      });
    } finally {
      if (mounted) {
        setState(() => _localPendingCommands.remove(device.id));
      }
    }
  }

  void _openChat() =>
      Navigator.of(context).push(fadeSlideRoute(const AiChatbotScreen()));

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

  void _openSensors() => Navigator.of(
    context,
  ).push(fadeSlideRoute(SensorsStatusScreen(sensorData: _dashboard!.sensors)));

  Future<void> _logout() async {
    await _liveSubscription?.cancel();
    _liveSubscription = null;
    if (mounted) {
      setState(() {
        _dashboard = null;
        _homeId = null;
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
    final parsed = _parsePairingPayload(payload);
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
      final result = await _api.claimPi(
        piId: parsed.piId,
        token: parsed.token,
        homeName: 'KahrabaIQ Home',
      );
      if (!mounted) {
        return;
      }
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            'Paired ${result['pi_id'] ?? parsed.piId} successfully.',
          ),
        ),
      );
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

  _PairingPayload? _parsePairingPayload(String payload) {
    final uri = Uri.tryParse(payload);
    if (uri != null && uri.scheme == 'kahrabaiq' && uri.host == 'pair') {
      final piId = uri.queryParameters['pi_id']?.trim();
      final token = uri.queryParameters['token']?.trim();
      if (piId != null &&
          piId.isNotEmpty &&
          token != null &&
          token.isNotEmpty) {
        return _PairingPayload(piId: piId, token: token);
      }
    }
    final parts = payload.split(RegExp(r'\s+'));
    if (parts.length >= 2) {
      return _PairingPayload(
        piId: parts.first.trim(),
        token: parts.last.trim(),
      );
    }
    return _PairingPayload(piId: NetworkConfig.defaultHomePiId, token: payload);
  }

  String _displayName() {
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
  });

  final String name;
  final VoidCallback onPair;
  final VoidCallback onLogout;
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
          title: 'Pair your home',
          message:
              'Scan or enter the Pi pairing code to unlock live energy, breakers, and sensors.',
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
          label: Text(isPairing ? 'Pairing' : 'Pair home'),
        ),
      ],
    );
  }
}

class _DashboardActions extends StatelessWidget {
  const _DashboardActions({
    required this.onSensors,
    required this.onPair,
    required this.isPairing,
    this.showPair = true,
  });

  final VoidCallback onSensors;
  final VoidCallback onPair;
  final bool isPairing;
  final bool showPair;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Expanded(
          child: OutlinedButton.icon(
            onPressed: onSensors,
            icon: const Icon(Icons.sensors),
            label: const Text('Sensors'),
          ),
        ),
        if (showPair) ...[
          const SizedBox(width: 12),
          Expanded(
            child: OutlinedButton.icon(
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
      ],
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

class _PairingPayload {
  const _PairingPayload({required this.piId, required this.token});

  final String piId;
  final String token;
}
