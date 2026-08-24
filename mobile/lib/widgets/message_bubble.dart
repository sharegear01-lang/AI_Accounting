import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:flutter_markdown/flutter_markdown.dart';

import '../providers/chat_provider.dart';
import 'approval_card.dart';
import 'typing_indicator.dart';

/// 单条消息气泡（用户/AI），对应 web 端 Chat.vue 的消息渲染逻辑
class MessageBubble extends StatelessWidget {
  final ChatMessage message;
  final String threadId;
  final bool disabled; // 请求在途时禁用确认卡按钮
  final Future<void> Function(bool approved) onResolved;
  final VoidCallback onExpired;

  const MessageBubble({
    super.key,
    required this.message,
    required this.threadId,
    this.disabled = false,
    required this.onResolved,
    required this.onExpired,
  });

  @override
  Widget build(BuildContext context) {
    final isUser = message.role == MessageRole.user;

    return Padding(
      padding: const EdgeInsets.only(bottom: 14),
      child: Row(
        mainAxisAlignment:
            isUser ? MainAxisAlignment.end : MainAxisAlignment.start,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          if (!isUser) ...[
            const _Avatar(emoji: '🤖'),
            const SizedBox(width: 10),
          ],
          Flexible(
            child: ConstrainedBox(
              constraints: const BoxConstraints(maxWidth: 300),
              child: Container(
                padding: const EdgeInsets.symmetric(
                  horizontal: 14,
                  vertical: 10,
                ),
                decoration: BoxDecoration(
                  color: isUser ? const Color(0xFF409EFF) : Colors.white,
                  borderRadius: BorderRadius.only(
                    topLeft: Radius.circular(isUser ? 10 : 2),
                    topRight: Radius.circular(isUser ? 2 : 10),
                    bottomLeft: const Radius.circular(10),
                    bottomRight: const Radius.circular(10),
                  ),
                  border: isUser
                      ? null
                      : Border.all(color: const Color(0xFFE4E7ED)),
                  boxShadow: [
                    if (!isUser)
                      BoxShadow(
                        color: Colors.black.withValues(alpha: 0.04),
                        blurRadius: 4,
                        offset: const Offset(0, 1),
                      ),
                  ],
                ),
                child: _buildContent(context, isUser),
              ),
            ),
          ),
          if (isUser) ...[
            const SizedBox(width: 10),
            const _Avatar(emoji: '🧑'),
          ],
        ],
      ),
    );
  }

  Widget _buildContent(BuildContext context, bool isUser) {
    // 用户消息：图片 + 文本
    if (isUser) {
      return Column(
        crossAxisAlignment: CrossAxisAlignment.end,
        children: [
          if (message.imageDataUrl != null && message.imageDataUrl!.isNotEmpty) ...[
            ClipRRect(
              borderRadius: BorderRadius.circular(6),
              child: Image.memory(
                base64Decode(message.imageDataUrl!.split(',').last),
                width: 180,
                fit: BoxFit.cover,
                errorBuilder: (_, __, ___) => const SizedBox(
                  width: 180,
                  height: 100,
                  child: Center(child: Text('图片加载失败')),
                ),
              ),
            ),
            const SizedBox(height: 8),
          ],
          Text(
            message.content,
            style: const TextStyle(
              color: Colors.white,
              fontSize: 15,
              height: 1.6,
            ),
          ),
        ],
      );
    }

    // AI 消息：加载中 / HITL 确认卡 / Markdown
    if (message.loading) {
      return const TypingIndicator();
    }
    if (message.isApproval) {
      return ApprovalCard(
        threadId: threadId,
        preview: message.approvalPreview,
        expiresInSeconds: message.expiresInSeconds,
        cancelled: message.cancelled,
        disabled: disabled,
        onResolved: onResolved,
        onExpired: onExpired,
      );
    }
    return MarkdownBody(
      data: message.content,
      styleSheet: MarkdownStyleSheet.fromTheme(Theme.of(context)).copyWith(
        p: const TextStyle(fontSize: 15, height: 1.6, color: Color(0xFF303133)),
        tableBorder: TableBorder.all(color: const Color(0xFFDCDFE6)),
        tableHead: const TextStyle(fontWeight: FontWeight.w600),
      ),
    );
  }
}

class _Avatar extends StatelessWidget {
  final String emoji;
  const _Avatar({required this.emoji});

  @override
  Widget build(BuildContext context) {
    return Container(
      width: 36,
      height: 36,
      decoration: BoxDecoration(
        color: const Color(0xFFE4E7ED),
        shape: BoxShape.circle,
      ),
      alignment: Alignment.center,
      child: Text(emoji, style: const TextStyle(fontSize: 18)),
    );
  }
}
