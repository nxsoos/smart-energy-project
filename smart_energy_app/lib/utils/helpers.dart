/// Helper functions for the app
library;

import 'package:intl/intl.dart';

/// Format energy value for display
String formatEnergy(double kWh) {
  if (kWh < 1) {
    return '${(kWh * 1000).toStringAsFixed(0)} Wh';
  }
  return '${kWh.toStringAsFixed(2)} kWh';
}

/// Format power value for display
String formatPower(double watts) {
  if (watts >= 1000) {
    return '${(watts / 1000).toStringAsFixed(2)} kW';
  }
  return '${watts.toStringAsFixed(0)} W';
}

/// Format cost in Bahraini Dinars
String formatCost(double bd) {
  return '${bd.toStringAsFixed(3)} BD';
}

/// Format timestamp
String formatTime(DateTime time) {
  return DateFormat('HH:mm').format(time);
}

/// Format date
String formatDate(DateTime date) {
  return DateFormat('MMM dd, yyyy').format(date);
}

/// Format date and time
String formatDateTime(DateTime dateTime) {
  return DateFormat('MMM dd, HH:mm').format(dateTime);
}

/// Calculate cost from kWh
double calculateCost(double kWh, double ratePerKWh) {
  return kWh * ratePerKWh;
}

/// Calculate percentage
double calculatePercentage(double value, double max) {
  if (max == 0) return 0;
  return (value / max) * 100;
}

/// Check if power is in safe range
bool isPowerSafe(double power, double maxPower) {
  return power < (maxPower * 0.8); // 80% threshold
}

/// Check if power is in warning range
bool isPowerWarning(double power, double maxPower) {
  return power >= (maxPower * 0.8) && power < (maxPower * 0.95);
}

/// Check if power is in danger range
bool isPowerDanger(double power, double maxPower) {
  return power >= (maxPower * 0.95);
}

/// Get time ago string
String getTimeAgo(DateTime dateTime) {
  final difference = DateTime.now().difference(dateTime);
  
  if (difference.inSeconds < 60) {
    return 'just now';
  } else if (difference.inMinutes < 60) {
    return '${difference.inMinutes}m ago';
  } else if (difference.inHours < 24) {
    return '${difference.inHours}h ago';
  } else {
    return '${difference.inDays}d ago';
  }
}

/// Validate IP address
bool isValidIP(String ip) {
  final ipRegex = RegExp(
    r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$',
  );
  
  if (!ipRegex.hasMatch(ip)) return false;
  
  final parts = ip.split('.');
  for (var part in parts) {
    final num = int.tryParse(part);
    if (num == null || num < 0 || num > 255) {
      return false;
    }
  }
  
  return true;
}

/// Validate temperature range
bool isValidTemperature(double temp, double min, double max) {
  return temp >= min && temp <= max;
}
