/// Represents an energy reading from the metering system
class EnergyReading {
  final DateTime timestamp;
  final double voltage; // Volts
  final double current; // Amps
  final double power; // Watts
  final double energyToday; // kWh for today
  final double energyTotal; // Total kWh

  EnergyReading({
    required this.timestamp,
    required this.voltage,
    required this.current,
    required this.power,
    required this.energyToday,
    required this.energyTotal,
  });

  factory EnergyReading.fromJson(Map<String, dynamic> json) {
    return EnergyReading(
      timestamp: DateTime.parse(json['timestamp'] as String),
      voltage: (json['voltage'] as num).toDouble(),
      current: (json['current'] as num).toDouble(),
      power: (json['power'] as num).toDouble(),
      energyToday: (json['energyToday'] as num).toDouble(),
      energyTotal: (json['energyTotal'] as num).toDouble(),
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
    };
  }

  // Calculate cost based on rate per kWh
  double calculateCost(double ratePerKWh) {
    return energyToday * ratePerKWh;
  }
}
