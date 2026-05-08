import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/theme/color_tokens.dart';
import '../../../core/utils/app_routes.dart';
import '../../../core/utils/constants.dart';
import '../../../core/widgets/alert_banner.dart';
import '../../../core/widgets/app_state_widgets.dart';
import '../../../shared/models/device.dart';
import '../../../shared/services/auth_service.dart';
import '../../../shared/services/kahrabaiq_api_service.dart';
import '../../ai_chat/screens/ai_chatbot_screen.dart';
import '../../pairing/screens/qr_scanner_screen.dart';
import '../../sensors/screens/sensors_status_screen.dart';
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
  DashboardData? _dashboard;
  StreamSubscription<DashboardData>? _liveSubscription;
  bool _isLoading = true;
  String? _error;
  final Set<String> _localPendingCommands = {};
  final Map<String, String> _localCommandErrors = {};

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
    });

    if (widget.enableRealtimeSync && NetworkConfig.useAwsIotLive) {
      _liveSubscription = _api
          .watchLiveDashboardData(homeId: NetworkConfig.defaultHomeId)
          .listen(_applyDashboardData, onError: _handleLiveError);
    }

    if (!NetworkConfig.remoteLiveOnly || !NetworkConfig.useAwsIotLive) {
      try {
        final dashboard = await _api.fetchDashboardData(
          homeId: NetworkConfig.defaultHomeId,
        );
        _applyDashboardData(dashboard);
      } catch (error) {
        if (!mounted) {
          return;
        }
        if (_dashboard == null && !NetworkConfig.useAwsIotLive) {
          setState(() {
            _isLoading = false;
            _error = 'Dashboard connection failed. Pull to retry.';
          });
        }
      }
    }
  }

  void _applyDashboardData(DashboardData dashboard) {
    if (!mounted) {
      return;
    }
    final liveDeviceIds = dashboard.devices.map((device) => device.id).toSet();
    setState(() {
      _dashboard = dashboard;
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
      _localCommandErrors.removeWhere((deviceId, _) => liveDeviceIds.contains(deviceId));
      _isLoading = false;
      _error = null;
    });
  }

  void _handleLiveError(Object error) {
    if (!mounted) {
      return;
    }
    if (_dashboard == null) {
      setState(() {
        _isLoading = false;
        _error = 'Live dashboard data is unavailable. Pull to retry.';
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    final dashboard = _dashboard;
    return Scaffold(
      body: SafeArea(
        child: _isLoading
            ? _DashboardLoading(onRetry: () => _loadDashboard())
            : _error != null
            ? AppErrorState(
                message: _error!,
                onRetry: () => _loadDashboard(),
              )
            : dashboard == null
            ? AppEmptyState(
                icon: Icons.dashboard_outlined,
                title: 'Waiting for live data',
                message: NetworkConfig.useAwsIotLive
                    ? 'AWS IoT is connected, but no dashboard message has arrived yet.'
                    : 'Connect to the Pi or enable AWS IoT live data.',
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
                    ),
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
                      sensorData: dashboard.sensors,
                    ),
                    const SizedBox(height: 16),
                    if (dashboard.alerts.isNotEmpty)
                      AlertBanner(
                        alert: dashboard.alerts.first,
                        onDismiss: () {},
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
                    ),
                  ],
                ),
              ),
      ),
    );
  }

  Future<void> _toggleDevice(Device device, bool value) async {
    final action = value ? 'turn_on' : 'turn_off';
    setState(() {
      _localPendingCommands.add(device.id);
      _localCommandErrors.remove(device.id);
    });
    try {
      final result = await _api.sendDeviceCommand(
        device.id,
        action,
        homeId: NetworkConfig.defaultHomeId,
      );
      if (!mounted) {
        return;
      }
      if (!result.success) {
        setState(() {
          _localCommandErrors[device.id] = result.message;
        });
      }
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _localCommandErrors[device.id] =
            error.toString().replaceFirst('Exception: ', '');
      });
    } finally {
      if (mounted) {
        setState(() => _localPendingCommands.remove(device.id));
      }
    }
  }

  void _openChat() =>
      Navigator.of(context).push(fadeSlideRoute(const AiChatbotScreen()));

  void _openSensors() => Navigator.of(
    context,
  ).push(fadeSlideRoute(SensorsStatusScreen(sensorData: _dashboard!.sensors)));

  void _openQrScanner() =>
      Navigator.of(context).push(fadeSlideRoute(const QrScannerScreen()));

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

class _DashboardActions extends StatelessWidget {
  const _DashboardActions({required this.onSensors, required this.onPair});

  final VoidCallback onSensors;
  final VoidCallback onPair;

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
        const SizedBox(width: 12),
        Expanded(
          child: OutlinedButton.icon(
            onPressed: onPair,
            icon: const Icon(Icons.qr_code_scanner),
            label: const Text('Pair'),
          ),
        ),
      ],
    );
  }
}
