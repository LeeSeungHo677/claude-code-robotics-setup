#!/usr/bin/env python3
"""SessionStart — 현재 작업 디렉토리의 성격과 지금 쓸 만한 세팅을 짧게 주입한다.

목적 두 가지:
  1. 매 세션 Claude 가 ls/git status 를 새로 돌리는 낭비를 없앤다.
  2. 만들어놓고 안 쓰게 되는 것을 막는다 — 지금 이 디렉토리에서 쓸 만한 것을 먼저 보여준다.

출력이 두 갈래다.
  `systemMessage`      → 사용자 화면. 실행 사용법 치트시트
  `additionalContext`  → Claude 컨텍스트. 프로젝트 감지·git·추천 (화면엔 안 보임)

**둘 다 짧게 유지한다.** additionalContext 는 컨텍스트 비용을 직접 내고,
systemMessage 도 컨텍스트 유입 여부가 확정되지 않았으므로 최악을 가정한다.
전체 사용법(README)은 여기 넣지 않는다 — `/setup:guide` 로 부를 때만 연다.

개수·날짜를 박아두지 않는다. 매번 센다 (박아두면 그날부터 낡는다).
"""

import datetime
import json
import os
import re
import subprocess
import sys

HOME = os.path.expanduser("~")
USER_SKILLS = os.path.join(HOME, ".claude", "skills")
CLAUDE_JSON = os.path.join(HOME, ".claude.json")

def _count(path, pat=None):
    try:
        if pat == "md":
            n = 0
            for root, _, files in os.walk(path):
                n += sum(1 for f in files if f.endswith(".md"))
            return n
        return len([d for d in os.listdir(path)
                    if os.path.isfile(os.path.join(path, d, "SKILL.md"))])
    except OSError:
        return 0


def cheatsheet(cwd, reco, dom):
    """켜자마자 보여주는 실행 사용법. 개수는 박아두지 않고 그때 센다.

    systemMessage 로 나가므로 사용자 화면용이다. 프로젝트 감지·git 상태 같은
    Claude 용 정보는 여기 넣지 않는다 (그건 additionalContext 쪽)."""
    ns = _count(os.path.join(HOME, ".claude", "skills"))
    ns += _count(os.path.join(cwd, ".claude", "skills"))
    na = len([f for f in os.listdir(os.path.join(HOME, ".claude", "agents"))
              if f.endswith(".md")]) if os.path.isdir(os.path.join(HOME, ".claude", "agents")) else 0
    nc = _count(os.path.join(HOME, ".claude", "commands"), "md")

    # 위 [에이전트] 절에 이미 나온 것은 빼고, 이 디렉토리에만 있는 것을 보여준다
    shown = ("ros2-reviewer", "robot-safety-reviewer", "robotics-architect", "Explore")
    extra = [r for r in reco if not any(s in r for s in shown)]
    here = " · ".join(extra) if extra else "(전용 커맨드 없음)"
    return "\n".join([
        f"━━ Claude 풀 세팅 ━━ 스킬 {ns} · 에이전트 {na} · 커맨드 {nc} ━━━━━━━━━━━━━━━",
        "[스킬] 부르지 않는다. 하려는 일을 말하면 열린다.",
        '   "논문 제대로 리뷰해줘"→paper-review   "이 레포 쓸만해?"→repo-review',
        '   "옵시디언 노트 검토"→notes-review     "빌드가 안 돼"→ros2-setup',
        '   "시뮬과 실기가 다른데"→sim-to-real-check  "보상함수"→rl-training',
        f"   이 레포에 맞는 스킬: {' · '.join(dom) if dom else '(자동 매칭 없음)'}",
        "[에이전트] 이름을 불러야 온다.",
        "   ros2-reviewer          PR 전·실기 투입 전 코드 리뷰",
        "   robot-safety-reviewer  실기 투입·납품 전, 안전 관련 변경 후",
        "   robotics-architect     처음 보는 워크스페이스 구조 파악",
        "   Explore                넓게 훑고 결론만 받을 때",
        "[커맨드]",
        "   /setup:guide 사용법  /setup:audit 점검  /setup:tech-scan 신기술",
        "   /robot:preflight 실기 전  /robot:diagnose  /robot:bag-analyze",
        "   /git:pr-create  /git:worktree  /workflow:orchestrate",
        f"   여기서: {here}",
        "[하네스]",
        "   긴 명령은 백그라운드로 — colcon build·학습 (120초에 안 잘림)",
        "   /rewind 되돌리기 · /resume 세션복구 · /compact 압축 · /model 모델",
        "[루프]",
        "   Monitor  빌드·로그 감시 — 실패 시그니처를 걸어야 크래시를 잡는다",
        "   cron     매일 06:00 논문 수집 → ~/knowledge/papers",
        "[지식] ~/knowledge — 논문·리뷰·로봇분석. 레포 안에 넣지 않는다",
        "━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━",
    ])


def run(cmd, cwd, timeout=3):
    try:
        r = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True,
                           timeout=timeout, shell=False)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


SKIP_DIRS = {"build", "install", "log", "node_modules", "__pycache__", ".git",
             ".venv", "venv", "vendor", "docs", "data", "models"}


def _has_pkg_under_src(src):
    if not os.path.isdir(src):
        return False
    try:
        for e in os.scandir(src):
            if e.is_dir() and os.path.exists(os.path.join(e.path, "package.xml")):
                return True
    except OSError:
        pass
    return False


def _ros_pkgs(cwd, depth=2):
    """package.xml 을 찾는다. 워크스페이스가 하위(robot/ros2_ws/src/…)에 있는 배치가 흔해
    깊이 2까지 훑는다. 빌드 산출물 디렉토리는 건너뛴다."""
    if os.path.exists(os.path.join(cwd, "package.xml")):
        return True
    if _has_pkg_under_src(os.path.join(cwd, "src")):
        return True
    if depth <= 0:
        return False
    try:
        for e in os.scandir(cwd):
            if not e.is_dir() or e.name.startswith(".") or e.name in SKIP_DIRS:
                continue
            if _ros_pkgs(e.path, depth - 1):
                return True
    except OSError:
        pass
    return False


def detect_stack(cwd):
    """디렉토리에 있는 표식 파일로 프로젝트 성격을 추정."""
    tags = []
    has = lambda *p: any(os.path.exists(os.path.join(cwd, x)) for x in p)

    if _ros_pkgs(cwd):
        tags.append("ROS 2 워크스페이스(colcon)" if has("src", "install", "build")
                    else "ROS 2 패키지")
    if has("pyproject.toml"):
        tags.append("Python(pyproject)")
    elif has("requirements.txt", "setup.py"):
        tags.append("Python")
    if has("package.json"):
        tags.append("Node/JS")
    if has("Cargo.toml"):
        tags.append("Rust")
    if has("go.mod"):
        tags.append("Go")
    if has("CMakeLists.txt"):
        tags.append("CMake")
    if has("Dockerfile", "docker-compose.yml", "compose.yaml", "docker-compose.yaml"):
        tags.append("Docker")
    return tags


# 스택 태그 → 추천 항목. 실제로 존재하는 것만 통과시킨다 (아래 _exists 검사).
RECO = {
    "ROS 2": [("cmd", "build", "빌드(백그라운드)"),
              ("cmd", "test", "테스트"),
              ("agent", "ros2-reviewer", "PR 전 리뷰"),
              ("agent", "robot-safety-reviewer", "실기 투입 전")],
    "Python": [("agent", "test-architect", "테스트 설계"),
               ("skill", "python-pro", "파이썬 심화")],
    "Node/JS": [("agent", "frontend-engineer", "UI 구현"),
                ("skill", "design-system", "대시보드 디자인")],
    "Docker": [("skill", "docker-ros2-development", "컨테이너")],
}


def _exists(kind, name, cwd):
    if kind == "cmd":
        return any(os.path.exists(os.path.join(d, "commands", f"{name}.md"))
                   for d in (os.path.join(cwd, ".claude"), os.path.join(HOME, ".claude")))
    sub = "agents" if kind == "agent" else "skills"
    for d in (os.path.join(cwd, ".claude"), os.path.join(HOME, ".claude")):
        p = os.path.join(d, sub, name)
        if kind == "agent" and os.path.exists(p + ".md"):
            return True
        if kind == "skill" and os.path.isdir(p):
            return True
    return False


def recommend(cwd, stack):
    out, seen = [], set()
    for tag in stack:
        for key, items in RECO.items():
            if not tag.startswith(key):
                continue
            for kind, name, why in items:
                if name in seen or not _exists(kind, name, cwd):
                    continue
                seen.add(name)
                out.append(f"/{name}" if kind == "cmd" else f"`{name}`({why})")
    return out[:5]


# 스택 태그 → 관련 스킬을 고르는 키워드. 로테이션이 엉뚱한 것을 권하지 않게 한다.
ROTATE_HINT = {
    "ROS 2": ("ros", "로봇", "robot", "nav2", "tf", "urdf", "관절", "센서", "실기", "제어"),
    "Python": ("python", "파이썬", "pytest", "asyncio"),
    "Node/JS": ("react", "typescript", "next", "프론트", "ui", "웹"),
    "Docker": ("docker", "컨테이너", "kubernetes"),
}


# 라틴 문자만 센다. 한국어를 넣으면 문법어(위치·서로·다른·하는·우리)가 점수를 먹어
# 엉뚱한 스킬이 1위로 올라온다 — 실제로 댄스 모션 레포에 notes-review 가 1위였다.
# 이 도메인의 변별력 있는 어휘는 대부분 라틴이다 (isaaclab, onnx, lerobot, orin …).
_TOKEN = re.compile(r"[a-z][a-z0-9]{2,}")


def _tokens(text):
    return set(_TOKEN.findall(text.lower()))


def domain_skills(cwd, top=3):
    """레포가 무엇에 관한 것인지 보고 관련 스킬을 고른다.

    도메인 목록을 코드에 박지 않는다 — 레포 텍스트(디렉토리명 + README 머리말)를
    스킬 설명과 대조해 점수를 낸다. 스킬을 추가하면 자동으로 후보가 되고 낡지 않는다.
    흔한 단어(로봇, ros …)는 여러 스킬에 나오므로 가중치를 낮춘다 (df 역수).
    """
    try:
        parts = []
        for e in os.scandir(cwd):
            if e.is_dir() and not e.name.startswith(".") and e.name not in SKIP_DIRS:
                parts.append(e.name.replace("_", " ").replace("-", " "))
        for name in ("README.md", "readme.md", "README.MD"):
            p = os.path.join(cwd, name)
            if os.path.isfile(p):
                parts.append(_head(p, 2000))
                break
        repo = _tokens(" ".join(parts))
        if len(repo) < 5:
            return []

        skills = {}
        for d in os.listdir(USER_SKILLS):
            p = os.path.join(USER_SKILLS, d, "SKILL.md")
            if not os.path.isfile(p):
                continue
            t = _head(p, 600)
            i = t.find("description:")
            desc = t[i:i + 400] if i >= 0 else ""
            skills[d] = _tokens(d.replace("-", " ") + " " + desc)

        df = {}
        for toks in skills.values():
            for tok in toks:
                df[tok] = df.get(tok, 0) + 1

        scored = []
        for name, toks in skills.items():
            hit = toks & repo
            s = sum(1.0 / df[t] for t in hit if df[t] <= 12)   # 12개 넘게 나오면 변별력 없음
            if s > 0.4:
                scored.append((s, name))
        scored.sort(reverse=True)
        return [n for _, n in scored[:top]]
    except Exception:
        return []


def _head(path, limit=700):
    """SKILL.md 앞부분만 읽는다. 88개를 전부 읽어야 하므로 통째로 읽지 않는다."""
    try:
        with open(path, encoding="utf-8") as f:
            return f.read(limit)
    except OSError:
        return ""


def rotation_skill(stack):
    """아직 한 번도 안 쓴 스킬 하나를 날짜 기준으로 돌아가며 노출한다.
    현재 스택과 관련된 것이 있으면 그쪽을 우선한다 — 로봇 작업 중에
    'authentication-patterns' 를 권하면 다음부터 안 읽는다."""
    try:
        names = sorted(d for d in os.listdir(USER_SKILLS)
                       if os.path.isfile(os.path.join(USER_SKILLS, d, "SKILL.md")))
        try:
            with open(CLAUDE_JSON, encoding="utf-8") as f:
                su = json.load(f).get("skillUsage") or {}
            used = {k for k, v in su.items() if (v or {}).get("usageCount", 0) > 0}
        except Exception:
            used = set()

        pool = [n for n in names if n not in used] or names

        kws = tuple(k for tag in stack for pre, ks in ROTATE_HINT.items()
                    if tag.startswith(pre) for k in ks)
        if kws:
            heads = {n: _head(os.path.join(USER_SKILLS, n, "SKILL.md")).lower() for n in pool}
            related = [n for n in pool if any(k in n or k in heads[n] for k in kws)]
            if related:
                pool = related

        pick = pool[datetime.date.today().toordinal() % len(pool)]
        text = _head(os.path.join(USER_SKILLS, pick, "SKILL.md"))
        desc = ""
        m = text.find("description:")
        if m >= 0:
            desc = " ".join(text[m + 12:].split("\n---")[0].split())
            desc = desc.lstrip(">|").strip()
        return pick, desc[:70]
    except Exception:
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    cwd = data.get("cwd") or os.getcwd()
    lines = []

    stack = detect_stack(cwd)
    if stack:
        lines.append(f"- 프로젝트 성격: {', '.join(stack)}")

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    if branch:
        dirty = run(["git", "status", "--porcelain"], cwd)
        n = len([l for l in dirty.split("\n") if l.strip()]) if dirty else 0
        lines.append(f"- git: `{branch}` ({f'변경 {n}개' if n else 'clean'})")
        last = run(["git", "log", "-1", "--pretty=%s"], cwd)
        if last:
            lines.append(f"- 최근 커밋: {last[:90]}")

    distro = os.environ.get("ROS_DISTRO")
    if distro:
        domain = os.environ.get("ROS_DOMAIN_ID", "0(기본)")
        rmw = os.environ.get("RMW_IMPLEMENTATION", "기본")
        lines.append(f"- ROS: {distro} / DOMAIN_ID={domain} / RMW={rmw}")

    reco = recommend(cwd, stack)
    if reco:
        lines.append(f"- 여기서 쓸 만한 것: {' · '.join(reco)}")

    dom = domain_skills(cwd)
    if dom:
        lines.append(f"- 이 레포 도메인에 맞는 스킬: {', '.join(dom)}")

    rot = rotation_skill(stack)
    if rot:
        lines.append(f"- 아직 안 써본 스킬: `{rot[0]}` — {rot[1]}")

    lines.append("- 세팅 전체 사용법: `/setup:guide`")

    if len(lines) <= 1:
        sys.exit(0)

    print(json.dumps({
        "systemMessage": cheatsheet(cwd, reco, dom),
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "## 세션 시작 컨텍스트 (자동 수집)\n" + "\n".join(lines),
        },
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
