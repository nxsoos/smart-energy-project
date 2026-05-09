import 'package:flutter/material.dart';
import 'core/theme/app_theme.dart';
import 'features/auth/screens/auth_screen.dart';
import 'features/dashboard/screens/home_screen.dart';
import 'shared/services/auth_service.dart';
import 'shared/services/notification_service.dart';
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
  await NotificationService.initialize();
  runApp(const KahrabaIQApp());
}

class KahrabaIQApp extends StatelessWidget {
  const KahrabaIQApp({super.key, this.enableRealtimeSync = true});

  final bool enableRealtimeSync;

  @override
  Widget build(BuildContext context) {
    return MaterialApp(
      title: appName,
      debugShowCheckedModeBanner: false,
      scrollBehavior: const NoStretchScrollBehavior(),
      theme: AppTheme.dark,
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
            body: Center(child: Icon(Icons.offline_bolt, size: 44)),
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
