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

class NoStretchScrollBehavior extends MaterialScrollBehavior {
  const NoStretchScrollBehavior();

  @override
  Widget buildOverscrollIndicator(
    BuildContext context,
    Widget child,
    ScrollableDetails details,
  ) {
    return child;
  }
}

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
    final homeId =
        profile.defaultHomeId ??
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
    return AnimatedBuilder(
      animation: AppThemeController.instance,
      builder: (context, _) {
        return MaterialApp(
          title: appName,
          debugShowCheckedModeBanner: false,
          scrollBehavior: const NoStretchScrollBehavior(),
          theme: _buildTheme(Brightness.light),
          darkTheme: _buildTheme(Brightness.dark),
          themeMode: AppThemeController.instance.mode,
          home: AuthGate(enableRealtimeSync: enableRealtimeSync),
        );
      },
    );
  }

  ThemeData _buildTheme(Brightness brightness) {
    final isDark = brightness == Brightness.dark;
    final background = isDark ? AppColors.background : const Color(0xFFF4F1E8);
    final surface = isDark ? AppColors.surface : const Color(0xFFFFFCF4);
    final surfaceElevated = isDark
        ? AppColors.surfaceElevated
        : const Color(0xFFF2EBDD);
    final outline = isDark ? AppColors.outline : const Color(0xFFD8CFBE);
    final textPrimary = isDark
        ? AppColors.textPrimary
        : const Color(0xFF17231D);
    final textSecondary = isDark
        ? AppColors.textSecondary
        : const Color(0xFF65766D);
    final colorScheme = ColorScheme.fromSeed(
      seedColor: AppColors.primary,
      brightness: brightness,
      primary: isDark ? AppColors.primary : AppColors.primaryDark,
      secondary: AppColors.accent,
      surface: surface,
    );

    return ThemeData(
      colorScheme: colorScheme,
      brightness: brightness,
      useMaterial3: true,
      scaffoldBackgroundColor: background,
      fontFamily: 'Roboto',
      textTheme: (isDark ? ThemeData.dark() : ThemeData.light()).textTheme
          .apply(bodyColor: textPrimary, displayColor: textPrimary),
      appBarTheme: AppBarTheme(
        centerTitle: false,
        elevation: 0,
        backgroundColor: Colors.transparent,
        foregroundColor: textPrimary,
        surfaceTintColor: Colors.transparent,
      ),
      cardTheme: CardThemeData(
        elevation: 0,
        color: surface,
        surfaceTintColor: Colors.transparent,
        margin: EdgeInsets.zero,
        shape: RoundedRectangleBorder(
          borderRadius: BorderRadius.circular(UIConstants.cardBorderRadius),
          side: BorderSide(color: outline),
        ),
      ),
      inputDecorationTheme: InputDecorationTheme(
        filled: true,
        fillColor: surfaceElevated,
        border: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: outline),
        ),
        enabledBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: outline),
        ),
        focusedBorder: OutlineInputBorder(
          borderRadius: BorderRadius.circular(16),
          borderSide: BorderSide(color: colorScheme.primary, width: 1.5),
        ),
        labelStyle: TextStyle(color: textSecondary),
        prefixIconColor: textSecondary,
      ),
      elevatedButtonTheme: ElevatedButtonThemeData(
        style: ElevatedButton.styleFrom(
          elevation: 0,
          backgroundColor: colorScheme.primary,
          foregroundColor: isDark
              ? AppColors.background
              : const Color(0xFFFFFCF4),
          padding: const EdgeInsets.symmetric(horizontal: 24, vertical: 16),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
          textStyle: const TextStyle(fontWeight: FontWeight.w800),
        ),
      ),
      outlinedButtonTheme: OutlinedButtonThemeData(
        style: OutlinedButton.styleFrom(
          foregroundColor: colorScheme.primary,
          side: BorderSide(color: outline),
          padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 14),
          shape: RoundedRectangleBorder(
            borderRadius: BorderRadius.circular(16),
          ),
        ),
      ),
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
    if (!NetworkConfig.useCognitoAuth) {
      return HomeScreen(enableRealtimeSync: widget.enableRealtimeSync);
    }

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
