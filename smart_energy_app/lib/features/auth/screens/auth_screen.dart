import 'package:flutter/material.dart';
import 'package:dio/dio.dart';
import 'package:firebase_auth/firebase_auth.dart';

import '../../../shared/services/auth_service.dart';
import '../../../core/utils/constants.dart';

enum _AuthMode { login, signup, forgotPassword }

class AuthScreen extends StatefulWidget {
  const AuthScreen({super.key});

  @override
  State<AuthScreen> createState() => _AuthScreenState();
}

class _AuthScreenState extends State<AuthScreen> {
  final _formKey = GlobalKey<FormState>();
  final _authService = AuthService();
  final _nameController = TextEditingController();
  final _emailController = TextEditingController();
  final _passwordController = TextEditingController();
  _AuthMode _mode = _AuthMode.login;
  bool _isBusy = false;
  String? _message;

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    super.dispose();
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
      if (_mode == _AuthMode.login) {
        await _authService.signIn(
          email: _emailController.text,
          password: _passwordController.text,
        );
      } else if (_mode == _AuthMode.signup) {
        await _authService.signUp(
          name: _nameController.text,
          email: _emailController.text,
          password: _passwordController.text,
        );
      } else {
        await _authService.sendPasswordReset(_emailController.text);
        setState(() {
          _message = 'Password reset email sent.';
        });
      }
    } catch (error) {
      setState(() {
        _message = _friendlyAuthError(error);
      });
    } finally {
      if (mounted) {
        setState(() {
          _isBusy = false;
        });
      }
    }
  }

  String _friendlyAuthError(Object error) {
    if (error is FirebaseAuthException) {
      switch (error.code) {
        case 'invalid-credential':
        case 'wrong-password':
        case 'user-not-found':
          return 'Email or password is incorrect.';
        case 'email-already-in-use':
          return 'An account already exists for this email. Try logging in.';
        case 'weak-password':
          return 'Choose a stronger password.';
        case 'operation-not-allowed':
          return 'Email/password sign-in is not enabled in Firebase Authentication.';
        case 'network-request-failed':
          return 'Network error. Check the internet connection and try again.';
      }
      return error.message ?? 'Firebase authentication failed: ${error.code}.';
    }

    if (error is DioException) {
      final statusCode = error.response?.statusCode;
      final detail = error.response?.data;
      return 'Account was created, but profile setup failed'
          '${statusCode == null ? '' : ' ($statusCode)'}. '
          '${_extractDetail(detail) ?? error.message ?? 'Redeploy the API server and log in again.'}';
    }

    final text = error.toString();
    if (text.contains('invalid-credential') ||
        text.contains('wrong-password') ||
        text.contains('user-not-found')) {
      return 'Email or password is incorrect.';
    }
    if (text.contains('email-already-in-use')) {
      return 'An account already exists for this email. Try logging in.';
    }
    if (text.contains('weak-password')) {
      return 'Choose a stronger password.';
    }
    return 'Authentication failed. Please check your details and try again.';
  }

  String? _extractDetail(dynamic data) {
    if (data is Map && data['detail'] != null) {
      return data['detail'].toString();
    }
    if (data == null) {
      return null;
    }
    return data.toString();
  }

  @override
  Widget build(BuildContext context) {
    final isSignup = _mode == _AuthMode.signup;
    final isForgotPassword = _mode == _AuthMode.forgotPassword;
    final title = isSignup
        ? 'Create account'
        : isForgotPassword
            ? 'Reset password'
            : 'Welcome back';
    final actionLabel = isSignup
        ? 'Sign Up'
        : isForgotPassword
            ? 'Send Reset Email'
            : 'Log In';

    return Scaffold(
      backgroundColor: AppColors.background,
      body: SafeArea(
        child: Center(
          child: SingleChildScrollView(
            padding: const EdgeInsets.all(24),
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 420),
              child: Card(
                child: Padding(
                  padding: const EdgeInsets.all(20),
                  child: Form(
                    key: _formKey,
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.stretch,
                      children: [
                        const Icon(
                          Icons.energy_savings_leaf,
                          color: AppColors.primary,
                          size: 44,
                        ),
                        const SizedBox(height: 12),
                        Text(
                          title,
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            fontSize: 24,
                            fontWeight: FontWeight.w800,
                          ),
                        ),
                        const SizedBox(height: 20),
                        if (isSignup) ...[
                          TextFormField(
                            controller: _nameController,
                            textInputAction: TextInputAction.next,
                            decoration: const InputDecoration(
                              labelText: 'Name',
                              prefixIcon: Icon(Icons.person_outline),
                            ),
                            validator: (value) =>
                                value?.trim().isEmpty == true ? 'Name is required.' : null,
                          ),
                          const SizedBox(height: 12),
                        ],
                        TextFormField(
                          controller: _emailController,
                          keyboardType: TextInputType.emailAddress,
                          textInputAction:
                              isForgotPassword ? TextInputAction.done : TextInputAction.next,
                          decoration: const InputDecoration(
                            labelText: 'Email',
                            prefixIcon: Icon(Icons.email_outlined),
                          ),
                          validator: (value) {
                            final text = value?.trim() ?? '';
                            if (!text.contains('@')) {
                              return 'Enter a valid email.';
                            }
                            return null;
                          },
                        ),
                        if (!isForgotPassword) ...[
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _passwordController,
                            obscureText: true,
                            textInputAction: TextInputAction.done,
                            decoration: const InputDecoration(
                              labelText: 'Password',
                              prefixIcon: Icon(Icons.lock_outline),
                            ),
                            validator: (value) {
                              if ((value ?? '').length < 6) {
                                return 'Password must be at least 6 characters.';
                              }
                              return null;
                            },
                            onFieldSubmitted: (_) => _submit(),
                          ),
                        ],
                        if (_message != null) ...[
                          const SizedBox(height: 12),
                          Text(
                            _message!,
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: _message!.contains('sent')
                                  ? AppColors.energySafe
                                  : AppColors.energyDanger,
                            ),
                          ),
                        ],
                        const SizedBox(height: 18),
                        ElevatedButton.icon(
                          onPressed: _isBusy ? null : _submit,
                          icon: _isBusy
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2),
                                )
                              : const Icon(Icons.login),
                          label: Text(actionLabel),
                        ),
                        const SizedBox(height: 8),
                        TextButton(
                          onPressed: _isBusy
                              ? null
                              : () {
                                  setState(() {
                                    _message = null;
                                    _mode = isSignup ? _AuthMode.login : _AuthMode.signup;
                                  });
                                },
                          child: Text(isSignup
                              ? 'Already have an account? Log in'
                              : 'Create a new account'),
                        ),
                        TextButton(
                          onPressed: _isBusy
                              ? null
                              : () {
                                  setState(() {
                                    _message = null;
                                    _mode = isForgotPassword
                                        ? _AuthMode.login
                                        : _AuthMode.forgotPassword;
                                  });
                                },
                          child: Text(isForgotPassword ? 'Back to login' : 'Forgot password?'),
                        ),
                      ],
                    ),
                  ),
                ),
              ),
            ),
          ),
        ),
      ),
    );
  }
}
