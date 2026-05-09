import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import 'metric_chip.dart';

/// Premium user/AI chat bubble.
class ChatBubble extends StatelessWidget {
  const ChatBubble({
    super.key,
    required this.text,
    required this.isUser,
    this.metrics = const [],
  });

  final String text;
  final bool isUser;
  final List<String> metrics;

  @override
  Widget build(BuildContext context) {
    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.78,
        ),
        margin: const EdgeInsets.only(bottom: 12),
        padding: const EdgeInsets.all(14),
        decoration: BoxDecoration(
          color: isUser
              ? ColorTokens.primary
              : ColorTokens.surface.withValues(alpha: 0.76),
          borderRadius: BorderRadius.circular(18),
          border: isUser
              ? null
              : Border.all(color: ColorTokens.accent.withValues(alpha: 0.35)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(
              text,
              style: AppTextStyles.body.copyWith(
                color: isUser
                    ? ColorTokens.background
                    : ColorTokens.textPrimary,
              ),
            ),
            if (metrics.isNotEmpty) ...[
              const SizedBox(height: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  for (final metric in metrics) MetricChip(label: metric),
                ],
              ),
            ],
          ],
        ),
      ),
    );
  }
}
