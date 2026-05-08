import 'package:flutter/material.dart';

import '../config/app_config.dart';

/// App-wide constants and configuration

// App Information
const String appName = 'KahrabaIQ';
const String appVersion = '1.0.0';

// Colors - Energy theme (Green)
class AppColors {
  static const Color primary = Color(0xFF2E7D32); // Dark Green
  static const Color primaryLight = Color(0xFF60AD5E);
  static const Color primaryDark = Color(0xFF005005);

  static const Color accent = Color(0xFF00C853); // Bright Green

  static const Color energySafe = Color(0xFF4CAF50); // Green
  static const Color energyWarning = Color(0xFFFF9800); // Orange
  static const Color energyDanger = Color(0xFFF44336); // Red

  static const Color background = Color(0xFFF5F5F5);
  static const Color surface = Colors.white;
  static const Color textPrimary = Color(0xFF212121);
  static const Color textSecondary = Color(0xFF757575);
}

// Device Types
enum DeviceType {
  light, // Branch 1: LED strip
  socket, // Branch 2: ESP32 socket
  airConditioner, // Branch 3: AC unit
}

// AC Modes
enum ACMode { cool, fan, auto }

// Alert Types
enum AlertType { overload, fire, highConsumption, sensorFailure }

// Energy Thresholds
class EnergyLimits {
  static const double maxPowerBranch1 = 1000.0; // Watts (10A fuse)
  static const double maxPowerBranch2 = 1600.0; // Watts (16A fuse)
  static const double maxPowerBranch3 = 2500.0; // Watts (25A fuse)

  static const double warningThreshold = 0.8; // 80% of max
  static const double dangerThreshold = 0.95; // 95% of max
}

// Temperature Limits
class TemperatureLimits {
  static const double minACTemp = 16.0;
  static const double maxACTemp = 30.0;
  static const double defaultACTemp = 24.0;

  static const double comfortableMin = 22.0;
  static const double comfortableMax = 26.0;
}

// Time Constants
class TimeConstants {
  static const int dataUpdateInterval = 1; // seconds
  static const int chartUpdateInterval = 5; // seconds
  static const int autoOffDelay = 5; // minutes after room vacant
}

// Network Configuration
class NetworkConfig {
  static const String defaultRaspberryPiIP = '192.168.1.100';
  static const int apiPort = 8000;
  static const int mqttPort = 1883;
  static const String firebaseRealtimeDatabaseUrl =
      AppConfig.firebaseRealtimeDatabaseUrl;
  static const String firebaseHomeId = AppConfig.firebaseHomeId;
  static const String backendApiUrl = AppConfig.backendApiUrl;
  static const String cloudApiUrl = AppConfig.cloudApiUrl;
  static const bool useLocalPiApi = AppConfig.useLocalPiApi;
  static const String awsRegion = AppConfig.awsRegion;
  static const String cognitoUserPoolId = AppConfig.cognitoUserPoolId;
  static const String cognitoAppClientId = AppConfig.cognitoAppClientId;
  static const String cognitoIdentityPoolId = AppConfig.cognitoIdentityPoolId;
  static const String awsIotEndpoint = AppConfig.awsIotEndpoint;
  static const String awsIotPolicyName = AppConfig.awsIotPolicyName;
  static const String awsIotLiveTopic = AppConfig.awsIotLiveTopic;
  static const String cognitoAdminGroup = AppConfig.cognitoAdminGroup;
  static const String cognitoMemberGroup = AppConfig.cognitoMemberGroup;
  static const bool remoteLiveOnly = AppConfig.remoteLiveOnly;
  static const int piApiTimeoutSeconds = AppConfig.piApiTimeoutSeconds;
  static bool get useAwsIotLive => AppConfig.useAwsIotLive;

  static String get apiBaseUrl => backendApiUrl;
  static String get mqttBrokerUrl => defaultRaspberryPiIP;

  // MQTT Topics
  static const String topicTemperature = 'sensors/temperature';
  static const String topicHumidity = 'sensors/humidity';
  static const String topicOccupancy = 'sensors/occupancy';
  static const String topicEnergyBranch1 = 'energy/branch1';
  static const String topicEnergyBranch2 = 'energy/branch2';
  static const String topicEnergyBranch3 = 'energy/branch3';
  static const String topicAlertFire = 'alerts/fire';
  static const String topicAlertOverload = 'alerts/overload';
}

// Electricity Pricing (Bahrain)
class ElectricityPricing {
  static const double costPerKWh = 0.003; // BD per kWh (3 fils)
  static const String currency = 'BD'; // Bahraini Dinar
}

// UI Constants
class UIConstants {
  static const double cardBorderRadius = 12.0;
  static const double buttonBorderRadius = 8.0;
  static const double defaultPadding = 16.0;
  static const double smallPadding = 8.0;
  static const double largePadding = 24.0;
}
