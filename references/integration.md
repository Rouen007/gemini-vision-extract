# 集成契约

## 请求

CLI 接受 `--request FILE`；`FILE` 可为 `-`，表示从 stdin 读取。请求对象字段：

| 字段 | 必需 | 说明 |
|---|---:|---|
| `prompt` | 是 | 领域提取指令 |
| `schema` | 是 | Gemini structured output 使用的 JSON Schema |
| `items` | 是 | `{id,path,context?}` 数组；path 必须为绝对路径 |
| `model` | 否 | 默认 `gemini-3.6-flash` |
| `max_items_per_batch` | 否 | 默认 2 |
| `max_raw_batch_bytes` | 否 | 默认 12 MiB |
| `concurrency` | 否 | 默认 3 |
| `attempts` | 否 | 默认 3 |
| `thinking_level` | 否 | 默认 `minimal` |

`context` 可以是字符串、数字、数组或对象。运行时在每张图片前插入：

```text
下一张图片元数据：{"id":"...","context":...}
```

Prompt 必须明确要求逐字返回 `id`，schema 应包含 `id` 或同义字段。

## 响应

成功：

```json
{
  "ok": true,
  "model": "gemini-3.6-flash",
  "input_count": 3,
  "batch_count": 2,
  "key_source": "macOS Keychain:gemini-api-key",
  "batches": [
    {"item_ids": ["a", "b"], "result": {}},
    {"item_ids": ["c"], "result": {}}
  ]
}
```

失败时进程返回非零，stderr 只含去敏后的错误。stdout 不返回半成品 envelope。

## 子进程集成

让通用 skill 自己管理 SDK 环境。先设置安装目录：

```bash
export GEMINI_VISION_SKILL_DIR="/path/to/gemini-vision-extract"
```

再调用运行时：

```python
import json, os, subprocess
from pathlib import Path

root = Path(os.environ["GEMINI_VISION_SKILL_DIR"]).expanduser()
run = subprocess.run(
    [str(root / ".venv/bin/python"), str(root / "scripts/gemini_vision.py"), "--request", "-"],
    input=json.dumps(request), text=True, capture_output=True,
)
if run.returncode:
    raise RuntimeError(run.stderr.strip())
envelope = json.loads(run.stdout)
results = [batch["result"] for batch in envelope["batches"]]
```

## Python API

调用方已安装 `google-genai` 时，可以把 `scripts/` 加入 `sys.path` 后使用：

```python
from gemini_vision import extract_items, resolve_api_key

key, source = resolve_api_key()
envelope = extract_items(items, prompt, schema, api_key=key)
```

Python API 输入的 `items` 与 JSON 请求一致；返回 envelope 与 CLI 一致。

## 调用方校验清单

- 输入图片数是否等于已解析数加未解决数。
- 每个输出 id 是否存在于输入，是否有遗漏或重复。
- 数值是否落在业务合理数量级。
- 可复算字段是否满足恒等式。
- 低置信或关键字段缺失时是否阻断外部写操作。
- 跨批同一实体如何合并，优先级是否确定。
