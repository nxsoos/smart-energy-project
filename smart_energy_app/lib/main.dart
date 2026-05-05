import 'package:flutter/material.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_messaging/firebase_messaging.dart';
import 'screens/auth_screen.dart';
import 'screens/home_screen.dart';
import 'services/auth_service.dart';
import 'services/firebase_realtime_service.dart';
import 'utils/constants.dart';

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
  final messaging = FirebaseMessaging.instance;
  await messaging.requestPermission(alert: true, badge: true, sound: true);
  final token = await messaging.getToken();
  if (token == null || token.isEmpty) {
    return;
  }
  if (FirebaseAuth.instance.currentUser != null) {
    await FirebaseRealtimeService().registerNotificationToken(
      homeId: NetworkConfig.firebaseHomeId,
      token: token,
      platform: 'android',
    );
  }
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

class AuthGate extends StatelessWidget {
  const AuthGate({super.key, required this.enableRealtimeSync});

  final bool enableRealtimeSync;

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
        return HomeScreen(enableRealtimeSync: enableRealtimeSync);
      },
    );
  }
}
