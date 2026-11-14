#!/usr/bin/env python3
"""protected-checks-guard.py 테스트 — 차단 / 통과(오탐 방지) 양쪽.

임시 프로젝트를 만들어 `.claude/protected-checks` 를 둔다. 명령 문자열을 이 파일 안에 두는 이유는
dangerous-command-guard 테스트와 같다 (Bash 로 직접 치면 훅이 테스트 명령 자체를 막는다).

실행: python3 ~/.claude/hooks/test_protected_checks_guard.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "protected-checks-guard.py")
DENY, PASS = "deny", "pass"


def run(body):
    r = subprocess.run([sys.executable, HOOK], input=json.dumps(body),
                       capture_output=True, text=True, timeout=10)
    return DENY if r.returncode == 2 else PASS


def bash(cmd, cwd):
    return run({"tool_name": "Bash", "tool_input": {"command": cmd}, "cwd": cwd})


def edit(path, cwd, tool="Edit"):
    return run({"tool_name": tool, "tool_input": {"file_path": path}, "cwd": cwd})


def make_project(tmp):
    proj = os.path.join(tmp, "proj")
    for d in ("tests", "sim/grader", "src", ".claude", "electronics"):
        os.makedirs(os.path.join(proj, d))
    files = ["tests/test_budget.py", "tests/conftest.py", "sim/grader/test_grader.py",
             "src/app.py", "check.sh", "electronics/board.kicad_dru", "electronics/board.kicad_sch"]
    for f in files:
        open(os.path.join(proj, f), "w").close()
    with open(os.path.join(proj, ".claude/protected-checks"), "w") as f:
        f.write("# 판정 기준\ntests/test_*.py\ntests/conftest.py\nsim/grader/\ncheck.sh\n*.kicad_dru\n")
    other = os.path.join(tmp, "other")                  # 목록 파일이 없는 프로젝트
    os.makedirs(os.path.join(other, "tests"))
    open(os.path.join(other, "tests/test_x.py"), "w").close()
    return proj, other


def main():
    tmp = tempfile.mkdtemp(prefix="pcguard-")
    proj, other = make_project(tmp)
    cases = [
        # ── Write/Edit ──
        (DENY, edit("tests/test_budget.py", proj)),
        (DENY, edit(os.path.join(proj, "sim/grader/test_grader.py"), "/"), ),
        (DENY, edit("electronics/board.kicad_dru", proj, "Write")),
        (DENY, edit(".claude/protected-checks", proj)),                    # 목록 자체
        (DENY, edit("tests/../tests/test_budget.py", proj)),                # 경로 정규화
        (PASS, edit("tests/test_new_stage.py", proj, "Write")),             # 새 check 는 허용
        (PASS, edit("src/app.py", proj)),
        (PASS, edit("electronics/board.kicad_sch", proj)),
        (PASS, edit("tests/test_x.py", other)),                             # opt-in 안 한 프로젝트
        # ── Bash: 막아야 하는 것 ──
        (DENY, bash("sed -i 's/0.28/0.34/' tests/test_budget.py", proj)),
        (DENY, bash("echo x > check.sh", proj)),
        (DENY, bash("ls && rm tests/conftest.py", proj)),
        (DENY, bash("rm -rf sim/grader", proj)),                            # 디렉토리째
        (DENY, bash("mv tests/test_budget.py /tmp/", proj)),
        (DENY, bash("git checkout -- tests/test_budget.py", proj)),
        (DENY, bash("cd tests && rm test_budget.py", proj)),                # cd 뒤 상대 경로
        (DENY, bash("cat new.py | tee tests/test_budget.py", proj)),
        (DENY, bash("cp /tmp/x.py tests/test_budget.py", proj)),
        (DENY, bash("chmod -x check.sh", proj)),
        (DENY, bash("sudo rm check.sh", proj)),
        # ── Bash: 통과해야 하는 것 (이전 프로젝트 전용 훅에서 나온 실제 오탐 3건 포함) ──
        (PASS, bash("./check.sh -q 2>&1 | tail -5", proj)),
        (PASS, bash("python3 /tmp/s.py <<'EOF'\nfix check.sh and tests/test_budget.py docs\nEOF", proj)),
        (PASS, bash("rm -rf /tmp/scratch && ./check.sh", proj)),
        (PASS, bash("cat tests/test_budget.py", proj)),
        (PASS, bash("pytest tests/ -q > /tmp/out.txt", proj)),
        (PASS, bash("cp tests/test_budget.py /tmp/copy.py", proj)),          # 읽어서 복사
        (PASS, bash("sed -i 's/a/b/' src/app.py", proj)),
        (PASS, bash("git diff tests/test_budget.py", proj)),
        (PASS, bash("rm tests/test_x.py", other)),
    ]
    fails = 0
    for i, (want, got) in enumerate(cases, 1):
        ok = want == got
        fails += not ok
        print(f"  {'PASS' if ok else 'FAIL'}  #{i:02} [{want}{'' if ok else '→' + got}]")
    # 깨진 입력은 조용히 통과 (fail-open)
    r = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True)
    ok = r.returncode == 0
    fails += not ok
    print(f"  {'PASS' if ok else 'FAIL'}  깨진 stdin → exit {r.returncode}")
    shutil.rmtree(tmp, ignore_errors=True)
    total = len(cases) + 1
    print(f"\n{total - fails}/{total} 통과")
    sys.exit(1 if fails else 0)


main()
