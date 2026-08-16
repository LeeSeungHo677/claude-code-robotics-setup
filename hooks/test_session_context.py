#!/usr/bin/env python3
"""session-context.py 훅 테스트 — 감지·추천·분량 상한.

이 훅의 출력은 **매 세션 컨텍스트 비용을 직접 낸다.** 그래서 내용뿐 아니라
분량 상한도 테스트한다. 기능을 더하다 보면 조용히 불어나는 것이 이 훅의 실패 모드다.

실행: python3 ~/.claude/hooks/test_session_context.py
"""
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))   # 설치 위치와 무관하게 옆의 훅을 테스트한다
HOOK = os.path.join(HERE, "session-context.py")
MAX_CHARS = 700          # 약 175토큰. 넘으면 설계 의도를 벗어난 것이다.


def emit(cwd, env=None):
    e = dict(os.environ)
    e.pop("ROS_DISTRO", None)
    if env:
        e.update(env)
    r = subprocess.run([sys.executable, HOOK], input=json.dumps({"cwd": cwd}),
                       capture_output=True, text=True, env=e, timeout=15)
    if r.returncode != 0 or not r.stdout.strip():
        return None, r.returncode
    return json.loads(r.stdout), r.returncode


def mk(tmp, *paths):
    for p in paths:
        full = os.path.join(tmp, p)
        os.makedirs(os.path.dirname(full), exist_ok=True)
        open(full, "a").close()
    return tmp


def main():
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f" — {detail}"))
        if not cond:
            fails.append(name)

    # 1) 아무것도 감지 안 되는 디렉토리에서도 사용법 안내는 나와야 한다.
    #    "어느 레포·어느 터미널에서 켜도 사용법이 보인다" 가 이 훅의 요구사항이다.
    #    (2026-08-17: 이전에는 감지 실패 시 조용히 종료했는데, 그러면 요구를 못 지킨다)
    t = tempfile.mkdtemp()
    out, rc = emit(t)
    ctx = out["hookSpecificOutput"]["additionalContext"] if out else ""
    check("미인식 디렉토리 — 사용법은 나온다", "/setup:guide" in ctx, f"out={out}")
    check("미인식 디렉토리 — 분량 최소", len(ctx) <= 300, f"{len(ctx)}자")
    shutil.rmtree(t, ignore_errors=True)

    # 2) ROS 워크스페이스가 하위에 있는 배치 (robot/ros2_ws/src/pkg/package.xml)
    t = mk(tempfile.mkdtemp(), "robot/ros2_ws/src/my_pkg/package.xml")
    out, _ = emit(t)
    ctx = out["hookSpecificOutput"]["additionalContext"] if out else ""
    check("하위 ROS 워크스페이스 감지", "ROS 2" in ctx, ctx[:120])
    check("ROS 추천 노출", "ros2-reviewer" in ctx or "robot-safety-reviewer" in ctx, ctx[:160])
    shutil.rmtree(t, ignore_errors=True)

    # 3) 빌드 산출물 안의 package.xml 은 무시해야 한다
    t = mk(tempfile.mkdtemp(), "build/foo/package.xml", "pyproject.toml")
    out, _ = emit(t)
    ctx = out["hookSpecificOutput"]["additionalContext"] if out else ""
    check("build/ 안의 package.xml 무시", "ROS 2" not in ctx, ctx[:120])
    shutil.rmtree(t, ignore_errors=True)

    # 4) Python 프로젝트
    t = mk(tempfile.mkdtemp(), "pyproject.toml")
    out, _ = emit(t)
    ctx = out["hookSpecificOutput"]["additionalContext"] if out else ""
    check("Python 감지", "Python(pyproject)" in ctx, ctx[:120])
    check("사용법 안내 포함", "/setup:guide" in ctx, ctx[:120])
    shutil.rmtree(t, ignore_errors=True)

    # 5) 분량 상한 — 이 훅의 핵심 제약
    t = mk(tempfile.mkdtemp(), "robot/ros2_ws/src/p/package.xml", "pyproject.toml",
           "package.json", "Dockerfile", "CMakeLists.txt")
    out, _ = emit(t, {"ROS_DISTRO": "humble"})
    ctx = out["hookSpecificOutput"]["additionalContext"] if out else ""
    check(f"분량 {len(ctx)}자 ≤ {MAX_CHARS}", len(ctx) <= MAX_CHARS, f"{len(ctx)}자")
    shutil.rmtree(t, ignore_errors=True)

    # 6) 추천은 실재하는 것만 — 없는 커맨드를 권하면 안 된다
    t = mk(tempfile.mkdtemp(), "src/p/package.xml")
    out, _ = emit(t)
    ctx = out["hookSpecificOutput"]["additionalContext"] if out else ""
    bad = [c for c in ("/build", "/test")
           if c in ctx and not os.path.exists(os.path.expanduser(f"~/.claude/commands{c}.md"))]
    check("없는 프로젝트 커맨드를 권하지 않음", not bad, f"권함: {bad}")
    shutil.rmtree(t, ignore_errors=True)

    # 7) 치트시트 — 켜자마자 보이는 실행 사용법
    t = mk(tempfile.mkdtemp(), "src/p/package.xml")
    out, _ = emit(t)
    sm = (out or {}).get("systemMessage", "")
    check("치트시트 출력", sm.startswith("━━ Claude 풀 세팅"), sm[:60])
    for must in ("[스킬]", "[에이전트]", "[커맨드]", "[하네스]", "[루프]", "/setup:guide"):
        check(f"치트시트에 {must}", must in sm, sm[:80])

    # 개수를 박아두면 안 된다 — 실제로 세는지 확인한다 (2026-08-17 교훈)
    real_agents = len([f for f in os.listdir(os.path.expanduser("~/.claude/agents"))
                       if f.endswith(".md")])
    check(f"에이전트 수를 실제로 셈({real_agents})", f"에이전트 {real_agents} " in sm,
          sm.split("\n")[0])

    # 없는 프로젝트 커맨드를 치트시트에 안내하면 안 된다
    check("치트시트가 없는 /build 를 안내하지 않음",
          "/build" not in sm or os.path.exists(os.path.join(t, ".claude/commands/build.md")),
          sm)
    shutil.rmtree(t, ignore_errors=True)

    # 8) 도메인 매칭 — README·디렉토리명을 스킬 설명과 대조해 고른다
    t = tempfile.mkdtemp()
    with open(os.path.join(t, "README.md"), "w", encoding="utf-8") as f:
        f.write("# X2 humanoid dance pipeline\n"
                "IsaacLab RL training, ONNX export, Orin deployment, retargeting from AMASS.\n")
    os.makedirs(os.path.join(t, "03_rl_training"), exist_ok=True)
    out, _ = emit(t)
    sm = (out or {}).get("systemMessage", "")
    ctx = out["hookSpecificOutput"]["additionalContext"] if out else ""
    picked = [s for s in ("legged-rl", "nvidia-isaac", "gpu-optimization", "rl-training")
              if s in sm]
    check("도메인 매칭 — 관련 스킬을 고름", bool(picked), sm[sm.find("이 레포에 맞는"):][:80])
    # 한국어 문법어로 엉뚱한 것이 1위가 되면 안 된다 (2026-08-17 실제 발생)
    check("도메인 매칭 — 무관한 스킬이 안 뽑힘",
          "notes-review" not in sm.split("이 레포에 맞는 스킬:")[-1].split("\n")[0],
          sm[sm.find("이 레포에 맞는"):][:80])
    check("도메인 결과가 Claude 컨텍스트에도 감", "도메인" in ctx, ctx[:100])
    shutil.rmtree(t, ignore_errors=True)

    # 9) 잘못된 stdin — 조용히 통과 (훅 버그가 세션을 막으면 안 된다)
    r = subprocess.run([sys.executable, HOOK], input="not json",
                       capture_output=True, text=True, timeout=15)
    check("깨진 stdin — exit 0", r.returncode == 0, f"exit {r.returncode}")

    print(f"\n{7 + 2 - len(fails)}/{7 + 2} 통과" if False else
          f"\n실패 {len(fails)}건" + (f": {fails}" if fails else " — 전부 통과"))
    sys.exit(1 if fails else 0)


main()
