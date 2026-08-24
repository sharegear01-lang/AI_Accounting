import 'dart:async';

import 'package:flutter/material.dart';

/// HITL 人工复核确认卡（对应 web 端 ApprovalCard.vue）
///
/// 展示 interrupt 预览，用户点"同意"或"拒绝"按钮，通过 /chat 的 approve
/// 字段直接恢复被 interrupt 暂停的图。带超时倒计时：超过 expiresInSeconds
/// 秒未操作则禁用按钮（后端也会在超时后自动按拒绝取消）。
/// [cancelled] 为 true 时表示用户发新消息导致后端自动取消了该确认，
/// 卡片展示『已取消』并禁用按钮（不再可点击）。
class ApprovalCard extends StatefulWidget {
  final String threadId;
  final String preview;
  final int? expiresInSeconds;
  final bool cancelled;
  final bool disabled; // 请求在途时禁用按钮（避免与新消息请求竞态）
  final Future<void> Function(bool approved) onResolved;
  final VoidCallback onExpired; // 本地倒计时归零

  const ApprovalCard({
    super.key,
    required this.threadId,
    required this.preview,
    this.expiresInSeconds,
    this.cancelled = false,
    this.disabled = false,
    required this.onResolved,
    required this.onExpired,
  });

  @override
  State<ApprovalCard> createState() => _ApprovalCardState();
}

class _ApprovalCardState extends State<ApprovalCard> {
  bool _busy = false;
  bool _expired = false;
  late int _remaining;
  Timer? _timer;

  @override
  void initState() {
    super.initState();
    _startCountdown();
  }

  void _startCountdown() {
    _stopCountdown();
    final expires = widget.expiresInSeconds;
    _remaining = (expires != null && expires > 0) ? expires : 0;
    if (_remaining > 0) {
      _timer = Timer.periodic(const Duration(seconds: 1), (_) {
        setState(() {
          _remaining -= 1;
          if (_remaining <= 0) {
            _stopCountdown();
            _expired = true;
            widget.onExpired();
          }
        });
      });
    }
  }

  void _stopCountdown() {
    _timer?.cancel();
    _timer = null;
  }

  @override
  void dispose() {
    _stopCountdown();
    super.dispose();
  }

  @override
  void didUpdateWidget(covariant ApprovalCard oldWidget) {
    super.didUpdateWidget(oldWidget);
    // 卡片被标记取消（用户发新消息）→ 停止倒计时
    if (!oldWidget.cancelled && widget.cancelled) {
      _stopCountdown();
    }
  }

  Future<void> _handle(bool approved) async {
    if (_busy || _expired || widget.cancelled || widget.disabled) return;
    setState(() => _busy = true);
    await widget.onResolved(approved);
    if (mounted) {
      _stopCountdown();
      setState(() => _busy = false);
    }
  }

  @override
  Widget build(BuildContext context) {
    return Container(
      width: double.infinity,
      padding: const EdgeInsets.all(14),
      decoration: BoxDecoration(
        color: const Color(0xFFFFF7E6),
        border: Border.all(color: const Color(0xFFE6A23C)),
        borderRadius: BorderRadius.circular(10),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(
                widget.cancelled
                    ? Icons.info_outline
                    : Icons.warning_amber_rounded,
                color: widget.cancelled
                    ? const Color(0xFF909399)
                    : const Color(0xFFE6A23C),
                size: 18,
              ),
              const SizedBox(width: 6),
              Expanded(
                child: Text(
                  widget.cancelled ? '该确认已被取消' : '需要您确认一项操作',
                  style: TextStyle(
                    color: widget.cancelled
                        ? const Color(0xFF909399)
                        : const Color(0xFFB88230),
                    fontWeight: FontWeight.w600,
                    fontSize: 14,
                  ),
                ),
              ),
              if (widget.cancelled)
                const Text(
                  '已取消',
                  style: TextStyle(fontSize: 12, color: Color(0xFF909399)),
                )
              else if (_expired)
                const Text(
                  '已超时',
                  style: TextStyle(fontSize: 12, color: Color(0xFF909399)),
                )
              else if (_remaining > 0)
                Text(
                  '$_remaining s',
                  style: const TextStyle(fontSize: 12, color: Color(0xFFE6A23C)),
                ),
            ],
          ),
          const SizedBox(height: 10),
          Text(
            widget.preview,
            style: const TextStyle(fontSize: 13, height: 1.6, color: Color(0xFF606266)),
          ),
          const SizedBox(height: 12),
          if (widget.cancelled)
            const Center(
              child: Text(
                '❌ 该操作已被您的新消息打断，自动取消，未执行。',
                style: TextStyle(fontSize: 13, color: Color(0xFF909399)),
              ),
            )
          else if (_expired)
            const Center(
              child: Text(
                '⏰ 确认超时，该操作已自动取消。',
                style: TextStyle(fontSize: 13, color: Color(0xFF909399)),
              ),
            )
          else
            Row(
              mainAxisAlignment: MainAxisAlignment.end,
              children: [
                _ActionButton(
                  label: '拒绝',
                  icon: Icons.close,
                  color: Colors.grey.shade500,
                  busy: _busy,
                  onTap: () => _handle(false),
                ),
                const SizedBox(width: 10),
                _ActionButton(
                  label: '同意',
                  icon: Icons.check,
                  color: const Color(0xFF67C23A),
                  busy: _busy,
                  onTap: () => _handle(true),
                ),
              ],
            ),
        ],
      ),
    );
  }
}

class _ActionButton extends StatelessWidget {
  final String label;
  final IconData icon;
  final Color color;
  final bool busy;
  final VoidCallback onTap;

  const _ActionButton({
    required this.label,
    required this.icon,
    required this.color,
    required this.busy,
    required this.onTap,
  });

  @override
  Widget build(BuildContext context) {
    return SizedBox(
      height: 32,
      child: TextButton.icon(
        onPressed: busy ? null : onTap,
        icon: busy
            ? const SizedBox(
                width: 14,
                height: 14,
                child: CircularProgressIndicator(strokeWidth: 2),
              )
            : Icon(icon, size: 16),
        label: Text(label),
        style: TextButton.styleFrom(
          foregroundColor: Colors.white,
          backgroundColor: color,
          disabledBackgroundColor: color.withValues(alpha: 0.5),
          padding: const EdgeInsets.symmetric(horizontal: 16),
          textStyle: const TextStyle(fontSize: 13),
        ),
      ),
    );
  }
}
