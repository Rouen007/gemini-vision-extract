---
name: gemini-vision-extract
description: 通过共享 Gemini 运行时批量读图并输出结构化 JSON；用于 OCR、截图字段提取、图像比较及该运行时配置排障，保留 schema、重试与并发限制。
---

# Gemini 图像结构化提取

把 Gemini 图像读取当作共享基础设施，不在业务 skill 内重复实现鉴权、base64、并发、重试或响应解析。
调用方只提供图片、逐图上下文、提示词和 JSON Schema；业务字段合并与领域校验仍留在调用方。

## 入口

在仓库目录中查看命令帮助：

```bash
python3 scripts/gemini_vision.py --help
```

首次配置或排查 Key，读取 [`references/key-setup.md`](references/key-setup.md)，然后在仓库目录中验证：

```bash
python3 scripts/gemini_vision.py --check-key
```

## 集成方式

优先使用 JSON stdin/stdout 子进程接口，让调用 skill 无需安装 Google SDK：

```bash
python3 scripts/gemini_vision.py --request request.json --out result.json
```

`request.json` 最小结构：

```json
{
  "prompt": "逐图提取发票号码和总额；看不清填 null。",
  "schema": {
    "type": "object",
    "properties": {
      "records": {"type": "array", "items": {"type": "object"}}
    },
    "required": ["records"]
  },
  "items": [
    {"id": "invoice-1", "path": "/absolute/invoice.png", "context": {"page": 1}}
  ]
}
```

结果是包含 `batches[].item_ids` 和 `batches[].result` 的 envelope。调用方必须按 `item_ids` 合并，
并执行领域校验；不要把模型返回直接用于交易、写库或外部写操作。完整契约和 Python API 见
[`references/integration.md`](references/integration.md)。

## 运行规则

- 使用稳定模型 `gemini-3.6-flash`；调用方确有速度/成本需求时再显式覆盖。
- 默认每批最多 2 张、最多 3 批并发、瞬时错误最多重试 3 次；不要重新堆回单个大请求。
- 支持 PNG、JPEG、WebP；请求总量按原始字节和图片数双重切批。
- Key 只从 `GEMINI_API_KEY`、`GOOGLE_API_KEY` 或 macOS 钥匙串读取，绝不打印。
- 两个环境变量同时存在但不同则停止，避免静默用错 Key。
- 提示词要求保留 `item id`，schema 也应包含对应标识，避免跨图串行。
- 使用结构化输出不等于内容正确；数值恒等式、数量级、覆盖率和必填字段必须由调用方复核。

## 职责边界

本 skill 负责：鉴权、图片编码、分批、并发、重试、Gemini 调用、JSON 解析和通用 envelope。

调用 skill 负责：图片裁剪、业务 prompt/schema、跨批合并、别名处理、字段归一化、领域校验、落盘与部署。
