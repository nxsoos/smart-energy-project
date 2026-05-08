/// Represents sensor data from ESP32 (temperature, humidity, occupancy)
class SensorData {
  final DateTime timestamp;
  final double temperature; // Celsius
  final double humidity; // Percentage
  final bool isOccupied; // From PIR sensor
  final double eco2; // ppm
  final double tvoc; // ppb
  final int aqi;
  final int smokeRaw;
  final int lightRaw;
  final int soundRaw;
  final int noise;
  final String noiseStatus;
  final String lightStatus;
  final String smokeStatus;
  final bool ahtOk;
  final bool ens160Ok;
  final bool online;

  SensorData({
    required this.timestamp,
    required this.temperature,
    required this.humidity,
    required this.isOccupied,
    this.eco2 = 0,
    this.tvoc = 0,
    this.aqi = 0,
    this.smokeRaw = 0,
    this.lightRaw = 0,
    this.soundRaw = 0,
    this.noise = 0,
    this.noiseStatus = 'Unknown',
    this.lightStatus = 'Unknown',
    this.smokeStatus = 'Unknown',
    this.ahtOk = false,
    this.ens160Ok = false,
    this.online = true,
  });

  factory SensorData.fromJson(Map<String, dynamic> json) {
    return SensorData(
      timestamp: DateTime.parse(json['timestamp'] as String),
      temperature: (json['temperature'] as num).toDouble(),
      humidity: (json['humidity'] as num).toDouble(),
      isOccupied: json['isOccupied'] as bool,
      eco2: (json['eco2'] as num?)?.toDouble() ?? 0,
      tvoc: (json['tvoc'] as num?)?.toDouble() ?? 0,
      aqi: (json['aqi'] as num?)?.toInt() ?? 0,
      smokeRaw: (json['smokeRaw'] as num?)?.toInt() ?? 0,
      lightRaw: (json['lightRaw'] as num?)?.toInt() ?? 0,
      soundRaw: (json['soundRaw'] as num?)?.toInt() ?? 0,
      noise: (json['noise'] as num?)?.toInt() ?? 0,
      noiseStatus: (json['noiseStatus'] as String?) ?? 'Unknown',
      lightStatus: (json['lightStatus'] as String?) ?? 'Unknown',
      smokeStatus: (json['smokeStatus'] as String?) ?? 'Unknown',
      ahtOk: (json['ahtOk'] as bool?) ?? false,
      ens160Ok: (json['ens160Ok'] as bool?) ?? false,
      online: (json['online'] as bool?) ?? true,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'timestamp': timestamp.toIso8601String(),
      'temperature': temperature,
      'humidity': humidity,
      'isOccupied': isOccupied,
      'eco2': eco2,
      'tvoc': tvoc,
      'aqi': aqi,
      'smokeRaw': smokeRaw,
      'lightRaw': lightRaw,
      'soundRaw': soundRaw,
      'noise': noise,
      'noiseStatus': noiseStatus,
      'lightStatus': lightStatus,
      'smokeStatus': smokeStatus,
      'ahtOk': ahtOk,
      'ens160Ok': ens160Ok,
      'online': online,
    };
  }

  // Check if temperature is comfortable
  bool get isComfortableTemp => temperature >= 18 && temperature <= 26;

  // Check if humidity is in comfortable range
  bool get isComfortableHumidity => humidity >= 30 && humidity <= 60;
}
