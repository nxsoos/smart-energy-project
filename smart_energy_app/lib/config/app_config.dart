class AppConfig {
  const AppConfig._();

  static const String firebaseRealtimeDatabaseUrl =
      'https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app';

  static const String firebaseHomeId = 'home_001';

  static const String backendApiUrl = String.fromEnvironment(
    'BACKEND_API_URL',
    defaultValue: 'http://10.220.38.94:5001',
  );

  static const bool useLocalPiApi = bool.fromEnvironment(
    'USE_LOCAL_PI_API',
    defaultValue: true,
  );

  static const String aiServiceUrl =
      'https://smart-energy-ai-237804589333.asia-southeast1.run.app';
}
