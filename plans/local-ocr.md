# 计划：本地轻量 OCR 替换 Qwen 云端 OCR 的可行性与实施方案

## Context（背景）

当前 OCR 走 Qwen3.5-OCR（Dashscope 云端 VLM），存在成本（按 token 计费）与
单次调用延迟（网络 + 云端推理）问题。用户提出：改用本地部署的轻量 OCR 模型，
以提升效率（延迟↓）并降低成本（无 API 费用），核心疑问是**准确率能否满足要求**。

## 现状盘点（已从代码确认）

| 项目 | 现状 |
|------|------|
| OCR 调用 | `app/services/ocr_service.py` 单一入口 `recognize_structured()`，仅被 `preprocess_node` 调用 |
| 能力本质 | Qwen3.5-OCR 是 **VLM 端到端语义提取**：图片 → 键值 JSON（实付金额/店铺名称/交易时间/订单编号） |
| 防幻觉闸门 | `OcrResult.is_bookable()`：必须 `recognized=True` 且金额可解析为合法 Decimal，否则拦截记账（金额猜不得） |
| 图片形态 | 电商订单截图（淘宝/拼多多/美团等）+ 电子小票；前端已压缩至 1280px 长边 JPEG 0.85 |
| 图片预处理 | `app/services/image.py`（像素预算缩放 + EXIF 校正 + 格式归一化），已具备 |
| 部署 | docker-compose 单机（目前只有 postgres），未声明 GPU |
| 超时 | `OCR_TIMEOUT_SECONDS`（.env 中为 20s，config 默认 5s），超时拦截降级 |

## 核心差距分析（为什么不能直接替换）

1. **能力错位**：Qwen3-OCR 做的是"看图提取字段"（语义理解：哪一个是实付金额）；
   本地轻量 OCR（PaddleOCR/RapidOCR）只输出 **文本行 + 坐标框**，没有语义。
   → 需要一个"文本框 → 字段"的**结构化层**，这是准确率风险最集中的地方。
2. **金额是硬闸门**：多金额票据（原价/优惠/实付）下，规则必须能准确挑中"实付"，
   挑错就是记错账——比识别失败更糟。现有闸门哲学"猜不得"必须保留。
3. **延迟不必然更优**：云端 Qwen 单次 ~1-2s；本地 CPU 跑 PaddleOCR 全图
   （1280px 截图、文本行多）官方标称 31ms 但真实用户实测 1.7~5.2s（GitHub #15952）；
   RapidOCR（ONNX）实测约 150-300ms/图。**CPU 部署是否真的更快需要实测**。

## 外部数据（web_search 已确认）

- Qwen3.5-OCR 定价：输入 ¥0.5/M tokens，输出 ¥2/M tokens（qwen-vl-ocr-latest 更便宜 ¥0.3/¥0.5）
- PP-OCRv5：识别模型 server 86.38% / mobile 81.29%（字符级）；官方 CPU 耗时与实测差异巨大
- RapidOCR：PaddleOCR 模型转 ONNX，脱离 Paddle 框架，依赖 ~150MB，CPU 150-300ms/图，精度略降
- 票据关键信息抽取：PaddleOCR 有 VI-LayoutXLM（SER+RE），但模板方案鲁棒性差，需针对真实样本微调

## 方案选项（待用户决策）

### 方案 A：纯本地（PaddleOCR/RapidOCR + 规则结构化）
- 检测+识别文本行 → 坐标布局 → 规则/正则提取 商户/金额/日期/订单号
- 零 API 成本，隐私好；风险：布局变体多、字段映射脆弱，金额挑错风险最高
- 依赖：paddleocr 或 rapidocr_onnxruntime（~150MB 依赖 + ~50MB 模型）

### 方案 B：本地 OCR + 本地小 LLM 结构化
- PaddleOCR 出文本 → 本地小模型（如 Qwen2.5-3B/GLM-4-9B）按现有 OCR_SYSTEM_PROMPT 出键值 JSON
- 语义提取质量接近 Qwen，仍全本地；代价：需 4-8GB 内存/GPU，延迟增加，依赖变重

### 方案 C：混合（本地优先 + 云端兜底）★ 最稳妥
- 本地 OCR 先跑：金额确认 → 直接记账（省成本、快）
- 本地识别失败 / 金额不可信 / 闸门不过 → **自动升级调 Qwen 云端兜底**（不直接拦截）
- 现有闸门与 `respond_blocked_node` 全部保留；兜底路径复用现有代码
- 成本：典型路径（清晰截图）零成本，疑难图才花钱；准确率不降反升（比现在多一层机会）

## 推荐路线

**先做 Phase 0 基准评测（不写生产代码）**，用真实图片回答"准确率能否达标"，
再按结果决定 A/B/C 与默认路径：

1. 收集 20-50 张真实图片（各平台订单截图 + 电子小票 + 部分模糊/复杂样本）
2. 人工标注 ground truth（金额/商户/日期，金额为必标注字段）
3. 跑三方对比：Qwen3.5-OCR（现状）vs RapidOCR+规则 vs PaddleOCR+规则
   指标：金额准确率（最关键）、商户/日期准确率、拦截率（宁可拦不可错）
4. 输出对比报告 → 用户拍板方案与默认路径

## Files to modify（Phase 0 后实现阶段）

- `app/config.py`：OCR_PROVIDER（qwen / local / hybrid）、模型路径、置信度阈值
- `app/services/ocr_service.py`：抽 Provider 抽象层（`recognize_structured` 签名不变，
  内部按 provider 分发；新增本地结构化层：文本行 → OcrResult）
- `app/services/image.py`：复用现有预处理（可能为本地 OCR 调整分辨率策略）
- `app/agent/nodes.py`：`preprocess_node` 兜底逻辑（本地失败 → 云端重试，而非直接拦截）
- `requirements.txt`：新增 rapidocr_onnxruntime / paddleocr 依赖
- 新增：`app/services/local_ocr.py`（本地识别 + 规则结构化）、`scripts/ocr_benchmark.py`（评测脚本）
- 测试：`test_preprocess.py` 增补本地 provider 分支 mock；新增基准测试数据目录

## Reuse（现有可复用）

- `app/services/image.py::compress_image` / `image_to_base64`：图片预处理
- `ocr_service.py::OcrResult / parse_ocr_output / _parse_amount`：结构化结果与金额解析/闸门逻辑，本地 provider 复用同一结果模型
- `app/agent/nodes.py::preprocess_node` 的拦截分支与 `respond_blocked_node`：兜底失败仍走原拦截
- `test_preprocess.py` 的 mock 模式：provider 切换可测

## Steps（待方案确定后细化）

- [ ] Phase 0：样本收集 + 标注 + 三方基准评测 → 出报告（不写生产代码）
- [ ] Phase 1：OCR Provider 抽象 + 本地 provider（规则结构化层）
- [ ] Phase 2：混合兜底逻辑（本地失败升级云端）或按评测结果定默认路径
- [ ] Phase 3：真实图片回归测试 + 上线开关

## Verification

- 基准脚本输出三方准确率对比表（金额/商户/日期/拦截率）
- 现有 `test_preprocess.py` 全绿（各 provider 分支）
- 用 `test_image1.jpg / test_image2.jpg` + 新增真实样本跑通 `test_ocr.py` 端到端
- 生产开关切换前后，日志中记录 provider 命中率与兜底率
