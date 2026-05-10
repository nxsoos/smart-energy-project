import '../../core/utils/constants.dart';
import '../../shared/models/ai_insights.dart';
import '../../shared/models/alert.dart';
import '../../shared/models/device.dart';
import '../../shared/models/energy_reading.dart';
import '../../shared/models/sensor_data.dart';
import '../../shared/services/kahrabaiq_api_service.dart';

class DemoScenarioData {
  const DemoScenarioData({
    required this.id,
    required this.name,
    required this.description,
    required this.dashboard,
  });

  final String id;
  final String name;
  final String description;
  final DashboardData dashboard;

  Map<String, dynamic> toBackendPayload() {
    return {
      'scenario_id': id,
      'scenario_name': name,
      'scenario_description': description,
      'room': {
        'temperature': dashboard.sensors.temperature,
        'humidity': dashboard.sensors.humidity,
        'motion': dashboard.sensors.isOccupied,
        'eco2': dashboard.sensors.eco2,
        'tvoc': dashboard.sensors.tvoc,
        'aqi': dashboard.sensors.aqi,
        'smokeStatus': dashboard.sensors.smokeStatus,
        'lightStatus': dashboard.sensors.lightStatus,
        'soundRaw': dashboard.sensors.soundRaw,
        'noise': dashboard.sensors.noise,
        'online': dashboard.sensors.online,
      },
      'energy': {
        'power': dashboard.reading.power,
        'voltage': dashboard.reading.voltage,
        'current': dashboard.reading.current,
        'energyToday': dashboard.reading.energyToday,
        'costToday': dashboard.reading.costToday,
        'tariff_BHD_per_kWh': dashboard.tariffBhdPerKwh,
      },
      'devices': {
        for (final device in dashboard.devices)
          device.id: {
            'id': device.id,
            'name': device.name,
            'isOn': device.isOn,
            'power': device.currentPower,
            'voltage': device.voltage,
            'current': device.current,
            'energyToday': device.energyToday,
            'online': device.online,
            'branch': device.branch,
          },
      },
      'occupancy': dashboard.occupancy,
      'recent_history': dashboard.settingsSummary['recent_history'] ?? {},
      'routine_context': dashboard.settingsSummary['routine_context'] ?? {},
      'store': false,
    };
  }
}

List<DemoScenario> get demoScenarioSummaries => demoScenarios
    .map(
      (scenario) => DemoScenario(
        id: scenario.id,
        name: scenario.name,
        description: scenario.description,
      ),
    )
    .toList(growable: false);

final List<DemoScenarioData> demoScenarios = [
  _scenario(
    id: 'normal_usage',
    name: 'Normal Usage',
    description: 'Low power, comfortable room conditions, and normal activity.',
    power: 82,
    energyToday: 1.18,
    costToday: 0.038,
    temperature: 24.4,
    humidity: 47,
    occupied: true,
    lightStatus: 'Normal',
    smokeStatus: 'Clear',
    socketOn: true,
    socketPower: 35,
    acOn: false,
    acPower: 0,
    statusLabel: 'Normal',
    statusTone: 'success',
    summary: 'Energy use looks normal for this time of day.',
    actionTitle: 'Keep monitoring',
    recommendationType: 'none',
    nextEnergy: 0.09,
    nextCost: 0.003,
    efficiency: 96,
    explanation:
        'Occupancy is present, power is low, and usage is close to the recent same-hour average.',
    notifications: [
      _notification(
        id: 'normal_monitoring',
        severity: 'info',
        category: 'routine',
        title: 'Normal usage pattern',
        message: 'KahrabaIQ is monitoring normal energy behavior.',
      ),
    ],
  ),
  _scenario(
    id: 'ac_left_on_empty',
    name: 'AC Left On Without Occupancy',
    description: 'AC breaker is drawing high power with no recent motion.',
    power: 1280,
    energyToday: 5.7,
    costToday: 0.182,
    temperature: 22.1,
    humidity: 44,
    occupied: false,
    lightStatus: 'Dim',
    smokeStatus: 'Clear',
    socketOn: false,
    socketPower: 0,
    acOn: true,
    acPower: 1235,
    occupancy: const {
      'occupancy_score': 0.04,
      'time_since_last_motion_minutes': 48,
    },
    history: const {
      'recent_energy_avg': 0.18,
      'recent_energy_std': 0.05,
      'same_hour_energy_avg': 0.14,
      'previous_hour_energy': 0.72,
      'routine_score': 0.82,
    },
    statusLabel: 'Likely Waste',
    statusTone: 'danger',
    summary: 'AC power is high while the room appears empty.',
    actionTitle: 'Turn off AC',
    recommendationType: 'turn_off_ac',
    nextEnergy: 1.05,
    nextCost: 0.034,
    efficiency: 42,
    explanation:
        'The AC is consuming about 1.2 kW and no motion has been seen for 48 minutes, so this is treated as energy waste.',
    notifications: [
      _notification(
        id: 'demo_ac_empty_alert',
        severity: 'high',
        category: 'energy',
        title: 'AC left on while empty',
        message: 'Turn off the AC or enable auto mode to reduce waste.',
        deviceId: 'breaker_02',
        recommendationType: 'turn_off_ac',
        confidence: 0.93,
      ),
    ],
  ),
  _scenario(
    id: 'socket_left_on',
    name: 'Socket/Device Left On',
    description: 'Socket breaker is active with no occupancy evidence.',
    power: 310,
    energyToday: 2.6,
    costToday: 0.083,
    temperature: 25.0,
    humidity: 50,
    occupied: false,
    lightStatus: 'Dark',
    smokeStatus: 'Clear',
    socketOn: true,
    socketPower: 285,
    acOn: false,
    acPower: 0,
    occupancy: const {
      'occupancy_score': 0.08,
      'time_since_last_motion_minutes': 36,
    },
    statusLabel: 'Possible Waste',
    statusTone: 'warning',
    summary: 'A socket-connected device appears to be left on.',
    actionTitle: 'Turn off socket',
    recommendationType: 'turn_off_socket',
    nextEnergy: 0.28,
    nextCost: 0.009,
    efficiency: 58,
    explanation:
        'Socket power is active while the room appears empty, so KahrabaIQ suggests switching it off if unused.',
    notifications: [
      _notification(
        id: 'demo_socket_left_on',
        severity: 'medium',
        category: 'recommendation',
        title: 'Device may be left on',
        message:
            'Review the socket device and turn it off if nobody is using it.',
        deviceId: 'breaker_01',
        recommendationType: 'turn_off_socket',
        confidence: 0.84,
      ),
    ],
  ),
  _scenario(
    id: 'unusual_ac_routine',
    name: 'Unusual AC Routine',
    description: 'AC is active at 2 AM outside the usual weekday pattern.',
    power: 970,
    energyToday: 4.2,
    costToday: 0.134,
    temperature: 23.0,
    humidity: 46,
    occupied: false,
    lightStatus: 'Dark',
    smokeStatus: 'Clear',
    socketOn: false,
    socketPower: 0,
    acOn: true,
    acPower: 940,
    history: const {
      'recent_energy_avg': 0.22,
      'recent_energy_std': 0.07,
      'same_hour_energy_avg': 0.10,
      'previous_hour_energy': 0.16,
      'weekday_routine_score': 0.12,
      'outside_routine_score': 0.91,
    },
    statusLabel: 'Unusual Routine',
    statusTone: 'warning',
    summary: 'AC is running outside the usual routine.',
    actionTitle: 'Confirm AC use',
    recommendationType: 'review_ac_schedule',
    nextEnergy: 0.82,
    nextCost: 0.026,
    efficiency: 61,
    explanation:
        'Recent history suggests this home usually uses AC around 6 PM on weekdays, not around 2 AM.',
    notifications: [
      _notification(
        id: 'demo_ac_outside_routine',
        severity: 'medium',
        category: 'routine',
        title: 'AC outside routine',
        message: 'Confirm whether the AC should stay on at this time.',
        deviceId: 'breaker_02',
        recommendationType: 'review_ac_schedule',
        confidence: 0.78,
      ),
    ],
  ),
  _scenario(
    id: 'high_energy_consumption',
    name: 'High Energy Consumption',
    description: 'Total power is much higher than recent same-hour usage.',
    power: 1840,
    energyToday: 7.4,
    costToday: 0.237,
    temperature: 25.6,
    humidity: 52,
    occupied: true,
    lightStatus: 'Bright',
    smokeStatus: 'Clear',
    socketOn: true,
    socketPower: 420,
    acOn: true,
    acPower: 1380,
    history: const {
      'recent_energy_avg': 0.31,
      'recent_energy_std': 0.08,
      'same_hour_energy_avg': 0.25,
      'previous_hour_energy': 0.29,
      'routine_score': 0.65,
    },
    statusLabel: 'Anomaly',
    statusTone: 'warning',
    summary: 'Energy use is much higher than normal for this hour.',
    actionTitle: 'Inspect breakers',
    recommendationType: 'review_unusual_energy_usage',
    nextEnergy: 1.42,
    nextCost: 0.045,
    efficiency: 54,
    explanation:
        'The current load is above the rolling average and same-hour comparison, mainly from AC and socket branches.',
    notifications: [
      _notification(
        id: 'demo_high_energy',
        severity: 'medium',
        category: 'anomaly',
        title: 'High energy anomaly',
        message:
            'Inspect AC and socket usage because current power is above the usual range.',
        recommendationType: 'review_unusual_energy_usage',
        confidence: 0.88,
      ),
    ],
  ),
  _scenario(
    id: 'smoke_gas_safety',
    name: 'Smoke/Gas Safety Alert',
    description: 'Smoke/gas sensor reports a critical safety condition.',
    power: 480,
    energyToday: 2.1,
    costToday: 0.067,
    temperature: 29.2,
    humidity: 55,
    occupied: true,
    lightStatus: 'Bright',
    smokeStatus: 'Smoke/Gas',
    socketOn: true,
    socketPower: 170,
    acOn: false,
    acPower: 0,
    statusLabel: 'Critical Safety',
    statusTone: 'critical',
    summary: 'Smoke or gas was detected. Check the room immediately.',
    actionTitle: 'Check room now',
    recommendationType: 'check_smoke_gas_sensor',
    nextEnergy: 0.18,
    nextCost: 0.006,
    efficiency: 20,
    explanation:
        'Safety overrides energy optimization. The AI creates a critical alert because smoke/gas is detected.',
    notifications: [
      _notification(
        id: 'demo_smoke_gas',
        severity: 'critical',
        category: 'safety',
        title: 'Gas or smoke detected',
        message:
            'Turn off affected devices if safe and check the room immediately.',
        recommendationType: 'check_smoke_gas_sensor',
        confidence: 1.0,
      ),
    ],
  ),
  _scenario(
    id: 'stale_sensor_breaker',
    name: 'Stale Breaker/Sensor Data',
    description:
        'Latest sensor and breaker data is old, lowering AI confidence.',
    power: 0,
    energyToday: 1.9,
    costToday: 0.061,
    temperature: 0,
    humidity: 0,
    occupied: false,
    lightStatus: 'Unknown',
    smokeStatus: 'Unknown',
    socketOn: false,
    socketPower: 0,
    acOn: false,
    acPower: 0,
    sensorOnline: false,
    breakerOnline: false,
    history: const {
      'sensor_staleness_seconds': 980,
      'breaker_staleness_seconds': 760,
      'recent_energy_avg': 0.16,
      'recent_energy_std': 0.03,
      'same_hour_energy_avg': 0.14,
      'previous_hour_energy': 0.15,
    },
    statusLabel: 'Needs Data',
    statusTone: 'warning',
    summary: 'AI confidence is limited because recent hardware data is stale.',
    actionTitle: 'Check connections',
    recommendationType: 'check_sensor_breaker_data',
    nextEnergy: 0.14,
    nextCost: 0.004,
    efficiency: 35,
    explanation:
        'The latest room sensor and breaker readings are old, so the AI asks for fresh Pi, ESP32, and breaker data before making strong decisions.',
    notifications: [
      _notification(
        id: 'demo_stale_data',
        severity: 'medium',
        category: 'system',
        title: 'Data freshness issue',
        message: 'Check Pi, ESP32, and breaker connectivity.',
        recommendationType: 'check_sensor_breaker_data',
        confidence: 0.72,
      ),
    ],
  ),
];

DemoScenarioData? findDemoScenario(String scenarioId) {
  for (final scenario in demoScenarios) {
    if (scenario.id == scenarioId) {
      return scenario;
    }
  }
  return null;
}

DemoScenarioData _scenario({
  required String id,
  required String name,
  required String description,
  required double power,
  required double energyToday,
  required double costToday,
  required double temperature,
  required double humidity,
  required bool occupied,
  required String lightStatus,
  required String smokeStatus,
  required bool socketOn,
  required double socketPower,
  required bool acOn,
  required double acPower,
  required String statusLabel,
  required String statusTone,
  required String summary,
  required String actionTitle,
  required String recommendationType,
  required double nextEnergy,
  required double nextCost,
  required double efficiency,
  required String explanation,
  required List<AiNotification> notifications,
  Map<String, dynamic> occupancy = const {},
  Map<String, dynamic> history = const {},
  bool sensorOnline = true,
  bool breakerOnline = true,
}) {
  final now = DateTime.now();
  final alerts = notifications
      .where((item) => item.isAlert)
      .map(
        (item) => Alert(
          id: item.id,
          type: item.category == 'safety'
              ? AlertType.fire
              : item.category == 'energy'
              ? AlertType.highConsumption
              : AlertType.sensorFailure,
          backendType: item.category,
          message: item.message,
          timestamp: item.createdAt,
          severity: item.severity,
        ),
      )
      .toList(growable: false);

  final dashboard = DashboardData(
    reading: EnergyReading(
      timestamp: now,
      voltage: breakerOnline ? 230 : 0,
      current: breakerOnline ? power / 230 : 0,
      power: power,
      energyToday: energyToday,
      energyTotal: energyToday,
      costToday: costToday,
    ),
    sensors: SensorData(
      timestamp: sensorOnline ? now : now.subtract(const Duration(minutes: 16)),
      temperature: temperature,
      humidity: humidity,
      isOccupied: occupied,
      eco2: sensorOnline ? 620 : 0,
      tvoc: sensorOnline ? 80 : 0,
      aqi: sensorOnline ? 2 : 0,
      smokeRaw: smokeStatus.toLowerCase().contains('smoke') ? 1 : 0,
      lightRaw: lightStatus == 'Bright'
          ? 1800
          : lightStatus == 'Dark'
          ? 80
          : 650,
      soundRaw: occupied ? 48 : 18,
      noise: occupied ? 1 : 0,
      noiseStatus: occupied ? 'Active' : 'Quiet',
      lightStatus: lightStatus,
      smokeStatus: smokeStatus,
      ahtOk: sensorOnline,
      ens160Ok: sensorOnline,
      online: sensorOnline,
    ),
    devices: [
      _device(
        id: 'breaker_01',
        name: 'Socket Breaker',
        type: DeviceType.socket,
        isOn: socketOn,
        power: socketPower,
        branch: 'Socket',
        online: breakerOnline,
      ),
      _device(
        id: 'breaker_02',
        name: 'AC Breaker',
        type: DeviceType.airConditioner,
        isOn: acOn,
        power: acPower,
        branch: 'AC',
        online: breakerOnline,
      ),
    ],
    alerts: alerts,
    tariffBhdPerKwh: ElectricityPricing.costPerKWh,
    aiDashboard: AiDashboardSummary(
      updatedAt: now,
      source: 'demo_ai',
      modelName: 'demo_scenario_ai',
      modelVersion: 'simulation',
      inputSource: 'local_demo_scenario',
      energyWaste: recommendationType != 'none' && statusTone != 'success',
      wasteConfidence: notifications.isEmpty
          ? 0.95
          : notifications.first.confidence ?? 0.86,
      abnormalUsage: statusLabel.toLowerCase() != 'normal',
      abnormalUsageConfidence: notifications.isEmpty
          ? 0.90
          : notifications.first.confidence ?? 0.82,
      recommendationType: recommendationType,
      statusCode: id,
      statusLabel: statusLabel,
      statusTone: statusTone,
      statusSummary: summary,
      actionTitle: actionTitle,
      nextHourEnergyKwh: nextEnergy,
      nextHourCostBhd: nextCost,
      efficiencyScore: efficiency,
      explanation: explanation,
      controlSuggestion: actionTitle,
    ),
    aiRecommendation: AiRecommendation(
      recommendationId: 'demo_$id',
      type: 'demo_ai_recommendation',
      priority: notifications.isEmpty ? 'low' : notifications.first.severity,
      title: actionTitle,
      message: summary,
      source: 'demo_ai',
      relatedDeviceId: notifications.isEmpty
          ? null
          : notifications.first.deviceId,
      recommendationType: recommendationType,
      status: 'active',
      createdAt: now,
      updatedAt: now,
    ),
    aiNotifications: notifications,
    actionSuggestions: recommendationType == 'none'
        ? const []
        : [
            ActionSuggestion(
              id: 'demo_suggestion_$id',
              deviceName: acOn
                  ? 'AC Breaker'
                  : socketOn
                  ? 'Socket Breaker'
                  : 'System',
              deviceId: acOn
                  ? 'breaker_02'
                  : socketOn
                  ? 'breaker_01'
                  : 'system',
              suggestedCommand: recommendationType.contains('turn_off')
                  ? 'turn_off'
                  : 'review',
              reason: explanation,
              status: 'demo',
            ),
          ],
    occupancy: {
      'state': occupied ? 'occupied' : 'empty',
      'occupied': occupied,
      'occupancy_score': occupied ? 0.82 : 0.05,
      'time_since_last_motion_minutes': occupied ? 1 : 35,
      ...occupancy,
    },
    settingsSummary: {'mode': 'demo', 'recent_history': history},
    criticalAlerts: alerts
        .where((alert) => alert.severity.toLowerCase() == 'critical')
        .map((alert) => alert.toJson())
        .toList(growable: false),
    control: const ControlModeInfo(
      mode: 'demo',
      label: 'Demo Mode',
      description:
          'Device control is disabled while simulated scenario data is shown.',
    ),
    scenarioId: id,
    scenarioName: name,
    scenarioDescription: description,
    deviceControlEnabled: false,
  );

  return DemoScenarioData(
    id: id,
    name: name,
    description: description,
    dashboard: dashboard,
  );
}

Device _device({
  required String id,
  required String name,
  required DeviceType type,
  required bool isOn,
  required double power,
  required String branch,
  required bool online,
}) {
  return Device(
    id: id,
    name: name,
    type: type,
    isOn: isOn && online,
    currentPower: online ? power : 0,
    branch: branch,
    online: online,
    localOnline: online,
    cloudOnline: online,
    controllable: false,
    energySupported: true,
    voltage: online ? 230 : 0,
    current: online ? power / 230 : 0,
    energyToday: online ? power / 1000 : 0,
    controlMethod: 'demo_simulation',
  );
}

AiNotification _notification({
  required String id,
  required String severity,
  required String category,
  required String title,
  required String message,
  String? deviceId,
  String? recommendationType,
  double? confidence,
}) {
  return AiNotification(
    id: id,
    homeId: 'home_demo',
    severity: severity,
    category: category,
    title: title,
    message: message,
    deviceId: deviceId,
    recommendationType: recommendationType,
    createdAt: DateTime.now(),
    acknowledged: false,
    source: 'demo_ai',
    confidence: confidence,
    explanation: message,
  );
}
