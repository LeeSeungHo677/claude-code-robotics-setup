#!/usr/bin/env python3
"""PostToolUse(Bash|Write|Edit|MultiEdit|NotebookEdit|WebFetch|mcp__.*) — 도구 실행 기록 + 같은 명령 반복 경고.

왜 필요한가:
  1) "그때 무엇을 실행했나" 를 나중에 확인할 수단이 없었다. 특히 ask 등급 명령
     (ros2 run/launch/param set/bag play)이 승인돼 실제로 실행된 기록은 사고 조사(incident-analysis)와
     파라미터 변경 이력(robot:tuning-log)의 근거가 된다.
  2) 같은 명령을 계속 다시 돌리는 루프를 모델의 자가 보고가 아니라 기계적으로 센다.
     CLAUDE.md 의 "같은 증상 3번 고쳐도 안 되면 멈추고 보고" 규칙을 거드는 장치다.

기록: ~/.claude/logs/tools-YYYY-MM.jsonl  (로컬에만. 디렉토리 권한 700)
  {ts, sid, cwd, tool, target}  — target 은 Bash 명령(500자) / 파일 경로 / URL / MCP 도구 이름.
  명령 안의 시크릿은 secret-scanner 패턴으로 가린다. 도구 출력은 기록하지 않는다.
보존: 180일 지난 월 파일은 지운다.

출력: 같은 Bash 명령이 연속 3회면 additionalContext 경고. 그 외에는 출력 없음. 절대 막지 않는다.
"""

import glob
import hashlib
import importlib.util
import json
import os
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hooklib import log_hook_error  # noqa: E402

LOG_DIR = os.path.expanduser("~/.claude/logs")
REPEAT_N = 3
KEEP_DAYS = 180


def _secret_patterns():
    try:
        spec = importlib.util.spec_from_file_location("secret_scanner", os.path.join(HERE, "secret-scanner.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return [rx for _, rx in mod.PATTERNS]
    except Exception:
        return []


def mask(s):
    for rx in _secret_patterns():
        s = rx.sub("«REDACTED»", s)
    return s


def target_of(tool, ti):
    if tool == "Bash":
        return mask(ti.get("command", ""))[:500]
    if tool in ("Write", "Edit", "MultiEdit"):
        return ti.get("file_path", "")
    if tool == "NotebookEdit":
        return ti.get("notebook_path", "")
    if tool == "WebFetch":
        return mask(ti.get("url", ""))[:300]
    return tool


def repeat_count(sid, key):
    """세션별로 직전 Bash 명령과 연속 횟수를 기억한다."""
    path = os.path.join(LOG_DIR, f".repeat-{sid[:16] or 'nosession'}.json")
    try:
        with open(path, encoding="utf-8") as f:
            st = json.load(f)
    except Exception:
        st = {}
    n = st.get("n", 0) + 1 if st.get("key") == key else 1
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"key": key, "n": n}, f)
    except OSError:
        pass
    return n


def housekeeping():
    now = time.time()
    for p in glob.glob(os.path.join(LOG_DIR, "tools-*.jsonl")):
        if now - os.path.getmtime(p) > KEEP_DAYS * 86400:
            os.remove(p)
    for p in glob.glob(os.path.join(LOG_DIR, ".repeat-*.json")):
        if now - os.path.getmtime(p) > 2 * 86400:
            os.remove(p)


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as e:
        log_hook_error("tool-run-log", f"stdin 파싱 실패: {e}")
        sys.exit(0)

    tool = data.get("tool_name", "")
    ti = data.get("tool_input") or {}
    sid = data.get("session_id", "") or ""
    target = target_of(tool, ti)

    try:
        os.makedirs(LOG_DIR, mode=0o700, exist_ok=True)
        rec = {"ts": time.strftime("%Y-%m-%dT%H:%M:%S"), "sid": sid[:8], "cwd": data.get("cwd", ""),
               "tool": tool, "target": target}
        with open(os.path.join(LOG_DIR, time.strftime("tools-%Y-%m.jsonl")), "a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
        if time.localtime().tm_min == 0:      # 정리는 가끔만
            housekeeping()
    except Exception as e:
        log_hook_error("tool-run-log", f"기록 실패: {e}")

    if tool != "Bash" or not target.strip():
        sys.exit(0)
    key = hashlib.sha1(" ".join(target.split()).encode()).hexdigest()
    n = repeat_count(sid, key)
    if n >= REPEAT_N and n % REPEAT_N == 0:
        msg = (f"[tool-run-log] 같은 명령을 {n}번 연속 실행했습니다: `{target[:80]}`. "
               "결과가 바뀔 이유가 없다면 접근을 바꾸거나, 시도 내역·가설을 정리해 사용자에게 보고한다 "
               "(CLAUDE.md: 같은 증상 3번 고쳐도 안 되면 멈추고 보고). 의도한 폴링이면 무시해도 된다.")
        print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}},
                         ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
