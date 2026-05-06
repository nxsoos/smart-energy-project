import 'package:flutter/material.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'screens/auth_screen.dart';
import 'screens/home_screen.dart';
import 'services/auth_service.dart';
import 'services/firebase_realtime_service.dart';
import 'utils/constants.dart';

const String _pushInstallationIdKey = 'push_installation_id';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    await Firebase.initializeApp();
    await _registerPushNotifications();
  } catch (_) {
    // Keep app running even when Firebase native config is not present.
  }
  runApp(const SmartEnergyApp());
}

Future<void> _registerPushNotifications() async {
  await _registerPushNotificationsForUser(FirebaseAuth.instance.currentUser);
}

Future<void> _registerPushNotificationsForUser(User? user) async {
  final messaging = FirebaseMessaging.instance;
  await messaging.requestPermission(alert: true, badge: true, sound: true);
  final token = await messaging.getToken();
  if (token == null || token.isEmpty) {
    return;
  }
  if (user != null) {
    final installationId = await _getPushInstallationId();
    await FirebaseRealtimeService().registerNotificationToken(
      homeId: NetworkConfig.firebaseHomeId,
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
      'smart_energy_${DateTime.now().microsecondsSinceEpoch.toRadixString(36)}';
  await prefs.setString(_pushInstallationIdKey, created);
  return created;
}

class SmartEnergyApp extends StatelessWidget {
  const SmartEnergyApp({super.key, this.enableRealtimeSync = true});

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

  void _registerPushForSignedInUser(User user) {
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
    return StreamBuilder<User?>(
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
