import '../utils/constants.dart';

/// Represents a system alert.
class Alert {
  final String id;
  final AlertType type;
  final String backendType;
  final String message;
  final DateTime timestamp;
  final String severity; // low, medium, high, critical
  final bool isActive;
  final String? affectedBranch;

  Alert({
    required this.id,
    required this.type,
    required this.backendType,
    required this.message,
    required this.timestamp,
    required this.severity,
    this.isActive = true,
    this.affectedBranch,
  });

  factory Alert.fromJson(Map<String, dynamic> json) {
    final backendType = (json['type'] as String?) ?? 'sensorfailure';

    return Alert(
      id: (json['id'] as String?) ?? DateTime.now().millisecondsSinceEpoch.toString(),
      type: _parseAlertType(backendType),
      backendType: backendType,
      message: (json['message'] as String?) ?? 'System alert',
      timestamp: _parseTimestamp(json['timestamp']),
      severity: (json['severity'] as String?) ?? (json['level'] as String?) ?? 'medium',
      isActive: json['isActive'] as bool? ?? true,
      affectedBranch: json['affectedBranch'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'type': backendType,
      'message': message,
      'timestamp': timestamp.toIso8601String(),
      'severity': severity,
      'isActive': isActive,
      'affectedBranch': affectedBranch,
    };
  }

  static AlertType _parseAlertType(String type) {
    switch (type.toLowerCase()) {
      case 'overload':
        return AlertType.overload;
      case 'fire':
      case 'safety':
        return AlertType.fire;
      case 'highconsumption':
      case 'high_consumption':
      case 'energy_waste':
        return AlertType.highConsumption;
      case 'comfort':
      case 'sensorfailure':
      case 'sensor_failure':
      default:
        return AlertType.sensorFailure;
    }
  }

  static DateTime _parseTimestamp(dynamic raw) {
    if (raw is int) {
      return raw > 1000000000000
          ? DateTime.fromMillisecondsSinceEpoch(raw)
          : DateTime.fromMillisecondsSinceEpoch(raw * 1000);
    }

    if (raw is num) {
      final value = raw.toInt();
      return value > 1000000000000
          ? DateTime.fromMillisecondsSinceEpoch(value)
          : DateTime.fromMillisecondsSinceEpoch(value * 1000);
    }

    if (raw is String) {
      final parsedInt = int.tryParse(raw);
      if (parsedInt != null) {
        return parsedInt > 1000000000000
            ? DateTime.fromMillisecondsSinceEpoch(parsedInt)
            : DateTime.fromMillisecondsSinceEpoch(parsedInt * 1000);
      }

      return DateTime.tryParse(raw) ?? DateTime.now();
    }

    return DateTime.now();
  }

  int get color {
    switch (severity.toLowerCase()) {
      case 'critical':
        return 0xFFF44336;
      case 'high':
        return 0xFFFF9800;
      case 'medium':
        return 0xFFFFC107;
      case 'low':
        return 0xFF2196F3;
      default:
        return 0xFF9E9E9E;
    }
  }
}
