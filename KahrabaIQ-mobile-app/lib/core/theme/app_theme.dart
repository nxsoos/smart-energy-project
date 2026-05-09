import 'package:flutter/material.dart';

import 'app_text_styles.dart';
import 'color_tokens.dart';

/// Global KahrabaIQ dark theme.
class AppTheme {
  const AppTheme._();

  static ThemeData get dark => ThemeData(
    brightness: Brightness.dark,
    useMaterial3: true,
    scaffoldBackgroundColor: ColorTokens.background,
    colorScheme: const ColorScheme.dark(
      primary: ColorTokens.primary,
      secondary: ColorTokens.accent,
      surface: ColorTokens.surface,
      error: ColorTokens.danger,
    ),
    textTheme: AppTextStyles.textTheme,
    cardTheme: CardThemeData(
      color: ColorTokens.surface,
      elevation: 0,
      margin: EdgeInsets.zero,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
    ),
    inputDecorationTheme: InputDecorationTheme(
      filled: true,
      fillColor: ColorTokens.surfaceElevated,
      labelStyle: AppTextStyles.caption,
      hintStyle: AppTextStyles.caption,
      prefixIconColor: ColorTokens.textSecondary,
      border: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: ColorTokens.border),
      ),
      enabledBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: ColorTokens.border),
      ),
      focusedBorder: OutlineInputBorder(
        borderRadius: BorderRadius.circular(12),
        borderSide: const BorderSide(color: ColorTokens.primary, width: 1.5),
      ),
    ),
  );
}
