import 'package:flutter/material.dart';
import 'features/auth/screens/auth_screen.dart';
import 'features/dashboard/screens/home_screen.dart';
import 'shared/services/auth_service.dart';
import 'core/utils/constants.dart';

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
  runApp(const KahrabaIQApp());
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
        return HomeScreen(enableRealtimeSync: widget.enableRealtimeSync);
      },
    );
  }
}
