import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';

/// AI recommendation banner for energy optimization.
class AiInsightsBanner extends StatelessWidget {
  const AiInsightsBanner({super.key, required this.text, required this.onTap});

  final String text;
  final VoidCallback onTap;

  @override
  Widget build(BuildContext context) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(18),
      child: Container(
        padding: const EdgeInsets.all(18),
        decoration: BoxDecoration(
          gradient: const LinearGradient(
            colors: [ColorTokens.primary, ColorTokens.accent],
          ),
          borderRadius: BorderRadius.circular(18),
          boxShadow: const [
            BoxShadow(color: ColorTokens.accentGlow, blurRadius: 24),
          ],
        ),
        child: Row(
          children: [
            const Icon(
              Icons.smart_toy_outlined,
              color: ColorTokens.textPrimary,
              size: 30,
            ),
            const SizedBox(width: 14),
            Expanded(child: Text(text, style: AppTextStyles.bodyMedium)),
            const Icon(Icons.arrow_forward, color: ColorTokens.textPrimary),
          ],
        ),
      ),
    );
  }
}
