import 'package:dio/dio.dart';
import 'package:flutter/material.dart';
import 'package:intl/intl.dart';

import '../../../core/config/app_config.dart';
import '../../../shared/services/auth_service.dart';
import '../../../core/utils/constants.dart';

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
      baseUrl: AppConfig.backendApiUrl,
      connectTimeout: const Duration(seconds: 15),
      receiveTimeout: const Duration(seconds: 45),
      headers: {'Content-Type': 'application/json'},
    ),
  );

  final TextEditingController _messageController = TextEditingController();
  final List<_ChatSession> _sessions = [];
  final List<_ChatMessage> _messages = [];
  _ChatSession? _selectedSession;
  bool _isLoadingSessions = true;
  bool _isLoadingMessages = false;
  bool _isSending = false;
  String? _error;

  static const List<String> _starterQuestions = [
    'What is current power?',
    'Explain today\'s cost',
    'Why is my energy usage high?',
    'What should I turn off?',
    'What happened today?',
  ];

  @override
  void initState() {
    super.initState();
    _loadSessions();
  }

  @override
  void dispose() {
    _messageController.dispose();
    super.dispose();
  }

  Future<Map<String, String>> _authHeaders() async {
    final token = await AuthService().getIdToken();
    return token == null ? const {} : {'Authorization': 'Bearer $token'};
  }

  Future<void> _loadSessions() async {
    setState(() {
      _isLoadingSessions = true;
      _error = null;
    });

    try {
      final response = await _dio.get(
        '/api/home/${widget.homeId}/chat/sessions',
        options: Options(headers: await _authHeaders()),
      );
      final data = _asMap(response.data);
      final sessions = _asList(data['sessions'])
          .map((item) => _ChatSession.fromMap(_asMap(item)))
          .toList();
      setState(() {
        _sessions
          ..clear()
          ..addAll(sessions);
      });
    } on DioException catch (error) {
      setState(() {
        _error = _friendlyError(error);
      });
    } catch (error) {
      setState(() {
        _error = 'Could not load chat sessions: $error';
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoadingSessions = false;
        });
      }
    }
  }

  Future<void> _createSession() async {
    try {
      final response = await _dio.post(
        '/api/home/${widget.homeId}/chat/sessions',
        options: Options(headers: await _authHeaders()),
        data: {'title': 'New Chat'},
      );
      final session = _ChatSession.fromMap(_asMap(_asMap(response.data)['session']));
      setState(() {
        _sessions.insert(0, session);
      });
      await _openSession(session);
    } on DioException catch (error) {
      setState(() {
        _error = _friendlyError(error);
      });
    }
  }

  Future<void> _openSession(_ChatSession session) async {
    setState(() {
      _selectedSession = session;
      _messages.clear();
      _isLoadingMessages = true;
      _error = null;
    });

    try {
      final response = await _dio.get(
        '/api/home/${widget.homeId}/chat/sessions/${session.id}/messages',
        queryParameters: {'limit': 100},
        options: Options(headers: await _authHeaders()),
      );
      final messages = _asList(_asMap(response.data)['messages'])
          .map((item) => _ChatMessage.fromMap(_asMap(item)))
          .toList();
      setState(() {
        _messages
          ..clear()
          ..addAll(messages);
      });
    } on DioException catch (error) {
      setState(() {
        _error = _friendlyError(error);
      });
    } finally {
      if (mounted) {
        setState(() {
          _isLoadingMessages = false;
        });
      }
    }
  }

  Future<void> _sendMessage([String? presetMessage]) async {
    final session = _selectedSession;
    final message = (presetMessage ?? _messageController.text).trim();
    if (session == null || message.isEmpty || _isSending) {
      return;
    }

    final optimistic = _ChatMessage(
      id: 'local_${DateTime.now().microsecondsSinceEpoch}',
      role: 'user',
      content: message,
      createdAt: DateTime.now(),
    );

    setState(() {
      _messages.add(optimistic);
      _messageController.clear();
      _isSending = true;
      _error = null;
    });

    try {
      final response = await _dio.post(
        '/api/home/${widget.homeId}/chat/sessions/${session.id}/message',
        options: Options(headers: await _authHeaders()),
        data: {
          'message': message,
          'home_name': widget.homeName,
          if (widget.scenarioId?.isNotEmpty ?? false)
            'scenario_id': widget.scenarioId,
          if (widget.scenarioName?.isNotEmpty ?? false)
            'scenario_name': widget.scenarioName,
        },
      );
      final data = _asMap(response.data);
      final assistant = _ChatMessage.fromMap(_asMap(data['assistant_message']));
      final updatedSession = _ChatSession.fromMap(_asMap(data['session']));
      setState(() {
        _messages.add(assistant);
        _selectedSession = updatedSession;
        final index = _sessions.indexWhere((item) => item.id == updatedSession.id);
        if (index >= 0) {
          _sessions[index] = updatedSession;
          _sessions.sort((a, b) => b.updatedAt.compareTo(a.updatedAt));
        }
      });
    } on DioException catch (error) {
      setState(() {
        _error = _friendlyError(error);
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

  Future<void> _renameSelectedSession() async {
    final session = _selectedSession;
    if (session == null) {
      return;
    }
    final controller = TextEditingController(text: session.title);
    final title = await showDialog<String>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Rename Chat'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'Title'),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(context).pop(controller.text.trim()),
            child: const Text('Save'),
          ),
        ],
      ),
    );
    controller.dispose();
    if (title == null || title.isEmpty) {
      return;
    }

    try {
      final response = await _dio.patch(
        '/api/home/${widget.homeId}/chat/sessions/${session.id}',
        options: Options(headers: await _authHeaders()),
        data: {'title': title},
      );
      final updated = _ChatSession.fromMap(_asMap(_asMap(response.data)['session']));
      setState(() {
        _selectedSession = updated;
        final index = _sessions.indexWhere((item) => item.id == updated.id);
        if (index >= 0) {
          _sessions[index] = updated;
        }
      });
    } on DioException catch (error) {
      setState(() {
        _error = _friendlyError(error);
      });
    }
  }

  Future<void> _archiveSelectedSession() async {
    final session = _selectedSession;
    if (session == null) {
      return;
    }
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Archive Chat'),
        content: Text('Archive "${session.title}"?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.of(context).pop(false),
            child: const Text('Cancel'),
          ),
          ElevatedButton(
            onPressed: () => Navigator.of(context).pop(true),
            child: const Text('Archive'),
          ),
        ],
      ),
    );
    if (confirmed != true) {
      return;
    }

    try {
      await _dio.delete(
        '/api/home/${widget.homeId}/chat/sessions/${session.id}',
        options: Options(headers: await _authHeaders()),
      );
      setState(() {
        _sessions.removeWhere((item) => item.id == session.id);
        _selectedSession = null;
        _messages.clear();
      });
    } on DioException catch (error) {
      setState(() {
        _error = _friendlyError(error);
      });
    }
  }

  String _friendlyError(DioException error) {
    final status = error.response?.statusCode;
    if (status == 403) {
      return 'You do not have permission to use the AI chat.';
    }
    if (status == 404) {
      return 'Chat sessions are not available on the deployed API yet. Deploy smart-energy-api, then reopen the chat.';
    }
    final responseData = error.response?.data;
    final detail = _asMap(responseData)['detail'] ?? responseData;
    return detail?.toString() ?? 'Chatbot request failed.';
  }

  @override
  Widget build(BuildContext context) {
    final session = _selectedSession;
    return Scaffold(
      backgroundColor: AppColors.background,
      appBar: AppBar(
        title: Text(
          session?.title ?? 'KahrabaIQ Chat',
          style: const TextStyle(
            color: Colors.white,
            fontWeight: FontWeight.bold,
          ),
        ),
        backgroundColor: AppColors.primary,
        iconTheme: const IconThemeData(color: Colors.white),
        leading: session == null
            ? null
            : IconButton(
                tooltip: 'Sessions',
                onPressed: () {
                  setState(() {
                    _selectedSession = null;
                    _messages.clear();
                  });
                },
                icon: const Icon(Icons.arrow_back),
              ),
        actions: [
          if (session == null)
            IconButton(
              tooltip: 'Refresh',
              onPressed: _loadSessions,
              icon: const Icon(Icons.refresh),
            )
          else ...[
            IconButton(
              tooltip: 'Rename',
              onPressed: _renameSelectedSession,
              icon: const Icon(Icons.edit_outlined),
            ),
            IconButton(
              tooltip: 'Archive',
              onPressed: _archiveSelectedSession,
              icon: const Icon(Icons.archive_outlined),
            ),
          ],
          IconButton(
            tooltip: 'New Chat',
            onPressed: _createSession,
            icon: const Icon(Icons.add_comment_outlined),
          ),
        ],
      ),
      body: session == null ? _buildSessionsView() : _buildMessagesView(),
    );
  }

  Widget _buildSessionsView() {
    if (_isLoadingSessions) {
      return const Center(child: CircularProgressIndicator());
    }
    return Column(
      children: [
        if (_error != null) _buildErrorBanner(),
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 8),
          child: SizedBox(
            width: double.infinity,
            child: ElevatedButton.icon(
              onPressed: _createSession,
              icon: const Icon(Icons.add),
              label: const Text('New Chat'),
            ),
          ),
        ),
        Expanded(
          child: _sessions.isEmpty
              ? _buildEmptySessions()
              : ListView.separated(
                  padding: const EdgeInsets.all(16),
                  itemCount: _sessions.length,
                  separatorBuilder: (context, index) => const SizedBox(height: 10),
                  itemBuilder: (context, index) => _buildSessionTile(_sessions[index]),
                ),
        ),
      ],
    );
  }

  Widget _buildEmptySessions() {
    return Center(
      child: Padding(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            const Icon(Icons.chat_bubble_outline, size: 44, color: AppColors.primary),
            const SizedBox(height: 12),
            const Text(
              'No chat sessions yet.',
              style: TextStyle(fontWeight: FontWeight.w800),
            ),
            const SizedBox(height: 6),
            Text(
              _chatContextLabel(),
              textAlign: TextAlign.center,
              style: const TextStyle(color: AppColors.textSecondary),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildSessionTile(_ChatSession session) {
    return Card(
      child: ListTile(
        onTap: () => _openSession(session),
        leading: const CircleAvatar(
          backgroundColor: AppColors.primary,
          foregroundColor: Colors.white,
          child: Icon(Icons.auto_awesome),
        ),
        title: Text(
          session.title,
          maxLines: 1,
          overflow: TextOverflow.ellipsis,
          style: const TextStyle(fontWeight: FontWeight.w800),
        ),
        subtitle: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            if (session.preview.isNotEmpty)
              Text(
                session.preview,
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            const SizedBox(height: 4),
            Text(
              '${_formatTime(session.updatedAt)} · ${session.messageCount} messages',
              style: const TextStyle(fontSize: 12),
            ),
          ],
        ),
        trailing: const Icon(Icons.chevron_right),
      ),
    );
  }

  Widget _buildMessagesView() {
    return Column(
      children: [
        Expanded(
          child: _isLoadingMessages
              ? const Center(child: CircularProgressIndicator())
              : ListView.builder(
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
    );
  }

  Widget _buildHeader() {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.only(bottom: 12),
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
    return Padding(
      padding: const EdgeInsets.only(bottom: 12),
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
    final isUser = message.role == 'user';
    final color = isUser
        ? AppColors.primary.withValues(alpha: 0.12)
        : Colors.white;
    final borderColor = isUser
        ? AppColors.primary.withValues(alpha: 0.28)
        : Colors.grey.shade300;

    return Align(
      alignment: isUser ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: const BoxConstraints(maxWidth: 340),
        margin: const EdgeInsets.only(bottom: 10),
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: color,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: borderColor),
        ),
        child: Text(
          message.content,
          style: const TextStyle(height: 1.35, color: AppColors.textPrimary),
        ),
      ),
    );
  }

  Widget _buildErrorBanner() {
    return Container(
      width: double.infinity,
      margin: const EdgeInsets.fromLTRB(16, 8, 16, 8),
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
                enabled: !_isSending,
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

  String _formatTime(DateTime value) {
    final now = DateTime.now();
    if (now.difference(value).inHours < 24) {
      return DateFormat('h:mm a').format(value);
    }
    return DateFormat('MMM d').format(value);
  }

  Map<String, dynamic> _asMap(dynamic value) {
    if (value is Map) {
      return value.map((key, val) => MapEntry(key.toString(), val));
    }
    return const {};
  }

  List<dynamic> _asList(dynamic value) {
    if (value is List) {
      return value;
    }
    if (value is Map) {
      return value.values.toList();
    }
    return const [];
  }
}

class _ChatSession {
  const _ChatSession({
    required this.id,
    required this.title,
    required this.preview,
    required this.messageCount,
    required this.updatedAt,
  });

  final String id;
  final String title;
  final String preview;
  final int messageCount;
  final DateTime updatedAt;

  factory _ChatSession.fromMap(Map<String, dynamic> data) {
    final updatedMs = _asInt(data['updated_at_ms']);
    return _ChatSession(
      id: (data['session_id'] ?? data['id'] ?? '').toString(),
      title: (data['title'] ?? 'New Chat').toString(),
      preview: (data['last_message_preview'] ?? '').toString(),
      messageCount: _asInt(data['message_count']) ?? 0,
      updatedAt: updatedMs == null
          ? DateTime.now()
          : DateTime.fromMillisecondsSinceEpoch(updatedMs),
    );
  }
}

class _ChatMessage {
  const _ChatMessage({
    required this.id,
    required this.role,
    required this.content,
    required this.createdAt,
  });

  final String id;
  final String role;
  final String content;
  final DateTime createdAt;

  factory _ChatMessage.fromMap(Map<String, dynamic> data) {
    final createdMs = _asInt(data['created_at_ms']);
    return _ChatMessage(
      id: (data['message_id'] ?? data['id'] ?? '').toString(),
      role: (data['role'] ?? 'assistant').toString(),
      content: (data['content'] ?? data['message'] ?? '').toString(),
      createdAt: createdMs == null
          ? DateTime.now()
          : DateTime.fromMillisecondsSinceEpoch(createdMs),
    );
  }
}

int? _asInt(dynamic value) {
  if (value is int) {
    return value;
  }
  if (value is double) {
    return value.round();
  }
  return int.tryParse(value?.toString() ?? '');
}
