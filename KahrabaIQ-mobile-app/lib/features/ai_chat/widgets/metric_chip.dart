import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';

/// Inline metric chip for AI messages.
class MetricChip extends StatelessWidget {
  const MetricChip({super.key, required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 5),
      decoration: BoxDecoration(
        color: ColorTokens.primaryGlow,
        borderRadius: BorderRadius.circular(8),
      ),
      child: Text(
        label,
        style: AppTextStyles.mono.copyWith(
          fontSize: 12,
          color: ColorTokens.primary,
        ),
      ),
    );
  }
}
