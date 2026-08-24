import 'package:dio/dio.dart';

import '../models/auth.dart';
import '../models/chat.dart';
import 'client.dart';

/// 后端 API 方法（对应 app/api/auth.py、app/api/chat.py 路由）
class Api {
  /// POST /register
  static Future<RegisterResponse> register(
    String username,
    String password,
  ) async {
    final resp = await ApiClient.dio.post(
      '/register',
      data: {'username': username, 'password': password},
    );
    return RegisterResponse.fromJson(resp.data as Map<String, dynamic>);
  }

  /// POST /login → {access_token, token_type}
  static Future<TokenResponse> login(String username, String password) async {
    final resp = await ApiClient.dio.post(
      '/login',
      data: {'username': username, 'password': password},
    );
    return TokenResponse.fromJson(resp.data as Map<String, dynamic>);
  }

  /// POST /chat（imageBase64 为纯 base64，不含 data:image/... 前缀）
  /// [approve] 非空时表示 HITL 按钮决策（True=同意 / False=拒绝），
  /// 直接恢复被 interrupt 暂停的图，不再走 Agent 流程。
  static Future<ChatResponse> chat({
    required String threadId,
    String message = '',
    bool? approve,
    String? imageBase64,
  }) async {
    final resp = await ApiClient.dio.post(
      '/chat',
      data: {
        'message': message,
        'thread_id': threadId,
        if (approve != null) 'approve': approve,
        if (imageBase64 != null && imageBase64.isNotEmpty)
          'image_base64': imageBase64,
      },
    );
    return ChatResponse.fromJson(resp.data as Map<String, dynamic>);
  }
}

/// 从 DioException 提取用户可读错误信息（后端 FastAPI 统一 {detail} 结构）
String friendlyError(Object e) {
  if (e is DioException) {
    final data = e.response?.data;
    if (data is Map && data['detail'] != null) {
      return data['detail'].toString();
    }
    switch (e.type) {
      case DioExceptionType.connectionTimeout:
      case DioExceptionType.connectionError:
        return '无法连接服务器，请检查网络与服务器地址';
      case DioExceptionType.badResponse:
        return '服务器返回错误（${e.response?.statusCode}）';
      default:
        return e.message ?? '请求失败';
    }
  }
  return e.toString();
}
