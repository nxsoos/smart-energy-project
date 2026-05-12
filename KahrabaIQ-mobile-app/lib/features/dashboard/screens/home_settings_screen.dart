import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../core/widgets/app_state_widgets.dart';
import '../../../shared/services/kahrabaiq_api_service.dart';

class HomeSettingsScreen extends StatefulWidget {
  const HomeSettingsScreen({
    super.key,
    required this.homeId,
    required this.canEdit,
    this.scenarioMode = false,
  });

  final String homeId;
  final bool canEdit;
  final bool scenarioMode;

  @override
  State<HomeSettingsScreen> createState() => _HomeSettingsScreenState();
}

class _HomeSettingsScreenState extends State<HomeSettingsScreen> {
  final KahrabaIqApiService _api = KahrabaIqApiService();
  final Map<String, TextEditingController> _controllers = {};
  final Map<String, bool> _toggles = {};
  bool _loading = true;
  bool _saving = false;
  String? _error;

  bool get _canEdit => widget.canEdit && !widget.scenarioMode;

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    for (final controller in _controllers.values) {
      controller.dispose();
    }
    super.dispose();
  }

  TextEditingController _controller(String key, Object? value) {
    return _controllers.putIfAbsent(
      key,
      () => TextEditingController(text: value?.toString() ?? ''),
    );
  }

  Future<void> _load() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final settings = await _api.fetchSettings(homeId: widget.homeId);
      _apply(settings.values);
      if (!mounted) return;
      setState(() {
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  void _apply(Map<String, dynamic> values) {
    for (final entry in values.entries) {
      if (entry.value is bool) {
        _toggles[entry.key] = entry.value as bool;
      } else {
        _controller(entry.key, entry.value).text = entry.value?.toString() ?? '';
      }
    }
  }

  String? _validate() {
    double number(String key) =>
        double.tryParse(_controllers[key]?.text.trim() ?? '') ?? double.nan;
    final comfortMin = number('comfort_temperature_min');
    final comfortMax = number('comfort_temperature_max');
    final highTemp = number('high_temperature_threshold');
    final humidityMin = number('humidity_min');
    final humidityMax = number('humidity_max');
    final monthlyCost = number('monthly_cost_limit_bhd');
    final dailyCost = number('daily_cost_limit_bhd');
    final monthlyEnergy = number('monthly_energy_limit_kwh');
    final dailyEnergy = number('daily_energy_limit_kwh');
    if ([comfortMin, comfortMax, highTemp, humidityMin, humidityMax, monthlyCost, dailyCost, monthlyEnergy, dailyEnergy].any((value) => value.isNaN)) {
      return 'Please fill all numeric fields with valid numbers.';
    }
    if (comfortMin >= comfortMax) {
      return 'Comfort minimum must be lower than comfort maximum.';
    }
    if (highTemp < comfortMax) {
      return 'High temperature threshold must be at least the comfort maximum.';
    }
    if (humidityMin >= humidityMax) {
      return 'Humidity minimum must be lower than humidity maximum.';
    }
    if (monthlyCost < dailyCost) {
      return 'Monthly cost limit must be greater than the daily cost limit.';
    }
    if (monthlyEnergy < dailyEnergy) {
      return 'Monthly energy limit must be greater than the daily energy limit.';
    }
    return null;
  }

  Map<String, dynamic> _payload() {
    final values = <String, dynamic>{};
    for (final entry in _controllers.entries) {
      final text = entry.value.text.trim();
      if (text.isEmpty) {
        continue;
      }
      if (_integerKeys.contains(entry.key)) {
        values[entry.key] = int.tryParse(text) ?? double.tryParse(text)?.round();
      } else {
        values[entry.key] = double.tryParse(text) ?? text;
      }
    }
    values.addAll(_toggles);
    values['updated_by'] = 'flutter_app';
    return values;
  }

  Future<void> _save() async {
    final validation = _validate();
    if (validation != null) {
      ScaffoldMessenger.of(context).showSnackBar(SnackBar(content: Text(validation)));
      return;
    }
    setState(() {
      _saving = true;
    });
    try {
      final settings = await _api.updateSettings(
        homeId: widget.homeId,
        values: _payload(),
      );
      _apply(settings.values);
      if (!mounted) return;
      setState(() {
        _saving = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('Settings saved. Dashboard and AI will use the new thresholds.')),
      );
      Navigator.of(context).pop(true);
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _saving = false;
      });
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(error.toString().replaceFirst('Exception: ', ''))),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text('Home Settings'),
        actions: [
          if (_canEdit)
            TextButton(
              onPressed: _saving ? null : _save,
              child: _saving ? const SizedBox.square(dimension: 18, child: CircularProgressIndicator(strokeWidth: 2)) : const Text('Save'),
            ),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : _error != null
          ? AppErrorState(message: _error!, onRetry: _load)
          : ListView(
              padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
              children: [
                if (!_canEdit)
                  _Notice(
                    text: widget.scenarioMode
                        ? 'Demo scenarios use temporary settings and do not modify the real home.'
                        : 'You can view these settings, but only home admins can edit them.',
                  ),
                _Section(
                  title: 'Energy & Budget',
                  children: [
                    _number('cost_per_kwh', 'Cost per kWh (BHD)', min: 0.001, max: 1),
                    _number('monthly_cost_limit_bhd', 'Monthly cost limit (BHD)', min: 0.1, max: 1000),
                    _number('monthly_energy_limit_kwh', 'Monthly energy limit (kWh)', min: 1, max: 100000),
                    _number('daily_cost_limit_bhd', 'Daily cost limit (BHD)', min: 0.1, max: 1000),
                    _number('daily_energy_limit_kwh', 'Daily energy limit (kWh)', min: 1, max: 10000),
                    _number('high_usage_warning_percent', 'Warning threshold (%)', min: 1, max: 100),
                  ],
                ),
                _Section(
                  title: 'Comfort & Environment',
                  children: [
                    _number('comfort_temperature_min', 'Comfort min (C)', min: 16, max: 30),
                    _number('comfort_temperature_max', 'Comfort max (C)', min: 18, max: 35),
                    _number('high_temperature_threshold', 'High temperature alert (C)', min: 25, max: 45),
                    _number('humidity_min', 'Humidity min (%)', min: 0, max: 100),
                    _number('humidity_max', 'Humidity max (%)', min: 0, max: 100),
                    _switch('air_quality_alert_enabled', 'Air quality alerts'),
                  ],
                ),
                _Section(
                  title: 'Occupancy Detection',
                  children: [
                    _number('motion_recent_seconds', 'Motion recent window (seconds)', min: 5, max: 600),
                    _number('sound_recent_seconds', 'Sound recent window (seconds)', min: 5, max: 600),
                    _number('occupancy_empty_minutes', 'Empty-room wait (minutes)', min: 1, max: 120),
                    _number('sound_activity_threshold', 'Sound activity threshold', min: 0, max: 4095),
                    _number('occupancy_confidence_threshold', 'Occupancy confidence', min: 0, max: 1),
                  ],
                ),
                _Section(
                  title: 'AI & Automation',
                  children: [
                    _switch('ai_recommendations_enabled', 'AI recommendations'),
                    _switch('ai_anomaly_detection_enabled', 'AI anomaly detection'),
                    _switch('ai_cost_forecast_enabled', 'AI cost forecast'),
                    _switch('auto_control_enabled', 'Automatic control'),
                    _switch('schedules_enabled', 'Schedules'),
                  ],
                ),
                _Section(
                  title: 'Notifications',
                  children: [
                    _switch('notifications_enabled', 'Notifications'),
                    _switch('cost_notifications_enabled', 'Cost notifications'),
                    _switch('energy_notifications_enabled', 'Energy notifications'),
                    _switch('safety_notifications_enabled', 'Safety notifications'),
                    _switch('device_status_notifications_enabled', 'Device status notifications'),
                    _switch('ai_notifications_enabled', 'AI notifications'),
                    _switch('quiet_hours_enabled', 'Quiet hours'),
                    _text('quiet_hours_start', 'Quiet hours start'),
                    _text('quiet_hours_end', 'Quiet hours end'),
                  ],
                ),
                _Section(
                  title: 'Device Status',
                  children: [
                    _number('device_offline_minutes', 'Device offline after (minutes)', min: 1, max: 180),
                    _number('sensor_stale_minutes', 'Sensor stale after (minutes)', min: 1, max: 180),
                    _number('breaker_stale_minutes', 'Breaker stale after (minutes)', min: 1, max: 180),
                    _number('hub_offline_minutes', 'Hub offline after (minutes)', min: 1, max: 180),
                  ],
                ),
              ],
            ),
    );
  }

  Widget _number(String key, String label, {required num min, required num max}) {
    return _field(
      key,
      label,
      helper: '$min to $max',
      keyboardType: const TextInputType.numberWithOptions(decimal: true),
    );
  }

  Widget _text(String key, String label) => _field(key, label, helper: 'HH:mm');

  Widget _field(
    String key,
    String label, {
    String? helper,
    TextInputType? keyboardType,
  }) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
      child: TextField(
        controller: _controller(key, ''),
        enabled: _canEdit,
        keyboardType: keyboardType,
        decoration: InputDecoration(
          labelText: label,
          helperText: helper,
          border: const OutlineInputBorder(),
        ),
      ),
    );
  }

  Widget _switch(String key, String label) {
    return SwitchListTile(
      contentPadding: EdgeInsets.zero,
      value: _toggles[key] ?? true,
      onChanged: _canEdit
          ? (value) {
              setState(() {
                _toggles[key] = value;
              });
            }
          : null,
      title: Text(label, style: AppTextStyles.bodyMedium),
    );
  }
}

class _Section extends StatelessWidget {
  const _Section({required this.title, required this.children});

  final String title;
  final List<Widget> children;

  @override
  Widget build(BuildContext context) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 20),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(title, style: AppTextStyles.h3),
          const SizedBox(height: 12),
          ...children,
        ],
      ),
    );
  }
}

class _Notice extends StatelessWidget {
  const _Notice({required this.text});

  final String text;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 16),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: ColorTokens.warning.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(8),
        border: Border.all(color: ColorTokens.warning.withValues(alpha: 0.45)),
      ),
      child: Text(text, style: AppTextStyles.body),
    );
  }
}

const _integerKeys = {
  'motion_recent_seconds',
  'sound_recent_seconds',
  'occupancy_empty_minutes',
  'device_offline_minutes',
  'sensor_stale_minutes',
  'breaker_stale_minutes',
  'hub_offline_minutes',
};
