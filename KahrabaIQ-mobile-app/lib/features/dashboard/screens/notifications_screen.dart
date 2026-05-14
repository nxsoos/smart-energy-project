import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../shared/models/alert.dart';
import '../../../shared/models/app_notification.dart';
import '../../../shared/services/kahrabaiq_api_service.dart';

class NotificationsScreen extends StatefulWidget {
  const NotificationsScreen({
    super.key,
    required this.homeId,
    required this.alerts,
  });

  final String homeId;
  final List<Alert> alerts;

  @override
  State<NotificationsScreen> createState() => _NotificationsScreenState();
}

class _NotificationsScreenState extends State<NotificationsScreen> {
  final KahrabaIqApiService _api = KahrabaIqApiService();
  late Future<List<AppNotification>> _future;

  @override
  void initState() {
    super.initState();
    _future = _api.fetchNotifications(homeId: widget.homeId);
  }

  Future<void> _reload() async {
    setState(() {
      _future = _api.fetchNotifications(homeId: widget.homeId);
    });
    await _future;
  }

  Future<void> _markRead(AppNotification notification) async {
    if (notification.read) {
      return;
    }
    await _api.markNotificationRead(
      homeId: widget.homeId,
      notificationId: notification.id,
    );
    await _reload();
  }

  Future<bool> _dismiss(AppNotification notification) async {
    await _api.dismissNotification(
      homeId: widget.homeId,
      notificationId: notification.id,
    );
    await _reload();
    if (!mounted) {
      return true;
    }
    ScaffoldMessenger.of(
      context,
    ).showSnackBar(const SnackBar(content: Text('Notification dismissed')));
    return true;
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: RefreshIndicator(
          color: ColorTokens.primary,
          onRefresh: _reload,
          child: FutureBuilder<List<AppNotification>>(
            future: _future,
            builder: (context, snapshot) {
              final notifications = snapshot.data ?? const <AppNotification>[];
              final activeAlerts = _dedupeAlerts(widget.alerts);
              return ListView(
                padding: const EdgeInsets.fromLTRB(20, 18, 20, 32),
                children: [
                  Row(
                    children: [
                      IconButton(
                        tooltip: 'Back',
                        onPressed: () => Navigator.of(context).pop(),
                        icon: const Icon(Icons.arrow_back),
                      ),
                      const SizedBox(width: 8),
                      Text('Notifications', style: AppTextStyles.h2),
                    ],
                  ),
                  const SizedBox(height: 18),
                  if (activeAlerts.isNotEmpty) ...[
                    Text('Active alerts', style: AppTextStyles.h3),
                    const SizedBox(height: 10),
                    for (final alert in activeAlerts)
                      _AlertNotificationTile(alert: alert),
                    const SizedBox(height: 18),
                  ],
                  Text('Recent notifications', style: AppTextStyles.h3),
                  const SizedBox(height: 10),
                  if (snapshot.connectionState == ConnectionState.waiting)
                    const _LoadingTiles()
                  else if (snapshot.hasError)
                    _EmptyPanel(
                      icon: Icons.cloud_off_outlined,
                      title: 'Could not load notifications',
                      message: snapshot.error.toString().replaceFirst(
                        'Exception: ',
                        '',
                      ),
                    )
                  else if (notifications.isEmpty)
                    const _EmptyPanel(
                      icon: Icons.notifications_none,
                      title: 'No notifications yet',
                      message:
                          'Safety alerts and system messages will appear here.',
                    )
                  else
                    for (final notification in notifications)
                      _NotificationTile(
                        notification: notification,
                        onTap: () => _markRead(notification),
                        onDismiss: () => _dismiss(notification),
                      ),
                ],
              );
            },
          ),
        ),
      ),
    );
  }
}

class _NotificationTile extends StatelessWidget {
  const _NotificationTile({
    required this.notification,
    required this.onTap,
    required this.onDismiss,
  });

  final AppNotification notification;
  final VoidCallback onTap;
  final Future<bool> Function() onDismiss;

  @override
  Widget build(BuildContext context) {
    final color = _severityColor(notification.severity);
    return Dismissible(
      key: ValueKey(notification.id),
      direction: DismissDirection.endToStart,
      confirmDismiss: (_) => onDismiss(),
      background: Container(
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.symmetric(horizontal: 18),
        alignment: Alignment.centerRight,
        decoration: BoxDecoration(
          color: ColorTokens.danger.withValues(alpha: 0.16),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: ColorTokens.danger.withValues(alpha: 0.35)),
        ),
        child: const Icon(Icons.delete_outline, color: ColorTokens.danger),
      ),
      child: Padding(
        padding: const EdgeInsets.only(bottom: 12),
        child: InkWell(
          borderRadius: BorderRadius.circular(16),
          onTap: onTap,
          child: Container(
            padding: const EdgeInsets.all(16),
            decoration: BoxDecoration(
              color: ColorTokens.surfaceElevated,
              borderRadius: BorderRadius.circular(16),
              border: Border.all(
                color: notification.read
                    ? ColorTokens.border
                    : color.withValues(alpha: 0.55),
              ),
            ),
            child: Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Icon(_iconFor(notification.type), color: color),
                const SizedBox(width: 12),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(notification.title, style: AppTextStyles.bodyMedium),
                      const SizedBox(height: 6),
                      Text(notification.body, style: AppTextStyles.caption),
                      const SizedBox(height: 8),
                      Text(
                        _formatTime(notification.createdAt),
                        style: AppTextStyles.caption,
                      ),
                    ],
                  ),
                ),
                if (!notification.read)
                  Container(
                    width: 9,
                    height: 9,
                    decoration: BoxDecoration(
                      color: color,
                      shape: BoxShape.circle,
                    ),
                  ),
              ],
            ),
          ),
        ),
      ),
    );
  }
}

class _AlertNotificationTile extends StatelessWidget {
  const _AlertNotificationTile({required this.alert});

  final Alert alert;

  @override
  Widget build(BuildContext context) {
    final color = _severityColor(alert.severity);
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: Container(
        padding: const EdgeInsets.all(16),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.12),
          borderRadius: BorderRadius.circular(16),
          border: Border.all(color: color.withValues(alpha: 0.45)),
        ),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Icon(Icons.warning_amber_rounded, color: color),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(_titleFor(alert), style: AppTextStyles.bodyMedium),
                  const SizedBox(height: 6),
                  Text(alert.message, style: AppTextStyles.caption),
                  const SizedBox(height: 8),
                  Text(
                    _formatTime(alert.timestamp),
                    style: AppTextStyles.caption,
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }
}

class _LoadingTiles extends StatelessWidget {
  const _LoadingTiles();

  @override
  Widget build(BuildContext context) {
    return Column(
      children: List.generate(
        3,
        (index) => Container(
          height: 86,
          margin: const EdgeInsets.only(bottom: 12),
          decoration: BoxDecoration(
            color: ColorTokens.surfaceElevated,
            borderRadius: BorderRadius.circular(16),
          ),
        ),
      ),
    );
  }
}

class _EmptyPanel extends StatelessWidget {
  const _EmptyPanel({
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(22),
      decoration: BoxDecoration(
        color: ColorTokens.surfaceElevated,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: ColorTokens.border),
      ),
      child: Column(
        children: [
          Icon(icon, color: ColorTokens.textSecondary, size: 32),
          const SizedBox(height: 12),
          Text(title, style: AppTextStyles.h3, textAlign: TextAlign.center),
          const SizedBox(height: 8),
          Text(
            message,
            style: AppTextStyles.caption,
            textAlign: TextAlign.center,
          ),
        ],
      ),
    );
  }
}

Color _severityColor(String severity) {
  switch (severity.toLowerCase()) {
    case 'critical':
    case 'high':
      return ColorTokens.danger;
    case 'medium':
      return ColorTokens.warning;
    case 'low':
      return ColorTokens.info;
    default:
      return ColorTokens.primary;
  }
}

IconData _iconFor(String type) {
  final normalized = type.toLowerCase();
  if (normalized.contains('cost') || normalized.contains('budget')) {
    return Icons.account_balance_wallet_outlined;
  }
  if (normalized.contains('energy')) {
    return Icons.bolt_outlined;
  }
  if (normalized.contains('device') ||
      normalized.contains('sensor') ||
      normalized.contains('offline') ||
      normalized.contains('stale')) {
    return Icons.devices_other_outlined;
  }
  if (normalized.contains('ai')) {
    return Icons.auto_awesome_outlined;
  }
  if (normalized.contains('critical') || normalized.contains('alert')) {
    return Icons.notification_important_outlined;
  }
  if (normalized.contains('recommend')) {
    return Icons.tips_and_updates_outlined;
  }
  return Icons.notifications_none;
}

String _formatTime(DateTime time) {
  final local = time.toLocal();
  final now = DateTime.now();
  final today = DateTime(now.year, now.month, now.day);
  final date = DateTime(local.year, local.month, local.day);
  final hour = local.hour.toString().padLeft(2, '0');
  final minute = local.minute.toString().padLeft(2, '0');
  if (date == today) {
    return 'Today $hour:$minute';
  }
  if (date == today.subtract(const Duration(days: 1))) {
    return 'Yesterday $hour:$minute';
  }
  final day = local.day.toString().padLeft(2, '0');
  final month = local.month.toString().padLeft(2, '0');
  return '$day/$month/${local.year} $hour:$minute';
}

List<Alert> _dedupeAlerts(List<Alert> alerts) {
  final byKey = <String, Alert>{};
  for (final alert in alerts) {
    final key = _isSmokeAlert(alert)
        ? 'smoke_detected_room1'
        : alert.id.isNotEmpty
        ? alert.id
        : '${alert.backendType}_${alert.message}'.toLowerCase();
    final existing = byKey[key];
    if (existing == null ||
        (existing.message == 'System alert' &&
            alert.message != 'System alert')) {
      byKey[key] = alert;
    }
  }
  return byKey.values.toList()
    ..sort((a, b) => b.timestamp.compareTo(a.timestamp));
}

bool _isSmokeAlert(Alert alert) {
  final id = alert.id.toLowerCase();
  final type = alert.backendType.toLowerCase();
  return id == 'smoke_detected_room1' ||
      type.contains('smoke') ||
      type.contains('gas');
}

String _titleFor(Alert alert) {
  if (_isSmokeAlert(alert)) {
    return 'Smoke/Gas Detected';
  }
  switch (alert.severity.toLowerCase()) {
    case 'critical':
      return 'Critical alert';
    case 'high':
      return 'High priority alert';
    case 'medium':
      return 'Attention needed';
    case 'low':
      return 'Notice';
    default:
      return 'Home alert';
  }
}
