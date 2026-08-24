// AIAcct 移动端冒烟测试：验证 app 可构建并渲染登录页

import 'package:flutter_test/flutter_test.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'package:aiacct_mobile/main.dart';

void main() {
  testWidgets('App builds and shows login screen', (WidgetTester tester) async {
    SharedPreferences.setMockInitialValues({});
    await tester.pumpWidget(const AiAcctApp());
    await tester.pumpAndSettle();

    // 登录页应显示应用标题与登录按钮
    expect(find.text('AI 会计助手'), findsOneWidget);
    expect(find.text('登 录'), findsOneWidget);
    expect(find.text('没有账号？去注册'), findsOneWidget);
  });
}
