#!/usr/bin/env python3
"""session-context.py 훅 테스트 — 감지·추천·분량 상한.

이 훅의 출력은 **매 세션 컨텍스트 비용을 직접 낸다.** 그래서 내용뿐 아니라
분량 상한도 테스트한다. 기능을 더하다 보면 조용히 불어나는 것이 이 훅의 실패 모드다.

실행: python3 ~/.claude/hooks/test_session_context.py
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))   # 설치 위치와 무관하게 옆의 훅을 테스트한다
HOOK = os.path.join(HERE, "session-context.py")
MAX_CHARS = 700          # additionalContext. 약 175토큰. 넘으면 설계 의도를 벗어난 것이다.
MAX_BANNER = 1800        # systemMessage(평문). 화면용이지만 모델 컨텍스트에도 들어간다.
BANNER_W = 70            # 훅의 BANNER_W 와 같아야 한다

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def dw(s):
    """화면 폭 (한글·CJK 2칸)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in ANSI.sub("", s))


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

    # 7) 배너 — 켜자마자 보이는 화면
    t = mk(tempfile.mkdtemp(), "src/p/package.xml")
    out, _ = emit(t)
    sm = (out or {}).get("systemMessage", "")
    plain = ANSI.sub("", sm)
    for must in ("이 레포에서 바로", "부르는 법", "자주 잊는 것", "/setup:guide"):
        check(f"배너에 '{must}'", must in plain, plain[:100])

    # 개수를 박아두면 안 된다 — 실제로 세는지 확인한다 (2026-08-17 교훈)
    real_agents = len([f for f in os.listdir(os.path.expanduser("~/.claude/agents"))
                       if f.endswith(".md")])
    check(f"에이전트 수를 실제로 셈({real_agents})", f"에이전트 {real_agents} " in plain,
          plain.split("\n")[1] if "\n" in plain else plain)

    # 현재 상태가 배너에 보여야 한다 — 이게 정적 목록보다 값이 큰 부분이다
    check("배너에 레포 이름", os.path.basename(t) in plain, plain[:120])

    # 줄 넘침 — 한글 폭 계산을 손으로 하면 반드시 틀린다 (2026-08-17 실제 5줄 초과)
    over = [(dw(l), l) for l in plain.split("\n") if dw(l) > BANNER_W]
    check(f"모든 줄 ≤ {BANNER_W}칸", not over,
          "; ".join(f"{w}칸 {l[:40]}" for w, l in over[:3]))

    # 꼬리말 — `!` 직접 실행 명령과 **권하는 이유**가 같이 보여야 한다.
    # 이유가 없으면 그냥 /setup:tree 를 쓰게 되고 출력 전체가 컨텍스트를 거친다.
    tip = "! python3 ~/.claude/bin/setup-tree.py"
    check("꼬리말에 ! 직접 실행 명령", tip in plain, plain[-300:])
    check("꼬리말에 권하는 이유", "컨텍스트를 안 쓴다" in plain and "토큰을 쓴다" in plain,
          plain[-300:])
    check("안내한 스크립트가 실재",
          os.path.isfile(os.path.expanduser("~/.claude/bin/setup-tree.py")), tip)

    # 색을 끌 수 있어야 한다 (터미널이 ANSI 를 못 그리면 되돌릴 수단)
    out2, _ = emit(t, {"CLAUDE_BANNER_PLAIN": "1"})
    sm2 = (out2 or {}).get("systemMessage", "")
    check("CLAUDE_BANNER_PLAIN=1 이면 ANSI 없음", "\x1b" not in sm2, repr(sm2[:60]))

    # 분량 상한 — 배너도 컨텍스트 비용을 낸다 (systemMessage 가 모델에 들어간다)
    check(f"배너 {len(sm2)}자 ≤ {MAX_BANNER}", len(sm2) <= MAX_BANNER, f"{len(sm2)}자")

    # 실재하지 않는 것을 광고하면 안 된다.
    #   ~2026-08-17 배너가 없는 `ros2-setup` 스킬을 매 세션 안내하고 있었다.
    home = os.path.expanduser("~/.claude")
    call = plain.split("부르는 법")[-1].split("자주 잊는 것")[0]
    for name in re.findall(r"→\s+([a-z][a-z0-9-]+)\s*$", call, re.M):
        check(f"광고한 스킬 실재: {name}",
              os.path.isfile(os.path.join(home, "skills", name, "SKILL.md")), name)
    for cmd in set(re.findall(r"/([a-z-]+):([a-z-]+)", plain)):
        check(f"광고한 커맨드 실재: /{cmd[0]}:{cmd[1]}",
              os.path.isfile(os.path.join(home, "commands", cmd[0], f"{cmd[1]}.md")), str(cmd))
    # 에이전트 (Explore 등 내장은 파일이 없으므로 제외)
    for ag in ("ros2-reviewer", "robot-safety-reviewer", "robotics-architect"):
        if ag in plain:
            check(f"광고한 에이전트 실재: {ag}",
                  os.path.isfile(os.path.join(home, "agents", f"{ag}.md")), ag)

    # 없는 프로젝트 커맨드를 배너에 안내하면 안 된다
    check("배너가 없는 /build 를 안내하지 않음",
          "/build" not in plain or os.path.exists(os.path.join(t, ".claude/commands/build.md")),
          plain)
    shutil.rmtree(t, ignore_errors=True)

    # 8) 도메인 매칭 — README·디렉토리명을 스킬 설명과 대조해 고른다
    t = tempfile.mkdtemp()
    with open(os.path.join(t, "README.md"), "w", encoding="utf-8") as f:
        f.write("# X2 humanoid dance pipeline\n"
                "IsaacLab RL training, ONNX export, Orin deployment, retargeting from AMASS.\n")
    os.makedirs(os.path.join(t, "03_rl_training"), exist_ok=True)
    out, _ = emit(t)
    sm = ANSI.sub("", (out or {}).get("systemMessage", ""))
    ctx = out["hookSpecificOutput"]["additionalContext"] if out else ""
    # 배너의 '이 레포에서 바로' 블록만 떼어 본다 (아래 정적 예시와 섞이면 안 된다)
    block = sm.split("이 레포에서 바로")[-1].split("부르는 법")[0]
    picked = [s for s in ("legged-rl", "nvidia-isaac", "gpu-optimization", "rl-training")
              if s in block]
    check("도메인 매칭 — 관련 스킬을 고름", bool(picked), block[:120])
    # 한국어 문법어로 엉뚱한 것이 1위가 되면 안 된다 (2026-08-17 실제 발생)
    check("도메인 매칭 — 무관한 스킬이 안 뽑힘", "notes-review" not in block, block[:120])
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
