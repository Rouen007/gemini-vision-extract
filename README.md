# gemini-vision-extract

通过共享 Gemini 运行时批量读图并输出结构化 JSON；用于 OCR、截图字段提取、图像比较及该运行时配置排障，保留 schema、重试与并发限制。

## 用途与使用方式

这是一个 Agent skill（Claude Code / Codex 通用格式），入口是 `SKILL.md`：
agent 按其中的 `description` 判断何时触发，按正文流程执行。脚本、参数和数据口径以 `SKILL.md` 为准。
人工使用时直接阅读 `SKILL.md`；带脚本的按其中给出的命令运行。

## 目录

- `.gitignore`
- `SKILL.md`
- `requirements.txt`
- `.venv/`
- `agents/`
- `references/`
- `scripts/`
- `tests/`
