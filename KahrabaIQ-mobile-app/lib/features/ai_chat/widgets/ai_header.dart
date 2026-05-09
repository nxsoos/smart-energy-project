import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';

/// Animated AI assistant header.
class AiHeader extends StatelessWidget {
  const AiHeader({super.key});

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 44,
          height: 44,
          decoration: const BoxDecoration(
            shape: BoxShape.circle,
            gradient: LinearGradient(
              colors: [ColorTokens.primary, ColorTokens.accent],
            ),
          ),
          child: const Icon(
            Icons.smart_toy_outlined,
            color: ColorTokens.textPrimary,
          ),
        ),
        const SizedBox(width: 12),
        Expanded(child: Text('KahrabaIQ AI', style: AppTextStyles.h2)),
        const Icon(Icons.circle, color: ColorTokens.success, size: 10),
        const SizedBox(width: 6),
        Text(
          'Online',
          style: AppTextStyles.caption.copyWith(color: ColorTokens.success),
        ),
      ],
    );
  }
}
