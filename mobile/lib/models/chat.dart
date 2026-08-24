// 聊天相关模型（与后端 app/schemas/chat.py 字段一致）

class ChatResponse {
  final String reply;
  final String threadId;
  final bool requiresConfirmation;
  final String? preview;
  final int? expiresInSeconds;
  final int cancelledConfirmations;

  ChatResponse({
    required this.reply,
    required this.threadId,
    this.requiresConfirmation = false,
    this.preview,
    this.expiresInSeconds,
    this.cancelledConfirmations = 0,
  });

  factory ChatResponse.fromJson(Map<String, dynamic> json) => ChatResponse(
        reply: json['reply'] as String? ?? '',
        threadId: json['thread_id'] as String? ?? '',
        requiresConfirmation: json['requires_confirmation'] as bool? ?? false,
        preview: json['preview'] as String?,
        expiresInSeconds: json['expires_in_seconds'] as int?,
        cancelledConfirmations: json['cancelled_confirmations'] as int? ?? 0,
      );
}
