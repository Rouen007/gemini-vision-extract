#!/usr/bin/env python3
"""Reusable Gemini image-to-JSON runtime.

The CLI keeps stdout machine-readable. Progress and errors go to stderr, and API
keys are never printed. See ../references/integration.md for the request contract.
"""

from __future__ import annotations

import argparse
import base64
import getpass
import json
import mimetypes
import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable


DEFAULT_MODEL = "gemini-3.6-flash"
KEYCHAIN_SERVICES = ("gemini-api-key",)
MAX_RAW_BATCH = 12 * 1024 * 1024
MAX_IMAGES_PER_BATCH = 2
DEFAULT_CONCURRENCY = 3
DEFAULT_ATTEMPTS = 3
SUPPORTED_MIME = {"image/png", "image/jpeg", "image/webp"}


def safe_error(exc: Exception, api_key: str | None = None) -> str:
    """Redact known credential values before an exception reaches stderr."""
    message = str(exc)
    secrets = {
        api_key or "",
        os.environ.get("GEMINI_API_KEY", "").strip(),
        os.environ.get("GOOGLE_API_KEY", "").strip(),
    }
    for secret in secrets:
        if secret:
            message = message.replace(secret, "[REDACTED]")
    return message


def resolve_api_key(
    env: dict[str, str] | None = None,
    services: tuple[str, ...] = KEYCHAIN_SERVICES,
) -> tuple[str, str]:
    env = os.environ if env is None else env
    gemini = env.get("GEMINI_API_KEY", "").strip()
    google = env.get("GOOGLE_API_KEY", "").strip()
    if gemini and google and gemini != google:
        raise RuntimeError(
            "GEMINI_API_KEY 与 GOOGLE_API_KEY 同时存在但值不同；请只保留一个。"
        )
    if gemini or google:
        return (gemini or google), ("GEMINI_API_KEY" if gemini else "GOOGLE_API_KEY")

    if sys.platform == "darwin":
        for service in services:
            proc = subprocess.run(
                ["security", "find-generic-password", "-a", getpass.getuser(),
                 "-s", service, "-w"],
                capture_output=True, text=True,
            )
            key = proc.stdout.strip()
            if proc.returncode == 0 and key:
                return key, f"macOS Keychain:{service}"
    raise RuntimeError(
        "未找到 Gemini Key；设置 GEMINI_API_KEY / GOOGLE_API_KEY，或按 "
        "references/key-setup.md 存入 macOS 钥匙串。"
    )


def _sdk():
    try:
        from google import genai
    except ImportError as exc:
        raise RuntimeError("缺少 google-genai；请安装 requirements.txt") from exc
    return genai


def check_api_key(api_key: str, model: str = DEFAULT_MODEL) -> str:
    client = _sdk().Client(api_key=api_key)
    try:
        info = client.models.get(model=model)
        return str(getattr(info, "name", None) or model)
    finally:
        client.close()


def _mime_type(path: Path) -> str:
    mime = mimetypes.guess_type(path.name)[0]
    if mime not in SUPPORTED_MIME:
        raise ValueError(f"不支持的图片格式：{path}（仅 PNG/JPEG/WebP）")
    return mime


def prepare_items(items: list[dict[str, Any]]) -> list[dict[str, Any]]:
    if not items:
        raise ValueError("items 不能为空")
    prepared = []
    seen = set()
    for raw in items:
        ident = str(raw.get("id") or "").strip()
        if not ident:
            raise ValueError("每个 item 都必须有非空 id")
        if ident in seen:
            raise ValueError(f"item id 重复：{ident}")
        seen.add(ident)
        path = Path(str(raw.get("path") or "")).expanduser()
        if not path.is_absolute():
            raise ValueError(f"图片路径必须是绝对路径：{path}")
        if not path.is_file():
            raise FileNotFoundError(f"图片不存在：{path}")
        _mime_type(path)
        prepared.append({
            "id": ident,
            "path": path,
            "context": raw.get("context"),
            "_bytes": path.stat().st_size,
        })
    return prepared


def make_batches(
    items: list[dict[str, Any]],
    max_raw_bytes: int = MAX_RAW_BATCH,
    max_items: int = MAX_IMAGES_PER_BATCH,
) -> list[list[dict[str, Any]]]:
    if max_raw_bytes <= 0 or max_items <= 0:
        raise ValueError("分批上限必须大于 0")
    batches: list[list[dict[str, Any]]] = []
    current: list[dict[str, Any]] = []
    used = 0
    for item in items:
        size = int(item["_bytes"])
        if size > max_raw_bytes:
            raise ValueError(f"单张图片超过批次上限：{item['path']} ({size} bytes)")
        if current and (used + size > max_raw_bytes or len(current) >= max_items):
            batches.append(current)
            current, used = [], 0
        current.append(item)
        used += size
    if current:
        batches.append(current)
    return batches


def _api_input(batch: list[dict[str, Any]], prompt: str) -> list[dict[str, Any]]:
    parts: list[dict[str, Any]] = [{"type": "text", "text": prompt}]
    for item in batch:
        metadata = {"id": item["id"], "context": item.get("context")}
        parts.append({
            "type": "text",
            "text": "下一张图片元数据：" + json.dumps(metadata, ensure_ascii=False),
        })
        parts.append({
            "type": "image",
            "data": base64.b64encode(item["path"].read_bytes()).decode("ascii"),
            "mime_type": _mime_type(item["path"]),
        })
    return parts


def _call_batch(
    batch: list[dict[str, Any]],
    prompt: str,
    schema: dict[str, Any],
    api_key: str,
    model: str,
    thinking_level: str,
    timeout: float,
) -> dict[str, Any]:
    client = _sdk().Client(api_key=api_key)
    try:
        interaction = client.interactions.create(
            model=model,
            input=_api_input(batch, prompt),
            response_format={
                "type": "text",
                "mime_type": "application/json",
                "schema": schema,
            },
            generation_config={"thinking_level": thinking_level},
            timeout=timeout,
        )
    finally:
        client.close()
    try:
        result = json.loads(interaction.output_text)
    except (TypeError, json.JSONDecodeError) as exc:
        raise RuntimeError("Gemini 返回的不是有效 JSON") from exc
    if not isinstance(result, dict):
        raise RuntimeError("Gemini 返回的顶层不是对象")
    return result


def _call_with_retry(
    batch: list[dict[str, Any]],
    prompt: str,
    schema: dict[str, Any],
    api_key: str,
    model: str,
    thinking_level: str,
    timeout: float,
    attempts: int,
) -> dict[str, Any]:
    retryable = ("disconnect", "timeout", "timed out", "429", "500", "502", "503", "504")
    for attempt in range(1, attempts + 1):
        try:
            return _call_batch(batch, prompt, schema, api_key, model, thinking_level, timeout)
        except Exception as exc:
            message = str(exc).lower()
            if attempt == attempts or not any(token in message for token in retryable):
                raise
            time.sleep(2 ** (attempt - 1))
    raise AssertionError("unreachable")


def extract_items(
    items: list[dict[str, Any]],
    prompt: str,
    schema: dict[str, Any],
    *,
    api_key: str | None = None,
    key_source: str | None = None,
    model: str = DEFAULT_MODEL,
    max_raw_batch_bytes: int = MAX_RAW_BATCH,
    max_items_per_batch: int = MAX_IMAGES_PER_BATCH,
    concurrency: int = DEFAULT_CONCURRENCY,
    attempts: int = DEFAULT_ATTEMPTS,
    thinking_level: str = "minimal",
    timeout: float = 180,
    progress: Callable[[int, int, list[str]], None] | None = None,
) -> dict[str, Any]:
    if not prompt.strip():
        raise ValueError("prompt 不能为空")
    if not isinstance(schema, dict) or not schema:
        raise ValueError("schema 必须是非空 JSON 对象")
    if concurrency <= 0 or attempts <= 0:
        raise ValueError("concurrency 和 attempts 必须大于 0")
    prepared = prepare_items(items)
    batches = make_batches(prepared, max_raw_batch_bytes, max_items_per_batch)
    if api_key is None:
        api_key, key_source = resolve_api_key()
    source = key_source or "provided-by-caller"
    if progress:
        for index, batch in enumerate(batches, 1):
            progress(index, len(batches), [item["id"] for item in batch])

    def run(batch):
        return _call_with_retry(
            batch, prompt, schema, api_key, model, thinking_level, timeout, attempts,
        )

    with ThreadPoolExecutor(max_workers=min(concurrency, len(batches))) as pool:
        results = list(pool.map(run, batches))
    return {
        "ok": True,
        "model": model,
        "input_count": len(prepared),
        "batch_count": len(batches),
        "key_source": source,
        "batches": [
            {"item_ids": [item["id"] for item in batch], "result": result}
            for batch, result in zip(batches, results)
        ],
    }


def _read_request(path: str) -> dict[str, Any]:
    text = sys.stdin.read() if path == "-" else Path(path).expanduser().read_text(encoding="utf-8")
    data = json.loads(text)
    if not isinstance(data, dict):
        raise ValueError("request 顶层必须是 JSON 对象")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Gemini 批量图片 → JSON Schema 结构化结果")
    parser.add_argument("--request", help="请求 JSON 文件；- 表示 stdin")
    parser.add_argument("--out", help="输出 JSON 文件；默认 stdout")
    parser.add_argument("--check-key", action="store_true", help="只验证 Key/模型，不上传图片")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--dry-run", action="store_true", help="只校验请求与分批，不调用 Gemini")
    args = parser.parse_args()
    api_key = None
    try:
        api_key, key_source = resolve_api_key()
        if args.check_key:
            name = check_api_key(api_key, args.model)
            print(json.dumps({"ok": True, "model": name, "key_source": key_source}, ensure_ascii=False))
            return 0
        if not args.request:
            parser.error("必须提供 --request，或使用 --check-key")
        request = _read_request(args.request)
        prepared = prepare_items(request.get("items") or [])
        batches = make_batches(
            prepared,
            int(request.get("max_raw_batch_bytes", MAX_RAW_BATCH)),
            int(request.get("max_items_per_batch", MAX_IMAGES_PER_BATCH)),
        )
        if args.dry_run:
            envelope = {
                "ok": True,
                "dry_run": True,
                "model": request.get("model", args.model),
                "input_count": len(prepared),
                "batch_count": len(batches),
                "batches": [[item["id"] for item in batch] for batch in batches],
                "key_source": key_source,
            }
        else:
            def progress(index, total, ids):
                print(f"提交第 {index}/{total} 批：{', '.join(ids)}", file=sys.stderr)

            envelope = extract_items(
                request.get("items") or [],
                str(request.get("prompt") or ""),
                request.get("schema") or {},
                api_key=api_key,
                key_source=key_source,
                model=str(request.get("model", args.model)),
                max_raw_batch_bytes=int(request.get("max_raw_batch_bytes", MAX_RAW_BATCH)),
                max_items_per_batch=int(request.get("max_items_per_batch", MAX_IMAGES_PER_BATCH)),
                concurrency=int(request.get("concurrency", DEFAULT_CONCURRENCY)),
                attempts=int(request.get("attempts", DEFAULT_ATTEMPTS)),
                thinking_level=str(request.get("thinking_level", "minimal")),
                timeout=float(request.get("timeout", 180)),
                progress=progress,
            )
        encoded = json.dumps(envelope, ensure_ascii=False, indent=2) + "\n"
        if args.out:
            Path(args.out).expanduser().write_text(encoded, encoding="utf-8")
        else:
            sys.stdout.write(encoded)
        return 0
    except Exception as exc:
        print(f"Gemini vision 失败：{safe_error(exc, api_key)}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
