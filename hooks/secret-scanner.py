#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit) — 파일에 기록되기 *전에* 시크릿 유출을 차단.
   PreToolUse(WebFetch|WebSearch|mcp__.*) — 외부로 나가는 요청 인자에 시크릿이 실리는 것을 차단 (2026-10-18).

입력: stdin JSON (Claude Code 규격)
동작: tool_input 안에 들어있는 '앞으로 쓰일 내용'을 검사한다.
      (디스크의 기존 파일이 아니라 write 예정 콘텐츠를 봐야 실제로 막힌다)
출력: 탐지 시 stdout에 deny JSON + stderr에 사유, exit 2
"""

import json
import os
import re
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
try:
    from hooklib import log_hook_error
except Exception:                    # 다른 훅이 이 파일을 모듈로 읽을 때도 깨지지 않게
    def log_hook_error(*_a, **_k):
        pass

# ── 탐지 패턴 ────────────────────────────────────────────────────────────────
PATTERNS = [
    ("AWS Access Key",      re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("AWS Secret Key",      re.compile(r"aws_secret_access_key\s*[:=]\s*['\"]?[A-Za-z0-9/+=]{40}")),
    ("GitHub Token",        re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9_]{36,}\b")),
    ("Anthropic API Key",   re.compile(r"\bsk-ant-[A-Za-z0-9_\-]{20,}")),
    ("OpenAI API Key",      re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_\-]{32,}")),
    ("Google API Key",      re.compile(r"\bAIza[0-9A-Za-z_\-]{35}\b")),
    ("Slack Token",         re.compile(r"\bxox[bpors]-[0-9a-zA-Z\-]{10,}")),
    ("Private Key Block",   re.compile(r"-----BEGIN (?:RSA |EC |DSA |OPENSSH |PGP )?PRIVATE KEY-----")),
    ("JWT Token",           re.compile(r"\beyJ[A-Za-z0-9_\-]{10,}\.eyJ[A-Za-z0-9_\-]{10,}\.[A-Za-z0-9_\-]{10,}")),
    ("DB URL with password", re.compile(r"\b(?:postgres|postgresql|mysql|mongodb|redis|amqp)(?:\+\w+)?://[^:/\s]+:[^@\s]{3,}@")),
    ("Generic Secret Assign", re.compile(
        r"(?i)\b(?:api[_\-]?key|secret[_\-]?key|access[_\-]?token|auth[_\-]?token|client[_\-]?secret|password|passwd)\s*[:=]\s*['\"][^'\"\s]{12,}['\"]")),
]

# 이 표식이 줄에 있으면 예제/플레이스홀더로 보고 통과
PLACEHOLDER = re.compile(
    r"(?i)(example|placeholder|your[_\-]?|changeme|dummy|sample|redacted|<[^>]+>|\bxxx+\b|\*{4,}|"
    r"os\.environ|os\.getenv|process\.env|getenv\(|System\.getenv|\$\{|\$\(|\bTODO\b|\bFIXME\b)")

# 검사 제외 경로
SKIP_PATH = re.compile(r"(?i)(\.env\.(example|sample|template)$|\.lock$|package-lock\.json$|"
                       r"(^|/)(node_modules|\.git|build|install|log|dist|__pycache__|\.venv|venv)/)")

BINARY_EXT = {".png", ".jpg", ".jpeg", ".gif", ".ico", ".pdf", ".zip", ".tar", ".gz", ".bz2",
              ".woff", ".woff2", ".ttf", ".eot", ".so", ".o", ".a", ".bin", ".pyc",
              ".db3", ".mcap", ".bag", ".pcd", ".ply", ".pt", ".pth", ".onnx", ".engine"}


def collect_text(tool_name, tool_input):
    """도구별로 '기록될 내용' 을 모은다."""
    chunks = []
    if tool_name == "Write":
        chunks.append(tool_input.get("content", ""))
    elif tool_name == "Edit":
        chunks.append(tool_input.get("new_string", ""))
    elif tool_name in ("MultiEdit", "NotebookEdit"):
        for e in tool_input.get("edits", []) or []:
            chunks.append(e.get("new_string", ""))
        chunks.append(tool_input.get("new_source", "") or "")
    return "\n".join(c for c in chunks if isinstance(c, str))


def is_egress(tool_name):
    return tool_name in ("WebFetch", "WebSearch") or tool_name.startswith("mcp__")


def egress_values(obj):
    """요청 인자 안의 문자열 값 전부 (URL 쿼리, prompt, MCP 인자 중첩 포함)."""
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from egress_values(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from egress_values(v)


def egress_findings(tool_input):
    """외부 요청은 줄 단위 placeholder 판정을 쓰지 않는다 — URL 에 'example.com' 만 있어도 통째로 통과돼 버린다.
    대신 **걸린 값 자체**가 placeholder 인지만 본다."""
    out = []
    for v in egress_values(tool_input):
        for name, rx in PATTERNS:
            m = rx.search(v)
            if m and not PLACEHOLDER.search(m.group(0)):
                out.append((0, name, m.group(0)[:12] + "…"))
                break
    return out


def deny(reason):
    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    print(reason, file=sys.stderr)
    sys.exit(2)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as e:
        log_hook_error("secret-scanner", f"stdin 파싱 실패: {e}")
        sys.exit(0)  # 입력을 못 읽으면 통과 (작업을 막지 않는다) — 대신 기록한다

    tool_name = data.get("tool_name", "")
    tool_input = data.get("tool_input", {}) or {}

    if is_egress(tool_name):
        findings = egress_findings(tool_input)
        if findings:
            detail = "\n".join(f"  - {name}: {snip}" for _, name, snip in findings[:5])
            deny(f"[secret-scanner] {tool_name} 요청 인자에 시크릿으로 보이는 값이 있어 차단했습니다 — "
                 f"외부 서비스로 나가면 회수할 수 없습니다.\n{detail}")
        sys.exit(0)

    file_path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""

    if SKIP_PATH.search(file_path):
        sys.exit(0)
    if os.path.splitext(file_path)[1].lower() in BINARY_EXT:
        sys.exit(0)

    text = collect_text(tool_name, tool_input)
    if not text.strip():
        sys.exit(0)

    findings = []
    for lineno, line in enumerate(text.split("\n"), start=1):
        if len(line) > 4000:          # 미니파이/데이터 라인은 오탐이 많다
            continue
        if PLACEHOLDER.search(line):
            continue
        for name, rx in PATTERNS:
            if rx.search(line):
                findings.append((lineno, name, line.strip()[:70]))
                break

    if not findings:
        sys.exit(0)

    where = os.path.basename(file_path) or tool_name
    detail = "\n".join(f"  - {name} (기록 예정 내용 {ln}번째 줄): {snippet}"
                       for ln, name, snippet in findings[:10])
    reason = (f"[secret-scanner] {where} 에 시크릿으로 보이는 값이 포함되어 차단했습니다.\n{detail}\n\n"
              f"환경변수/시크릿 매니저로 옮기거나, 예제라면 placeholder(YOUR_KEY, <token> 등)로 바꾸세요.")

    print(json.dumps({
        "hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason,
        }
    }))
    print(reason, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
