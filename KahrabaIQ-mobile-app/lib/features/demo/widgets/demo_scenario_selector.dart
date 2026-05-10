import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../demo_scenarios.dart';

class DemoScenarioSelector extends StatelessWidget {
  const DemoScenarioSelector({
    super.key,
    required this.scenarios,
    required this.selectedScenario,
    required this.isGeneratingAi,
    required this.onSelect,
    required this.onReturnToLive,
  });

  final List<DemoScenarioData> scenarios;
  final DemoScenarioData? selectedScenario;
  final bool isGeneratingAi;
  final ValueChanged<DemoScenarioData> onSelect;
  final VoidCallback onReturnToLive;

  @override
  Widget build(BuildContext context) {
    final isActive = selectedScenario != null;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ColorTokens.surfaceElevated,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(
          color: isActive ? ColorTokens.warning : ColorTokens.border,
        ),
        boxShadow: const [BoxShadow(color: ColorTokens.shadow, blurRadius: 18)],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Container(
                width: 38,
                height: 38,
                decoration: BoxDecoration(
                  color: ColorTokens.primary.withValues(alpha: 0.15),
                  borderRadius: BorderRadius.circular(12),
                ),
                child: const Icon(
                  Icons.science_outlined,
                  color: ColorTokens.primary,
                ),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        Text('Demo Scenarios', style: AppTextStyles.h3),
                        if (isActive) ...[
                          const SizedBox(width: 8),
                          const _DemoBadge(),
                        ],
                      ],
                    ),
                    const SizedBox(height: 2),
                    Text(
                      'Test AI behavior using simulated home conditions.',
                      style: AppTextStyles.caption,
                    ),
                  ],
                ),
              ),
            ],
          ),
          const SizedBox(height: 14),
          SizedBox(
            height: 42,
            child: ListView.separated(
              scrollDirection: Axis.horizontal,
              itemCount: scenarios.length,
              separatorBuilder: (context, index) => const SizedBox(width: 8),
              itemBuilder: (context, index) {
                final scenario = scenarios[index];
                final selected = scenario.id == selectedScenario?.id;
                return ChoiceChip(
                  selected: selected,
                  label: Text(scenario.name),
                  onSelected: (_) => onSelect(scenario),
                  selectedColor: ColorTokens.primary.withValues(alpha: 0.22),
                  backgroundColor: ColorTokens.surface,
                  labelStyle: AppTextStyles.caption.copyWith(
                    color: selected
                        ? ColorTokens.primary
                        : ColorTokens.textSecondary,
                  ),
                  side: BorderSide(
                    color: selected ? ColorTokens.primary : ColorTokens.border,
                  ),
                );
              },
            ),
          ),
          if (selectedScenario != null) ...[
            const SizedBox(height: 12),
            Text(selectedScenario!.description, style: AppTextStyles.caption),
            if (isGeneratingAi) ...[
              const SizedBox(height: 10),
              Row(
                children: [
                  const SizedBox(
                    width: 16,
                    height: 16,
                    child: CircularProgressIndicator(strokeWidth: 2),
                  ),
                  const SizedBox(width: 10),
                  Text(
                    'Generating AI insight...',
                    style: AppTextStyles.caption.copyWith(
                      color: ColorTokens.primary,
                    ),
                  ),
                ],
              ),
            ],
            const SizedBox(height: 12),
            Row(
              children: [
                Expanded(
                  child: FilledButton.icon(
                    onPressed: () => onSelect(selectedScenario!),
                    icon: const Icon(Icons.play_arrow),
                    label: const Text('Preview Scenario'),
                  ),
                ),
                const SizedBox(width: 10),
                OutlinedButton.icon(
                  onPressed: onReturnToLive,
                  icon: const Icon(Icons.sensors),
                  label: const Text('Live Data'),
                ),
              ],
            ),
          ],
        ],
      ),
    );
  }
}

class _DemoBadge extends StatelessWidget {
  const _DemoBadge();

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
      decoration: BoxDecoration(
        color: ColorTokens.warning.withValues(alpha: 0.16),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: ColorTokens.warning.withValues(alpha: 0.45)),
      ),
      child: Text(
        'Demo Mode',
        style: AppTextStyles.caption.copyWith(color: ColorTokens.warning),
      ),
    );
  }
}
