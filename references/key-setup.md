# Gemini Key 配置

## macOS 钥匙串（推荐）

从 [Google AI Studio](https://aistudio.google.com/apikey) 复制完整 Key。在终端执行：

```bash
security add-generic-password -U -a "$USER" -s gemini-api-key -w
```

出现 `password data for new item:` 后再粘贴 Key并回车；输入不回显属于正常行为。不要把 Key 写在
`-w` 后，否则会进入 shell 历史和进程参数。

验证 Google 鉴权且不上传图片。在仓库目录中运行：

```bash
python3 scripts/gemini_vision.py --check-key
```

## 环境变量（临时替代）

```bash
read -rs "GEMINI_API_KEY?Gemini API Key: " && echo
export GEMINI_API_KEY
```

脚本接受 `GEMINI_API_KEY` 或 `GOOGLE_API_KEY`。两者同时存在但值不同会停止。关闭终端后临时变量失效。

## 删除和轮换

先在 AI Studio 撤销旧 Key，再删除本机通用条目：

```bash
security delete-generic-password -a "$USER" -s gemini-api-key
```

轮换时直接重复推荐的 `add-generic-password -U` 命令即可覆盖。

## 常见错误

| 错误 | 处理 |
|---|---|
| `未找到 Gemini Key` | 重新执行钥匙串录入命令 |
| `API_KEY_INVALID` | 保存了示例、残缺值或已撤销 Key；重新复制完整 Key |
| 环境变量值冲突 | `unset GOOGLE_API_KEY` 或 `unset GEMINI_API_KEY` |
| `403 PERMISSION_DENIED` | 检查 Key 项目、API 权限和地区策略 |
| `429 RESOURCE_EXHAUSTED` | 等待配额恢复或更换有额度的项目 |
| `Server disconnected` | 保持小批请求；运行时会自动重试 |

排错只报告错误码、来源和长度；不要输出、截图或粘贴 Key。
