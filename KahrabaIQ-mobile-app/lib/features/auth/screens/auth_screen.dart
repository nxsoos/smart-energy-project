import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../shared/services/auth_service.dart';
import '../widgets/auth_form_widgets.dart';

/// Premium KahrabaIQ authentication screen.
class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen>
    with SingleTickerProviderStateMixin {
  static const _pendingEmailKey = 'kahrabaiq.pending_confirmation_email';

  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final AuthService _authService = AuthService();
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _verificationCodeController =
      TextEditingController();
  final FocusNode _nameFocusNode = FocusNode();
  final FocusNode _emailFocusNode = FocusNode();
  final FocusNode _passwordFocusNode = FocusNode();
  final FocusNode _verificationCodeFocusNode = FocusNode();
  late final AnimationController _logoController;
  AuthMode _mode = AuthMode.login;
  bool _isBusy = false;
  String? _message;
  String? _pendingVerificationEmail;
  String? _pendingVerificationPassword;

  @override
  void initState() {
    super.initState();
    _logoController = AnimationController(
      vsync: this,
      duration: const Duration(seconds: 8),
    )..repeat();
    _restorePendingConfirmation();
  }

  @override
  void dispose() {
    _logoController.dispose();
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _verificationCodeController.dispose();
    _nameFocusNode.dispose();
    _emailFocusNode.dispose();
    _passwordFocusNode.dispose();
    _verificationCodeFocusNode.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isSignup = _mode == AuthMode.signup;
    final isVerifying = _mode == AuthMode.verifySignup;
    final title = isVerifying ? 'Verify your email' : 'Welcome to KahrabaIQ';
    final subtitle = isVerifying
        ? 'Enter the code sent to ${_pendingVerificationEmail ?? 'your email'}.'
        : 'AI-Powered Smart Energy Control';
    return Scaffold(
      resizeToAvoidBottomInset: true,
      body: SafeArea(
        child: Container(
          decoration: const BoxDecoration(
            gradient: RadialGradient(
              center: Alignment.topCenter,
              radius: 0.9,
              colors: [ColorTokens.accentGlow, ColorTokens.background],
            ),
          ),
          child: LayoutBuilder(
            builder: (context, constraints) {
              final bottomInset = MediaQuery.of(context).viewInsets.bottom;
              final keyboardOpen = bottomInset > 0;
              final viewportHeight = constraints.maxHeight + bottomInset;
              final compact = viewportHeight < 760;
              final topPadding = compact ? 12.0 : 16.0;
              final bottomPadding = 24.0 + bottomInset;
              final minHeight =
                  constraints.maxHeight - topPadding - bottomPadding;
              final contentMinHeight = minHeight < 0 ? 0.0 : minHeight;
              final logoGap = compact ? 8.0 : 12.0;
              final animationGap = compact ? 14.0 : 18.0;
              final titleGap = compact ? 20.0 : 24.0;
              final tabsGap = compact ? 14.0 : 18.0;
              final submitGap = compact ? 16.0 : 18.0;

              return SingleChildScrollView(
                keyboardDismissBehavior:
                    ScrollViewKeyboardDismissBehavior.onDrag,
                physics: keyboardOpen
                    ? const ClampingScrollPhysics()
                    : const NeverScrollableScrollPhysics(),
                padding: EdgeInsets.fromLTRB(
                  24,
                  topPadding,
                  24,
                  bottomPadding,
                ),
                child: ConstrainedBox(
                  constraints: BoxConstraints(minHeight: contentMinHeight),
                  child: Align(
                    alignment: Alignment.topCenter,
                    child: ConstrainedBox(
                      constraints: const BoxConstraints(maxWidth: 440),
                      child: Form(
                        key: _formKey,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.stretch,
                          children: [
                            AuthHeader(screenHeight: viewportHeight),
                            SizedBox(height: logoGap),
                            ElectricityAnimation(
                              controller: _logoController,
                              screenHeight: viewportHeight,
                            ),
                            SizedBox(height: animationGap),
                            _AuthTitle(title: title, subtitle: subtitle),
                            SizedBox(height: titleGap),
                            if (!isVerifying) ...[
                              AuthModeTabs(
                                mode: _mode,
                                onChanged: (mode) => setState(() {
                                  _mode = mode;
                                  _message = null;
                                }),
                              ),
                              SizedBox(height: tabsGap),
                            ],
                            AuthForm(
                              mode: _mode,
                              nameController: _nameController,
                              emailController: _emailController,
                              passwordController: _passwordController,
                              verificationCodeController:
                                  _verificationCodeController,
                              nameFocusNode: _nameFocusNode,
                              emailFocusNode: _emailFocusNode,
                              passwordFocusNode: _passwordFocusNode,
                              verificationCodeFocusNode:
                                  _verificationCodeFocusNode,
                              onSubmit: _submit,
                            ),
                            SizedBox(height: submitGap),
                            AuthSubmitSection(
                              message: _message,
                              isSignup: isSignup,
                              isVerifying: isVerifying,
                              isBusy: _isBusy,
                              onSubmit: _submit,
                              onResendCode: _resendVerificationCode,
                              onUseDifferentEmail: () => setState(() {
                                _mode = AuthMode.signup;
                                _message = null;
                              }),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ),
                ),
              );
            },
          ),
        ),
      ),
    );
  }

  Future<void> _submit() async {
    if (!_formKey.currentState!.validate() || _isBusy) {
      return;
    }
    setState(() {
      _isBusy = true;
      _message = null;
    });
    try {
      if (_mode == AuthMode.verifySignup) {
        final email = _pendingVerificationEmail ?? _emailController.text.trim();
        final password =
            _pendingVerificationPassword ?? _passwordController.text;
        await _authService.confirmSignUp(
          email: email,
          code: _verificationCodeController.text.trim(),
        );
        await _clearPendingConfirmation();
        if (password.isNotEmpty) {
          await _authService.signIn(email: email, password: password);
        } else {
          setState(() {
            _mode = AuthMode.login;
            _message = 'Account verified. Sign in to continue.';
          });
        }
      } else if (_mode == AuthMode.signup) {
        final email = _emailController.text.trim();
        final password = _passwordController.text;
        final result = await _authService.signUp(
          name: _nameController.text.trim(),
          email: email,
          password: password,
        );
        if (result.userConfirmed) {
          await _clearPendingConfirmation();
          await _authService.signIn(email: email, password: password);
        } else {
          await _savePendingConfirmation(email);
          setState(() {
            _mode = AuthMode.verifySignup;
            _pendingVerificationEmail = email;
            _pendingVerificationPassword = password;
            _verificationCodeController.clear();
            _message = 'Enter the verification code sent to your email.';
          });
        }
      } else {
        await _authService.signIn(
          email: _emailController.text.trim(),
          password: _passwordController.text,
        );
      }
    } catch (error) {
      setState(() => _message = _friendlyAuthError(error));
    } finally {
      if (mounted) {
        setState(() => _isBusy = false);
      }
    }
  }

  Future<void> _resendVerificationCode() async {
    final email = _pendingVerificationEmail ?? _emailController.text.trim();
    if (email.isEmpty || _isBusy) {
      return;
    }
    setState(() {
      _isBusy = true;
      _message = null;
    });
    try {
      await _authService.resendSignUpCode(email);
      await _savePendingConfirmation(email);
      setState(() => _message = 'A new verification code was sent.');
    } catch (error) {
      setState(() => _message = _friendlyAuthError(error));
    } finally {
      if (mounted) {
        setState(() => _isBusy = false);
      }
    }
  }

  String _friendlyAuthError(Object error) {
    if (error is CognitoUserConfirmationNecessaryException) {
      final email = _emailController.text.trim();
      if (email.isNotEmpty) {
        _openVerification(email, password: _passwordController.text);
        _savePendingConfirmation(email);
      }
      return 'Enter the verification code sent to your email.';
    }
    if (error is CognitoClientException) {
      final code = (error.code ?? '').toLowerCase();
      final message = (error.message ?? '').toLowerCase();
      final email = _emailController.text.trim();
      if (email.isNotEmpty &&
          (code.contains('usernameexist') ||
              message.contains('already exists') ||
              code.contains('usernotconfirmed') ||
              message.contains('not confirmed'))) {
        _openVerification(email, password: _passwordController.text);
        _savePendingConfirmation(email);
        if (code.contains('usernameexist') ||
            message.contains('already exists')) {
          _authService.resendSignUpCode(email).catchError((_) {});
          return 'This account already exists but still needs verification. Enter the code or tap Resend code.';
        }
        return 'This account is not verified yet. Enter the code or tap Resend code.';
      }
      if (code.contains('codemismatch')) {
        return 'That verification code is not correct. Check the code and try again.';
      }
      if (code.contains('expiredcode')) {
        return 'That verification code expired. Tap Resend code to get a new one.';
      }
      if (code.contains('limitexceeded')) {
        return 'Too many attempts. Wait a bit, then try again.';
      }
      return error.message ?? 'Authentication failed: ${error.code}';
    }
    return 'Authentication failed. Check your credentials and try again.';
  }

  Future<void> _restorePendingConfirmation() async {
    final prefs = await SharedPreferences.getInstance();
    final email = prefs.getString(_pendingEmailKey);
    if (!mounted || email == null || email.isEmpty) {
      return;
    }
    setState(() {
      _emailController.text = email;
      _openVerification(email);
      _message = 'Finish verifying your email, or tap Resend code.';
    });
  }

  void _openVerification(String email, {String? password}) {
    _pendingVerificationEmail = email.trim().toLowerCase();
    _pendingVerificationPassword = password;
    _verificationCodeController.clear();
    _mode = AuthMode.verifySignup;
  }

  Future<void> _savePendingConfirmation(String email) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_pendingEmailKey, email.trim().toLowerCase());
  }

  Future<void> _clearPendingConfirmation() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_pendingEmailKey);
  }
}

class _AuthTitle extends StatelessWidget {
  const _AuthTitle({required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      children: [
        Text(title, style: AppTextStyles.h1, textAlign: TextAlign.center),
        const SizedBox(height: 8),
        Text(
          subtitle,
          style: AppTextStyles.body.copyWith(color: ColorTokens.textSecondary),
          textAlign: TextAlign.center,
        ),
      ],
    );
  }
}

class AuthForm extends StatelessWidget {
  const AuthForm({
    super.key,
    required this.mode,
    required this.nameController,
    required this.emailController,
    required this.passwordController,
    required this.verificationCodeController,
    required this.nameFocusNode,
    required this.emailFocusNode,
    required this.passwordFocusNode,
    required this.verificationCodeFocusNode,
    required this.onSubmit,
  });

  final AuthMode mode;
  final TextEditingController nameController;
  final TextEditingController emailController;
  final TextEditingController passwordController;
  final TextEditingController verificationCodeController;
  final FocusNode nameFocusNode;
  final FocusNode emailFocusNode;
  final FocusNode passwordFocusNode;
  final FocusNode verificationCodeFocusNode;
  final VoidCallback onSubmit;

  @override
  Widget build(BuildContext context) {
    final isSignup = mode == AuthMode.signup;
    final isVerifying = mode == AuthMode.verifySignup;
    return AutofillGroup(
      child: AnimatedSize(
        duration: const Duration(milliseconds: 220),
        curve: Curves.easeOutCubic,
        alignment: Alignment.topCenter,
        child: Column(
          key: ValueKey<AuthMode>(mode),
          crossAxisAlignment: CrossAxisAlignment.stretch,
          children: [
            if (isVerifying)
              AuthField(
                controller: verificationCodeController,
                focusNode: verificationCodeFocusNode,
                label: 'Verification code',
                icon: Icons.verified_user_outlined,
                keyboardType: TextInputType.number,
                textInputAction: TextInputAction.done,
                onFieldSubmitted: (_) => onSubmit(),
              )
            else ...[
              AnimatedSwitcher(
                duration: const Duration(milliseconds: 220),
                switchInCurve: Curves.easeOutCubic,
                switchOutCurve: Curves.easeInCubic,
                transitionBuilder: (child, animation) => SizeTransition(
                  sizeFactor: animation,
                  axisAlignment: -1,
                  child: FadeTransition(opacity: animation, child: child),
                ),
                child: isSignup
                    ? Padding(
                        key: const ValueKey('name-field'),
                        padding: const EdgeInsets.only(bottom: 12),
                        child: AuthField(
                          controller: nameController,
                          focusNode: nameFocusNode,
                          label: 'Name',
                          icon: Icons.person_outline,
                          textInputAction: TextInputAction.next,
                          autofillHints: const [AutofillHints.name],
                          onFieldSubmitted: (_) =>
                              emailFocusNode.requestFocus(),
                        ),
                      )
                    : const SizedBox.shrink(key: ValueKey('no-name-field')),
              ),
              AuthField(
                controller: emailController,
                focusNode: emailFocusNode,
                label: 'Email',
                icon: Icons.email_outlined,
                keyboardType: TextInputType.emailAddress,
                textInputAction: TextInputAction.next,
                autofillHints: const [
                  AutofillHints.email,
                  AutofillHints.username,
                ],
                onFieldSubmitted: (_) => passwordFocusNode.requestFocus(),
              ),
              const SizedBox(height: 12),
              AuthField(
                controller: passwordController,
                focusNode: passwordFocusNode,
                label: 'Password',
                icon: Icons.lock_outline,
                obscureText: true,
                textInputAction: TextInputAction.done,
                autofillHints: isSignup
                    ? const [AutofillHints.newPassword]
                    : const [AutofillHints.password],
                onFieldSubmitted: (_) => onSubmit(),
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class AuthSubmitSection extends StatelessWidget {
  const AuthSubmitSection({
    super.key,
    required this.message,
    required this.isSignup,
    required this.isVerifying,
    required this.isBusy,
    required this.onSubmit,
    required this.onResendCode,
    required this.onUseDifferentEmail,
  });

  final String? message;
  final bool isSignup;
  final bool isVerifying;
  final bool isBusy;
  final VoidCallback onSubmit;
  final VoidCallback onResendCode;
  final VoidCallback onUseDifferentEmail;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        if (message != null) ...[
          Text(
            message!,
            style: AppTextStyles.caption.copyWith(color: ColorTokens.warning),
            textAlign: TextAlign.center,
          ),
          const SizedBox(height: 14),
        ],
        AuthGradientButton(
          label: isVerifying
              ? 'Verify account'
              : isSignup
              ? 'Create account'
              : 'Sign in',
          isBusy: isBusy,
          onPressed: onSubmit,
        ),
        if (isVerifying) ...[
          const SizedBox(height: 12),
          TextButton(
            onPressed: isBusy ? null : onResendCode,
            child: const Text('Resend code'),
          ),
          TextButton(
            onPressed: isBusy ? null : onUseDifferentEmail,
            child: const Text('Use a different email'),
          ),
        ],
      ],
    );
  }
}
