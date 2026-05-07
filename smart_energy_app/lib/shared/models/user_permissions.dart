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
    required this.canGenerateInvites,
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
  final bool canGenerateInvites;

  bool get isAdmin => role == 'home_admin' || role == 'admin';
  bool get isHomeAdmin => isAdmin;
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
    canGenerateInvites: false,
  );

  static const admin = UserPermissions(
    role: 'home_admin',
    canView: true,
    canControlDevices: true,
    canChangeSettings: true,
    canManageUsers: true,
    canManageSchedules: true,
    canChangeControlMode: true,
    canUseAiChat: true,
    canAcknowledgeAlerts: true,
    canGenerateInvites: true,
  );

  static const member = UserPermissions(
    role: 'member',
    canView: true,
    canControlDevices: true,
    canChangeSettings: false,
    canManageUsers: false,
    canManageSchedules: false,
    canChangeControlMode: false,
    canUseAiChat: true,
    canAcknowledgeAlerts: true,
    canGenerateInvites: false,
  );

  factory UserPermissions.fromHomeMap(Map<String, dynamic> data) {
    final rawRole = (data['role'] ?? 'viewer').toString().toLowerCase();
    final role = rawRole == 'admin' ? 'home_admin' : rawRole;
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
      canGenerateInvites: _asBool(data['can_generate_invites']),
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
