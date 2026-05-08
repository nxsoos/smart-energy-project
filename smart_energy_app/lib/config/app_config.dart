class AppConfig {
  const AppConfig._();

  static const String firebaseRealtimeDatabaseUrl =
      'https://seniorproject-energy-default-rtdb.asia-southeast1.firebasedatabase.app';

  static const String firebaseHomeId = 'home_001';

  static const String backendApiUrl = String.fromEnvironment(
    'BACKEND_API_URL',
    defaultValue: 'http://10.220.38.94:5001',
  );

  static const String cloudApiUrl = String.fromEnvironment(
    'CLOUD_API_URL',
    defaultValue: '',
  );

  static const String awsRegion = String.fromEnvironment(
    'AWS_REGION',
    defaultValue: 'eu-west-1',
  );

  static const String cognitoUserPoolId = String.fromEnvironment(
    'COGNITO_USER_POOL_ID',
    defaultValue: '',
  );

  static const String cognitoAppClientId = String.fromEnvironment(
    'COGNITO_APP_CLIENT_ID',
    defaultValue: '',
  );

  static const String cognitoIdentityPoolId = String.fromEnvironment(
    'COGNITO_IDENTITY_POOL_ID',
    defaultValue: '',
  );

  static const String awsIotEndpoint = String.fromEnvironment(
    'AWS_IOT_ENDPOINT',
    defaultValue: 'a2olbiowu565t4-ats.iot.eu-west-1.amazonaws.com',
  );

  static const String awsIotPolicyName = String.fromEnvironment(
    'AWS_IOT_POLICY_NAME',
    defaultValue: 'SmartEnergyFlutterLiveSubscribePolicy',
  );

  static const String awsIotLiveTopic = String.fromEnvironment(
    'AWS_IOT_LIVE_TOPIC',
    defaultValue: 'homes/home_001/live/state',
  );

  static const String cognitoAdminGroup = String.fromEnvironment(
    'COGNITO_ADMIN_GROUP',
    defaultValue: 'SmartEnergyAdmins',
  );

  static const String cognitoMemberGroup = String.fromEnvironment(
    'COGNITO_MEMBER_GROUP',
    defaultValue: 'SmartEnergyMembers',
  );

  static bool get useAwsIotLive =>
      cognitoUserPoolId.isNotEmpty &&
      cognitoAppClientId.isNotEmpty &&
      cognitoIdentityPoolId.isNotEmpty &&
      awsIotEndpoint.isNotEmpty &&
      awsIotPolicyName.isNotEmpty &&
      awsIotLiveTopic.isNotEmpty;

  static const bool useLocalPiApi = bool.fromEnvironment(
    'USE_LOCAL_PI_API',
    defaultValue: true,
  );

  static const bool remoteLiveOnly = bool.fromEnvironment(
    'REMOTE_LIVE_ONLY',
    defaultValue: false,
  );

  static const int piApiTimeoutSeconds = int.fromEnvironment(
    'PI_API_TIMEOUT_SECONDS',
    defaultValue: 6,
  );

  static const String aiServiceUrl =
      'https://smart-energy-ai-237804589333.asia-southeast1.run.app';
}
