#!/usr/bin/env python3
"""SessionStart — Claude Code 버전이 지난 세션 이후 올라갔으면 알린다.

CronCreate 는 세션이 끝나면 사라져서 주기 작업에 못 쓴다 (2026-08-17 확인).
Claude Code 는 자동 업데이트되므로 "최신인가" 가 아니라 "지난번 이후 뭐가 바뀌었나" 가
필요한 정보고, 그건 네트워크 없이 설치된 버전만 비교하면 판정된다.

- 상태 파일: ~/.claude/.version-seen  (마지막으로 알린 버전 한 줄)
- 버전이 같으면 출력 없이 exit 0. 첫 실행도 조용히 기록만 하고 끝낸다.
- 어떤 실패든 조용히 통과시킨다. 훅 버그가 세션 시작을 막으면 안 된다.
"""
import json
import os
import sys

STATE = os.path.expanduser("~/.claude/.version-seen")

# 설치 경로 후보 — 네이티브(npm global) 우선, 그다음 레거시 로컬
CANDIDATES = [
    os.path.expanduser("~/.npm-global/lib/node_modules/@anthropic-ai/claude-code/package.json"),
    os.path.expanduser("~/.claude/local/node_modules/@anthropic-ai/claude-code/package.json"),
    "/usr/lib/node_modules/@anthropic-ai/claude-code/package.json",
    "/usr/local/lib/node_modules/@anthropic-ai/claude-code/package.json",
]


def installed_version():
    for p in CANDIDATES:
        try:
            with open(p, encoding="utf-8") as f:
                v = json.load(f).get("version")
            if isinstance(v, str) and v.strip():
                return v.strip()
        except Exception:
            continue
    return None


def vtuple(v):
    """3.4.5 → (3,4,5). 비교 불가능한 형식이면 None."""
    parts = v.split(".")
    try:
        return tuple(int(p) for p in parts[:3])
    except ValueError:
        return None


def main():
    cur = installed_version()
    if not cur:
        return

    prev = None
    try:
        with open(STATE, encoding="utf-8") as f:
            prev = f.read().strip() or None
    except Exception:
        pass

    # 상태 먼저 기록 — 알림 생성에 실패해도 다음 세션에서 같은 알림이 반복되지 않게
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        with open(STATE, "w", encoding="utf-8") as f:
            f.write(cur + "\n")
    except Exception:
        return

    if prev is None or prev == cur:
        return  # 첫 실행이거나 변화 없음 → 조용히

    a, b = vtuple(prev), vtuple(cur)
    if a is None or b is None:
        return  # 상태 파일이 깨졌거나 버전 형식이 낯설다 → 엉터리 알림보다 침묵
    if b < a:
        return  # 다운그레이드는 알리지 않는다 (롤백은 의도된 행동)

    print(
        f"## Claude Code 업데이트됨: {prev} → {cur}\n"
        f"새로 생긴 기능이 세팅에 반영할 만한지 확인하려면 CHANGELOG 를 보라 "
        f"(github.com/anthropics/claude-code · `claude-code-guide` 에이전트). "
        f"반입 판단은 `setup-maintenance` 의 4항목 게이트를 따른다 — "
        f"실제로 쓸 것인가 / 기존 스킬 한 섹션이면 되는가 / 안정화됐는가 / 공식문서 베끼기 아닌가."
    )


try:
    main()
except Exception:
    pass
sys.exit(0)
