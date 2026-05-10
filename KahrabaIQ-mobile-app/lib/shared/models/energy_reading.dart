/// Represents an energy reading from the metering system
class EnergyReading {
  final DateTime timestamp;
  final double voltage; // Volts
  final double current; // Amps
  final double power; // Watts
  final double energyToday; // kWh for today
  final double energyMonth; // kWh for the current month
  final double energyTotal; // Total kWh
  final double costToday; // Cost for today
  final double costMonth; // Cost for the current month
  final bool monthDataAvailable;
  final String monthSource;

  EnergyReading({
    required this.timestamp,
    required this.voltage,
    required this.current,
    required this.power,
    required this.energyToday,
    this.energyMonth = 0.0,
    required this.energyTotal,
    this.costToday = 0.0,
    this.costMonth = 0.0,
    this.monthDataAvailable = true,
    this.monthSource = '',
  });

  factory EnergyReading.fromJson(Map<String, dynamic> json) {
    return EnergyReading(
      timestamp: DateTime.parse(json['timestamp'] as String),
      voltage: (json['voltage'] as num).toDouble(),
      current: (json['current'] as num).toDouble(),
      power: (json['power'] as num).toDouble(),
      energyToday: (json['energyToday'] as num).toDouble(),
      energyMonth: (json['energyMonth'] as num?)?.toDouble() ?? 0.0,
      energyTotal: (json['energyTotal'] as num).toDouble(),
      costToday: (json['costToday'] as num?)?.toDouble() ?? 0.0,
      costMonth: (json['costMonth'] as num?)?.toDouble() ?? 0.0,
      monthDataAvailable: json['monthDataAvailable'] as bool? ?? true,
      monthSource: json['monthSource'] as String? ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'timestamp': timestamp.toIso8601String(),
      'voltage': voltage,
      'current': current,
      'power': power,
      'energyToday': energyToday,
      'energyMonth': energyMonth,
      'energyTotal': energyTotal,
      'costToday': costToday,
      'costMonth': costMonth,
      'monthDataAvailable': monthDataAvailable,
      'monthSource': monthSource,
    };
  }

  // Calculate cost based on rate per kWh
  double calculateCost(double ratePerKWh) {
    return costToday > 0 ? costToday : energyToday * ratePerKWh;
  }

  double calculateMonthCost(double ratePerKWh) {
    return costMonth > 0 ? costMonth : energyMonth * ratePerKWh;
  }
}
