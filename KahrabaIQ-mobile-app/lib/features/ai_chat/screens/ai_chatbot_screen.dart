import 'package:flutter/material.dart';

import '../../../core/config/app_config.dart';
import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../core/widgets/app_state_widgets.dart';
import '../../../shared/services/kahrabaiq_api_service.dart';
import '../widgets/ai_header.dart';
import '../widgets/chat_bubble.dart';
import '../widgets/chat_input_bar.dart';
import '../widgets/quick_action_chips.dart';

/// KahrabaIQ AI assistant backed by EC2 chat sessions and Gemini.
class AiChatbotScreen extends StatefulWidget {
  const AiChatbotScreen({
    super.key,
    this.homeId = AppConfig.defaultHomeId,
    this.homeName = 'Home 1',
    this.scenarioId,
    this.scenarioName,
    this.dashboard,
  });

  final String homeId;
  final String homeName;
  final String? scenarioId;
  final String? scenarioName;
  final DashboardData? dashboard;

  @override
  State<AiChatbotScreen> createState() => _AiChatbotScreenState();
}

class _AiChatbotScreenState extends State<AiChatbotScreen> {
  final KahrabaIqApiService _api = KahrabaIqApiService();
  final TextEditingController _controller = TextEditingController();
  final ScrollController _scrollController = ScrollController();
  List<ChatSessionSummary> _sessions = const [];
  List<ChatMessageEntry> _messages = const [];
  ChatSessionSummary? _selectedSession;
  bool _isLoading = true;
  bool _isSending = false;
  String? _error;

  bool get _isDemo => widget.scenarioId != null;
  String get _chatMode => _isDemo ? 'demo_scenario' : 'live';

  @override
  void initState() {
    super.initState();
    _loadChat();
  }

  @override
  void didUpdateWidget(covariant AiChatbotScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    if (oldWidget.homeId != widget.homeId ||
        oldWidget.scenarioId != widget.scenarioId) {
      _selectedSession = null;
      _messages = const [];
      _loadChat();
    }
  }

  @override
  void dispose() {
    _controller.dispose();
    _scrollController.dispose();
    super.dispose();
  }

  Future<void> _loadChat() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      var sessions = await _api.fetchChatSessions(
        homeId: widget.homeId,
        mode: _chatMode,
        scenarioId: widget.scenarioId,
      );
      ChatSessionSummary session;
      if (sessions.isEmpty) {
        session = await _api.createChatSession(
          homeId: widget.homeId,
          mode: _chatMode,
          scenarioId: widget.scenarioId,
          scenarioName: widget.scenarioName,
        );
        sessions = [session];
      } else {
        session = _selectedSession == null
            ? sessions.first
            : sessions.firstWhere(
                (item) => item.id == _selectedSession!.id,
                orElse: () => sessions.first,
              );
      }
      final messages = await _api.fetchChatMessages(
        homeId: widget.homeId,
        sessionId: session.id,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _sessions = sessions;
        _selectedSession = session;
        _messages = messages;
        _isLoading = false;
      });
      _scrollToBottom();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.toString().replaceFirst('Exception: ', '');
        _isLoading = false;
      });
    }
  }

  Future<void> _selectSession(ChatSessionSummary session) async {
    setState(() {
      _selectedSession = session;
      _messages = const [];
      _isLoading = true;
      _error = null;
    });
    await _loadChat();
  }

  Future<void> _newSession() async {
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      final session = await _api.createChatSession(
        homeId: widget.homeId,
        mode: _chatMode,
        scenarioId: widget.scenarioId,
        scenarioName: widget.scenarioName,
      );
      final sessions = await _api.fetchChatSessions(
        homeId: widget.homeId,
        mode: _chatMode,
        scenarioId: widget.scenarioId,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _sessions = sessions;
        _selectedSession = session;
        _messages = const [];
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.toString().replaceFirst('Exception: ', '');
        _isLoading = false;
      });
    }
  }

  Future<void> _deleteSession(ChatSessionSummary session) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete this chat?'),
        content: const Text('This will remove the chat from your history.'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Delete'),
          ),
        ],
      ),
    );
    if (confirmed != true) {
      return;
    }
    setState(() {
      _isLoading = true;
      _error = null;
    });
    try {
      await _api.deleteChatSession(
        homeId: widget.homeId,
        sessionId: session.id,
      );
      var sessions = await _api.fetchChatSessions(
        homeId: widget.homeId,
        mode: _chatMode,
        scenarioId: widget.scenarioId,
      );
      ChatSessionSummary nextSession;
      if (sessions.isEmpty) {
        nextSession = await _api.createChatSession(
          homeId: widget.homeId,
          mode: _chatMode,
          scenarioId: widget.scenarioId,
          scenarioName: widget.scenarioName,
        );
        sessions = [nextSession];
      } else {
        nextSession = sessions.first;
      }
      final messages = await _api.fetchChatMessages(
        homeId: widget.homeId,
        sessionId: nextSession.id,
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _sessions = sessions;
        _selectedSession = nextSession;
        _messages = messages;
        _isLoading = false;
      });
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _error = error.toString().replaceFirst('Exception: ', '');
        _isLoading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      body: SafeArea(
        child: Padding(
          padding: const EdgeInsets.fromLTRB(20, 24, 20, 16),
          child: Column(
            children: [
              Row(
                children: [
                  IconButton(
                    tooltip: 'Back',
                    onPressed: () => Navigator.of(context).pop(),
                    icon: const Icon(Icons.arrow_back),
                  ),
                  const Expanded(child: AiHeader()),
                  IconButton(
                    tooltip: 'New chat',
                    onPressed: _isLoading || _isSending ? null : _newSession,
                    icon: const Icon(Icons.add_comment_outlined),
                  ),
                ],
              ),
              const SizedBox(height: 12),
              _SessionBar(
                sessions: _sessions,
                selectedSession: _selectedSession,
                isDemo: _isDemo,
                scenarioName: widget.scenarioName,
                onSelect: _selectSession,
                onDelete: _deleteSession,
              ),
              const SizedBox(height: 12),
              QuickActionChips(onSelected: _sendPreset),
              const SizedBox(height: 18),
              Expanded(child: _body()),
              if (_isSending) ...[
                const SizedBox(height: 8),
                Text(
                  'Gemini is thinking...',
                  style: AppTextStyles.caption.copyWith(
                    color: ColorTokens.primary,
                  ),
                ),
              ],
              const SizedBox(height: 8),
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
      return AppErrorState(message: _error!, onRetry: _loadChat);
    }
    if (_messages.isEmpty) {
      return AppEmptyState(
        icon: Icons.chat_bubble_outline,
        title: 'No conversation yet',
        message: _isDemo
            ? 'Ask Gemini about this simulated scenario. It will not control real devices.'
            : 'Ask Gemini about live energy, monthly cost, safety, or device status.',
      );
    }
    return ListView.builder(
      controller: _scrollController,
      itemCount: _messages.length,
      itemBuilder: (context, index) {
        final message = _messages[index];
        return ChatBubble(
          text: message.content,
          isUser: message.isUser,
          metrics: const [],
        );
      },
    );
  }

  void _sendPreset(String text) {
    _controller.text = text;
    _sendMessage();
  }

  Future<void> _sendMessage() async {
    final text = _controller.text.trim();
    final session = _selectedSession;
    if (text.isEmpty || session == null || _isSending) {
      return;
    }
    _controller.clear();
    final optimistic = ChatMessageEntry(
      id: 'local_${DateTime.now().millisecondsSinceEpoch}',
      role: 'user',
      content: text,
      createdAt: DateTime.now(),
    );
    setState(() {
      _messages = [..._messages, optimistic];
      _isSending = true;
      _error = null;
    });
    _scrollToBottom();
    try {
      final result = await _api.sendChatMessage(
        homeId: widget.homeId,
        sessionId: session.id,
        message: text,
        homeName: widget.homeName,
        mode: _chatMode,
        scenarioId: widget.scenarioId,
        scenarioName: widget.scenarioName,
        context: _chatContext(),
      );
      if (!mounted) {
        return;
      }
      setState(() {
        _selectedSession = result.session;
        _sessions = [
          result.session,
          ..._sessions.where((item) => item.id != result.session.id),
        ];
        _messages = [
          ..._messages.where((item) => item.id != optimistic.id),
          result.userMessage,
          result.assistantMessage,
        ];
        _isSending = false;
      });
      _scrollToBottom();
    } catch (error) {
      if (!mounted) {
        return;
      }
      setState(() {
        _isSending = false;
        _error = error.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (!_scrollController.hasClients) {
        return;
      }
      _scrollController.animateTo(
        _scrollController.position.maxScrollExtent,
        duration: const Duration(milliseconds: 250),
        curve: Curves.easeOut,
      );
    });
  }

  Map<String, dynamic>? _chatContext() {
    final dashboard = widget.dashboard;
    if (dashboard == null) {
      return null;
    }
    final sensorAge = DateTime.now().difference(dashboard.sensors.timestamp);
    final sensorStale = !dashboard.sensors.online ||
        dashboard.sensors.timestamp.year < 2024 ||
        sensorAge.inSeconds > 45;
    return {
      'mode': _chatMode,
      'simulation': _isDemo,
      'scenario_id': widget.scenarioId,
      'scenario_name': widget.scenarioName,
      'energy': {
        'current_power_w': dashboard.reading.power,
        'energy_today_kwh': dashboard.reading.energyToday,
        'cost_today_bhd': dashboard.reading.costToday,
        'month_kwh': dashboard.reading.energyMonth,
        'month_cost_bhd': dashboard.reading.costMonth,
        'month_data_available': dashboard.reading.monthDataAvailable,
        'month_source': dashboard.reading.monthSource,
      },
      'sensors': {
        'online': dashboard.sensors.online && !sensorStale,
        'stale': sensorStale,
        'status_label': sensorStale ? 'offline' : 'online',
        'last_seen_iso': dashboard.sensors.timestamp.toIso8601String(),
        'last_seen_ms': dashboard.sensors.timestamp.millisecondsSinceEpoch,
        'last_seen_age_seconds': sensorAge.inSeconds,
        'temperature': dashboard.sensors.temperature,
        'humidity': dashboard.sensors.humidity,
        'motion': dashboard.sensors.isOccupied,
        'smoke_status': dashboard.sensors.smokeStatus,
        'noise_status': dashboard.sensors.noiseStatus,
        'light_status': dashboard.sensors.lightStatus,
        'aqi': dashboard.sensors.aqi,
      },
      'hub_status': dashboard.hubStatus,
      'devices': [
        for (final device in dashboard.devices)
          {
            'id': device.id,
            'name': device.name,
            'online': device.online,
            'stale': device.stale,
            'status_label': device.statusLabel,
            'is_on': device.isOn,
            'power_w': device.currentPower,
            'branch': device.branch,
            'last_seen_iso': device.lastSeen?.toIso8601String(),
            'last_seen_age_seconds': device.lastSeenAgeSeconds,
          },
      ],
      'ai': dashboard.aiDashboard == null
          ? null
          : {
              'status_label': dashboard.aiDashboard!.statusLabel,
              'status_tone': dashboard.aiDashboard!.statusTone,
              'status_summary': dashboard.aiDashboard!.statusSummary,
              'action_title': dashboard.aiDashboard!.actionTitle,
              'recommendation_type': dashboard.aiDashboard!.recommendationType,
              'explanation': dashboard.aiDashboard!.explanation,
              'energy_waste': dashboard.aiDashboard!.energyWaste,
              'next_hour_energy_kwh': dashboard.aiDashboard!.nextHourEnergyKwh,
              'next_hour_cost_bhd': dashboard.aiDashboard!.nextHourCostBhd,
              'source': dashboard.aiDashboard!.source,
            },
      'alerts': [for (final alert in dashboard.alerts) alert.toJson()],
      'notifications': [
        for (final item in dashboard.aiNotifications)
          {
            'id': item.id,
            'severity': item.severity,
            'category': item.category,
            'title': item.title,
            'message': item.message,
            'recommendation_type': item.recommendationType,
            'confidence': item.confidence,
          },
      ],
      'suggestions': [
        for (final item in dashboard.actionSuggestions)
          {
            'id': item.id,
            'device_name': item.deviceName,
            'device_id': item.deviceId,
            'suggested_command': item.suggestedCommand,
            'reason': item.reason,
            'status': item.status,
          },
      ],
    };
  }
}

class _SessionBar extends StatelessWidget {
  const _SessionBar({
    required this.sessions,
    required this.selectedSession,
    required this.isDemo,
    required this.scenarioName,
    required this.onSelect,
    required this.onDelete,
  });

  final List<ChatSessionSummary> sessions;
  final ChatSessionSummary? selectedSession;
  final bool isDemo;
  final String? scenarioName;
  final ValueChanged<ChatSessionSummary> onSelect;
  final ValueChanged<ChatSessionSummary> onDelete;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
      decoration: BoxDecoration(
        color: ColorTokens.surfaceElevated,
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: ColorTokens.border),
      ),
      child: Row(
        children: [
          Icon(
            isDemo ? Icons.science_outlined : Icons.sensors,
            color: isDemo ? ColorTokens.warning : ColorTokens.primary,
          ),
          const SizedBox(width: 10),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  selectedSession?.title ?? 'New Chat',
                  style: AppTextStyles.bodyMedium,
                  overflow: TextOverflow.ellipsis,
                ),
                Text(
                  isDemo
                      ? 'Demo scenario: ${scenarioName ?? 'Simulated data'}'
                      : 'Live data context',
                  style: AppTextStyles.caption,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ),
          if (sessions.isNotEmpty)
            PopupMenuButton<ChatSessionSummary>(
              tooltip: 'Chat history',
              icon: const Icon(Icons.history),
              onSelected: onSelect,
              itemBuilder: (context) => [
                for (final session in sessions)
                  PopupMenuItem(
                    value: session,
                    child: Row(
                      children: [
                        Expanded(
                          child: Text(
                            session.title,
                            overflow: TextOverflow.ellipsis,
                          ),
                        ),
                        IconButton(
                          tooltip: 'Delete chat',
                          icon: const Icon(Icons.delete_outline, size: 18),
                          onPressed: () {
                            Navigator.of(context).pop();
                            onDelete(session);
                          },
                        ),
                      ],
                    ),
                  ),
              ],
            ),
        ],
      ),
    );
  }
}
