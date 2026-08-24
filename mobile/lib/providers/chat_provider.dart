import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api.dart';

enum MessageRole { user, assistant }

/// 单条聊天消息（含 HITL 确认卡所需字段）
class ChatMessage {
  final MessageRole role;
  final String content;
  final bool isApproval;
  final String approvalPreview;
  final int? expiresInSeconds; // HITL 确认剩余秒数（超时自动取消）
  final bool loading;
  final String? imageDataUrl; // 用户消息附带的图片（data URL 用于本地展示）
  // HITL 确认卡生命周期状态（由 Provider 跟踪，驱动卡片展示）
  final bool resolved; // 用户已点击同意/拒绝
  final bool expired; // 本地倒计时归零
  final bool cancelled; // 用户发新消息导致后端自动取消

  const ChatMessage({
    required this.role,
    required this.content,
    this.isApproval = false,
    this.approvalPreview = '',
    this.expiresInSeconds,
    this.loading = false,
    this.imageDataUrl,
    this.resolved = false,
    this.expired = false,
    this.cancelled = false,
  });

  ChatMessage copyWith({
    bool? resolved,
    bool? expired,
    bool? cancelled,
  }) =>
      ChatMessage(
        role: role,
        content: content,
        isApproval: isApproval,
        approvalPreview: approvalPreview,
        expiresInSeconds: expiresInSeconds,
        loading: loading,
        imageDataUrl: imageDataUrl,
        resolved: resolved ?? this.resolved,
        expired: expired ?? this.expired,
        cancelled: cancelled ?? this.cancelled,
      );
}

/// 聊天状态管理：消息列表 + 发送 + HITL 批准/拒绝
class ChatProvider extends ChangeNotifier {
  final List<ChatMessage> _messages = [];
  String _threadId = '';
  bool _sending = false;

  List<ChatMessage> get messages => List.unmodifiable(_messages);
  String get threadId => _threadId;
  bool get sending => _sending;

  /// 会话初始化：恢复 thread_id + 欢迎语（与 web 端一致）
  Future<void> init() async {
    final prefs = await SharedPreferences.getInstance();
    _threadId = prefs.getString('thread_id') ??
        'mobile_${DateTime.now().millisecondsSinceEpoch}';
    await prefs.setString('thread_id', _threadId);

    _messages.clear();
    _messages.add(const ChatMessage(
      role: MessageRole.assistant,
      content: '你好！我是你的 AI 记账助手 📊\n\n可以这样使用我：\n'
          '- **记一笔账**：直接描述消费，如"中午吃了麦当劳花了35元"\n'
          '- **传图记账**：点击左下角图片按钮上传订单截图\n'
          '- **查询账单**：问我"这个月吃饭花了多少钱"\n'
          '- **修改/删除**：我会先展示预览，经你确认后才会执行',
    ));
    notifyListeners();
  }

  void clear() {
    _messages.clear();
    notifyListeners();
  }

  /// 发送消息（文本或图片；与 web 端相同，无文本时以图片为主）
  Future<void> sendMessage(String text, {String? imageDataUrl}) async {
    if (_sending) return;
    final trimmed = text.trim();
    if (trimmed.isEmpty && imageDataUrl == null) return;

    _sending = true;
    _messages.add(ChatMessage(
      role: MessageRole.user,
      content: trimmed.isEmpty ? '(图片记账)' : trimmed,
      imageDataUrl: imageDataUrl,
    ));
    _messages.add(const ChatMessage(
      role: MessageRole.assistant,
      content: '',
      loading: true,
    ));
    notifyListeners();

    try {
      final resp = await Api.chat(
        message: trimmed.isEmpty ? '请识别图片并完成记账' : trimmed,
        threadId: _threadId,
        imageBase64: imageDataUrl?.split(',').last, // 去掉 data:image/jpeg;base64, 前缀
      );
      _removeLoading();

      // 用户发新消息时，后端自动取消了挂起的待确认操作 → 把仍在展示中的确认卡标记为已取消
      if (resp.cancelledConfirmations > 0) {
        _markPendingCardsCancelled();
      }

      // requires_confirmation=true → HITL interrupt，渲染确认卡（同意/拒绝按钮）
      final isApproval = resp.requiresConfirmation;
      _messages.add(ChatMessage(
        role: MessageRole.assistant,
        content: isApproval ? (resp.preview ?? resp.reply) : resp.reply,
        isApproval: isApproval,
        approvalPreview: isApproval ? (resp.preview ?? resp.reply) : '',
        expiresInSeconds: resp.expiresInSeconds,
      ));
    } catch (e) {
      _removeLoading();
      _messages.add(ChatMessage(
        role: MessageRole.assistant,
        content: '❌ 请求失败：${friendlyError(e)}',
      ));
    } finally {
      _sending = false;
      notifyListeners();
    }
  }

  /// HITL 确认：同意/拒绝后结果作为 AI 消息追加（与 web 端 handleResolved 一致）
  /// [message] 为对应的确认卡消息，用于标记已处理（停止倒计时、禁用按钮）。
  Future<void> resolveHitl(ChatMessage message, bool approved) async {
    _replaceMessage(message, message.copyWith(resolved: true));
    try {
      final resp = await Api.chat(threadId: _threadId, approve: approved);
      _messages.add(ChatMessage(role: MessageRole.assistant, content: resp.reply));
    } catch (e) {
      _messages.add(ChatMessage(
        role: MessageRole.assistant,
        content: '❌ 操作失败：${friendlyError(e)}',
      ));
    }
    notifyListeners();
  }

  /// 确认卡本地倒计时归零（标记已超时，禁用按钮）
  void markExpired(ChatMessage message) {
    _replaceMessage(message, message.copyWith(expired: true));
  }

  /// 把仍在展示中的待确认卡片标记为『已取消』（用户发新消息被后端自动取消）
  void _markPendingCardsCancelled() {
    for (var i = 0; i < _messages.length; i++) {
      final m = _messages[i];
      if (m.isApproval && !m.resolved && !m.expired && !m.cancelled) {
        _messages[i] = m.copyWith(cancelled: true);
      }
    }
    notifyListeners();
  }

  void _replaceMessage(ChatMessage oldMsg, ChatMessage newMsg) {
    final idx = _messages.indexWhere((m) => identical(m, oldMsg));
    if (idx != -1) _messages[idx] = newMsg;
  }

  void _removeLoading() {
    final idx = _messages.indexWhere((m) => m.loading);
    if (idx != -1) _messages.removeAt(idx);
  }
}
