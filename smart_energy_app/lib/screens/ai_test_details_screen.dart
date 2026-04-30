import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../utils/constants.dart';

// Temporary test/demo page for validating Smart Energy AI scenarios.
// This screen reads /homes/home_test only and can be removed later.
class AiTestDetailsScreen extends StatefulWidget {
  const AiTestDetailsScreen({super.key});

  @override
  State<AiTestDetailsScreen> createState() => _AiTestDetailsScreenState();
}

class _AiTestDetailsScreenState extends State<AiTestDetailsScreen> {
  final Dio _dio = Dio(
    BaseOptions(
      baseUrl: NetworkConfig.firebaseRealtimeDatabaseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 10),
    ),
  );

  bool _isLoading = false;
  String? _error;
  Map<String, dynamic> _home = const {};

  Map<String, dynamic> get _backend => _asMap(_home['backend']);
  Map<String, dynamic> get _backendAi => _asMap(_backend['ai']);
  Map<String, dynamic> get _dashboard => _asMap(_backend['dashboard']);
  Map<String, dynamic> get _recommendations =>
      _asMap(_backend['recommendations']);
  Map<String, dynamic> get _activeAlerts => _asMap(_backend['active_alerts']);

  Map<String, dynamic> get _metadata => _asMap(_backendAi['test_metadata']);
  Map<String, dynamic> get _expected => _asMap(_backendAi['test_expected']);
  Map<String, dynamic> get _latest => _asMap(_backendAi['latest_prediction']);
  Map<String, dynamic> get _dashboardAi => _asMap(_dashboard['ai']);
  Map<String, dynamic> get _recommendation =>
      _asMap(_recommendations['ai_energy_insight']);
  Map<String, dynamic> get _aiAlert =>
      _asMap(_activeAlerts['ai_abnormal_usage']);
  Map<String, dynamic> get _dailySummary => _asMap(_backendAi['daily_summary']);
  Map<String, dynamic> get _history => _asMap(_backendAi['prediction_history']);

  @override
  void initState() {
    super.initState();
    _loadData();
  }

  Future<void> _loadData() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });

    try {
      final response = await _dio.get('/homes/home_test.json');
      if (!mounted) {
        return;
      }
      setState(() {
        _home = _asMap(response.data);
      });
    } catch (_) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = 'Could not load /homes/home_test from Firebase.';
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoading = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: const Text(
          'AI Test Details',
          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
        ),
        backgroundColor: AppColors.primary,
        iconTheme: const IconThemeData(color: Colors.white),
        actions: [
          IconButton(
            tooltip: 'Refresh',
            icon: const Icon(Icons.refresh, color: Colors.white),
            onPressed: _isLoading ? null : _loadData,
          ),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadData,
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (_isLoading) ...[
                const LinearProgressIndicator(),
                const SizedBox(height: 12),
              ],
              _buildNoteCard(),
              if (_error != null) ...[
                const SizedBox(height: 12),
                _buildMessageCard(
                  icon: Icons.error_outline,
                  title: 'Firebase load failed',
                  message: _error!,
                  color: AppColors.energyDanger,
                ),
              ],
              const SizedBox(height: 12),
              _buildScenarioCard(),
              const SizedBox(height: 12),
              _buildExpectedCard(),
              const SizedBox(height: 12),
              _buildComparisonCard(),
              const SizedBox(height: 12),
              _buildLatestPredictionCard(),
              const SizedBox(height: 12),
              _buildDashboardAiCard(),
              const SizedBox(height: 12),
              _buildRecommendationCard(),
              const SizedBox(height: 12),
              _buildAiAlertCard(),
              const SizedBox(height: 12),
              _buildDailySummaryCard(),
              const SizedBox(height: 12),
              _buildHistoryCard(),
              const SizedBox(height: 24),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildNoteCard() {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Icon(Icons.science_outlined, color: AppColors.primary),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    'Temporary AI scenario testing page',
                    style: TextStyle(
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 4),
                  Text(
                    'This page uses /homes/home_test and is for AI scenario testing only.',
                    style: TextStyle(color: Colors.grey[700], height: 1.3),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildScenarioCard() {
    if (_metadata.isEmpty) {
      return _buildMessageCard(
        icon: Icons.info_outline,
        title: 'Active Test Scenario',
        message: 'No active test scenario',
        color: Colors.grey,
      );
    }

    return _buildSectionCard(
      title: 'Active Test Scenario',
      icon: Icons.assignment_outlined,
      children: [
        _buildKeyValue('active_scenario', _metadata['active_scenario']),
        _buildKeyValue('written_at', _metadata['written_at']),
        _buildKeyValue('written_by', _metadata['written_by']),
        _buildKeyValue('notes', _metadata['notes']),
      ],
    );
  }

  Widget _buildExpectedCard() {
    if (_expected.isEmpty) {
      return _buildMessageCard(
        icon: Icons.rule_outlined,
        title: 'Expected Result',
        message: 'No expected test result found',
        color: Colors.grey,
      );
    }

    return _buildSectionCard(
      title: 'Expected Result',
      icon: Icons.rule_outlined,
      children: [
        _buildKeyValue('scenario_name', _expected['scenario_name']),
        _buildKeyValue(
          'expected_energy_waste',
          _expected['expected_energy_waste'],
        ),
        _buildKeyValue(
          'expected_abnormal_usage',
          _expected['expected_abnormal_usage'],
        ),
        _buildKeyValue(
          'expected_recommendation_type',
          _expected['expected_recommendation_type'],
        ),
        _buildKeyValue(
          'expected_description',
          _expected['expected_description'],
        ),
      ],
    );
  }

  Widget _buildComparisonCard() {
    final expectedWaste = _expected['expected_energy_waste'];
    final actualWaste = _pick(_latest, ['energy_waste', 'energyWaste']);
    final expectedAbnormal = _expected['expected_abnormal_usage'];
    final actualAbnormal = _pick(_latest, ['abnormal_usage', 'abnormalUsage']);
    final expectedRecommendation = _expected['expected_recommendation_type'];
    final actualRecommendation = _pick(_latest, [
      'recommendation_type',
      'recommendationType',
    ]);

    return _buildSectionCard(
      title: 'Expected vs Actual',
      icon: Icons.compare_arrows_outlined,
      children: [
        _buildComparisonRow(
          label: 'Energy waste',
          expected: expectedWaste,
          actual: actualWaste,
          expectedValue: _asNullableBool(expectedWaste),
          actualValue: _asNullableBool(actualWaste),
        ),
        _buildComparisonRow(
          label: 'Abnormal usage',
          expected: expectedAbnormal,
          actual: actualAbnormal,
          expectedValue: _asNullableBool(expectedAbnormal),
          actualValue: _asNullableBool(actualAbnormal),
        ),
        _buildComparisonRow(
          label: 'Recommendation type',
          expected: expectedRecommendation,
          actual: actualRecommendation,
          expectedValue: _normalizeText(expectedRecommendation),
          actualValue: _normalizeText(actualRecommendation),
        ),
      ],
    );
  }

  Widget _buildLatestPredictionCard() {
    if (_latest.isEmpty) {
      return _buildMessageCard(
        icon: Icons.online_prediction_outlined,
        title: 'Actual Latest AI Prediction',
        message: 'No AI prediction yet',
        color: Colors.grey,
      );
    }

    return _buildSectionCard(
      title: 'Actual Latest AI Prediction',
      icon: Icons.online_prediction_outlined,
      children: [
        _buildKeyValue('timestamp', _latest['timestamp']),
        _buildKeyValue('last_checked_at', _latest['last_checked_at']),
        _buildKeyValue('last_changed_at', _latest['last_changed_at']),
        _buildKeyValue('history_written', _latest['history_written']),
        _buildKeyValue('change_reason', _latest['change_reason']),
        _buildKeyValue(
          'energy_waste',
          _pick(_latest, ['energy_waste', 'energyWaste']),
        ),
        _buildKeyValue(
          'abnormal_usage',
          _pick(_latest, ['abnormal_usage', 'abnormalUsage']),
        ),
        _buildKeyValue(
          'recommendation_type',
          _pick(_latest, ['recommendation_type', 'recommendationType']),
        ),
        _buildKeyValue(
          'next_hour_energy',
          _pick(_latest, [
            'next_hour_energy',
            'next_hour_energy_kWh',
            'next_hour_energy_kwh',
          ]),
        ),
        _buildKeyValue(
          'next_hour_cost',
          _pick(_latest, [
            'next_hour_cost',
            'next_hour_cost_BHD',
            'next_hour_cost_bhd',
          ]),
        ),
        _buildKeyValue(
          'efficiency_score',
          _pick(_latest, ['efficiency_score', 'efficiencyScore']),
        ),
        _buildKeyValue('explanation', _latest['explanation']),
        _buildKeyValue('same_status_count', _latest['same_status_count']),
        _buildKeyValue('checks_since_change', _latest['checks_since_change']),
      ],
    );
  }

  Widget _buildDashboardAiCard() {
    if (_dashboardAi.isEmpty) {
      return _buildMessageCard(
        icon: Icons.dashboard_outlined,
        title: 'Dashboard AI Result',
        message: 'No dashboard AI result yet',
        color: Colors.grey,
      );
    }

    return _buildSectionCard(
      title: 'Dashboard AI Result',
      icon: Icons.dashboard_outlined,
      children: _dashboardAi.entries
          .map((entry) => _buildKeyValue(entry.key, entry.value))
          .toList(),
    );
  }

  Widget _buildRecommendationCard() {
    if (_recommendation.isEmpty) {
      return _buildMessageCard(
        icon: Icons.lightbulb_outline,
        title: 'AI Recommendation',
        message: 'No AI recommendation found',
        color: Colors.grey,
      );
    }

    return _buildSectionCard(
      title: 'AI Recommendation',
      icon: Icons.lightbulb_outline,
      children: [
        _buildKeyValue('title', _recommendation['title']),
        _buildKeyValue('message', _recommendation['message']),
        _buildKeyValue(
          'recommendation_type',
          _pick(_recommendation, ['recommendation_type', 'recommendationType']),
        ),
        _buildKeyValue(
          'priority/severity',
          _pick(_recommendation, ['priority', 'severity']),
        ),
        _buildKeyValue('status', _recommendation['status']),
        _buildKeyValue('created_at', _recommendation['created_at']),
        _buildKeyValue('updated_at', _recommendation['updated_at']),
        if (_pick(_recommendation, ['resolved_at', 'resolvedAt']) != null)
          _buildKeyValue(
            'resolved',
            _pick(_recommendation, ['resolved_at', 'resolvedAt']),
          ),
      ],
    );
  }

  Widget _buildAiAlertCard() {
    if (_aiAlert.isEmpty) {
      return _buildMessageCard(
        icon: Icons.check_circle_outline,
        title: 'AI Abnormal Usage Alert',
        message: 'No active AI abnormal usage alert',
        color: AppColors.energySafe,
      );
    }

    return _buildSectionCard(
      title: 'AI Abnormal Usage Alert',
      icon: Icons.warning_amber_outlined,
      children: [
        _buildKeyValue('title', _aiAlert['title']),
        _buildKeyValue('message', _aiAlert['message']),
        _buildKeyValue('severity', _pick(_aiAlert, ['severity', 'priority'])),
        _buildKeyValue('status', _aiAlert['status']),
        _buildKeyValue('created_at', _aiAlert['created_at']),
        _buildKeyValue('updated_at', _aiAlert['updated_at']),
      ],
    );
  }

  Widget _buildDailySummaryCard() {
    if (_dailySummary.isEmpty) {
      return _buildMessageCard(
        icon: Icons.today_outlined,
        title: 'Daily Summary',
        message: 'No daily summary yet',
        color: Colors.grey,
      );
    }

    return _buildSectionCard(
      title: 'Daily Summary',
      icon: Icons.today_outlined,
      children: [
        _buildKeyValue(
          'total_ai_checks_today',
          _pick(_dailySummary, ['total_ai_checks_today', 'prediction_count']),
        ),
        _buildKeyValue(
          'history_records_today',
          _dailySummary['history_records_today'],
        ),
        _buildKeyValue(
          'waste_predictions_today',
          _pick(_dailySummary, [
            'waste_predictions_today',
            'waste_prediction_count',
          ]),
        ),
        _buildKeyValue(
          'abnormal_predictions_today',
          _pick(_dailySummary, [
            'abnormal_predictions_today',
            'abnormal_prediction_count',
          ]),
        ),
        _buildKeyValue(
          'average_efficiency_score',
          _pick(_dailySummary, [
            'average_efficiency_score',
            'averageEfficiencyScore',
          ]),
        ),
        _buildKeyValue(
          'latest_status_message',
          _pick(_dailySummary, ['latest_status_message', 'summary']),
        ),
      ],
    );
  }

  Widget _buildHistoryCard() {
    final records = _historyRecords();
    if (records.isEmpty) {
      return _buildMessageCard(
        icon: Icons.history_outlined,
        title: 'Prediction History',
        message: 'No prediction history yet',
        color: Colors.grey,
      );
    }

    return _buildSectionCard(
      title: 'Latest Prediction History',
      icon: Icons.history_outlined,
      children: records.map(_buildHistoryRecord).toList(),
    );
  }

  Widget _buildHistoryRecord(Map<String, dynamic> record) {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 10),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.background,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.grey.shade300),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text(
            _formatValue(record['timestamp']),
            style: const TextStyle(
              fontWeight: FontWeight.w800,
              color: AppColors.textPrimary,
            ),
          ),
          const SizedBox(height: 8),
          Wrap(
            spacing: 6,
            runSpacing: 6,
            children: [
              _smallChip('waste: ${_formatValue(record['energy_waste'])}'),
              _smallChip('abnormal: ${_formatValue(record['abnormal_usage'])}'),
              _smallChip(
                'type: ${_formatValue(_pick(record, ['recommendation_type', 'recommendationType']))}',
              ),
              _smallChip(
                'score: ${_formatValue(_pick(record, ['efficiency_score', 'efficiencyScore']))}',
              ),
              _smallChip(
                'energy: ${_formatValue(_pick(record, ['next_hour_energy', 'next_hour_energy_kWh', 'next_hour_energy_kwh']))}',
              ),
              _smallChip(
                'cost: ${_formatValue(_pick(record, ['next_hour_cost', 'next_hour_cost_BHD', 'next_hour_cost_bhd']))}',
              ),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            _formatValue(record['explanation']),
            style: const TextStyle(
              fontSize: 13,
              height: 1.3,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildSectionCard({
    required String title,
    required IconData icon,
    required List<Widget> children,
  }) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: AppColors.primary),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    title,
                    style: const TextStyle(
                      fontSize: 16,
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                    ),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 12),
            ...children,
          ],
        ),
      ),
    );
  }

  Widget _buildMessageCard({
    required IconData icon,
    required String title,
    required String message,
    required Color color,
  }) {
    return Card(
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Row(
          children: [
            Icon(icon, color: color),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: const TextStyle(
                      fontWeight: FontWeight.w800,
                      color: AppColors.textPrimary,
                    ),
                  ),
                  const SizedBox(height: 3),
                  Text(
                    message,
                    style: const TextStyle(color: AppColors.textSecondary),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildKeyValue(String label, dynamic value) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 8),
      child: Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          SizedBox(
            width: 150,
            child: Text(
              label,
              style: const TextStyle(
                fontSize: 12,
                fontWeight: FontWeight.w700,
                color: AppColors.textSecondary,
              ),
            ),
          ),
          Expanded(
            child: Text(
              _formatValue(value),
              style: const TextStyle(
                fontSize: 13,
                height: 1.25,
                color: AppColors.textPrimary,
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildComparisonRow<T>({
    required String label,
    required dynamic expected,
    required dynamic actual,
    required T? expectedValue,
    required T? actualValue,
  }) {
    final status = _comparisonStatus(expectedValue, actualValue);
    final color = _comparisonColor(status);

    return Padding(
      padding: const EdgeInsets.only(bottom: 10),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(
                child: Text(
                  label,
                  style: const TextStyle(
                    fontWeight: FontWeight.w800,
                    color: AppColors.textPrimary,
                  ),
                ),
              ),
              Chip(
                label: Text(status),
                visualDensity: VisualDensity.compact,
                backgroundColor: color.withValues(alpha: 0.14),
                side: BorderSide(color: color.withValues(alpha: 0.35)),
                labelStyle: TextStyle(
                  color: color,
                  fontWeight: FontWeight.w800,
                  fontSize: 12,
                ),
              ),
            ],
          ),
          Text(
            'Expected: ${_formatValue(expected)}',
            style: const TextStyle(
              fontSize: 12,
              color: AppColors.textSecondary,
            ),
          ),
          Text(
            'Actual: ${_formatValue(actual)}',
            style: const TextStyle(
              fontSize: 12,
              color: AppColors.textSecondary,
            ),
          ),
        ],
      ),
    );
  }

  Widget _smallChip(String label) {
    return Chip(
      label: Text(label),
      visualDensity: VisualDensity.compact,
      backgroundColor: AppColors.primary.withValues(alpha: 0.08),
      side: BorderSide(color: AppColors.primary.withValues(alpha: 0.16)),
      labelStyle: const TextStyle(fontSize: 11, color: AppColors.primaryDark),
    );
  }

  List<Map<String, dynamic>> _historyRecords() {
    final records = _history.entries
        .map((entry) => {'_key': entry.key, ..._asMap(entry.value)})
        .where((record) => record.length > 1)
        .toList();

    records.sort((a, b) {
      final bTime = _sortTimestamp(b);
      final aTime = _sortTimestamp(a);
      return bTime.compareTo(aTime);
    });

    return records.take(10).toList();
  }

  int _sortTimestamp(Map<String, dynamic> record) {
    final raw = _pick(record, ['timestamp', 'updated_at', 'created_at']);
    if (raw is int) {
      return raw;
    }
    if (raw is num) {
      return raw.toInt();
    }
    if (raw is String) {
      final asInt = int.tryParse(raw);
      if (asInt != null) {
        return asInt;
      }
      return DateTime.tryParse(raw)?.millisecondsSinceEpoch ?? 0;
    }
    return 0;
  }

  String _comparisonStatus(dynamic expected, dynamic actual) {
    if (expected == null || actual == null) {
      return 'Not available';
    }
    return expected == actual ? 'Match' : 'Different';
  }

  Color _comparisonColor(String status) {
    switch (status) {
      case 'Match':
        return AppColors.energySafe;
      case 'Different':
        return AppColors.energyDanger;
      default:
        return Colors.grey;
    }
  }

  String _formatValue(dynamic value) {
    if (value == null) {
      return 'Not available';
    }
    if (value is DateTime) {
      return DateFormat('MMM d, yyyy HH:mm:ss').format(value);
    }
    if (value is num || value is bool) {
      return value.toString();
    }
    if (value is Map) {
      return value.entries
          .map((entry) => '${entry.key}: ${_formatValue(entry.value)}')
          .join(', ');
    }
    if (value is List) {
      return value.map(_formatValue).join(', ');
    }
    final text = value.toString().trim();
    return text.isEmpty ? 'Not available' : text;
  }

  String? _normalizeText(dynamic value) {
    if (value == null) {
      return null;
    }
    final text = value.toString().trim().toLowerCase();
    return text.isEmpty ? null : text;
  }

  bool? _asNullableBool(dynamic value) {
    if (value == null) {
      return null;
    }
    if (value is bool) {
      return value;
    }
    if (value is num) {
      return value != 0;
    }
    if (value is String) {
      final normalized = value.trim().toLowerCase();
      if (normalized == 'true' ||
          normalized == '1' ||
          normalized == 'yes' ||
          normalized == 'abnormal' ||
          normalized == 'detected') {
        return true;
      }
      if (normalized == 'false' ||
          normalized == '0' ||
          normalized == 'no' ||
          normalized == 'normal' ||
          normalized == 'none' ||
          normalized == 'clear') {
        return false;
      }
    }
    return null;
  }

  dynamic _pick(Map<String, dynamic> source, List<String> keys) {
    for (final key in keys) {
      if (source.containsKey(key) && source[key] != null) {
        return source[key];
      }
    }
    return null;
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map) {
      return value.map((key, val) => MapEntry(key.toString(), val));
    }
    return const {};
  }
}
