import 'package:dio/dio.dart';
import 'package:shared_preferences/shared_preferences.dart';

/// dio 统一封装：baseUrl 可配置 + JWT 自动附加（与前端 axios 拦截器一致）
///
/// - 默认 baseUrl 指向 Android 模拟器访问宿主机后端的地址 10.0.2.2:8000
/// - 真机调试时在登录页"服务器设置"中改为局域网 IP
/// - 请求拦截器自动附加 `Authorization: Bearer <token>`
class ApiClient {
  ApiClient._();

  static const String _tokenKey = 'auth_token';
  static const String _serverUrlKey = 'server_url';
  static const String defaultBaseUrl = 'http://10.0.2.2:8000';

  static String baseUrl = defaultBaseUrl;

  static final Dio dio = Dio(
    BaseOptions(
      baseUrl: baseUrl,
      connectTimeout: const Duration(seconds: 10),
      receiveTimeout: const Duration(seconds: 120),
      headers: {'Content-Type': 'application/json'},
    ),
  )..interceptors.add(
      InterceptorsWrapper(
        onRequest: (options, handler) async {
          final prefs = await SharedPreferences.getInstance();
          final token = prefs.getString(_tokenKey);
          if (token != null && token.isNotEmpty) {
            options.headers['Authorization'] = 'Bearer $token';
          }
          handler.next(options);
        },
        onError: (e, handler) {
          // 401：token 失效/未登录 → 清理本地凭证，由 UI 层跳回登录页
          if (e.response?.statusCode == 401) {
            _clearCredentials();
          }
          handler.next(e);
        },
      ),
    );

  /// 启动时恢复本地配置（服务器地址 / 登录态由 Provider 恢复）
  static Future<void> loadSettings() async {
    final prefs = await SharedPreferences.getInstance();
    baseUrl = prefs.getString(_serverUrlKey) ?? defaultBaseUrl;
    dio.options.baseUrl = baseUrl;
  }

  /// 修改服务器地址（登录页设置入口调用）
  static Future<void> setBaseUrl(String url) async {
    var normalized = url.trim();
    if (normalized.endsWith('/')) {
      normalized = normalized.substring(0, normalized.length - 1);
    }
    baseUrl = normalized;
    dio.options.baseUrl = normalized;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_serverUrlKey, normalized);
  }

  static Future<void> saveToken(String token) async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString(_tokenKey, token);
  }

  static Future<void> _clearCredentials() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove(_tokenKey);
  }
}
