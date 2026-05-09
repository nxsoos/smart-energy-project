import 'package:fl_chart/fl_chart.dart';
import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';

/// Sensor card with value, status badge, and sparkline.
class SensorCard extends StatelessWidget {
  const SensorCard({
    super.key,
    required this.icon,
    required this.label,
    required this.value,
    required this.unit,
    required this.isHealthy,
    required this.points,
    this.statusLabel,
    this.showChart = true,
  });

  final IconData icon;
  final String label;
  final String value;
  final String unit;
  final bool isHealthy;
  final List<double> points;
  final String? statusLabel;
  final bool showChart;

  @override
  Widget build(BuildContext context) {
    final color = isHealthy ? ColorTokens.success : ColorTokens.danger;
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: ColorTokens.surface,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.24)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, color: color),
              const Spacer(),
              _Badge(
                text: statusLabel ?? (isHealthy ? 'Normal' : 'Alert'),
                color: color,
              ),
            ],
          ),
          const Spacer(),
          Text(label, style: AppTextStyles.caption),
          const SizedBox(height: 4),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              Text(value, style: AppTextStyles.mono.copyWith(fontSize: 22)),
              const SizedBox(width: 4),
              Text(unit, style: AppTextStyles.caption),
            ],
          ),
          if (showChart) ...[
            const SizedBox(height: 12),
            SizedBox(height: 34, child: LineChart(_chartData(color))),
          ],
        ],
      ),
    );
  }

  LineChartData _chartData(Color color) {
    return LineChartData(
      gridData: const FlGridData(show: false),
      titlesData: const FlTitlesData(show: false),
      borderData: FlBorderData(show: false),
      lineBarsData: [
        LineChartBarData(
          spots: [
            for (var i = 0; i < points.length; i++)
              FlSpot(i.toDouble(), points[i]),
          ],
          isCurved: true,
          color: color,
          dotData: const FlDotData(show: false),
          belowBarData: BarAreaData(
            show: true,
            color: color.withValues(alpha: 0.12),
          ),
        ),
      ],
    );
  }
}

class _Badge extends StatelessWidget {
  const _Badge({required this.text, required this.color});

  final String text;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        text,
        style: AppTextStyles.caption.copyWith(color: color, fontSize: 10),
      ),
    );
  }
}
