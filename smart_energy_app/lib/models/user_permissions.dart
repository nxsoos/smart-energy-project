class UserPermissions {
  const UserPermissions({
    required this.role,
    required this.canView,
    required this.canControlDevices,
    required this.canChangeSettings,
    required this.canManageUsers,
    required this.canManageSchedules,
    required this.canChangeControlMode,
    required this.canUseAiChat,
    required this.canAcknowledgeAlerts,
  });

  final String role;
  final bool canView;
  final bool canControlDevices;
  final bool canChangeSettings;
  final bool canManageUsers;
  final bool canManageSchedules;
  final bool canChangeControlMode;
  final bool canUseAiChat;
  final bool canAcknowledgeAlerts;

  bool get isAdmin => role == 'admin';
  bool get isMember => role == 'member';
  bool get isViewer => role == 'viewer';

  static const viewer = UserPermissions(
    role: 'viewer',
    canView: true,
    canControlDevices: false,
    canChangeSettings: false,
    canManageUsers: false,
    canManageSchedules: false,
    canChangeControlMode: false,
    canUseAiChat: false,
    canAcknowledgeAlerts: false,
  );

  static const admin = UserPermissions(
    role: 'admin',
    canView: true,
    canControlDevices: true,
    canChangeSettings: true,
    canManageUsers: true,
    canManageSchedules: true,
    canChangeControlMode: true,
    canUseAiChat: true,
    canAcknowledgeAlerts: true,
  );

  factory UserPermissions.fromHomeMap(Map<String, dynamic> data) {
    final role = (data['role'] ?? 'viewer').toString().toLowerCase();
    return UserPermissions(
      role: role,
      canView: _asBool(data['can_view'], true),
      canControlDevices: _asBool(data['can_control_devices']),
      canChangeSettings: _asBool(data['can_change_settings']),
      canManageUsers: _asBool(data['can_manage_users']),
      canManageSchedules: _asBool(data['can_manage_schedules']),
      canChangeControlMode: _asBool(data['can_change_control_mode']),
      canUseAiChat: _asBool(data['can_use_ai_chat']),
      canAcknowledgeAlerts: _asBool(data['can_acknowledge_alerts']),
    );
  }

  static bool _asBool(dynamic value, [bool fallback = false]) {
    if (value is bool) {
      return value;
    }
    if (value is num) {
      return value != 0;
    }
    return fallback;
  }
}
