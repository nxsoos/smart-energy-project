import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';

/// Dashboard top bar with greeting and notification state.
class DashboardHeader extends StatelessWidget {
  const DashboardHeader({
    super.key,
    required this.name,
    required this.alertCount,
    this.onNotifications,
    this.onLogout,
  });

  final String name;
  final int alertCount;
  final VoidCallback? onNotifications;
  final VoidCallback? onLogout;

  @override
  Widget build(BuildContext context) {
    return Row(
      children: [
        Container(
          width: 48,
          height: 48,
          padding: const EdgeInsets.all(7),
          decoration: BoxDecoration(
            shape: BoxShape.circle,
            color: Colors.black,
            border: Border.all(color: ColorTokens.primaryGlow),
          ),
          child: ClipOval(
            child: Image.asset(
              'assets/brand/kahrabaiq-emblem.png',
              fit: BoxFit.contain,
              filterQuality: FilterQuality.high,
            ),
          ),
        ),
        const SizedBox(width: 14),
        Expanded(
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text('Good morning, $name', style: AppTextStyles.h2),
              const SizedBox(height: 3),
              Text(
                'Your home is running intelligently',
                style: AppTextStyles.caption,
              ),
            ],
          ),
        ),
        Stack(
          clipBehavior: Clip.none,
          children: [
            IconButton(
              tooltip: 'Notifications',
              onPressed: onNotifications,
              icon: const Icon(
                Icons.notifications_none,
                color: ColorTokens.textPrimary,
              ),
            ),
            if (alertCount > 0)
              Positioned(
                right: 8,
                top: 8,
                child: Container(
                  width: 10,
                  height: 10,
                  decoration: const BoxDecoration(
                    color: ColorTokens.danger,
                    shape: BoxShape.circle,
                  ),
                ),
              ),
          ],
        ),
        if (onLogout != null) ...[
          const SizedBox(width: 2),
          IconButton(
            tooltip: 'Log out',
            onPressed: onLogout,
            icon: const Icon(Icons.logout, color: ColorTokens.textPrimary),
          ),
        ],
      ],
    );
  }
}
