import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';

/// Timeline row for recent sensor events.
class SensorEventTile extends StatelessWidget {
  const SensorEventTile({
    super.key,
    required this.title,
    required this.time,
    required this.isHealthy,
  });

  final String title;
  final String time;
  final bool isHealthy;

  @override
  Widget build(BuildContext context) {
    final color = isHealthy ? ColorTokens.success : ColorTokens.warning;
    return Row(
      children: [
        Column(
          children: [
            Container(
              width: 10,
              height: 10,
              decoration: BoxDecoration(color: color, shape: BoxShape.circle),
            ),
            Container(width: 1, height: 38, color: ColorTokens.border),
          ],
        ),
        const SizedBox(width: 12),
        Expanded(child: Text(title, style: AppTextStyles.bodyMedium)),
        Text(time, style: AppTextStyles.caption),
      ],
    );
  }
}
