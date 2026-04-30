import '../utils/constants.dart';

/// Represents a controllable device in the system
class Device {
  final String id;
  final String name;
  final DeviceType type;
  final bool isOn;
  final double currentPower; // Watts
  final String branch; // Branch 1, 2, or 3

  Device({
    required this.id,
    required this.name,
    required this.type,
    required this.isOn,
    required this.currentPower,
    required this.branch,
  });

  factory Device.fromJson(Map<String, dynamic> json) {
    return Device(
      id: json['id'] as String,
      name: json['name'] as String,
      type: _parseDeviceType(json['type'] as String),
      isOn: json['isOn'] as bool,
      currentPower: (json['currentPower'] as num).toDouble(),
      branch: json['branch'] as String,
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
    };
  }

  Device copyWith({
    String? id,
    String? name,
    DeviceType? type,
    bool? isOn,
    double? currentPower,
    String? branch,
  }) {
    return Device(
      id: id ?? this.id,
      name: name ?? this.name,
      type: type ?? this.type,
      isOn: isOn ?? this.isOn,
      currentPower: currentPower ?? this.currentPower,
      branch: branch ?? this.branch,
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
