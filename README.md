# Gemini 图像结构化提取

用 Gemini 批量读取 PNG、JPEG、WebP 图片，并按 JSON Schema 返回结构化结果。这个仓库提供可复用的运行时 CLI 和 agent skill，负责 API 鉴权、图片编码、分批、并发、重试和 JSON envelope；业务字段定义与校验仍由调用方负责。

## 适用场景

- 从截图、单据或图表中提取字段。
- 对多张图片使用同一提示词和 schema 做批量识别。
- 让其他 skill 通过子进程接口复用统一的 Gemini 调用方式。

模型输出可能读错文字、数字、标的代码或图表。涉及金额、交易、写库或外部动作时，调用方必须独立复核结果。

## 安装

需要 Python 3.10+ 和可访问 Gemini API 的网络。依赖只有 google-genai：

~~~bash
git clone https://github.com/OWNER/REPOSITORY.git
cd gemini-vision-extract
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python3 scripts/gemini_vision.py --help
~~~

将命令中的 OWNER/REPOSITORY 替换成此仓库的地址。使用 agent 时，将整个仓库作为 skill 安装，确保 SKILL.md、scripts/ 和 references/ 保持相对位置。

## 配置 API Key

支持 GEMINI_API_KEY 或 GOOGLE_API_KEY 环境变量；macOS 上也可使用 Passwords / Keychain 中名为 gemini-api-key 的通用项目。两个环境变量同时存在但值不同会停止运行，避免静默使用错误凭据。

推荐按 [Key 配置说明](references/key-setup.md) 把 Key 录入系统钥匙串。Key 不要写入脚本、请求 JSON、README、shell 命令参数或版本控制。只验证密钥和模型、不上传图片：

~~~bash
python3 scripts/gemini_vision.py --check-key
~~~

## 快速运行

准备 request.json。每个图片路径必须是绝对路径，item id 必须非空且不能重复：

~~~json
{
  "prompt": "逐图提取发票号码和总额；看不清填 null。返回每张图片的 item id。",
  "schema": {
    "type": "object",
    "properties": {
      "records": {
        "type": "array",
        "items": {
          "type": "object",
          "properties": {
            "id": {"type": "string"},
            "invoice_number": {"type": ["string", "null"]},
            "total": {"type": ["number", "null"]}
          },
          "required": ["id", "invoice_number", "total"]
        }
      }
    },
    "required": ["records"]
  },
  "items": [
    {
      "id": "invoice-1",
      "path": "/absolute/path/to/invoice.png",
      "context": {"page": 1}
    }
  ]
}
~~~

先确认 Key 已配置，再做图片输入和分批校验（dry-run 不调用 Gemini，但当前 CLI 仍会先解析 Key），然后正式运行：

~~~bash
python3 scripts/gemini_vision.py --request request.json --dry-run
python3 scripts/gemini_vision.py --request request.json --out result.json
~~~

默认把 JSON 写到 stdout；指定 --out 后写入文件。成功响应包含 batches，每批带 item_ids 和 result。调用方应按 item_ids 合并并检查缺失、重复及业务合理性；失败时进程返回非零，stderr 为去敏错误。

## 默认行为与限制

- 默认模型为 gemini-3.6-flash，可通过 --model 覆盖；模型是否可用取决于 Gemini API 当前提供情况。
- 默认每批最多 2 张、每批原图总量上限 12 MiB、并发 3 批、瞬时失败最多尝试 3 次。
- 仅支持 PNG、JPEG、WebP；图片路径必须是绝对路径。
- 提示词应要求逐图返回 id，schema 也应包含 id 或同义标识，以免跨图结果串位。
- Key 只允许来自上述环境变量或 macOS Keychain；运行时不输出 Key 值。
- 调用方负责裁剪图片、合并批次、字段归一化、领域校验和落盘。

## 详细文档

- [SKILL.md](SKILL.md)：运行原则与职责边界。
- [集成契约](references/integration.md)：请求 / 响应 schema、子进程与 Python API 示例。
- [Key 配置与排错](references/key-setup.md)：Keychain、环境变量、轮换和常见错误。
- **scripts/gemini_vision.py**：CLI 实现。

## 许可证

当前仓库未附 LICENSE 文件。公开可见不等于授予复制、修改或再分发许可。
