import 'package:flutter/material.dart';
import 'package:google_fonts/google_fonts.dart';

import 'color_tokens.dart';

/// Premium KahrabaIQ typography scale.
class AppTextStyles {
  const AppTextStyles._();

  static TextStyle get h1 => GoogleFonts.inter(
    fontSize: 28,
    fontWeight: FontWeight.w800,
    letterSpacing: -0.5,
    color: ColorTokens.textPrimary,
  );

  static TextStyle get h2 => GoogleFonts.inter(
    fontSize: 22,
    fontWeight: FontWeight.w800,
    letterSpacing: -0.4,
    color: ColorTokens.textPrimary,
  );

  static TextStyle get h3 => GoogleFonts.inter(
    fontSize: 18,
    fontWeight: FontWeight.w700,
    letterSpacing: -0.2,
    color: ColorTokens.textPrimary,
  );

  static TextStyle get body => GoogleFonts.inter(
    fontSize: 14,
    fontWeight: FontWeight.w400,
    color: ColorTokens.textPrimary,
  );

  static TextStyle get bodyMedium => GoogleFonts.inter(
    fontSize: 14,
    fontWeight: FontWeight.w600,
    color: ColorTokens.textPrimary,
  );

  static TextStyle get caption => GoogleFonts.inter(
    fontSize: 12,
    fontWeight: FontWeight.w500,
    color: ColorTokens.textSecondary,
  );

  static TextStyle get mono => GoogleFonts.jetBrainsMono(
    fontSize: 16,
    fontWeight: FontWeight.w700,
    color: ColorTokens.textPrimary,
  );

  static TextTheme get textTheme => TextTheme(
    displayLarge: h1,
    headlineMedium: h2,
    titleLarge: h3,
    bodyMedium: body,
    labelMedium: caption,
  );
}
