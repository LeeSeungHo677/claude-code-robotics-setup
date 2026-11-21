#!/usr/bin/env python3
"""lint-on-edit.py 테스트 — 표시(flag) / 무시(pass) 두 갈래 + 파일을 고치지 않는지.

이 훅은 막지 않는다. 실패 모드는 ① opt-in 안 한 프로젝트에서 떠드는 것 ② 파일을 몰래 고치는 것
③ 느리거나 깨져서 편집을 붙잡는 것. 셋 다 케이스로 고정한다.

실행: python3 ~/.claude/hooks/test_lint_on_edit.py   (standalone, PATH 에 ruff 필요)
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "lint-on-edit.py")
FLAG, PASS = "flag", "pass"

BAD = "import os\n\n\ndef f(x):\n    return x == None\n"      # F401 미사용 import, E711 None 비교
CLEAN = "def f(x):\n    return x + 1\n"


def run(payload, env=None, raw=None):
    t0 = time.time()
    r = subprocess.run([sys.executable, HOOK], input=raw if raw is not None else json.dumps(payload),
                       capture_output=True, text=True, timeout=30, env={**os.environ, **(env or {})})
    return r, time.time() - t0


def decide(tool, path, env=None):
    r, _ = run({"tool_name": tool, "tool_input": {"file_path": path}, "cwd": os.path.dirname(path)}, env)
    if r.returncode != 0:
        return f"exit{r.returncode}", r.stdout
    return (FLAG if "lint-on-edit" in r.stdout else PASS), r.stdout


def project(tmp, name, marker=True, files=None, pyproject=None):
    root = os.path.join(tmp, name)
    os.makedirs(os.path.join(root, ".claude"), exist_ok=True)
    os.makedirs(os.path.join(root, "pkg"), exist_ok=True)
    if marker:
        open(os.path.join(root, ".claude", "lint-on-edit"), "w").close()
    if pyproject:
        open(os.path.join(root, "pyproject.toml"), "w").write(pyproject)
    for rel, body in (files or {}).items():
        open(os.path.join(root, rel), "w").write(body)
    return root


def fake_ruff(root, script):
    d = os.path.join(root, ".venv", "bin")
    os.makedirs(d, exist_ok=True)
    p = os.path.join(d, "ruff")
    open(p, "w").write("#!/bin/sh\n" + script + "\n")
    os.chmod(p, 0o755)


def main():
    if not shutil.which("ruff"):
        print("ruff 가 PATH 에 없어 테스트할 수 없음"); sys.exit(1)
    tmp = tempfile.mkdtemp(prefix="lint-on-edit-test-")
    results = []

    def check(want, label, got, extra=True):
        ok = got == want and extra
        results.append(ok)
        print(f"  {'PASS' if ok else 'FAIL'}  [{want:4}{'' if ok else '→' + str(got)}] {label}")

    try:
        on = project(tmp, "on", files={"pkg/bad.py": BAD, "pkg/clean.py": CLEAN, "notes.txt": BAD})
        bad = os.path.join(on, "pkg/bad.py")
        got, out = decide("Edit", bad)
        check(FLAG, "opt-in + 위반 있는 .py (Edit) → 규칙 코드가 컨텍스트에", got, "F401" in out and "E711" in out)
        got, _ = decide("Write", bad)
        check(FLAG, "Write 도 대상", got)
        got, _ = decide("Edit", os.path.join(on, "pkg/clean.py"))
        check(PASS, "opt-in + 깨끗한 파일 → 출력 없음", got)
        got, _ = decide("Edit", os.path.join(on, "notes.txt"))
        check(PASS, ".py 아닌 파일은 무시", got)
        got, _ = decide("Read", bad)
        check(PASS, "Read 도구는 대상 아님", got)
        got, _ = decide("Edit", os.path.join(on, "pkg/없는파일.py"))
        check(PASS, "존재하지 않는 파일 → 조용히 통과", got)

        r, _ = run({"tool_name": "Edit", "tool_input": {"file_path": "pkg/bad.py"}, "cwd": on})
        check(FLAG, "상대 경로는 cwd 기준으로 푼다", FLAG if "lint-on-edit" in r.stdout else PASS)

        off = project(tmp, "off", marker=False, files={"pkg/bad.py": BAD})
        got, _ = decide("Edit", os.path.join(off, "pkg/bad.py"))
        check(PASS, "opt-in 파일 없는 프로젝트 → 무동작", got)

        d = project(tmp, "dirmarker", marker=False, files={"pkg/bad.py": BAD})
        os.makedirs(os.path.join(d, ".claude", "lint-on-edit"))
        got, _ = decide("Edit", os.path.join(d, "pkg/bad.py"))
        check(PASS, "lint-on-edit 가 디렉토리면 opt-in 아님", got)

        home = os.path.join(tmp, "home")
        project(tmp, "home", files={"pkg/bad.py": BAD})          # 홈 자체에 마커
        got, _ = decide("Edit", os.path.join(home, "pkg/bad.py"), env={"HOME": home})
        check(PASS, "홈 디렉토리의 마커는 전역 opt-in 으로 치지 않는다", got)

        fx = project(tmp, "fixtrue", files={"pkg/bad.py": BAD}, pyproject="[tool.ruff]\nfix = true\n")
        got, _ = decide("Edit", os.path.join(fx, "pkg/bad.py"))
        body = open(os.path.join(fx, "pkg/bad.py")).read()
        check(FLAG, "프로젝트 설정 fix = true 여도 파일을 고치지 않는다", got, body == BAD)

        ex = project(tmp, "excluded", files={"pkg/bad.py": BAD},
                     pyproject='[tool.ruff]\nextend-exclude = ["pkg"]\n')
        got, _ = decide("Edit", os.path.join(ex, "pkg/bad.py"))
        check(PASS, "프로젝트 exclude 를 따른다 (--force-exclude)", got)

        vv = project(tmp, "venv", files={"pkg/bad.py": BAD})
        fake_ruff(vv, 'echo "pkg/bad.py:1:1: XVENV fake venv ruff"; exit 1')
        got, out = decide("Edit", os.path.join(vv, "pkg/bad.py"))
        check(FLAG, "프로젝트 .venv 의 ruff 를 PATH 보다 먼저 쓴다", got, "XVENV" in out)

        nr = project(tmp, "noruff", files={"pkg/bad.py": BAD})
        got, _ = decide("Edit", os.path.join(nr, "pkg/bad.py"), env={"PATH": "/nonexistent"})
        check(PASS, "ruff 가 어디에도 없으면 건너뛴다", got)

        cfg = project(tmp, "cfgerr", files={"pkg/bad.py": BAD})
        fake_ruff(cfg, 'echo "pkg/bad.py:1:1: E999 partial"; echo "error: bad config" >&2; exit 2')
        got, _ = decide("Edit", os.path.join(cfg, "pkg/bad.py"))
        check(PASS, "ruff 가 exit 2(설정 오류) → 조용히 통과", got)

        slow = project(tmp, "slow", files={"pkg/bad.py": BAD})
        fake_ruff(slow, "sleep 5; exit 1")
        r, dt = run({"tool_name": "Edit", "tool_input": {"file_path": os.path.join(slow, "pkg/bad.py")}},
                    env={"LINT_ON_EDIT_TIMEOUT": "0.5"})
        check(PASS, f"ruff 가 느리면 타임아웃 후 통과 ({dt:.1f}s)",
              PASS if r.returncode == 0 and not r.stdout.strip() else FLAG, dt < 3)

        r, _ = run(None, env={"HOME": os.path.join(tmp, "h2")}, raw="not json")
        check(PASS, "깨진 stdin — 출력 없이 exit 0", PASS if r.returncode == 0 and not r.stdout.strip() else FLAG)

        many = project(tmp, "many", files={"pkg/m.py": "".join(f"import mod{i}\n" for i in range(30))})
        got, out = decide("Edit", os.path.join(many, "pkg/m.py"))
        ctx = json.loads(out)["hookSpecificOutput"]["additionalContext"] if got == FLAG else ""
        check(FLAG, "위반 30건 → 20줄만 + '외 10건'", got, "30건" in ctx and "외 10건" in ctx)
    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    fails = results.count(False)
    print(f"\n{len(results) - fails}/{len(results)} 통과")
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
