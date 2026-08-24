import 'package:flutter/material.dart';

/// 打字指示器：三个跳动圆点（与 web 端 CSS 动画对应）
class TypingIndicator extends StatelessWidget {
  const TypingIndicator({super.key});

  @override
  Widget build(BuildContext context) {
    return const SizedBox(
      width: 40,
      height: 20,
      child: Row(
        mainAxisAlignment: MainAxisAlignment.center,
        children: [
          _Dot(delay: Duration.zero),
          SizedBox(width: 5),
          _Dot(delay: Duration(milliseconds: 200)),
          SizedBox(width: 5),
          _Dot(delay: Duration(milliseconds: 400)),
        ],
      ),
    );
  }
}

class _Dot extends StatefulWidget {
  final Duration delay;
  const _Dot({required this.delay});

  @override
  State<_Dot> createState() => _DotState();
}

class _DotState extends State<_Dot> with SingleTickerProviderStateMixin {
  late final AnimationController _controller;

  @override
  void initState() {
    super.initState();
    _controller = AnimationController(
      vsync: this,
      duration: const Duration(milliseconds: 1400),
    )..repeat();
  }

  @override
  void dispose() {
    _controller.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    return AnimatedBuilder(
      animation: _controller,
      builder: (context, _) {
        // 与 web 端 blink 动画同步：0/80/100% 透明度低，40% 透明度高
        final t = _controller.value;
        final opacity = (t < 0.4 || t >= 0.8) ? 0.3 : 1.0;
        return Container(
          width: 8,
          height: 8,
          decoration: BoxDecoration(
            color: Colors.grey.withValues(alpha: opacity),
            shape: BoxShape.circle,
          ),
        );
      },
    );
  }
}
