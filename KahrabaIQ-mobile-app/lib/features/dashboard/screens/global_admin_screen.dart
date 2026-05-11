import 'package:flutter/material.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../shared/services/kahrabaiq_api_service.dart';

class GlobalAdminScreen extends StatefulWidget {
  const GlobalAdminScreen({super.key});

  @override
  State<GlobalAdminScreen> createState() => _GlobalAdminScreenState();
}

class _GlobalAdminScreenState extends State<GlobalAdminScreen> {
  final KahrabaIqApiService _api = KahrabaIqApiService();
  List<PlatformAdminHome> _homes = const [];
  PlatformAdminHomeDetail? _selectedDetail;
  bool _loading = true;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadHomes();
  }

  Future<void> _loadHomes() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final homes = await _api.fetchPlatformAdminHomes();
      if (!mounted) return;
      setState(() {
        _homes = homes;
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _error = 'Could not load homes: $error';
        _loading = false;
      });
    }
  }

  Future<void> _selectHome(PlatformAdminHome home) async {
    setState(() {
      _selectedDetail = null;
      _error = null;
    });
    try {
      final detail = await _api.fetchPlatformAdminHomeDetail(
        homeId: home.homeId,
      );
      if (!mounted) return;
      setState(() => _selectedDetail = detail);
    } catch (error) {
      if (!mounted) return;
      setState(() => _error = 'Could not load home detail: $error');
    }
  }

  Future<void> _removeMember(HomeMember member) async {
    final detail = _selectedDetail;
    if (detail == null) return;
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Remove member?'),
        content: Text('Remove ${member.displayName} from ${detail.home.name}?'),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Remove'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      await _api.removePlatformAdminHomeMember(
        homeId: detail.home.homeId,
        uid: member.uid,
      );
      await _selectHome(detail.home);
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(const SnackBar(content: Text('Member removed.')));
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Could not remove member: $error')),
      );
    }
  }

  Future<void> _deleteHome(PlatformAdminHome home) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        title: const Text('Delete home?'),
        content: Text(
          'This permanently deletes ${home.name}, removes its members, and returns its Pi to pairing mode when online.',
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(context, false),
            child: const Text('Cancel'),
          ),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: ColorTokens.danger),
            onPressed: () => Navigator.pop(context, true),
            child: const Text('Delete Home'),
          ),
        ],
      ),
    );
    if (confirmed != true) return;
    try {
      final message = await _api.deletePlatformAdminHome(homeId: home.homeId);
      await _loadHomes();
      if (!mounted) return;
      setState(() => _selectedDetail = null);
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text(message)));
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(
        context,
      ).showSnackBar(SnackBar(content: Text('Could not delete home: $error')));
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(title: const Text('Global Admin')),
      body: RefreshIndicator(
        onRefresh: _loadHomes,
        child: ListView(
          padding: const EdgeInsets.fromLTRB(20, 18, 20, 32),
          children: [
            Text('Platform Control', style: AppTextStyles.h1),
            const SizedBox(height: 8),
            Text(
              'Manage every home, member, and Pi pairing state.',
              style: AppTextStyles.body.copyWith(
                color: ColorTokens.textSecondary,
              ),
            ),
            const SizedBox(height: 18),
            if (_error != null) _AdminNotice(message: _error!, danger: true),
            if (_loading)
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 48),
                child: Center(child: CircularProgressIndicator()),
              )
            else if (_homes.isEmpty)
              const _AdminNotice(message: 'No homes found.')
            else
              ..._homes.map(
                (home) => _HomeAdminCard(
                  home: home,
                  selected: _selectedDetail?.home.homeId == home.homeId,
                  onOpen: () => _selectHome(home),
                  onDelete: () => _deleteHome(home),
                ),
              ),
            if (_selectedDetail != null) ...[
              const SizedBox(height: 18),
              _HomeDetailCard(
                detail: _selectedDetail!,
                onRemoveMember: _removeMember,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

class _HomeAdminCard extends StatelessWidget {
  const _HomeAdminCard({
    required this.home,
    required this.selected,
    required this.onOpen,
    required this.onDelete,
  });

  final PlatformAdminHome home;
  final bool selected;
  final VoidCallback onOpen;
  final VoidCallback onDelete;

  @override
  Widget build(BuildContext context) {
    return Container(
      margin: const EdgeInsets.only(bottom: 12),
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: selected
            ? ColorTokens.primary.withValues(alpha: 0.12)
            : ColorTokens.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(
          color: selected ? ColorTokens.primary : ColorTokens.border,
        ),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Expanded(child: Text(home.name, style: AppTextStyles.h3)),
              _StatusPill(label: home.status),
            ],
          ),
          const SizedBox(height: 8),
          Text(
            home.homeId,
            style: AppTextStyles.caption.copyWith(
              color: ColorTokens.textSecondary,
            ),
          ),
          const SizedBox(height: 10),
          Text(
            'Pi: ${home.piId ?? 'none'}  |  Members: ${home.memberCount}',
            style: AppTextStyles.caption,
          ),
          const SizedBox(height: 12),
          Row(
            children: [
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: onOpen,
                  icon: const Icon(Icons.visibility),
                  label: const Text('Details'),
                ),
              ),
              const SizedBox(width: 10),
              Expanded(
                child: OutlinedButton.icon(
                  onPressed: onDelete,
                  icon: const Icon(Icons.delete_outline),
                  label: const Text('Delete'),
                ),
              ),
            ],
          ),
        ],
      ),
    );
  }
}

class _HomeDetailCard extends StatelessWidget {
  const _HomeDetailCard({required this.detail, required this.onRemoveMember});

  final PlatformAdminHomeDetail detail;
  final ValueChanged<HomeMember> onRemoveMember;

  @override
  Widget build(BuildContext context) {
    final piStatus = detail.pi.isEmpty
        ? 'No Pi linked'
        : '${detail.pi['pi_id'] ?? detail.home.piId} | ${detail.pi['status'] ?? 'unknown'}';
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ColorTokens.surfaceElevated,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: ColorTokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Home Detail', style: AppTextStyles.h2),
          const SizedBox(height: 8),
          Text(
            piStatus,
            style: AppTextStyles.caption.copyWith(
              color: ColorTokens.textSecondary,
            ),
          ),
          const SizedBox(height: 16),
          Text('Members', style: AppTextStyles.h3),
          const SizedBox(height: 8),
          if (detail.members.isEmpty)
            Text('No members.', style: AppTextStyles.caption)
          else
            ...detail.members.map(
              (member) => ListTile(
                contentPadding: EdgeInsets.zero,
                title: Text(member.displayName),
                subtitle: Text('${member.email} | ${member.role}'),
                trailing: IconButton(
                  tooltip: 'Remove member',
                  icon: const Icon(
                    Icons.person_remove_outlined,
                    color: ColorTokens.danger,
                  ),
                  onPressed: () => onRemoveMember(member),
                ),
              ),
            ),
        ],
      ),
    );
  }
}

class _StatusPill extends StatelessWidget {
  const _StatusPill({required this.label});

  final String label;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
      decoration: BoxDecoration(
        color: ColorTokens.primary.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
      ),
      child: Text(
        label,
        style: AppTextStyles.caption.copyWith(color: ColorTokens.primary),
      ),
    );
  }
}

class _AdminNotice extends StatelessWidget {
  const _AdminNotice({required this.message, this.danger = false});

  final String message;
  final bool danger;

  @override
  Widget build(BuildContext context) {
    final color = danger ? ColorTokens.danger : ColorTokens.primary;
    return Container(
      margin: const EdgeInsets.only(bottom: 14),
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: color.withValues(alpha: 0.32)),
      ),
      child: Text(
        message,
        style: AppTextStyles.caption.copyWith(color: ColorTokens.textPrimary),
      ),
    );
  }
}
