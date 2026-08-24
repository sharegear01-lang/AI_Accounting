// 鉴权相关模型（与后端 app/schemas/auth.py 字段一致）

class TokenResponse {
  final String accessToken;
  final String tokenType;

  TokenResponse({required this.accessToken, this.tokenType = 'bearer'});

  factory TokenResponse.fromJson(Map<String, dynamic> json) => TokenResponse(
        accessToken: json['access_token'] as String? ?? '',
        tokenType: json['token_type'] as String? ?? 'bearer',
      );
}

class RegisterResponse {
  final String userId;
  final String username;
  final String message;

  RegisterResponse({
    required this.userId,
    required this.username,
    this.message = '注册成功',
  });

  factory RegisterResponse.fromJson(Map<String, dynamic> json) =>
      RegisterResponse(
        userId: json['user_id'] as String? ?? '',
        username: json['username'] as String? ?? '',
        message: json['message'] as String? ?? '注册成功',
      );
}

/// 错误响应（后端 FastAPI 统一 {detail: ...} 结构）
class ApiError {
  final int? statusCode;
  final String detail;

  ApiError({this.statusCode, required this.detail});

  @override
  String toString() => detail;
}
