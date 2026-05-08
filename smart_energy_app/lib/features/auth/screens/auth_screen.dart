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
  late final AnimationController _logoController;
  AuthMode _mode = AuthMode.login;
  bool _isBusy = false;
  String? _message;

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
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final isSignup = _mode == AuthMode.signup;
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
                        'Welcome to KahrabaIQ',
                        style: AppTextStyles.h1,
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 8),
                      Text(
                        'AI-Powered Smart Energy Control',
                        style: AppTextStyles.body.copyWith(
                          color: ColorTokens.textSecondary,
                        ),
                        textAlign: TextAlign.center,
                      ),
                      const SizedBox(height: 28),
                      AuthModeTabs(
                        mode: _mode,
                        onChanged: (mode) => setState(() => _mode = mode),
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
                        label: isSignup ? 'Create account' : 'Sign in',
                        isBusy: _isBusy,
                        onPressed: _submit,
                      ),
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
      if (_mode == AuthMode.signup) {
        await _authService.signUp(
          name: _nameController.text.trim(),
          email: _emailController.text.trim(),
          password: _passwordController.text,
        );
        setState(
          () => _message =
              'Account created. Check your email if verification is required, then sign in.',
        );
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

  String _friendlyAuthError(Object error) {
    if (error is CognitoUserConfirmationNecessaryException) {
      return 'Confirm your email, then sign in again.';
    }
    if (error is CognitoClientException) {
      return error.message ?? 'Authentication failed: ${error.code}';
    }
    return 'Authentication failed. Check your credentials and try again.';
  }
}
