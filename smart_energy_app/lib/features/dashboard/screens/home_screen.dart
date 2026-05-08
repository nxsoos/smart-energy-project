import 'dart:async';

import 'package:flutter/material.dart';

import '../../../core/theme/color_tokens.dart';
import '../../../core/utils/app_routes.dart';
import '../../../core/utils/constants.dart';
import '../../../core/widgets/alert_banner.dart';
import '../../../core/widgets/app_state_widgets.dart';
import '../../../shared/models/alert.dart';
import '../../../shared/models/device.dart';
import '../../../shared/models/energy_reading.dart';
import '../../../shared/models/sensor_data.dart';
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
  late EnergyReading _reading;
  late SensorData _sensorData;
  late List<Device> _devices;
  late List<Alert> _alerts;
  Timer? _pulseTimer;
  bool _isLoading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadDashboard();
    _pulseTimer = Timer.periodic(
      const Duration(seconds: 6),
      (_) => _simulateLiveUpdate(),
    );
  }

  @override
  void dispose() {
    _pulseTimer?.cancel();
    super.dispose();
  }

  Future<void> _loadDashboard() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    await Future<void>.delayed(const Duration(milliseconds: 500));
    if (!mounted) {
      return;
    }
    setState(() {
      _reading = EnergyReading(
        timestamp: DateTime.now(),
        voltage: 232.4,
        current: 8.9,
        power: 2140,
        energyToday: 7.8,
        energyTotal: 1428,
        costToday: 0.023,
      );
      _sensorData = SensorData(
        timestamp: DateTime.now(),
        temperature: 23.4,
        humidity: 46,
        isOccupied: true,
        smokeRaw: 120,
        lightRaw: 670,
        soundRaw: 28,
        noiseStatus: 'Quiet',
        lightStatus: 'Bright',
        smokeStatus: 'Clear',
        ahtOk: true,
        ens160Ok: true,
      );
      _devices = _initialDevices();
      _alerts = [
        Alert(
          id: 'usage-warning',
          type: AlertType.highConsumption,
          backendType: 'high_consumption',
          message: 'AC usage is trending above the evening baseline.',
          timestamp: DateTime.now(),
          severity: 'medium',
          affectedBranch: 'Matter AC Switch',
        ),
      ];
      _isLoading = false;
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: _isLoading
            ? _DashboardLoading(onRetry: _loadDashboard)
            : _error != null
            ? AppErrorState(message: _error!, onRetry: _loadDashboard)
            : RefreshIndicator(
                color: ColorTokens.primary,
                onRefresh: _loadDashboard,
                child: ListView(
                  padding: const EdgeInsets.fromLTRB(20, 24, 20, 32),
                  children: [
                    DashboardHeader(name: 'Ali', alertCount: _alerts.length),
                    const SizedBox(height: 24),
                    EnergyHeroCard(
                      reading: _reading,
                      costToday: _reading.calculateCost(
                        ElectricityPricing.costPerKWh,
                      ),
                    ),
                    const SizedBox(height: 16),
                    QuickStatsRow(reading: _reading, sensorData: _sensorData),
                    const SizedBox(height: 16),
                    if (_alerts.isNotEmpty)
                      AlertBanner(
                        alert: _alerts.first,
                        onDismiss: () => setState(() => _alerts.removeAt(0)),
                      ),
                    const SizedBox(height: 16),
                    AiInsightsBanner(
                      text:
                          'AI suggests turning off AC for 30 minutes, saving about 0.8 kWh.',
                      onTap: _openChat,
                    ),
                    const SizedBox(height: 22),
                    DevicesSection(devices: _devices, onToggle: _toggleDevice),
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

  void _simulateLiveUpdate() {
    if (!mounted || _isLoading) {
      return;
    }
    setState(() {
      _reading = EnergyReading(
        timestamp: DateTime.now(),
        voltage: _reading.voltage,
        current: _reading.current,
        power: _reading.power == 2140 ? 2380 : 2140,
        energyToday: _reading.energyToday + 0.02,
        energyTotal: _reading.energyTotal + 0.02,
        costToday: _reading.costToday + 0.001,
      );
    });
  }

  void _toggleDevice(Device device, bool value) {
    setState(() {
      _devices = _devices
          .map(
            (item) => item.id == device.id ? item.copyWith(isOn: value) : item,
          )
          .toList();
    });
  }

  void _openChat() =>
      Navigator.of(context).push(fadeSlideRoute(const AiChatbotScreen()));

  void _openSensors() => Navigator.of(
    context,
  ).push(fadeSlideRoute(SensorsStatusScreen(sensorData: _sensorData)));

  void _openQrScanner() =>
      Navigator.of(context).push(fadeSlideRoute(const QrScannerScreen()));

  List<Device> _initialDevices() => [
    Device(
      id: 'breaker_01',
      name: 'Kitchen Breaker',
      type: DeviceType.socket,
      isOn: true,
      currentPower: 420,
      branch: 'Branch 1',
    ),
    Device(
      id: 'breaker_02',
      name: 'Living Room',
      type: DeviceType.light,
      isOn: true,
      currentPower: 180,
      branch: 'Branch 2',
    ),
    Device(
      id: 'matter_ac_switch',
      name: 'AC Switch',
      type: DeviceType.airConditioner,
      isOn: false,
      currentPower: 0,
      branch: 'Matter',
      controlMethod: 'home_assistant',
    ),
  ];
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
