import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:flutter/material.dart';

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
  final GlobalKey<FormState> _formKey = GlobalKey<FormState>();
  final AuthService _authService = AuthService();
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _verificationCodeController =
      TextEditingController();
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
  }

  @override
  void dispose() {
    _logoController.dispose();
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _verificationCodeController.dispose();
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
      body: SafeArea(
        child: Container(
          decoration: const BoxDecoration(
            gradient: RadialGradient(
              center: Alignment.topCenter,
              radius: 0.9,
              colors: [ColorTokens.accentGlow, ColorTokens.background],
            ),
          ),
          child: Center(
            child: SingleChildScrollView(
              padding: const EdgeInsets.all(24),
              child: ConstrainedBox(
                constraints: const BoxConstraints(maxWidth: 440),
                child: Form(
                  key: _formKey,
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      AuthAnimatedLogo(controller: _logoController),
                      const SizedBox(height: 24),
                      Text(
                        title,
                        style: AppTextStyles.h1,
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        subtitle,
                        style: AppTextStyles.body.copyWith(
                          color: ColorTokens.textSecondary,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 28),
                      if (!isVerifying) ...[
                        AuthModeTabs(
                          mode: _mode,
                          onChanged: (mode) => setState(() {
                            _mode = mode;
                            _message = null;
                          }),
                        ),
                        const SizedBox(height: 18),
                        if (isSignup) ...[
                          AuthField(
                            controller: _nameController,
                            label: 'Name',
                            icon: Icons.person_outline,
                          ),
                          const SizedBox(height: 12),
                        ],
                        AuthField(
                          controller: _emailController,
                          label: 'Email',
                          icon: Icons.email_outlined,
                          keyboardType: TextInputType.emailAddress,
                        ),
                        const SizedBox(height: 12),
                        AuthField(
                          controller: _passwordController,
                          label: 'Password',
                          icon: Icons.lock_outline,
                          obscureText: true,
                        ),
                      ] else ...[
                        AuthField(
                          controller: _verificationCodeController,
                          label: 'Verification code',
                          icon: Icons.verified_user_outlined,
                          keyboardType: TextInputType.number,
                        ),
                      ],
                      if (_message != null) ...[
                        const SizedBox(height: 14),
                        Text(
                          _message!,
                          style: AppTextStyles.caption.copyWith(
                            color: ColorTokens.warning,
                          ),
                          textAlign: TextAlign.center,
                        ),
                      ],
                      const SizedBox(height: 18),
                      AuthGradientButton(
                        label: isVerifying
                            ? 'Verify account'
                            : isSignup
                            ? 'Create account'
                            : 'Sign in',
                        isBusy: _isBusy,
                        onPressed: _submit,
                      ),
                      if (isVerifying) ...[
                        const SizedBox(height: 12),
                        TextButton(
                          onPressed: _isBusy ? null : _resendVerificationCode,
                          child: const Text('Resend code'),
                        ),
                        TextButton(
                          onPressed: _isBusy
                              ? null
                              : () => setState(() {
                                  _mode = AuthMode.signup;
                                  _message = null;
                                }),
                          child: const Text('Use a different email'),
                        ),
                      ],
                    ],
                  ),
                ),
              ),
            ),
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
          await _authService.signIn(email: email, password: password);
        } else {
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
        _pendingVerificationEmail = email;
        _pendingVerificationPassword = _passwordController.text;
        _verificationCodeController.clear();
        _mode = AuthMode.verifySignup;
      }
      return 'Enter the verification code sent to your email.';
    }
    if (error is CognitoClientException) {
      return error.message ?? 'Authentication failed: ${error.code}';
    }
    return 'Authentication failed. Check your credentials and try again.';
  }
}
