import 'package:flutter/material.dart';
import 'package:amazon_cognito_identity_dart_2/cognito.dart';
import 'package:dio/dio.dart';

import '../../../shared/services/auth_service.dart';
import '../../../core/utils/constants.dart';

enum _AuthMode { login, signup, confirmSignup, forgotPassword, confirmReset }

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
  final _codeController = TextEditingController();
  final _newPasswordController = TextEditingController();
  _AuthMode _mode = _AuthMode.login;
  bool _isBusy = false;
  String? _message;

  @override
  void dispose() {
    _nameController.dispose();
    _emailController.dispose();
    _passwordController.dispose();
    _codeController.dispose();
    _newPasswordController.dispose();
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
        final result = await _authService.signUp(
          name: _nameController.text,
          email: _emailController.text,
          password: _passwordController.text,
        );
        if (!result.userConfirmed) {
          setState(() {
            _mode = _AuthMode.confirmSignup;
            _message = 'Enter the verification code sent to your email.';
          });
          return;
        }
        await _authService.signIn(
          email: _emailController.text,
          password: _passwordController.text,
        );
      } else if (_mode == _AuthMode.confirmSignup) {
        await _authService.confirmSignUp(
          email: _emailController.text,
          code: _codeController.text,
        );
        await _authService.signIn(
          email: _emailController.text,
          password: _passwordController.text,
        );
      } else {
        if (_mode == _AuthMode.forgotPassword) {
          await _authService.sendPasswordReset(_emailController.text);
          setState(() {
            _mode = _AuthMode.confirmReset;
            _message = 'Enter the reset code sent to your email.';
          });
        } else {
          await _authService.confirmPasswordReset(
            email: _emailController.text,
            code: _codeController.text,
            newPassword: _newPasswordController.text,
          );
          setState(() {
            _mode = _AuthMode.login;
            _message = 'Password updated. Log in with your new password.';
          });
        }
      }
    } catch (error) {
      debugPrint('Auth error: $error');
      if (error is CognitoUserConfirmationNecessaryException) {
        setState(() {
          _mode = _AuthMode.confirmSignup;
          _message = 'Enter the verification code sent to your email.';
        });
        return;
      }
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

  Future<void> _resendVerificationCode() async {
    final email = _emailController.text.trim();
    if (!email.contains('@') || _isBusy) {
      setState(() {
        _message = 'Enter a valid email first.';
      });
      return;
    }
    setState(() {
      _isBusy = true;
      _message = null;
    });
    try {
      await _authService.resendSignUpCode(email);
      setState(() {
        _message = 'Verification code sent again. Check inbox and spam.';
      });
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
    if (error is CognitoClientException) {
      switch (error.code) {
        case 'NotAuthorizedException':
        case 'UserNotFoundException':
          return 'Email or password is incorrect.';
        case 'UsernameExistsException':
          return 'An account already exists for this email. Try logging in.';
        case 'InvalidPasswordException':
          return 'Choose a stronger password.';
        case 'CodeMismatchException':
          return 'The verification code is incorrect.';
        case 'ExpiredCodeException':
          return 'The verification code expired. Request a new one.';
        case 'NetworkError':
          return 'Network error. Check the internet connection and try again.';
      }
      return error.message ?? 'AWS Cognito authentication failed: ${error.code}.';
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
        text.contains('user-not-found') ||
        text.contains('NotAuthorizedException')) {
      return 'Email or password is incorrect.';
    }
    if (text.contains('email-already-in-use')) {
      return 'An account already exists for this email. Try logging in.';
    }
    if (text.contains('weak-password')) {
      return 'Choose a stronger password.';
    }
    return 'Authentication failed: $text';
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
    final isConfirmSignup = _mode == _AuthMode.confirmSignup;
    final isForgotPassword = _mode == _AuthMode.forgotPassword;
    final isConfirmReset = _mode == _AuthMode.confirmReset;
    final title = isSignup
        ? 'Create account'
        : isConfirmSignup
            ? 'Verify email'
        : isForgotPassword
            ? 'Reset password'
            : isConfirmReset
                ? 'Confirm reset'
            : 'Welcome back';
    final actionLabel = isSignup
        ? 'Sign Up'
        : isConfirmSignup
            ? 'Verify Email'
        : isForgotPassword
            ? 'Send Reset Email'
            : isConfirmReset
                ? 'Update Password'
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
                        if (isConfirmSignup || isConfirmReset) ...[
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _codeController,
                            keyboardType: TextInputType.number,
                            textInputAction: isConfirmReset
                                ? TextInputAction.next
                                : TextInputAction.done,
                            decoration: const InputDecoration(
                              labelText: 'Verification code',
                              prefixIcon: Icon(Icons.verified_outlined),
                            ),
                            validator: (value) {
                              if ((value ?? '').trim().isEmpty) {
                                return 'Code is required.';
                              }
                              return null;
                            },
                            onFieldSubmitted: (_) {
                              if (!isConfirmReset) {
                                _submit();
                              }
                            },
                          ),
                        ],
                        if (!isForgotPassword &&
                            !isConfirmSignup &&
                            !isConfirmReset) ...[
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
                        if (isConfirmReset) ...[
                          const SizedBox(height: 12),
                          TextFormField(
                            controller: _newPasswordController,
                            obscureText: true,
                            textInputAction: TextInputAction.done,
                            decoration: const InputDecoration(
                              labelText: 'New password',
                              prefixIcon: Icon(Icons.lock_reset),
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
                                    _mode = isSignup || isConfirmSignup
                                        ? _AuthMode.login
                                        : _AuthMode.signup;
                                  });
                                },
                          child: Text(isSignup || isConfirmSignup
                              ? 'Already have an account? Log in'
                              : 'Create a new account'),
                        ),
                        if (isConfirmSignup)
                          TextButton(
                            onPressed:
                                _isBusy ? null : _resendVerificationCode,
                            child: const Text('Resend verification code'),
                          ),
                        TextButton(
                          onPressed: _isBusy
                              ? null
                              : () {
                                  setState(() {
                                    _message = null;
                                    _mode = isForgotPassword || isConfirmReset
                                        ? _AuthMode.login
                                        : _AuthMode.forgotPassword;
                                  });
                                },
                          child: Text(
                            isForgotPassword || isConfirmReset
                                ? 'Back to login'
                                : 'Forgot password?',
                          ),
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
