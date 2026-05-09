import 'package:flutter/material.dart';

import '../../../core/theme/color_tokens.dart';

/// Floating AI chat input bar.
class ChatInputBar extends StatelessWidget {
  const ChatInputBar({
    super.key,
    required this.controller,
    required this.onSend,
  });

  final TextEditingController controller;
  final VoidCallback onSend;

  @override
  Widget build(BuildContext context) {
    return ValueListenableBuilder<TextEditingValue>(
      valueListenable: controller,
      builder: (context, value, _) {
        final hasText = value.text.trim().isNotEmpty;
        return Container(
          padding: const EdgeInsets.all(10),
          decoration: BoxDecoration(
            color: ColorTokens.surface,
            borderRadius: BorderRadius.circular(18),
            border: Border.all(
              color: hasText ? ColorTokens.primary : ColorTokens.border,
            ),
            boxShadow: hasText
                ? const [
                    BoxShadow(color: ColorTokens.primaryGlow, blurRadius: 20),
                  ]
                : null,
          ),
          child: Row(
            children: [
              IconButton(
                tooltip: 'Voice input',
                onPressed: () {},
                icon: const Icon(
                  Icons.mic_none,
                  color: ColorTokens.textSecondary,
                ),
              ),
              Expanded(
                child: TextField(
                  controller: controller,
                  decoration: const InputDecoration(
                    hintText: 'Ask your home...',
                    border: InputBorder.none,
                    enabledBorder: InputBorder.none,
                    focusedBorder: InputBorder.none,
                  ),
                ),
              ),
              IconButton(
                tooltip: 'Send message',
                onPressed: hasText ? onSend : null,
                icon: Icon(
                  Icons.arrow_upward,
                  color: hasText ? ColorTokens.primary : ColorTokens.textMuted,
                ),
              ),
            ],
          ),
        );
      },
    );
  }
}
