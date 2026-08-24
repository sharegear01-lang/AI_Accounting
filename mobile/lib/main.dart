import 'package:flutter/material.dart';
import 'package:provider/provider.dart';

import 'api/client.dart';
import 'providers/auth_provider.dart';
import 'providers/chat_provider.dart';
import 'screens/chat_screen.dart';
import 'screens/login_screen.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  // 恢复本地配置（服务器地址）
  await ApiClient.loadSettings();
  runApp(const AiAcctApp());
}

class AiAcctApp extends StatelessWidget {
  const AiAcctApp({super.key});

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => AuthProvider()),
        ChangeNotifierProvider(create: (_) => ChatProvider()),
      ],
      child: MaterialApp(
        title: 'AI 会计助手',
        debugShowCheckedModeBanner: false,
        theme: ThemeData(
          useMaterial3: true,
          colorScheme: ColorScheme.fromSeed(seedColor: const Color(0xFF409EFF)),
          scaffoldBackgroundColor: const Color(0xFFF7F8FA),
        ),
        home: const _AuthGate(),
      ),
    );
  }
}

/// 登录态门卫：未登录 → 登录页；已登录 → 聊天页（对应前端路由守卫）
class _AuthGate extends StatefulWidget {
  const _AuthGate();

  @override
  State<_AuthGate> createState() => _AuthGateState();
}

class _AuthGateState extends State<_AuthGate> {
  @override
  void initState() {
    super.initState();
    // 恢复登录态（token / username）
    WidgetsBinding.instance.addPostFrameCallback((_) {
      context.read<AuthProvider>().restore();
    });
  }

  @override
  Widget build(BuildContext context) {
    final auth = context.watch<AuthProvider>();
    // restore() 完成前（无 token）短暂显示启动页，避免闪烁登录页
    if (!auth.isLoggedIn) {
      return const LoginScreen();
    }
    return const ChatScreen();
  }
}
