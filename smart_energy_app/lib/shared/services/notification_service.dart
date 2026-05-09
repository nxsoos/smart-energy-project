import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter_local_notifications/flutter_local_notifications.dart';

class NotificationService {
  NotificationService._();

  static final FlutterLocalNotificationsPlugin _plugin =
      FlutterLocalNotificationsPlugin();
  static bool _initialized = false;

  static Future<void> initialize() async {
    if (_initialized || kIsWeb) {
      return;
    }

    const android = AndroidInitializationSettings('@mipmap/ic_launcher');
    const settings = InitializationSettings(android: android);
    await _plugin.initialize(settings: settings);

    if (Platform.isAndroid) {
      final androidPlugin = _plugin
          .resolvePlatformSpecificImplementation<
            AndroidFlutterLocalNotificationsPlugin
          >();
      await androidPlugin?.createNotificationChannel(
        const AndroidNotificationChannel(
          'kahrabaiq_safety',
          'Safety alerts',
          description: 'Critical KahrabaIQ smoke and safety alerts.',
          importance: Importance.max,
          playSound: true,
        ),
      );
      await androidPlugin?.requestNotificationsPermission();
    }

    _initialized = true;
  }

  static Future<void> showSmokeAlert({
    required String alertId,
    required String message,
  }) async {
    await initialize();
    if (kIsWeb) {
      return;
    }

    await _plugin.show(
      id: alertId.hashCode,
      title: 'Smoke/Gas Detected',
      body: message.isEmpty
          ? 'Smoke or gas was detected. Check the area immediately.'
          : message,
      notificationDetails: const NotificationDetails(
        android: AndroidNotificationDetails(
          'kahrabaiq_safety',
          'Safety alerts',
          channelDescription: 'Critical KahrabaIQ smoke and safety alerts.',
          importance: Importance.max,
          priority: Priority.high,
          category: AndroidNotificationCategory.alarm,
          fullScreenIntent: true,
          visibility: NotificationVisibility.public,
        ),
      ),
    );
  }
}
