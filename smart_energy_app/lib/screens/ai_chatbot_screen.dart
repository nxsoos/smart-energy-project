import 'package:dio/dio.dart';
import 'package:flutter/material.dart';

import '../config/app_config.dart';
import '../utils/constants.dart';

class AiChatbotScreen extends StatefulWidget {
  const AiChatbotScreen({
    super.key,
    this.homeId = AppConfig.firebaseHomeId,
    this.homeName = 'Home 1',
    this.scenarioId,
    this.scenarioName,
  });

  final String homeId;
  final String homeName;
  final String? scenarioId;
  final String? scenarioName;

  @override
  State<AiChatbotScreen> createState() => _AiChatbotScreenState();
}

class _AiChatbotScreenState extends State<AiChatbotScreen> {
  final Dio _dio = Dio(
    BaseOptions(
      baseUrl: AppConfig.aiServiceUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 45),
      headers: {'Content-Type': 'application/json'},
    ),
  );

  final TextEditingController _messageController = TextEditingController();
  final List<_ChatMessage> _messages = [];
  bool _isSending = false;
  String? _error;

  static const List<String> _starterQuestions = [
    'Why is my energy usage high?',
    'Why is energy waste detected?',
    'Why is the efficiency score low?',
    'What should I turn off?',
    'What happened today?',
  ];

  @override
  void dispose() {
    _messageController.dispose();
    super.dispose();
  }

  Future<void> _sendMessage([String? presetMessage]) async {
    final message = (presetMessage ?? _messageController.text).trim();
    if (message.isEmpty || _isSending) {
      return;
    }

    setState(() {
      _messages.add(_ChatMessage(text: message, isUser: true));
      _messageController.clear();
      _isSending = true;
      _error = null;
    });

    try {
      final response = await _dio.post(
        '/chat/${widget.homeId}',
        data: {
          'message': message,
          'home_id': widget.homeId,
          'home_name': widget.homeName,
          'conversation_history': _messages
              .take(_messages.length - 1)
              .toList()
              .map(
                (chatMessage) => {
                  'role': chatMessage.isUser ? 'user' : 'assistant',
                  'message': chatMessage.text,
                },
              )
              .toList(),
          if (widget.scenarioId?.isNotEmpty ?? false)
            'scenario_id': widget.scenarioId,
          if (widget.scenarioName?.isNotEmpty ?? false)
            'scenario_name': widget.scenarioName,
        },
      );

      final data = _asMap(response.data);
      final answer = data['answer']?.toString().trim();

      setState(() {
        _messages.add(
          _ChatMessage(
            text: answer?.isNotEmpty == true
                ? answer!
                : 'No chatbot answer was returned.',
            isUser: false,
          ),
        );
      });
    } on DioException catch (error) {
      final responseData = error.response?.data;
      final detail = _asMap(responseData)['detail'] ?? responseData;
      setState(() {
        _error = detail?.toString() ?? 'Chatbot request failed.';
      });
    } catch (error) {
      setState(() {
        _error = 'Chatbot request failed: $error';
      });
    } finally {
      if (mounted) {
        setState(() {
          _isSending = false;
        });
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(
          widget.homeId == 'home_test'
              ? 'AI Chatbot Test'
              : 'Smart Energy Chatbot',
          style: const TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
          ),
        ),
        backgroundColor: AppColors.primary,
        iconTheme: const IconThemeData(color: Colors.white),
      ),
      body: Column(
        children: [
          Expanded(
            child: ListView.builder(
              keyboardDismissBehavior: ScrollViewKeyboardDismissBehavior.onDrag,
              padding: const EdgeInsets.fromLTRB(16, 16, 16, 24),
              itemCount: _messages.length + 1,
              itemBuilder: (context, index) {
                if (index == 0) {
                  return Column(
                    crossAxisAlignment: CrossAxisAlignment.stretch,
                    children: [
                      _buildHeader(),
                      if (_messages.isEmpty) _buildStarterQuestions(),
                    ],
                  );
                }

                return _buildMessageBubble(_messages[index - 1]);
              },
            ),
          ),
          if (_error != null) _buildErrorBanner(),
          if (_isSending) const LinearProgressIndicator(minHeight: 2),
          _buildInputBar(),
        ],
      ),
    );
  }

  Widget _buildHeader() {
    return Container(
      width: double.infinity,
      margin: EdgeInsets.zero,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: AppColors.primary.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(12),
        border: Border.all(color: AppColors.primary.withValues(alpha: 0.18)),
      ),
      child: Row(
        children: [
          const Icon(Icons.auto_awesome, color: AppColors.primary),
          const SizedBox(width: 10),
          Expanded(
            child: Text(
              _chatContextLabel(),
              style: const TextStyle(
                height: 1.3,
                color: AppColors.textPrimary,
                fontWeight: FontWeight.w600,
              ),
            ),
          ),
        ],
      ),
    );
  }

  String _chatContextLabel() {
    final scenario = widget.scenarioName ?? widget.scenarioId;
    if (widget.homeId == 'home_test' && scenario?.isNotEmpty == true) {
      return 'Ask about AI predictions, energy waste, cost, efficiency, and recommendations for ${widget.homeName} ($scenario).';
    }
    return 'Ask about AI predictions, energy waste, cost, efficiency, and recommendations for ${widget.homeName}.';
  }

  Widget _buildStarterQuestions() {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.only(top: 12),
      child: Wrap(
        spacing: 8,
        runSpacing: 8,
        children: _starterQuestions.map((question) {
          return ActionChip(
            label: Text(question, maxLines: 1, overflow: TextOverflow.ellipsis),
            avatar: const Icon(Icons.question_answer_outlined, size: 16),
            onPressed: _isSending ? null : () => _sendMessage(question),
          );
        }).toList(),
      ),
    );
  }

  Widget _buildMessageBubble(_ChatMessage message) {
    final isUser = message.isUser;
    final color = isUser
        ? AppColors.primary.withValues(alpha: 0.12)
        : Colors.white;
    final borderColor = isUser
        ? AppColors.primary.withValues(alpha: 0.28)
        : Colors.grey.shade300;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 320),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: borderColor),
        ),
        child: Text(
          message.text,
          style: const TextStyle(height: 1.35, color: AppColors.textPrimary),
        ),
      ),
    );
  }

  Widget _buildErrorBanner() {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 0, 16, 8),
      padding: const EdgeInsets.all(12),
      decoration: BoxDecoration(
        color: AppColors.energyDanger.withValues(alpha: 0.08),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: AppColors.energyDanger.withValues(alpha: 0.25),
        ),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: AppColors.energyDanger),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              _error!,
              style: const TextStyle(color: AppColors.energyDanger),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildInputBar() {
    return SafeArea(
      top: false,
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Row(
          children: [
            Expanded(
              child: TextField(
                controller: _messageController,
                minLines: 1,
                maxLines: 4,
                textInputAction: TextInputAction.send,
                decoration: InputDecoration(
                  hintText: 'Ask the AI...',
                  filled: true,
                  fillColor: Colors.white,
                  border: OutlineInputBorder(
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                onSubmitted: (_) => _sendMessage(),
              ),
            ),
            const SizedBox(width: 8),
            IconButton.filled(
              tooltip: 'Send',
              onPressed: _isSending ? null : _sendMessage,
              icon: const Icon(Icons.send),
            ),
          ],
        ),
      ),
    );
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map) {
      return value.map((key, val) => MapEntry(key.toString(), val));
    }
    return const {};
  }
}

class _ChatMessage {
  const _ChatMessage({required this.text, required this.isUser});

  final String text;
  final bool isUser;
}
