import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';

import '../api/api.dart';
import '../api/client.dart';

/// 登录态管理：JWT token 持久化 + 登录/注册/登出
class AuthProvider extends ChangeNotifier {
  String? _token;
  String? _username;

  String? get token => _token;
  String? get username => _username;
  bool get isLoggedIn => _token != null && _token!.isNotEmpty;

  /// 启动时从本地恢复登录态
  Future<void> restore() async {
    final prefs = await SharedPreferences.getInstance();
    _token = prefs.getString('auth_token');
    _username = prefs.getString('username');
    notifyListeners();
  }

  /// 登录：换取 JWT 并持久化
  Future<void> login(String username, String password) async {
    final resp = await Api.login(username, password);
    _token = resp.accessToken;
    _username = username;
    await ApiClient.saveToken(resp.accessToken);
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('username', username);
    notifyListeners();
  }

  /// 注册（成功后由 UI 层引导用户切到登录）
  Future<void> register(String username, String password) async {
    await Api.register(username, password);
  }

  Future<void> logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('auth_token');
    await prefs.remove('username');
    _token = null;
    _username = null;
    notifyListeners();
  }
}
