#!/usr/bin/env python3
"""version-watch.py 훅 테스트 — 알림 케이스와 침묵 케이스 양쪽.

임시 HOME 을 만들어 실제 ~/.claude 를 건드리지 않는다.
실행: python3 ~/.claude/hooks/test_version_watch.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))   # 설치 위치와 무관하게 옆의 훅을 테스트한다
HOOK = os.path.join(HERE, "version-watch.py")
PKG_REL = ".npm-global/lib/node_modules/@anthropic-ai/claude-code/package.json"


def run(home, version, seen=None, write_pkg=True):
    """임시 HOME 에서 훅을 1회 실행하고 (stdout, exit code, 남은 상태) 반환."""
    if write_pkg:
        p = os.path.join(home, PKG_REL)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        with open(p, "w", encoding="utf-8") as f:
            json.dump({"name": "@anthropic-ai/claude-code", "version": version}, f)

    state = os.path.join(home, ".claude/.version-seen")
    os.makedirs(os.path.dirname(state), exist_ok=True)
    if seen is None:
        if os.path.exists(state):
            os.remove(state)
    else:
        with open(state, "w", encoding="utf-8") as f:
            f.write(seen)

    env = dict(os.environ, HOME=home)
    r = subprocess.run([sys.executable, HOOK], capture_output=True, text=True,
                       env=env, input="{}", timeout=10)
    after = None
    if os.path.exists(state):
        with open(state, encoding="utf-8") as f:
            after = f.read().strip()
    return r.stdout.strip(), r.returncode, after


CASES = [
    # (설명, seen, 설치버전, pkg존재, 출력있어야?, 기대 상태)
    ("첫 실행 — 조용히 기록만",          None,      "2.1.233", True,  False, "2.1.233"),
    ("변화 없음 — 침묵",                 "2.1.233", "2.1.233", True,  False, "2.1.233"),
    ("업그레이드 — 알림",                "2.1.233", "2.2.0",   True,  True,  "2.2.0"),
    ("패치 업그레이드 — 알림",           "2.1.233", "2.1.240", True,  True,  "2.1.240"),
    ("다운그레이드(롤백) — 침묵",        "2.2.0",   "2.1.233", True,  False, "2.1.233"),
    ("빈 상태 파일 — 첫 실행 취급",      "",        "2.1.233", True,  False, "2.1.233"),
    ("깨진 버전 문자열 — 침묵",          "abc",     "2.1.233", True,  False, "2.1.233"),
    ("package.json 없음 — 완전 무동작",  "2.1.233", "-",       False, False, "2.1.233"),
]


def main():
    fails = 0
    for desc, seen, ver, pkg, want_out, want_state in CASES:
        home = tempfile.mkdtemp(prefix="vw-test-")
        try:
            out, rc, state = run(home, ver, seen, pkg)
            ok = True
            if rc != 0:
                ok = False; why = f"exit {rc} (0이어야 함)"
            elif want_out and not out:
                ok = False; why = "알림이 나와야 하는데 없음"
            elif not want_out and out:
                ok = False; why = f"조용해야 하는데 출력함: {out[:60]}"
            elif state != want_state:
                ok = False; why = f"상태 {state!r} (기대 {want_state!r})"
            if ok:
                print(f"  PASS  {desc}")
            else:
                print(f"  FAIL  {desc} — {why}"); fails += 1
        finally:
            shutil.rmtree(home, ignore_errors=True)
    print(f"\n{len(CASES) - fails}/{len(CASES)} 통과")
    sys.exit(1 if fails else 0)


main()
