import '../utils/constants.dart';

/// Represents a controllable device in the system
class Device {
  final String id;
  final String name;
  final DeviceType type;
  final bool isOn;
  final double currentPower; // Watts
  final String branch; // Branch 1, 2, or 3
  final bool online;
  final bool localOnline;
  final bool cloudOnline;
  final bool controllable;
  final bool commandInProgress;
  final bool energySupported;
  final String? controlMethod;
  final String? pendingTargetState;
  final String? lastCommandMessage;

  Device({
    required this.id,
    required this.name,
    required this.type,
    required this.isOn,
    required this.currentPower,
    required this.branch,
    this.online = true,
    this.localOnline = true,
    this.cloudOnline = true,
    this.controllable = true,
    this.commandInProgress = false,
    this.energySupported = true,
    this.controlMethod,
    this.pendingTargetState,
    this.lastCommandMessage,
  });

  factory Device.fromJson(Map<String, dynamic> json) {
    return Device(
      id: json['id'] as String,
      name: json['name'] as String,
      type: _parseDeviceType(json['type'] as String),
      isOn: json['isOn'] as bool,
      currentPower: (json['currentPower'] as num?)?.toDouble() ?? 0,
      branch: json['branch'] as String,
      online: json['online'] as bool? ?? true,
      localOnline: json['localOnline'] as bool? ?? true,
      cloudOnline: json['cloudOnline'] as bool? ?? true,
      controllable: json['controllable'] as bool? ?? true,
      commandInProgress: json['commandInProgress'] as bool? ?? false,
      energySupported: json['energySupported'] as bool? ?? true,
      controlMethod: json['controlMethod'] as String?,
      pendingTargetState: json['pendingTargetState'] as String?,
      lastCommandMessage: json['lastCommandMessage'] as String?,
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'name': name,
      'type': type.toString().split('.').last,
      'isOn': isOn,
      'currentPower': currentPower,
      'branch': branch,
      'online': online,
      'localOnline': localOnline,
      'cloudOnline': cloudOnline,
      'controllable': controllable,
      'commandInProgress': commandInProgress,
      'energySupported': energySupported,
      'controlMethod': controlMethod,
      'pendingTargetState': pendingTargetState,
      'lastCommandMessage': lastCommandMessage,
    };
  }

  Device copyWith({
    String? id,
    String? name,
    DeviceType? type,
    bool? isOn,
    double? currentPower,
    String? branch,
    bool? online,
    bool? localOnline,
    bool? cloudOnline,
    bool? controllable,
    bool? commandInProgress,
    bool? energySupported,
    String? controlMethod,
    String? pendingTargetState,
    String? lastCommandMessage,
  }) {
    return Device(
      id: id ?? this.id,
      name: name ?? this.name,
      type: type ?? this.type,
      isOn: isOn ?? this.isOn,
      currentPower: currentPower ?? this.currentPower,
      branch: branch ?? this.branch,
      online: online ?? this.online,
      localOnline: localOnline ?? this.localOnline,
      cloudOnline: cloudOnline ?? this.cloudOnline,
      controllable: controllable ?? this.controllable,
      commandInProgress: commandInProgress ?? this.commandInProgress,
      energySupported: energySupported ?? this.energySupported,
      controlMethod: controlMethod ?? this.controlMethod,
      pendingTargetState: pendingTargetState ?? this.pendingTargetState,
      lastCommandMessage: lastCommandMessage ?? this.lastCommandMessage,
    );
  }

  static DeviceType _parseDeviceType(String type) {
    switch (type.toLowerCase()) {
      case 'light':
        return DeviceType.light;
      case 'socket':
        return DeviceType.socket;
      case 'airconditioner':
      case 'ac':
        return DeviceType.airConditioner;
      default:
        return DeviceType.socket;
    }
  }
}
