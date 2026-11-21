#!/usr/bin/env python3
"""PostToolUse(Write|Edit|MultiEdit) — 방금 편집한 .py 에 `ruff check` 를 돌려 결과를 컨텍스트로 붙인다.

왜 필요한가:
  편집 직후 린트 오류(미사용 import, 정의 안 된 이름, 잘못된 비교)를 그 자리에서 보면 다음 편집에서 바로 고친다.
  테스트까지 가서야 보면 원인 찾는 데 시간이 든다.

동작:
  - **opt-in**: 편집된 파일에서 위로 올라가며 `.claude/lint-on-edit` **파일**이 있는 디렉토리를 프로젝트 루트로 본다.
    없으면 아무것도 안 한다. 홈 디렉토리(`~/.claude/lint-on-edit`)는 루트로 치지 않는다 — 전역 opt-in 사고 방지.
  - ruff 선택: 프로젝트 venv(`.venv/bin/ruff`, `venv/bin/ruff`) 우선, 없으면 PATH 의 ruff, 그것도 없으면 건너뜀.
  - `--no-fix` 로 실행한다. 프로젝트 설정에 `fix = true` 가 있어도 훅이 파일을 고치지 않는다.
    `--force-exclude` 로 프로젝트의 exclude 설정을 따른다. 실행 위치는 프로젝트 루트(설정 탐색 기준).
  - **막지 않는다.** 위반이 있으면 `additionalContext` 로 붙이고 exit 0. 위반 없으면 출력 없음.
  - 입력 파싱 실패·ruff 실행 실패·타임아웃은 조용히 통과한다 (파싱 실패는 hook-errors.log 에 기록).

입력: stdin JSON / 출력: 위반 시 additionalContext JSON, 아니면 출력 없이 exit 0
환경변수: LINT_ON_EDIT_TIMEOUT (초, 기본 5) — 테스트용
"""

import json
import os
import shutil
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hooklib import log_hook_error  # noqa: E402

MARKER = os.path.join(".claude", "lint-on-edit")
MAX_LINES = 20


def find_root(path):
    home = os.path.realpath(os.path.expanduser("~"))
    d = os.path.dirname(os.path.realpath(path))
    while True:
        if d != home and os.path.isfile(os.path.join(d, MARKER)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def find_ruff(root):
    for venv in (".venv", "venv"):
        p = os.path.join(root, venv, "bin", "ruff")
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p
    return shutil.which("ruff")


def main():
    try:
        data = json.load(sys.stdin)
        tool = data.get("tool_name", "")
        path = (data.get("tool_input") or {}).get("file_path", "")
    except Exception as e:
        log_hook_error("lint-on-edit", f"stdin 파싱 실패: {e}")
        sys.exit(0)

    if tool not in ("Write", "Edit", "MultiEdit") or not isinstance(path, str) or not path.endswith(".py"):
        sys.exit(0)
    if not os.path.isabs(path):
        path = os.path.join(data.get("cwd") or os.getcwd(), path)
    if not os.path.isfile(path):
        sys.exit(0)

    root = find_root(path)
    if not root:
        sys.exit(0)
    ruff = find_ruff(root)
    if not ruff:
        sys.exit(0)

    try:
        timeout = float(os.environ.get("LINT_ON_EDIT_TIMEOUT", "5"))
        r = subprocess.run([ruff, "check", "--no-fix", "--force-exclude", "--output-format", "concise", path],
                           cwd=root, capture_output=True, text=True, timeout=timeout)
    except Exception:
        sys.exit(0)

    # ruff: 0 = 위반 없음, 1 = 위반 있음, 2 = 설정 오류 등 → 1 만 보고한다
    if r.returncode != 1:
        sys.exit(0)
    lines = [ln for ln in r.stdout.splitlines() if ln.strip() and not ln.startswith(("Found ", "[*]", "No fixes"))]
    if not lines:
        sys.exit(0)
    shown = lines[:MAX_LINES]
    more = f"\n… 외 {len(lines) - MAX_LINES}건" if len(lines) > MAX_LINES else ""
    rel = os.path.relpath(path, root)
    msg = (f"[lint-on-edit] 방금 편집한 {rel} 에 ruff 위반 {len(lines)}건 (차단 아님 — 이번 변경과 관련 있으면 고친다, "
           f"원래 있던 것이면 손대지 말고 필요 시 보고):\n" + "\n".join(shown) + more)
    print(json.dumps({"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": msg}},
                     ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
