import 'package:flutter/material.dart';

import '../../../core/config/app_config.dart';
import '../../../core/widgets/app_state_widgets.dart';
import '../widgets/ai_header.dart';
import '../widgets/chat_bubble.dart';
import '../widgets/chat_input_bar.dart';
import '../widgets/quick_action_chips.dart';

/// Futuristic KahrabaIQ AI assistant screen.
class AiChatbotScreen extends StatefulWidget {
  const AiChatbotScreen({
    super.key,
    this.homeId = AppConfig.defaultHomeId,
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
  final TextEditingController _controller = TextEditingController();
  final List<_Message> _messages = [
    const _Message(
      text:
          'I am monitoring your home energy system. Current usage is efficient, but AC demand is rising.',
      isUser: false,
      metrics: ['23°C', '2.1 kW'],
    ),
  ];
  final bool _isLoading = false;
  String? _error;

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
          child: Column(
            children: [
              const AiHeader(),
              const SizedBox(height: 18),
              QuickActionChips(onSelected: _sendPreset),
              const SizedBox(height: 18),
              Expanded(child: _body()),
              ChatInputBar(controller: _controller, onSend: _sendMessage),
            ],
          ),
        ),
      ),
    );
  }

  Widget _body() {
    if (_isLoading) {
      return const Column(
        children: [
          AppShimmer(height: 72),
          SizedBox(height: 12),
          AppShimmer(height: 96),
        ],
      );
    }
    if (_error != null) {
      return AppErrorState(
        message: _error!,
        onRetry: () => setState(() => _error = null),
      );
    }
    if (_messages.isEmpty) {
      return const AppEmptyState(
        icon: Icons.chat_bubble_outline,
        title: 'No conversation yet',
        message: 'Ask KahrabaIQ AI about safety, cost, or device automation.',
      );
    }
    return ListView.builder(
      itemCount: _messages.length,
      itemBuilder: (context, index) {
        final message = _messages[index];
        return ChatBubble(
          text: message.text,
          isUser: message.isUser,
          metrics: message.metrics,
        );
      },
    );
  }

  void _sendPreset(String text) {
    _controller.text = text;
    _sendMessage();
  }

  void _sendMessage() {
    final text = _controller.text.trim();
    if (text.isEmpty) {
      return;
    }
    setState(() {
      _messages.add(_Message(text: text, isUser: true));
      _messages.add(
        _Message(
          text: _responseFor(text),
          isUser: false,
          metrics: const ['0.8 kWh', 'BD 0.002'],
        ),
      );
      _controller.clear();
    });
  }

  String _responseFor(String text) {
    if (text.toLowerCase().contains('safe')) {
      return 'All monitored safety signals are normal. Smoke is clear, motion is expected, and current draw is below the warning threshold.';
    }
    return 'I can reduce demand by scheduling the AC and turning off idle sockets. The projected saving is small but immediate.';
  }
}

class _Message {
  const _Message({
    required this.text,
    required this.isUser,
    this.metrics = const [],
  });

  final String text;
  final bool isUser;
  final List<String> metrics;
}
