import '../../core/utils/constants.dart';

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
    final backendType =
        (json['alert_type'] as String?) ??
        (json['category'] as String?) ??
        (json['type'] as String?) ??
        'sensorfailure';
    final alertId =
        (json['alert_id'] as String?) ??
        (json['id'] as String?) ??
        (json['alertId'] as String?) ??
        DateTime.now().millisecondsSinceEpoch.toString();
    final isSmokeAlert =
        alertId == 'smoke_detected_room1' ||
        backendType.toLowerCase().contains('smoke') ||
        backendType.toLowerCase().contains('gas');
    final message =
        (json['message'] as String?) ??
        (json['body'] as String?) ??
        (json['title'] as String?) ??
        (isSmokeAlert
            ? 'Smoke or gas was detected in Room 1. Check immediately.'
            : 'System alert');

    final status = (json['status'] as String? ?? '').trim().toLowerCase();

    return Alert(
      id: alertId,
      type: _parseAlertType(backendType),
      backendType: backendType,
      message: message,
      timestamp: _parseTimestamp(
        json['created_at_ms'] ??
            json['created_at_iso'] ??
            json['createdAt'] ??
            json['first_detected_at_ms'] ??
            json['started_at_ms'] ??
            json['timestamp_ms'] ??
            json['timestamp'] ??
            json['created_at_ms'] ??
            json['updated_at_ms'],
      ),
      severity:
          (json['severity'] as String?) ??
          (json['level'] as String?) ??
          (isSmokeAlert ? 'critical' : 'medium'),
      isActive:
          json['isActive'] as bool? ??
          !{
            'resolved',
            'auto_resolved',
            'cleared',
            'clear',
            'dismissed',
            'closed',
          }.contains(status),
      affectedBranch:
          json['affectedBranch'] as String? ??
          json['room_id'] as String? ??
          json['branch'] as String?,
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
      case 'smoke_detected':
      case 'smoke':
      case 'gas':
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
