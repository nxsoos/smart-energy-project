class AppNotification {
  const AppNotification({
    required this.id,
    required this.title,
    required this.body,
    required this.type,
    required this.severity,
    required this.createdAt,
    required this.read,
  });

  final String id;
  final String title;
  final String body;
  final String type;
  final String severity;
  final DateTime createdAt;
  final bool read;

  factory AppNotification.fromJson(Map<String, dynamic> json) {
    return AppNotification(
      id: _asString(json['notification_id'] ?? json['id']),
      title: _asString(json['title'], fallback: 'KahrabaIQ Alert'),
      body: _asString(json['body'] ?? json['message'], fallback: 'New home notification.'),
      type: _asString(json['category'] ?? json['type'], fallback: 'notification'),
      severity: _asString(json['severity'], fallback: 'info'),
      createdAt: _parseTimestamp(
        json['created_at_ms'] ?? json['timestamp_ms'] ?? json['created_at_iso'],
      ),
      read: json['read'] == true,
    );
  }

  static String _asString(dynamic value, {String fallback = ''}) {
    final text = value?.toString().trim();
    return text == null || text.isEmpty ? fallback : text;
  }

  static DateTime _parseTimestamp(dynamic value) {
    if (value is num) {
      final timestamp = value.toInt();
      return DateTime.fromMillisecondsSinceEpoch(
        timestamp > 1000000000000 ? timestamp : timestamp * 1000,
      );
    }
    if (value is String) {
      final asNumber = int.tryParse(value);
      if (asNumber != null) {
        return DateTime.fromMillisecondsSinceEpoch(
          asNumber > 1000000000000 ? asNumber : asNumber * 1000,
        );
      }
      return DateTime.tryParse(value) ?? DateTime.now();
    }
    return DateTime.now();
  }
}
