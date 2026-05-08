import 'package:flutter/material.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'features/auth/screens/auth_screen.dart';
import 'features/dashboard/screens/home_screen.dart';
import 'shared/services/auth_service.dart';
import 'shared/services/firebase_realtime_service.dart';
import 'core/utils/constants.dart';

const String _pushInstallationIdKey = 'push_installation_id';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await Firebase.initializeApp();
    await _registerPushNotifications();
  } catch (_) {
    // Keep app running even when Firebase native config is not present.
  }
  runApp(const KahrabaIQApp());
}

Future<void> _registerPushNotifications() async {
  await _registerPushNotificationsForUser(AuthService().currentUser);
}

Future<void> _registerPushNotificationsForUser(AppUser? user) async {
  final messaging = FirebaseMessaging.instance;
  await messaging.requestPermission(alert: true, badge: true, sound: true);
  final token = await messaging.getToken();
  if (token == null || token.isEmpty) {
    return;
  }
  if (user != null) {
    final profile = await AuthService().loadCurrentUserProfile();
    final homeId = profile.defaultHomeId ??
        (profile.homes.isNotEmpty ? profile.homes.first.homeId : null);
    if (homeId == null || homeId.isEmpty) {
      return;
    }
    final installationId = await _getPushInstallationId();
    await FirebaseRealtimeService().registerNotificationToken(
      homeId: homeId,
      token: token,
      userId: user.uid,
      platform: 'android',
      installationId: installationId,
    );
  }
}

Future<String> _getPushInstallationId() async {
  final prefs = await SharedPreferences.getInstance();
  final existing = prefs.getString(_pushInstallationIdKey);
  if (existing != null && existing.isNotEmpty) {
    return existing;
  }
  final created =
      'kahrabaiq_${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}';
  await prefs.setString(_pushInstallationIdKey, created);
  return created;
}

class KahrabaIQApp extends StatelessWidget {
  const KahrabaIQApp({super.key, this.enableRealtimeSync = true});

  final bool enableRealtimeSync;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: appName,
      debugShowCheckedModeBanner: false,
      theme: ThemeData(
        colorScheme: ColorScheme.fromSeed(
          seedColor: AppColors.primary,
          primary: AppColors.primary,
          secondary: AppColors.accent,
        ),
        useMaterial3: true,
        scaffoldBackgroundColor: AppColors.background,
        appBarTheme: const AppBarTheme(centerTitle: false, elevation: 0),
        cardTheme: CardThemeData(
          elevation: 2,
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(12),
          ),
        ),
        elevatedButtonTheme: ElevatedButtonThemeData(
          style: ElevatedButton.styleFrom(
            elevation: 2,
            padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 12),
          ),
        ),
      ),
      home: AuthGate(enableRealtimeSync: enableRealtimeSync),
    );
  }
}

class AuthGate extends StatefulWidget {
  const AuthGate({super.key, required this.enableRealtimeSync});

  final bool enableRealtimeSync;

  @override
  State<AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<AuthGate> {
  final Set<String> _registeredPushUsers = <String>{};

  void _registerPushForSignedInUser(AppUser user) {
    if (_registeredPushUsers.contains(user.uid)) {
      return;
    }
    _registeredPushUsers.add(user.uid);
    WidgetsBinding.instance.addPostFrameCallback((_) async {
      try {
        await _registerPushNotificationsForUser(user);
      } catch (_) {
        _registeredPushUsers.remove(user.uid);
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return StreamBuilder<AppUser?>(
      stream: AuthService().authStateChanges,
      builder: (context, snapshot) {
        if (snapshot.connectionState == ConnectionState.waiting) {
          return const Scaffold(
            body: Center(child: CircularProgressIndicator()),
          );
        }
        if (!snapshot.hasData) {
          return const AuthScreen();
        }
        _registerPushForSignedInUser(snapshot.data!);
        return HomeScreen(enableRealtimeSync: widget.enableRealtimeSync);
      },
    );
  }
}
