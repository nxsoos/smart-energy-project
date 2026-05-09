import 'dart:async';
import 'dart:convert';

import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:aws_common/aws_common.dart';
import 'package:aws_signature_v4/aws_signature_v4.dart';
import 'package:dio/dio.dart';

import '../models/user_permissions.dart';
import '../../core/utils/constants.dart';

class AppUser {
  const AppUser({required this.uid, required this.email, this.displayName});

  final String uid;
  final String email;
  final String? displayName;
}

class SignUpResult {
  const SignUpResult({required this.userConfirmed});

  final bool userConfirmed;
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
}

class AwsIotConnectionConfig {
  const AwsIotConnectionConfig({
    required this.signedUrl,
    required this.clientId,
    required this.topic,
  });

  final String signedUrl;
  final String clientId;
  final String topic;
}

class AuthService {
  factory AuthService() => _instance;

  AuthService._internal() {
    _restoreCachedUser();
  }

  static final AuthService _instance = AuthService._internal();

  final StreamController<AppUser?> _authStateController =
      StreamController<AppUser?>.broadcast();
  final Completer<void> _restoreCompleter = Completer<void>();

  CognitoUserPool? _userPool;
  CognitoUser? _cognitoUser;
  CognitoUserSession? _session;
  CognitoCredentials? _credentials;
  AppUser? _currentUser;
  String? _attachedPolicyIdentityId;
  bool _restoreStarted = false;

  Stream<AppUser?> get authStateChanges async* {
    await _restoreCompleter.future;
    yield _currentUser;
    yield* _authStateController.stream;
  }

  AppUser? get currentUser => _currentUser;

  CognitoUserPool get _pool {
    if (NetworkConfig.cognitoUserPoolId.isEmpty ||
        NetworkConfig.cognitoAppClientId.isEmpty) {
      throw StateError(
        'AWS Cognito is not configured. Pass COGNITO_USER_POOL_ID and '
        'COGNITO_APP_CLIENT_ID with --dart-define.',
      );
    }
    return _userPool ??= CognitoUserPool(
      NetworkConfig.cognitoUserPoolId,
      NetworkConfig.cognitoAppClientId,
    );
  }

  CognitoCredentials get _awsCredentials {
    if (NetworkConfig.cognitoIdentityPoolId.isEmpty) {
      throw StateError(
        'AWS Cognito Identity Pool is not configured. Pass '
        'COGNITO_IDENTITY_POOL_ID with --dart-define.',
      );
    }
    return _credentials ??= CognitoCredentials(
      NetworkConfig.cognitoIdentityPoolId,
      _pool,
      region: NetworkConfig.awsRegion,
    );
  }

  Future<void> _restoreCachedUser() async {
    if (_restoreStarted) {
      return;
    }
    _restoreStarted = true;
    try {
      if (NetworkConfig.cognitoUserPoolId.isEmpty ||
          NetworkConfig.cognitoAppClientId.isEmpty) {
        return;
      }
      final user = await _pool.getCurrentUser();
      if (user == null) {
        return;
      }
      final session = await user.getSession();
      if (session == null || !session.isValid()) {
        return;
      }
      _cognitoUser = user;
      _session = session;
      _currentUser = _userFromSession(session);
    } catch (_) {
      _currentUser = null;
    } finally {
      if (!_restoreCompleter.isCompleted) {
        _restoreCompleter.complete();
      }
      _authStateController.add(_currentUser);
    }
  }

  Future<void> signIn({required String email, required String password}) async {
    final normalizedEmail = email.trim().toLowerCase();
    final user = CognitoUser(normalizedEmail, _pool);
    final authDetails = AuthenticationDetails(
      username: normalizedEmail,
      password: password,
    );
    final session = await user.authenticateUser(authDetails);
    if (session == null || !session.isValid()) {
      throw StateError('Cognito did not return a valid session.');
    }

    _cognitoUser = user;
    _session = session;
    _currentUser = _userFromSession(session, fallbackEmail: normalizedEmail);
    _attachedPolicyIdentityId = null;
    _authStateController.add(_currentUser);
  }

  Future<SignUpResult> signUp({
    required String name,
    required String email,
    required String password,
    String homeId = NetworkConfig.defaultHomeId,
  }) async {
    final normalizedEmail = email.trim().toLowerCase();
    final result = await _pool.signUp(
      normalizedEmail,
      password,
      userAttributes: [
        AttributeArg(name: 'email', value: normalizedEmail),
        if (name.trim().isNotEmpty)
          AttributeArg(name: 'name', value: name.trim()),
      ],
    );
    return SignUpResult(userConfirmed: result.userConfirmed == true);
  }

  Future<void> confirmSignUp({
    required String email,
    required String code,
  }) async {
    final user = CognitoUser(email.trim().toLowerCase(), _pool);
    await user.confirmRegistration(code.trim());
  }

  Future<void> resendSignUpCode(String email) async {
    final user = CognitoUser(email.trim().toLowerCase(), _pool);
    await user.resendConfirmationCode();
  }

  Future<void> sendPasswordReset(String email) async {
    final user = CognitoUser(email.trim().toLowerCase(), _pool);
    await user.forgotPassword();
  }

  Future<void> confirmPasswordReset({
    required String email,
    required String code,
    required String newPassword,
  }) async {
    final user = CognitoUser(email.trim().toLowerCase(), _pool);
    await user.confirmPassword(code.trim(), newPassword);
  }

  Future<void> signOut() async {
    final user = _cognitoUser;
    if (user != null) {
      await user.signOut();
    }
    await _credentials?.resetAwsCredentials();
    _cognitoUser = null;
    _session = null;
    _currentUser = null;
    _credentials = null;
    _attachedPolicyIdentityId = null;
    _authStateController.add(null);
  }

  Future<String?> getIdToken({bool forceRefresh = false}) async {
    if (!NetworkConfig.useCognitoAuth) {
      return null;
    }
    final session = await _validSession();
    return session?.getIdToken().getJwtToken();
  }

  Future<UserPermissions> loadPermissions({
    String homeId = NetworkConfig.defaultHomeId,
  }) async {
    final session = await _validSession();
    if (_currentUser == null || session == null) {
      return UserPermissions.viewer;
    }
    final groups = _groupsFromSession(session);
    if (_containsGroup(groups, NetworkConfig.cognitoAdminGroup) ||
        _containsGroup(groups, 'admin')) {
      return UserPermissions.admin;
    }
    if (_containsGroup(groups, NetworkConfig.cognitoMemberGroup) ||
        _containsGroup(groups, 'member')) {
      return UserPermissions.member;
    }
    return UserPermissions.viewer;
  }

  Future<CurrentUserProfile> loadCurrentUserProfile() async {
    final session = await _validSession();
    final user = _currentUser;
    if (user == null || session == null) {
      throw StateError('User is not signed in.');
    }

    if (NetworkConfig.useCognitoAuth && NetworkConfig.apiBaseUrl.isNotEmpty) {
      return _loadCurrentUserProfileFromApi(session, user);
    }

    final permissions = await loadPermissions();
    final groups = _groupsFromSession(session);
    final platformRole = _containsGroup(groups, NetworkConfig.cognitoAdminGroup)
        ? 'platform_admin'
        : 'user';
    return CurrentUserProfile(
      uid: user.uid,
      email: user.email,
      displayName: user.displayName ?? user.email,
      platformRole: platformRole,
      defaultHomeId: NetworkConfig.defaultHomeId,
      homes: [
        UserHomeAccess(
          homeId: NetworkConfig.defaultHomeId,
          name: 'KahrabaIQ Home',
          role: permissions.role,
          permissions: permissions,
        ),
      ],
    );
  }

  Future<CurrentUserProfile> _loadCurrentUserProfileFromApi(
    CognitoUserSession session,
    AppUser user,
  ) async {
    final token = session.getIdToken().getJwtToken();
    if (token == null || token.isEmpty) {
      throw StateError('Cognito did not return an ID token.');
    }
    final dio = Dio(
      BaseOptions(
        baseUrl: NetworkConfig.apiBaseUrl,
        connectTimeout: Duration(seconds: NetworkConfig.piApiTimeoutSeconds),
        receiveTimeout: Duration(seconds: NetworkConfig.piApiTimeoutSeconds),
        headers: {'Authorization': 'Bearer $token'},
      ),
    );
    final response = await dio.get('/api/me');
    final data = _asMap(response.data);
    final homes = _asList(data['homes'])
        .map((item) {
          final home = _asMap(item);
          final role = _normalizeRole(
            _asString(home['role'], fallback: 'viewer'),
          );
          final permissions = UserPermissions.fromHomeMap({
            'role': role,
            ..._asMap(home['permissions']),
          });
          return UserHomeAccess(
            homeId: _asString(home['home_id']),
            name: _asString(home['name'], fallback: 'KahrabaIQ Home'),
            role: role,
            permissions: permissions,
            piId: _nullableString(home['pi_id']),
            status: _asString(home['status'], fallback: 'active'),
          );
        })
        .where((home) => home.homeId.isNotEmpty)
        .toList();
    final platformRole = _asString(data['platform_role'], fallback: 'user');
    return CurrentUserProfile(
      uid: _asString(data['uid'], fallback: user.uid),
      email: _asString(data['email'], fallback: user.email),
      displayName: _asString(
        data['display_name'],
        fallback: user.displayName ?? user.email,
      ),
      platformRole: platformRole,
      defaultHomeId: _nullableString(data['default_home_id']),
      homes: homes,
    );
  }

  Future<AwsIotConnectionConfig> createAwsIotConnectionConfig({
    required String homeId,
  }) async {
    if (!NetworkConfig.useAwsIotLive) {
      throw StateError(
        'AWS IoT live is not configured. Pass the Cognito and AWS IoT '
        'values with --dart-define.',
      );
    }
    if (homeId != NetworkConfig.defaultHomeId) {
      throw ArgumentError.value(homeId, 'homeId', 'Unsupported home ID');
    }

    final credentials = await _loadAwsCredentials().timeout(
      const Duration(seconds: 10),
      onTimeout: () => throw TimeoutException(
        'Timed out while getting temporary AWS credentials from Cognito '
        'Identity Pool.',
      ),
    );
    await _attachIotPolicy(credentials).timeout(
      const Duration(seconds: 10),
      onTimeout: () => throw TimeoutException(
        'Timed out while attaching the AWS IoT policy to this Cognito '
        'identity. Check the Identity Pool authenticated role allows '
        'iot:AttachPolicy.',
      ),
    );
    final userSuffix = _safeClientSuffix(credentials.userIdentityId ?? 'user');
    final clientId = 'smart-energy-app-$homeId-$userSuffix';
    return AwsIotConnectionConfig(
      signedUrl: _buildAwsIotWebSocketUrl(credentials),
      clientId: clientId,
      topic: NetworkConfig.awsIotLiveTopic,
    );
  }

  Future<Map<String, dynamic>> queueAwsRemoteDeviceCommand({
    required String homeId,
    required String deviceId,
    required String command,
    bool emergency = false,
    String? alertId,
    String? reason,
  }) async {
    throw StateError(
      'Direct DynamoDB command writes are disabled. Use the EC2 backend '
      'command API so user permissions, command expiry, and audit history '
      'are enforced centrally.',
    );
  }

  Future<CognitoUserSession?> _validSession() async {
    if (!NetworkConfig.useCognitoAuth) {
      return null;
    }
    if (_session != null && _session!.isValid()) {
      return _session;
    }
    final user = _cognitoUser ?? await _pool.getCurrentUser();
    if (user == null) {
      return null;
    }
    final session = await user.getSession();
    if (session == null || !session.isValid()) {
      return null;
    }
    _cognitoUser = user;
    _session = session;
    _currentUser = _userFromSession(session);
    return session;
  }

  Future<CognitoCredentials> _loadAwsCredentials() async {
    final session = await _validSession();
    final idToken = session?.getIdToken().getJwtToken();
    if (idToken == null || idToken.isEmpty) {
      throw StateError('Please log in before connecting to AWS IoT.');
    }
    final credentials = _awsCredentials;
    await credentials.getAwsCredentials(idToken);
    if ((credentials.accessKeyId ?? '').isEmpty ||
        (credentials.secretAccessKey ?? '').isEmpty ||
        (credentials.sessionToken ?? '').isEmpty ||
        (credentials.userIdentityId ?? '').isEmpty) {
      throw StateError('Cognito Identity Pool did not return AWS credentials.');
    }
    return credentials;
  }

  Future<void> _attachIotPolicy(CognitoCredentials credentials) async {
    final identityId = credentials.userIdentityId;
    if (identityId == null || identityId == _attachedPolicyIdentityId) {
      return;
    }

    final policyName = NetworkConfig.awsIotPolicyName;
    final body = jsonEncode({'target': identityId});
    final signer = AWSSigV4Signer(
      credentialsProvider: AWSCredentialsProvider(
        AWSCredentials(
          credentials.accessKeyId!,
          credentials.secretAccessKey!,
          credentials.sessionToken,
        ),
      ),
    );
    final request = AWSHttpRequest(
      method: AWSHttpMethod.put,
      uri: Uri.https(
        'iot.${NetworkConfig.awsRegion}.amazonaws.com',
        '/target-policies/$policyName',
      ),
      headers: const {'Content-Type': 'application/json'},
      body: body.codeUnits,
    );
    final signedRequest = await signer.sign(
      request,
      credentialScope: AWSCredentialScope(
        region: NetworkConfig.awsRegion,
        service: AWSService.iot,
      ),
    );

    await Dio(
      BaseOptions(
        connectTimeout: const Duration(seconds: 8),
        receiveTimeout: const Duration(seconds: 8),
      ),
    ).putUri(
      signedRequest.uri,
      data: body,
      options: Options(headers: signedRequest.headers),
    );
    _attachedPolicyIdentityId = identityId;
  }

  AppUser _userFromSession(
    CognitoUserSession session, {
    String? fallbackEmail,
  }) {
    final payload = session.getIdToken().payload;
    final email = payload is Map
        ? (payload['email']?.toString() ?? fallbackEmail ?? '')
        : (fallbackEmail ?? '');
    final uid = payload is Map ? (payload['sub']?.toString() ?? email) : email;
    final name = payload is Map ? payload['name']?.toString() : null;
    return AppUser(uid: uid, email: email, displayName: name);
  }

  Set<String> _groupsFromSession(CognitoUserSession session) {
    final payload = session.getIdToken().payload;
    if (payload is! Map) {
      return const {};
    }
    final rawGroups = payload['cognito:groups'];
    if (rawGroups is List) {
      return rawGroups.map((group) => group.toString()).toSet();
    }
    if (rawGroups is String && rawGroups.trim().isNotEmpty) {
      return rawGroups.split(',').map((group) => group.trim()).toSet();
    }
    return const {};
  }

  bool _containsGroup(Set<String> groups, String expected) {
    return groups.any((group) => group.toLowerCase() == expected.toLowerCase());
  }

  Map<String, dynamic> _asMap(dynamic value) {
    return value is Map
        ? value.map((key, val) => MapEntry(key.toString(), val))
        : <String, dynamic>{};
  }

  List<dynamic> _asList(dynamic value) {
    return value is List ? value : const <dynamic>[];
  }

  String _asString(dynamic value, {String fallback = ''}) {
    final text = value?.toString() ?? '';
    return text.isEmpty ? fallback : text;
  }

  String? _nullableString(dynamic value) {
    final text = value?.toString().trim() ?? '';
    return text.isEmpty ? null : text;
  }

  String _normalizeRole(String role) {
    final normalized = role.trim().toLowerCase();
    return normalized == 'admin' ? 'home_admin' : normalized;
  }

  String _buildAwsIotWebSocketUrl(CognitoCredentials credentials) {
    final host = NetworkConfig.awsIotEndpoint;
    final signer = AWSSigV4Signer(
      credentialsProvider: AWSCredentialsProvider(
        AWSCredentials(
          credentials.accessKeyId!,
          credentials.secretAccessKey!,
          credentials.sessionToken,
        ),
      ),
    );
    final signed = signer.presignSync(
      AWSHttpRequest(method: AWSHttpMethod.get, uri: Uri.https(host, '/mqtt')),
      credentialScope: AWSCredentialScope(
        region: NetworkConfig.awsRegion,
        service: AWSService.iotCore,
      ),
      expiresIn: const Duration(minutes: 5),
      serviceConfiguration: const BaseServiceConfiguration(
        omitSessionToken: true,
      ),
    );
    return signed.replace(scheme: 'wss').toString();
  }

  String _safeClientSuffix(String value) {
    return value.replaceAll(RegExp(r'[^A-Za-z0-9_-]'), '-');
  }
}
