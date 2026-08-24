import 'dart:convert';

import 'package:flutter/material.dart';
import 'package:image/image.dart' as img;
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';

import '../providers/auth_provider.dart';
import '../providers/chat_provider.dart';
import '../widgets/message_bubble.dart';

/// 聊天主界面（对应 web 端 Chat.vue）
class ChatScreen extends StatefulWidget {
  const ChatScreen({super.key});

  @override
  State<ChatScreen> createState() => _ChatScreenState();
}

class _ChatScreenState extends State<ChatScreen> {
  static const _suggestions = [
    '昨天下午在星巴克花了45元买咖啡',
    '看看最近的账单',
    '帮我删除最新一笔记录',
  ];

  final _inputCtrl = TextEditingController();
  final _scrollCtrl = ScrollController();
  final _picker = ImagePicker();
  String? _pendingImageDataUrl; // 待发送图片（data URL）

  @override
  void initState() {
    super.initState();
    // 会话初始化（thread_id + 欢迎语）
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<ChatProvider>().init();
    });
  }

  @override
  void dispose() {
    _inputCtrl.dispose();
    _scrollCtrl.dispose();
    super.dispose();
  }

  void _scrollToBottom() {
    WidgetsBinding.instance.addPostFrameCallback((_) {
      if (_scrollCtrl.hasClients) {
        _scrollCtrl.animateTo(
          _scrollCtrl.position.maxScrollExtent,
          duration: const Duration(milliseconds: 200),
          curve: Curves.easeOut,
        );
      }
    });
  }

  /// 选择图片并压缩至 1280px 长边 / JPEG 0.85（与 web 端参数一致）
  Future<void> _pickAndCompressImage() async {
    try {
      final file = await _picker.pickImage(
        source: ImageSource.gallery,
        maxWidth: 2000, // 先限制原图尺寸，避免内存峰值
      );
      if (file == null) return;

      final bytes = await file.readAsBytes();
      final decoded = img.decodeImage(bytes);
      if (decoded == null) {
        _toast('无法解析图片');
        return;
      }

      // 长边归一化至 1280px（低于此值保持原尺寸）
      const maxSide = 1280;
      var width = decoded.width;
      var height = decoded.height;
      if (width > maxSide || height > maxSide) {
        final ratio = maxSide / (width > height ? width : height);
        width = (width * ratio).round();
        height = (height * ratio).round();
      }
      final resized = img.copyResize(decoded, width: width, height: height);
      final jpg = img.encodeJpg(resized, quality: 85);
      final dataUrl = 'data:image/jpeg;base64,${base64Encode(jpg)}';

      if (!mounted) return;
      setState(() => _pendingImageDataUrl = dataUrl);
    } catch (e) {
      _toast('图片处理失败：$e');
    }
  }

  Future<void> _send() async {
    final chat = context.read<ChatProvider>();
    final text = _inputCtrl.text;
    final image = _pendingImageDataUrl;

    if (text.trim().isEmpty && image == null) return;
    if (chat.sending) return;

    setState(() => _pendingImageDataUrl = null);
    _inputCtrl.clear();

    await chat.sendMessage(text, imageDataUrl: image);
    _scrollToBottom();
  }

  void _toast(String msg) {
    if (!mounted) return;
    ScaffoldMessenger.of(context)
        .showSnackBar(SnackBar(content: Text(msg), duration: const Duration(seconds: 2)));
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    final chat = context.watch<ChatProvider>();

    return Scaffold(
      backgroundColor: const Color(0xFFF7F8FA),
      appBar: AppBar(
        backgroundColor: Colors.white,
        elevation: 0.5,
        title: const Row(
          children: [
            Text('🧾', style: TextStyle(fontSize: 20)),
            SizedBox(width: 8),
            Text('AI 会计助手', style: TextStyle(fontSize: 17, fontWeight: FontWeight.w600)),
          ],
        ),
        actions: [
          Center(
            child: Text(
              '👤 ${auth.username ?? ''}',
              style: const TextStyle(fontSize: 13, color: Colors.grey),
            ),
          ),
          IconButton(
            icon: const Icon(Icons.logout, color: Color(0xFFF56C6C), size: 20),
            tooltip: '退出登录',
            onPressed: () async {
              await auth.logout();
              chat.clear();
            },
          ),
          const SizedBox(width: 4),
        ],
      ),
      body: Column(
        children: [
          Expanded(
            child: chat.messages.isEmpty
                ? _buildEmptyState()
                : _buildMessageList(chat),
          ),
          _buildInputBar(chat),
        ],
      ),
    );
  }

  /// 空态：建议词（点击直接发送）
  Widget _buildEmptyState() {
    return Center(
      child: Column(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          const Text('💰', style: TextStyle(fontSize: 56)),
          const SizedBox(height: 16),
          const Text('开始记账吧！',
              style: TextStyle(fontSize: 18, fontWeight: FontWeight.w600, color: Color(0xFF303133))),
          const SizedBox(height: 8),
          Text('支持文字描述或截图上传，例如：',
              style: TextStyle(fontSize: 13, color: Colors.grey.shade500)),
          const SizedBox(height: 20),
          ..._suggestions.map(
            (s) => Padding(
              padding: const EdgeInsets.symmetric(vertical: 5),
              child: ActionChip(
                label: Text(s, style: const TextStyle(fontSize: 13)),
                backgroundColor: Colors.white,
                side: const BorderSide(color: Color(0xFFE4E7ED)),
                onPressed: () {
                  _inputCtrl.text = s;
                  _send();
                },
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildMessageList(ChatProvider chat) {
    return ListView.builder(
      controller: _scrollCtrl,
      padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 16),
      itemCount: chat.messages.length,
      itemBuilder: (context, index) {
        final msg = chat.messages[index];
        return MessageBubble(
          message: msg,
          threadId: chat.threadId,
          disabled: chat.sending,
          onResolved: (approved) async {
            await chat.resolveHitl(msg, approved);
            _scrollToBottom();
          },
          onExpired: () => chat.markExpired(msg),
        );
      },
    );
  }

  Widget _buildInputBar(ChatProvider chat) {
    return Container(
      padding: const EdgeInsets.fromLTRB(12, 10, 12, 12),
      decoration: const BoxDecoration(
        color: Colors.white,
        border: Border(top: BorderSide(color: Color(0xFFE4E7ED))),
      ),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          // 待发送图片预览
          if (_pendingImageDataUrl != null)
            Padding(
              padding: const EdgeInsets.only(bottom: 8),
              child: Row(
                children: [
                  Stack(
                    children: [
                      ClipRRect(
                        borderRadius: BorderRadius.circular(6),
                        child: Image.memory(
                          base64Decode(_pendingImageDataUrl!.split(',').last),
                          width: 56,
                          height: 56,
                          fit: BoxFit.cover,
                        ),
                      ),
                      Positioned(
                        top: -6,
                        right: -6,
                        child: GestureDetector(
                          onTap: () => setState(() => _pendingImageDataUrl = null),
                          child: Container(
                            decoration: const BoxDecoration(
                              color: Color(0xFFF56C6C),
                              shape: BoxShape.circle,
                            ),
                            child: const Icon(Icons.close, size: 14, color: Colors.white),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(width: 10),
                  Text('将随消息一起发送，自动压缩至 1280px',
                      style: TextStyle(fontSize: 12, color: Colors.grey.shade500)),
                ],
              ),
            ),
          Row(
            crossAxisAlignment: CrossAxisAlignment.end,
            children: [
              IconButton(
                icon: const Icon(Icons.image_outlined, color: Color(0xFF409EFF)),
                tooltip: '上传图片',
                onPressed: _pickAndCompressImage,
              ),
              Expanded(
                child: TextField(
                  controller: _inputCtrl,
                  minLines: 1,
                  maxLines: 4,
                  textInputAction: TextInputAction.send,
                  onSubmitted: (_) => _send(),
                  decoration: InputDecoration(
                    hintText: '输入记账内容，如：昨天在星巴克花了45元买咖啡',
                    hintStyle: TextStyle(fontSize: 14, color: Colors.grey.shade400),
                    isDense: true,
                    contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    filled: true,
                    fillColor: const Color(0xFFF5F7FA),
                    border: OutlineInputBorder(
                      borderRadius: BorderRadius.circular(8),
                      borderSide: BorderSide.none,
                    ),
                  ),
                ),
              ),
              const SizedBox(width: 8),
              FilledButton(
                onPressed: chat.sending ? null : _send,
                style: FilledButton.styleFrom(
                  backgroundColor: const Color(0xFF409EFF),
                  padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                  disabledBackgroundColor: const Color(0xFF409EFF).withValues(alpha: 0.5),
                ),
                child: chat.sending
                    ? const SizedBox(
                        width: 16,
                        height: 16,
                        child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                      )
                    : const Text('发送'),
              ),
            ],
          ),
        ],
      ),
    );
  }
}
