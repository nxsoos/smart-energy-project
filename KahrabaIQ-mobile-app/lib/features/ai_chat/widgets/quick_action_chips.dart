import 'package:flutter/material.dart';

import '../../../core/theme/color_tokens.dart';

/// Suggested AI prompts.
class QuickActionChips extends StatelessWidget {
  const QuickActionChips({super.key, required this.onSelected});

  final ValueChanged<String> onSelected;

  @override
  Widget build(BuildContext context) {
    const actions = ['Energy report', 'Is it safe?', 'Why this AI result?'];
    return SingleChildScrollView(
      scrollDirection: Axis.horizontal,
      child: Row(
        children: [
          for (final action in actions)
            Padding(
              padding: const EdgeInsets.only(right: 8),
              child: ActionChip(
                label: Text(action),
                onPressed: () => onSelected(action),
                backgroundColor: ColorTokens.surfaceElevated,
                side: const BorderSide(color: ColorTokens.border),
              ),
            ),
        ],
      ),
    );
  }
}
