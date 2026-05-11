import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:qr_flutter/qr_flutter.dart';

import '../../../core/theme/app_text_styles.dart';
import '../../../core/theme/color_tokens.dart';
import '../../../shared/services/kahrabaiq_api_service.dart';

class HomeAdminPanelScreen extends StatefulWidget {
  const HomeAdminPanelScreen({
    super.key,
    required this.homeId,
    required this.currentUserUid,
  });

  final String homeId;
  final String currentUserUid;

  @override
  State<HomeAdminPanelScreen> createState() => _HomeAdminPanelScreenState();
}

class _HomeAdminPanelScreenState extends State<HomeAdminPanelScreen> {
  static const int _maxInvitedUsers = 3;

  final KahrabaIqApiService _api = KahrabaIqApiService();
  List<HomeMember> _members = const [];
  HomeInvite? _invite;
  String _selectedRole = 'viewer';
  int _selectedMaxUses = 1;
  bool _loading = true;
  bool _generating = false;
  String? _error;

  @override
  void initState() {
    super.initState();
    _loadMembers();
  }

  int get _invitedCount => _members
      .where((member) => member.role == 'member' || member.role == 'viewer')
      .length;

  int get _remainingSlots => (_maxInvitedUsers - _invitedCount).clamp(0, _maxInvitedUsers).toInt();

  List<int> get _maxUseOptions => List<int>.generate(_remainingSlots, (index) => index + 1);

  Future<void> _loadMembers() async {
    setState(() {
      _loading = true;
      _error = null;
    });
    try {
      final members = await _api.fetchMembers(homeId: widget.homeId);
      if (!mounted) return;
      setState(() {
        _members = members;
        _selectedMaxUses = _remainingSlots <= 0 ? 1 : _selectedMaxUses.clamp(1, _remainingSlots).toInt();
        _loading = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _loading = false;
        _error = error.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  Future<void> _generateInvite() async {
    if (_remainingSlots <= 0) return;
    setState(() {
      _generating = true;
      _error = null;
    });
    try {
      final invite = await _api.createHomeInvite(
        homeId: widget.homeId,
        role: _selectedRole,
        maxUses: _selectedMaxUses,
      );
      if (!mounted) return;
      setState(() {
        _invite = invite;
        _generating = false;
      });
    } catch (error) {
      if (!mounted) return;
      setState(() {
        _generating = false;
        _error = error.toString().replaceFirst('Exception: ', '');
      });
    }
  }

  Future<void> _removeMember(HomeMember member) async {
    final confirmed = await showDialog<bool>(
      context: context,
      builder: (context) => AlertDialog(
        backgroundColor: ColorTokens.surfaceElevated,
        title: Text('Remove ${member.displayName}?', style: AppTextStyles.h3),
        content: Text(
          'This person will lose access to this home immediately.',
          style: AppTextStyles.body,
        ),
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
      await _api.removeMember(homeId: widget.homeId, uid: member.uid);
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('${member.displayName} was removed.')),
      );
      await _loadMembers();
    } catch (error) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text('Remove failed: ${error.toString().replaceFirst('Exception: ', '')}')),
      );
    }
  }

  Future<void> _copyInvite() async {
    final payload = _invite?.qrPayload;
    if (payload == null || payload.isEmpty) return;
    await Clipboard.setData(ClipboardData(text: payload));
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      const SnackBar(content: Text('Invite code copied.')),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: ColorTokens.background,
      appBar: AppBar(
        backgroundColor: ColorTokens.background,
        foregroundColor: ColorTokens.textPrimary,
        elevation: 0,
        title: const Text('Home Admin Panel'),
      ),
      body: SafeArea(
        child: RefreshIndicator(
          color: ColorTokens.primary,
          onRefresh: _loadMembers,
          child: ListView(
            padding: const EdgeInsets.fromLTRB(20, 16, 20, 32),
            children: [
              Text('Manage People', style: AppTextStyles.h1),
              const SizedBox(height: 8),
              Text(
                'Invite up to $_maxInvitedUsers total viewers or members. Home admins are protected.',
                style: AppTextStyles.body.copyWith(color: ColorTokens.textSecondary),
              ),
              const SizedBox(height: 18),
              _SlotSummary(used: _invitedCount, total: _maxInvitedUsers),
              if (_error != null) ...[
                const SizedBox(height: 14),
                _ErrorBanner(message: _error!),
              ],
              const SizedBox(height: 22),
              _SectionHeader(title: 'People', subtitle: '${_members.length} total users'),
              const SizedBox(height: 12),
              if (_loading)
                const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()))
              else if (_members.isEmpty)
                const _EmptyCard(message: 'No people are listed yet.')
              else
                ..._members.map(
                  (member) => Padding(
                    padding: const EdgeInsets.only(bottom: 12),
                    child: _MemberCard(
                      member: member,
                      isCurrentUser: member.uid == widget.currentUserUid,
                      onRemove: member.role == 'member' || member.role == 'viewer'
                          ? () => _removeMember(member)
                          : null,
                    ),
                  ),
                ),
              const SizedBox(height: 22),
              _SectionHeader(title: 'Invite QR', subtitle: 'Choose access level and QR use limit'),
              const SizedBox(height: 12),
              _InviteBuilderCard(
                selectedRole: _selectedRole,
                selectedMaxUses: _selectedMaxUses,
                maxUseOptions: _maxUseOptions,
                remainingSlots: _remainingSlots,
                generating: _generating,
                onRoleChanged: (role) => setState(() {
                  _selectedRole = role;
                  _invite = null;
                }),
                onMaxUsesChanged: (value) => setState(() {
                  _selectedMaxUses = value;
                  _invite = null;
                }),
                onGenerate: _generateInvite,
              ),
              if (_invite != null) ...[
                const SizedBox(height: 16),
                _InviteQrCard(invite: _invite!, onCopy: _copyInvite),
              ],
            ],
          ),
        ),
      ),
    );
  }
}

class _SlotSummary extends StatelessWidget {
  const _SlotSummary({required this.used, required this.total});

  final int used;
  final int total;

  @override
  Widget build(BuildContext context) {
    final remaining = (total - used).clamp(0, total).toInt();
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ColorTokens.primaryGlow,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: ColorTokens.primary.withValues(alpha: 0.28)),
      ),
      child: Row(
        children: [
          const Icon(Icons.group_add, color: ColorTokens.primary),
          const SizedBox(width: 12),
          Expanded(
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('Available slots: $remaining / $total', style: AppTextStyles.h3),
                const SizedBox(height: 4),
                Text(
                  '$used viewer/member ${used == 1 ? 'person is' : 'people are'} already using invite slots.',
                  style: AppTextStyles.caption,
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

class _SectionHeader extends StatelessWidget {
  const _SectionHeader({required this.title, required this.subtitle});

  final String title;
  final String subtitle;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Text(title, style: AppTextStyles.h2),
        const SizedBox(height: 4),
        Text(subtitle, style: AppTextStyles.caption),
      ],
    );
  }
}

class _MemberCard extends StatelessWidget {
  const _MemberCard({
    required this.member,
    required this.isCurrentUser,
    required this.onRemove,
  });

  final HomeMember member;
  final bool isCurrentUser;
  final VoidCallback? onRemove;

  @override
  Widget build(BuildContext context) {
    final roleLabel = _roleLabel(member.role);
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ColorTokens.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: ColorTokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              CircleAvatar(
                backgroundColor: _roleColor(member.role).withValues(alpha: 0.18),
                foregroundColor: _roleColor(member.role),
                child: Text(_initial(member.displayName, member.email)),
              ),
              const SizedBox(width: 12),
              Expanded(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Text(
                      isCurrentUser ? '${member.displayName} (You)' : member.displayName,
                      style: AppTextStyles.h3,
                    ),
                    const SizedBox(height: 3),
                    Text(member.email, style: AppTextStyles.caption),
                  ],
                ),
              ),
              _RoleBadge(label: roleLabel, color: _roleColor(member.role)),
            ],
          ),
          const SizedBox(height: 12),
          Text(_permissionSummary(member.role), style: AppTextStyles.body),
          const SizedBox(height: 12),
          Row(
            children: [
              if (member.addedAt != null)
                Expanded(
                  child: Text(
                    'Joined ${_formatDate(member.addedAt!)}',
                    style: AppTextStyles.caption,
                  ),
                )
              else
                const Spacer(),
              if (onRemove == null)
                Text('Protected', style: AppTextStyles.caption.copyWith(color: ColorTokens.success))
              else
                TextButton.icon(
                  onPressed: onRemove,
                  icon: const Icon(Icons.person_remove, size: 18),
                  label: const Text('Remove'),
                  style: TextButton.styleFrom(foregroundColor: ColorTokens.danger),
                ),
            ],
          ),
        ],
      ),
    );
  }

  static String _initial(String name, String email) {
    final source = name.trim().isNotEmpty ? name.trim() : email.trim();
    return source.isEmpty ? '?' : source.characters.first.toUpperCase();
  }

  static String _roleLabel(String role) {
    if (role == 'home_admin') return 'Home Admin';
    if (role == 'member') return 'Member';
    return 'Viewer';
  }

  static Color _roleColor(String role) {
    if (role == 'home_admin') return ColorTokens.primary;
    if (role == 'member') return ColorTokens.success;
    return ColorTokens.info;
  }

  static String _permissionSummary(String role) {
    if (role == 'home_admin') return 'Full access, invite management, and device control.';
    if (role == 'member') return 'Can view the dashboard and control devices.';
    return 'Can view the dashboard only.';
  }

  static String _formatDate(DateTime date) => '${date.year}-${date.month.toString().padLeft(2, '0')}-${date.day.toString().padLeft(2, '0')}';
}

class _RoleBadge extends StatelessWidget {
  const _RoleBadge({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
      decoration: BoxDecoration(
        color: color.withValues(alpha: 0.14),
        borderRadius: BorderRadius.circular(999),
        border: Border.all(color: color.withValues(alpha: 0.32)),
      ),
      child: Text(label, style: AppTextStyles.caption.copyWith(color: color)),
    );
  }
}

class _InviteBuilderCard extends StatelessWidget {
  const _InviteBuilderCard({
    required this.selectedRole,
    required this.selectedMaxUses,
    required this.maxUseOptions,
    required this.remainingSlots,
    required this.generating,
    required this.onRoleChanged,
    required this.onMaxUsesChanged,
    required this.onGenerate,
  });

  final String selectedRole;
  final int selectedMaxUses;
  final List<int> maxUseOptions;
  final int remainingSlots;
  final bool generating;
  final ValueChanged<String> onRoleChanged;
  final ValueChanged<int> onMaxUsesChanged;
  final VoidCallback onGenerate;

  @override
  Widget build(BuildContext context) {
    final disabled = remainingSlots <= 0 || generating;
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ColorTokens.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: ColorTokens.border),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Access role', style: AppTextStyles.h3),
          const SizedBox(height: 10),
          SegmentedButton<String>(
            segments: const [
              ButtonSegment(value: 'viewer', icon: Icon(Icons.visibility), label: Text('Viewer')),
              ButtonSegment(value: 'member', icon: Icon(Icons.tune), label: Text('Member')),
            ],
            selected: {selectedRole},
            onSelectionChanged: disabled ? null : (values) => onRoleChanged(values.first),
          ),
          const SizedBox(height: 10),
          Text(
            selectedRole == 'member'
                ? 'Members can view and control devices.'
                : 'Viewers can only view the dashboard.',
            style: AppTextStyles.caption,
          ),
          const SizedBox(height: 16),
          Text('QR uses', style: AppTextStyles.h3),
          const SizedBox(height: 8),
          if (remainingSlots <= 0)
            Text('No invite slots available. Remove a viewer/member to create a new invite.', style: AppTextStyles.caption.copyWith(color: ColorTokens.warning))
          else
            DropdownButtonFormField<int>(
              initialValue: selectedMaxUses.clamp(1, remainingSlots).toInt(),
              dropdownColor: ColorTokens.surfaceElevated,
              decoration: const InputDecoration(labelText: 'Allowed uses'),
              items: maxUseOptions
                  .map((value) => DropdownMenuItem(value: value, child: Text('$value ${value == 1 ? 'person' : 'people'}')))
                  .toList(),
              onChanged: disabled ? null : (value) => value == null ? null : onMaxUsesChanged(value),
            ),
          const SizedBox(height: 16),
          FilledButton.icon(
            onPressed: disabled ? null : onGenerate,
            icon: generating
                ? const SizedBox(width: 18, height: 18, child: CircularProgressIndicator(strokeWidth: 2))
                : const Icon(Icons.qr_code_2),
            label: Text(generating ? 'Generating' : 'Generate Invite QR'),
          ),
        ],
      ),
    );
  }
}

class _InviteQrCard extends StatelessWidget {
  const _InviteQrCard({required this.invite, required this.onCopy});

  final HomeInvite invite;
  final VoidCallback onCopy;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(16),
      decoration: BoxDecoration(
        color: ColorTokens.surfaceElevated,
        borderRadius: BorderRadius.circular(20),
        border: Border.all(color: ColorTokens.primary.withValues(alpha: 0.32)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Text('Invite QR Ready', style: AppTextStyles.h2),
          const SizedBox(height: 8),
          Text(
            '${_roleLabel(invite.role)} access for up to ${invite.maxUses} ${invite.maxUses == 1 ? 'person' : 'people'}.',
            style: AppTextStyles.caption,
          ),
          const SizedBox(height: 16),
          Center(
            child: Container(
              padding: const EdgeInsets.all(14),
              decoration: BoxDecoration(color: Colors.white, borderRadius: BorderRadius.circular(18)),
              child: QrImageView(data: invite.qrPayload, size: 220, backgroundColor: Colors.white),
            ),
          ),
          const SizedBox(height: 16),
          Text('Manual invite code', style: AppTextStyles.h3),
          const SizedBox(height: 8),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: ColorTokens.background,
              borderRadius: BorderRadius.circular(14),
              border: Border.all(color: ColorTokens.border),
            ),
            child: Text(invite.qrPayload, style: AppTextStyles.caption.copyWith(color: ColorTokens.textPrimary)),
          ),
          const SizedBox(height: 12),
          OutlinedButton.icon(
            onPressed: onCopy,
            icon: const Icon(Icons.copy),
            label: const Text('Copy code'),
          ),
        ],
      ),
    );
  }

  static String _roleLabel(String role) => role == 'member' ? 'Member' : 'Viewer';
}

class _ErrorBanner extends StatelessWidget {
  const _ErrorBanner({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: ColorTokens.danger.withValues(alpha: 0.12),
        borderRadius: BorderRadius.circular(16),
        border: Border.all(color: ColorTokens.danger.withValues(alpha: 0.32)),
      ),
      child: Row(
        children: [
          const Icon(Icons.error_outline, color: ColorTokens.danger),
          const SizedBox(width: 10),
          Expanded(child: Text(message, style: AppTextStyles.caption.copyWith(color: ColorTokens.textPrimary))),
        ],
      ),
    );
  }
}

class _EmptyCard extends StatelessWidget {
  const _EmptyCard({required this.message});

  final String message;

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: const EdgeInsets.all(18),
      decoration: BoxDecoration(
        color: ColorTokens.surface,
        borderRadius: BorderRadius.circular(18),
        border: Border.all(color: ColorTokens.border),
      ),
      child: Text(message, style: AppTextStyles.caption),
    );
  }
}
