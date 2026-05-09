import 'package:flutter/material.dart';
import 'package:shimmer/shimmer.dart';

import '../theme/app_text_styles.dart';
import '../theme/color_tokens.dart';

/// Reusable shimmer block for premium loading states.
class AppShimmer extends StatelessWidget {
  const AppShimmer({
    super.key,
    required this.height,
    this.width,
    this.radius = 16,
  });

  final double height;
  final double? width;
  final double radius;

  @override
  Widget build(BuildContext context) {
    return Shimmer.fromColors(
      baseColor: ColorTokens.surface,
      highlightColor: ColorTokens.surfaceElevated,
      child: Container(
        width: width ?? double.infinity,
        height: height,
        decoration: BoxDecoration(
          color: ColorTokens.surface,
          borderRadius: BorderRadius.circular(radius),
        ),
      ),
    );
  }
}

/// Empty state with icon and helpful copy.
class AppEmptyState extends StatelessWidget {
  const AppEmptyState({
    super.key,
    required this.icon,
    required this.title,
    required this.message,
  });

  final IconData icon;
  final String title;
  final String message;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, color: ColorTokens.primary, size: 42),
            const SizedBox(height: 14),
            Text(title, style: AppTextStyles.h3, textAlign: TextAlign.center),
            const SizedBox(height: 8),
            Text(
              message,
              style: AppTextStyles.caption,
              textAlign: TextAlign.center,
            ),
          ],
        ),
      ),
    );
  }
}

/// Error state with retry action.
class AppErrorState extends StatelessWidget {
  const AppErrorState({
    super.key,
    required this.message,
    required this.onRetry,
  });

  final String message;
  final VoidCallback onRetry;

  @override
  Widget build(BuildContext context) {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(
              Icons.error_outline,
              color: ColorTokens.danger,
              size: 42,
            ),
            const SizedBox(height: 14),
            Text('Something went offline', style: AppTextStyles.h3),
            const SizedBox(height: 8),
            Text(
              message,
              style: AppTextStyles.caption,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 18),
            OutlinedButton.icon(
              onPressed: onRetry,
              icon: const Icon(Icons.refresh),
              label: const Text('Retry'),
            ),
          ],
        ),
      ),
    );
  }
}
