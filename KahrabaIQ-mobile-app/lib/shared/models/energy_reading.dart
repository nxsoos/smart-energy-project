/// Represents an energy reading from the metering system
class EnergyReading {
  final DateTime timestamp;
  final double voltage; // Volts
  final double current; // Amps
  final double power; // Watts
  final double energyToday; // kWh for today
  final double energyTotal; // Total kWh
  final double costToday; // Cost for today

  EnergyReading({
    required this.timestamp,
    required this.voltage,
    required this.current,
    required this.power,
    required this.energyToday,
    required this.energyTotal,
    this.costToday = 0.0,
  });

  factory EnergyReading.fromJson(Map<String, dynamic> json) {
    return EnergyReading(
      timestamp: DateTime.parse(json['timestamp'] as String),
      voltage: (json['voltage'] as num).toDouble(),
      current: (json['current'] as num).toDouble(),
      power: (json['power'] as num).toDouble(),
      energyToday: (json['energyToday'] as num).toDouble(),
      energyTotal: (json['energyTotal'] as num).toDouble(),
      costToday: (json['costToday'] as num?)?.toDouble() ?? 0.0,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'timestamp': timestamp.toIso8601String(),
      'voltage': voltage,
      'current': current,
      'power': power,
      'energyToday': energyToday,
      'energyTotal': energyTotal,
      'costToday': costToday,
    };
  }

  // Calculate cost based on rate per kWh
  double calculateCost(double ratePerKWh) {
    return costToday > 0 ? costToday : energyToday * ratePerKWh;
  }
}
