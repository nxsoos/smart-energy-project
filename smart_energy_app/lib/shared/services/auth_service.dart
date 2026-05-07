import 'package:dio/dio.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../models/user_permissions.dart';
import '../../core/utils/constants.dart';

Map<String, dynamic> _asMap(dynamic value) {
  return value is Map ? Map<String, dynamic>.from(value) : <String, dynamic>{};
}

List<dynamic> _asList(dynamic value) {
  return value is List ? value : const <dynamic>[];
}

class UserHomeAccess {
  const UserHomeAccess({
    required this.homeId,
    required this.name,
    required this.role,
    required this.permissions,
    this.piId,
    this.status = 'active',
  });

  final String homeId;
  final String name;
  final String role;
  final UserPermissions permissions;
  final String? piId;
  final String status;

  factory UserHomeAccess.fromMap(Map<String, dynamic> data) {
    final permissions = {
      'role': data['role'],
      ..._asMap(data['permissions']),
    };
    return UserHomeAccess(
      homeId: (data['home_id'] ?? data['id'] ?? '').toString(),
      name: (data['name'] ?? data['home_id'] ?? 'Home').toString(),
      role: (data['role'] ?? 'viewer').toString(),
      permissions: UserPermissions.fromHomeMap(permissions),
      piId: data['pi_id']?.toString(),
      status: (data['status'] ?? 'active').toString(),
    );
  }
}

class CurrentUserProfile {
  const CurrentUserProfile({
    required this.uid,
    required this.email,
    required this.displayName,
    required this.platformRole,
    required this.defaultHomeId,
    required this.homes,
  });

  final String uid;
  final String email;
  final String displayName;
  final String platformRole;
  final String? defaultHomeId;
  final List<UserHomeAccess> homes;

  bool get isPlatformAdmin => platformRole == 'platform_admin';

  factory CurrentUserProfile.fromMap(Map<String, dynamic> data) {
    return CurrentUserProfile(
      uid: (data['uid'] ?? '').toString(),
      email: (data['email'] ?? '').toString(),
      displayName: (data['display_name'] ?? data['email'] ?? 'User').toString(),
      platformRole: (data['platform_role'] ?? 'user').toString(),
      defaultHomeId: data['default_home_id']?.toString(),
      homes: _asList(data['homes'])
          .map((item) => UserHomeAccess.fromMap(_asMap(item)))
          .where((home) => home.homeId.isNotEmpty)
          .toList(),
    );
  }
}

class AuthService {
  AuthService();

  FirebaseAuth get _auth => FirebaseAuth.instance;

  Stream<User?> get authStateChanges => _auth.authStateChanges();
  User? get currentUser => _auth.currentUser;

  Future<void> signIn({required String email, required String password}) async {
    final credential = await _auth.signInWithEmailAndPassword(
      email: email.trim(),
      password: password,
    );
    final user = credential.user;
    if (user != null) {
      await ensureUserProfile(user: user);
    }
  }

  Future<void> signUp({
    required String name,
    required String email,
    required String password,
    String homeId = NetworkConfig.firebaseHomeId,
  }) async {
    final credential = await _auth.createUserWithEmailAndPassword(
      email: email.trim(),
      password: password,
    );
    final user = credential.user;
    if (user == null) {
      throw StateError('Firebase Auth did not return a user.');
    }
    await user.updateDisplayName(name.trim());
    await createUserProfile(user: user, displayName: name.trim(), homeId: homeId);
  }

  Future<void> sendPasswordReset(String email) async {
    await _auth.sendPasswordResetEmail(email: email.trim());
  }

  Future<void> signOut() => _auth.signOut();

  Future<String?> getIdToken({bool forceRefresh = false}) async {
    return _auth.currentUser?.getIdToken(forceRefresh);
  }

  Future<void> createUserProfile({
    required User user,
    required String displayName,
    String homeId = NetworkConfig.firebaseHomeId,
  }) async {
    final token = await user.getIdToken(true);
    await Dio(
      BaseOptions(
        baseUrl: NetworkConfig.apiBaseUrl,
        connectTimeout: const Duration(seconds: 30),
        receiveTimeout: const Duration(seconds: 30),
      ),
    ).post(
      '/api/auth/complete-signup',
      data: {
        'display_name': displayName.isEmpty ? (user.email ?? 'User') : displayName,
        'home_id': homeId,
      },
      options: Options(headers: {'Authorization': 'Bearer $token'}),
    );
  }

  Future<void> ensureUserProfile({
    required User user,
    String homeId = NetworkConfig.firebaseHomeId,
  }) async {
    if (NetworkConfig.useLocalPiApi) {
      return;
    }

    final permissions = await loadPermissions(homeId: homeId);
    if (permissions.role != 'viewer' ||
        permissions.canControlDevices ||
        permissions.canUseAiChat) {
      return;
    }

    await createUserProfile(
      user: user,
      displayName: user.displayName ?? user.email ?? 'User',
      homeId: homeId,
    );
  }

  Future<UserPermissions> loadPermissions({
    String homeId = NetworkConfig.firebaseHomeId,
  }) async {
    final user = _auth.currentUser;
    if (user == null) {
      return UserPermissions.viewer;
    }
    if (NetworkConfig.useLocalPiApi) {
      return UserPermissions.admin;
    }
    final profile = await loadCurrentUserProfile();
    for (final home in profile.homes) {
      if (home.homeId == homeId) {
        return home.permissions;
      }
    }
    return profile.isPlatformAdmin ? UserPermissions.admin : UserPermissions.viewer;
  }

  Future<CurrentUserProfile> loadCurrentUserProfile() async {
    final token = await getIdToken();
    if (token == null) {
      throw StateError('User is not signed in.');
    }
    final response = await Dio(
      BaseOptions(
        baseUrl: NetworkConfig.apiBaseUrl,
        connectTimeout: const Duration(seconds: 30),
        receiveTimeout: const Duration(seconds: 30),
      ),
    ).get('/api/me', options: Options(headers: {'Authorization': 'Bearer $token'}));
    return CurrentUserProfile.fromMap(_asMap(response.data));
  }

}
