"""LLM provider configuration and request helpers for company agents."""

from __future__ import annotations

import dataclasses
import json
import os
import threading
import urllib.error
import urllib.request
from pathlib import Path


ROOT = Path(__file__).resolve().parent
ENV_FILE = ROOT / ".env"


@dataclasses.dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    provider: str
    base_url: str
    model: str
    api_key: str
    timeout_seconds: int
    temperature: float
    max_tokens: int
    agent_limit: int
    concurrency: int

    @property
    def available(self) -> bool:
        return self.enabled and self.provider != "none" and bool(self.base_url and self.model)

    @property
    def requires_bearer_token(self) -> bool:
        return self.provider == "chatgpt_oauth"


def parse_bool(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def parse_int(value: str, default: int, minimum: int | None = None) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    if minimum is not None:
        parsed = max(minimum, parsed)
    return parsed


def parse_float(value: str, default: float) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_env(path: Path = ENV_FILE) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        return env
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'")
        env[key.strip()] = value
    return env


def env_value(env: dict[str, str], key: str, default: str = "") -> str:
    return os.environ.get(key, env.get(key, default))


def read_secret_file(path_text: str) -> str:
    if not path_text:
        return ""
    path = Path(path_text).expanduser()
    if not path.exists():
        return ""
    return path.read_text(encoding="utf-8").strip()


def build_llm_config() -> LLMConfig:
    env = load_env()
    provider = env_value(env, "LLM_PROVIDER", "none").strip().lower()
    if provider == "gpt-oss":
        provider = "gpt_oss"
    if provider in {"chatgpt-oauth", "chatgpt oauth"}:
        provider = "chatgpt_oauth"

    if provider == "ollama":
        base_url = env_value(env, "OLLAMA_BASE_URL", "http://localhost:11434")
        model = env_value(env, "OLLAMA_MODEL", "gpt-oss:20b")
        api_key = ""
    elif provider == "gpt_oss":
        base_url = env_value(env, "GPT_OSS_BASE_URL", "http://localhost:8000/v1")
        model = env_value(env, "GPT_OSS_MODEL", "gpt-oss")
        api_key = env_value(env, "GPT_OSS_API_KEY", "")
    elif provider == "chatgpt_oauth":
        base_url = env_value(env, "CHATGPT_OAUTH_BASE_URL", "https://api.openai.com/v1")
        model = env_value(env, "CHATGPT_OAUTH_MODEL", "")
        api_key = env_value(env, "CHATGPT_OAUTH_ACCESS_TOKEN", "")
        if not api_key:
            api_key = read_secret_file(env_value(env, "CHATGPT_OAUTH_TOKEN_FILE", ""))
    else:
        base_url = ""
        model = ""
        api_key = ""

    return LLMConfig(
        enabled=parse_bool(env_value(env, "LLM_ENABLED", "false")),
        provider=provider,
        base_url=base_url.rstrip("/"),
        model=model,
        api_key=api_key,
        timeout_seconds=parse_int(env_value(env, "LLM_TIMEOUT_SECONDS", "30"), 30, minimum=1),
        temperature=parse_float(env_value(env, "LLM_TEMPERATURE", "0.2"), 0.2),
        max_tokens=parse_int(env_value(env, "LLM_MAX_TOKENS", "700"), 700, minimum=1),
        agent_limit=parse_int(env_value(env, "LLM_AGENT_LIMIT", "55"), 55, minimum=0),
        concurrency=parse_int(env_value(env, "LLM_CONCURRENCY", "2"), 2, minimum=1),
    )


def post_json(url: str, payload: dict[str, object], headers: dict[str, str], timeout: int) -> dict[str, object]:
    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json", **headers},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


def summarize_http_error(error: urllib.error.HTTPError) -> str:
    try:
        body = error.read().decode("utf-8", errors="replace").strip()
    except Exception:
        body = ""
    if not body:
        return f"HTTP {error.code}: {error.reason}"
    try:
        payload = json.loads(body)
    except json.JSONDecodeError:
        payload = None
    if isinstance(payload, dict):
        detail = payload.get("error")
        if isinstance(detail, dict):
            message = detail.get("message")
            code = detail.get("code")
            error_type = detail.get("type")
            parts = [f"HTTP {error.code}"]
            if error_type:
                parts.append(str(error_type))
            if code:
                parts.append(str(code))
            if message:
                parts.append(str(message))
            return ": ".join(parts)
    return f"HTTP {error.code}: {body[:500]}"


def call_llm(
    config: LLMConfig,
    system_prompt: str,
    user_prompt: str,
    semaphore: threading.Semaphore | None = None,
) -> tuple[str | None, str | None]:
    if not config.available:
        return None, "LLM disabled or incomplete configuration"
    if config.requires_bearer_token and not config.api_key:
        return None, f"{config.provider} requires a bearer token"

    try:
        if semaphore is not None:
            semaphore.acquire()
        if config.provider == "ollama":
            response = post_json(
                f"{config.base_url}/api/chat",
                {
                    "model": config.model,
                    "stream": False,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "options": {
                        "temperature": config.temperature,
                        "num_predict": config.max_tokens,
                    },
                },
                headers={},
                timeout=config.timeout_seconds,
            )
            message = response.get("message", {})
            if isinstance(message, dict):
                content = message.get("content")
                return str(content).strip() if content else None, None
            return None, "Ollama response did not include message.content"

        if config.provider == "gpt_oss":
            headers = {}
            if config.api_key:
                headers["Authorization"] = f"Bearer {config.api_key}"
            response = post_json(
                f"{config.base_url}/chat/completions",
                {
                    "model": config.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                },
                headers=headers,
                timeout=config.timeout_seconds,
            )
            choices = response.get("choices", [])
            if isinstance(choices, list) and choices:
                message = choices[0].get("message", {})
                if isinstance(message, dict):
                    content = message.get("content")
                    return str(content).strip() if content else None, None
            return None, "gpt_oss response did not include choices[0].message.content"

        if config.provider == "chatgpt_oauth":
            response = post_json(
                f"{config.base_url}/chat/completions",
                {
                    "model": config.model,
                    "messages": [
                        {"role": "system", "content": system_prompt},
                        {"role": "user", "content": user_prompt},
                    ],
                    "temperature": config.temperature,
                    "max_tokens": config.max_tokens,
                },
                headers={"Authorization": f"Bearer {config.api_key}"},
                timeout=config.timeout_seconds,
            )
            choices = response.get("choices", [])
            if isinstance(choices, list) and choices:
                message = choices[0].get("message", {})
                if isinstance(message, dict):
                    content = message.get("content")
                    return str(content).strip() if content else None, None
            return None, "chatgpt_oauth response did not include choices[0].message.content"

        return None, f"Unsupported LLM provider: {config.provider}"
    except urllib.error.HTTPError as error:
        return None, summarize_http_error(error)
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError, KeyError, TypeError) as error:
        return None, f"{type(error).__name__}: {error}"
    finally:
        if semaphore is not None:
            semaphore.release()
