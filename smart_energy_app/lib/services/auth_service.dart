import 'package:dio/dio.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_database/firebase_database.dart';

import '../models/user_permissions.dart';
import '../utils/constants.dart';

class AuthService {
  AuthService();

  final FirebaseAuth _auth = FirebaseAuth.instance;

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
    final permissions = await loadPermissions(homeId: homeId);
    if (permissions.role != 'viewer' ||
        permissions.canControlDevices ||
        permissions.canUseAiChat) {
      return;
    }

    final database = FirebaseDatabase.instanceFor(
      app: FirebaseDatabase.instance.app,
      databaseURL: NetworkConfig.firebaseRealtimeDatabaseUrl,
    );
    final profileSnapshot = await database.ref('users/${user.uid}').get();
    if (profileSnapshot.exists) {
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
    final database = FirebaseDatabase.instanceFor(
      app: FirebaseDatabase.instance.app,
      databaseURL: NetworkConfig.firebaseRealtimeDatabaseUrl,
    );
    final snapshot = await database.ref('users/${user.uid}/homes/$homeId').get();
    return UserPermissions.fromHomeMap(_asMap(snapshot.value));
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map) {
      return value.map((key, val) => MapEntry(key.toString(), val));
    }
    return const {};
  }
}
