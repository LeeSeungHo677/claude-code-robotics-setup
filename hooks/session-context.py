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
import unicodedata

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


# ─────────────────────────── 배너 렌더링 ───────────────────────────
# 훅에는 tty 가 없어 터미널 폭을 알 수 없다(shutil.get_terminal_size → 0).
# 고정 폭으로 그리되 좁은 창에서 접히지 않게 보수적으로 잡는다.
BANNER_W = 70

_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_PLAIN = bool(os.environ.get("CLAUDE_BANNER_PLAIN") or os.environ.get("NO_COLOR"))


def _c(code, s):
    """ANSI 색. CLAUDE_BANNER_PLAIN=1 또는 NO_COLOR 가 있으면 평문으로 떨어진다.
    색이 깨지는 터미널에서 되돌릴 수단을 남겨둔다."""
    return s if _PLAIN or not s else f"\x1b[{code}m{s}\x1b[0m"


def _w(s):
    """화면 폭. 한글·CJK 는 2칸으로 센다.
    공백으로 수동 정렬하면 한글 줄에서 반드시 어긋나는데, 그걸 막는 유일한 지점이다."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in _ANSI.sub("", s))


def _pad(s, n):
    return s + " " * max(0, n - _w(s))


def _clip(s, n):
    """폭 n 으로 자른다. 넘치면 … 를 붙인다 (색 코드 없는 평문 전용)."""
    out, w = [], 0
    for ch in s:
        cw = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if w + cw > n - 1:
            return "".join(out) + "…"
        out.append(ch)
        w += cw
    return "".join(out)


def _dim(s):    return _c("2", s)
def _bold(s):   return _c("1", s)
def _cyan(s):   return _c("36", s)
def _green(s):  return _c("32", s)
def _yellow(s): return _c("33", s)


# 트리 도식으로 그린다. 닫힌 박스(╭─┐)는 첫 줄에 붙는 'SessionStart:… says:'
# 프리픽스와 좁은 터미널에서 깨지지만, 왼쪽 레일만 쓰는 트리는 안 깨진다.
RAIL = "│"
INDENT = 4          # 레일 다음 들여쓰기
LW = 12             # 라벨 컬럼 폭. 가장 긴 라벨('백그라운드' 10칸)보다 넓어야 한다


def _row(label, value, lw=LW):
    """레일 + 라벨 + 값. 라벨 폭을 화면 폭 기준으로 맞춘다 (한글이 섞여도 정렬된다)."""
    return _dim(RAIL) + " " * INDENT + _pad(_cyan(label), lw) + value


def _wrap(label, items, lw=LW, sep=" · "):
    """items 를 화면 폭 안에서 접어 여러 줄로 만든다.

    폭 계산을 손으로 하지 않기 위한 것이다 — 아래 문구를 나중에 고쳐도 줄이
    넘치지 않는다. 한글이 섞이면 손계산은 반드시 틀린다(실제로 5줄이 넘쳤다)."""
    avail = BANNER_W - 1 - INDENT - lw
    lines, cur = [], []
    for it in items:
        if cur and _w(sep.join(cur + [it])) > avail:
            lines.append(sep.join(cur))
            cur = [it]
        else:
            cur.append(it)
    if cur:
        lines.append(sep.join(cur))
    return [_row(label if i == 0 else "", ln, lw) for i, ln in enumerate(lines)]


def _unrail(s):
    """마지막 가지의 본문은 세로줄이 끝났으므로 레일을 지운다.
    색 코드가 앞에 붙으므로 startswith 로는 못 잡는다 — 첫 등장 위치를 찾는다."""
    i = s.find(RAIL)
    return s[:i] + " " + s[i + 1:] if i >= 0 else s


# 배너에 이름으로 등장하는 것들. 실재 여부를 테스트가 전수 검사한다
# (예전에 없는 `ros2-setup` 을 매 세션 광고하고 있었다).
SAY_EXAMPLES = [
    ('"논문 제대로 리뷰해줘"', "paper-review"),
    ('"시뮬과 실기가 다른데"', "sim-to-real-check"),
    ('"QoS 가 안 맞아"', "ros2-engineering"),
    ('"보상함수 설계"', "rl-training"),
    ('"이 레포 쓸만해?"', "repo-review"),
]
CALL_AGENTS = [
    ("ros2-reviewer", "PR 전"),
    ("robot-safety-reviewer", "실기 전"),
    ("robotics-architect", "구조 파악"),
    ("Explore", "넓게 훑기"),          # 내장 에이전트 — 파일이 없다
]
CALL_CMDS = [
    ("/setup:guide", "사용법"), ("/setup:audit", "점검"),
    ("/robot:preflight", "실기 전"), ("/robot:diagnose", "진단"),
    ("/git:pr-create", "PR"), ("/workflow:orchestrate", "다단계"),
]


def banner(f):
    """켜자마자 보이는 화면. systemMessage 로 나가고 Claude 컨텍스트에도 들어간다.

    그래서 정적 목록을 늘리지 않는다 — 늘려야 할 것은 **지금 이 레포에서 달라지는
    정보**(브랜치·변경 수·매칭된 스킬)뿐이다. 박제된 문구는 낡고 비용만 낸다."""
    ns, na, nc, unused = f["counts"]
    rule = _dim("━" * BANNER_W)
    L = ["", rule]

    # ── 상태 줄: 어디서 · 어떤 상태로 켰는지 ──────────────────────────
    head = " " + _bold(_clip(f["repo"], 28))
    if f["branch"]:
        state = _green("clean") if not f["dirty"] else _yellow(f"변경 {f['dirty']}")
        head += "  " + _cyan(f["branch"]) + " " + state
    right = _dim(f"스킬 {ns} · 에이전트 {na} · 커맨드 {nc} ")
    L.append(_pad(head, BANNER_W - _w(right)) + right)

    env = list(f["stack"])
    if f["ros"]:
        env.append(f["ros"])
    if env:
        L.append(" " + _dim(_clip(" · ".join(env), BANNER_W - 2)))
    if f["last"]:
        L.append(" " + _dim("↳ " + _clip(f["last"], BANNER_W - 4)))
    L.append(rule)

    # 섹션을 (제목, 곁말, 본문) 으로 모아 두고 마지막에 가지를 그린다 —
    # 매칭이 없어 섹션이 통째로 비면 └─ 위치가 달라진다.
    secs = []

    # ── 이 레포에 자동 매칭된 것 ─────────────────────────────────────
    body = []
    skills = f["dom"] + [n for k, n, _ in f["reco"] if k == "skill" and n not in f["dom"]]
    agents = [(n, why) for k, n, why in f["reco"] if k == "agent"]
    cmds = [f"/{n}" for k, n, _ in f["reco"] if k == "cmd"]
    if skills:
        body += _wrap("스킬", [_cyan(s) for s in skills[:4]])
    for i, (n, why) in enumerate(agents[:3]):
        body.append(_row("에이전트" if i == 0 else "", _pad(_cyan(n), 24) + _dim(why)))
    if cmds:
        body.append(_row("커맨드", " · ".join(_cyan(c) for c in cmds)))
    if not body:
        body.append(_row("", _dim("자동 매칭 없음 — 그냥 하려는 일을 말하면 된다")))
    secs.append(("이 레포에서 바로", "", body))

    # ── 부르는 법 ───────────────────────────────────────────────────
    # 예시는 한 줄에 하나씩, 화살표를 세로로 맞춘다 — 붙여 쓰면 어느 말이 어느
    # 스킬을 여는지 눈으로 짚기 어렵다.
    body = []
    cw = max(_w(say) for say, _ in SAY_EXAMPLES) + 2
    for i, (say, sk) in enumerate(SAY_EXAMPLES):
        body.append(_row("스킬" if i == 0 else "", _pad(say, cw) + _dim("→ ") + _cyan(sk)))
    body += _wrap("에이전트", [f"{_cyan(n)} {_dim(why)}" for n, why in CALL_AGENTS])
    body += _wrap("커맨드", [f"{_cyan(n)} {_dim(why)}" for n, why in CALL_CMDS])
    secs.append(("부르는 법", "말하면 스킬이 열리고, 이름을 부르면 온다", body))

    # ── 매번 까먹는 것 ───────────────────────────────────────────────
    secs.append(("자주 잊는 것", "", [
        _row("백그라운드", "colcon build · 학습 · rosbag " + _dim("→ 120초에 안 잘린다")),
        _row("Monitor", "빌드·로그 감시 " + _dim("실패 시그니처를 걸어야 잡는다")),
        _row("cron", (f"{f['ncron']}개 돌고 있다 " + _dim("/setup:tree 루프 로 확인")
                      if f["ncron"] else _dim("등록된 것 없음"))),
        _row("되돌리기", _cyan("/rewind") + _dim(" 되돌리기 · ") + _cyan("/resume")
             + _dim(" 세션복구 · ") + _cyan("/compact") + _dim(" 압축")),
        _row("지식", "~/knowledge " + _dim("논문·리뷰·로봇분석. 레포에 넣지 않는다")),
    ]))

    # ── 안 써본 스킬 하나 ────────────────────────────────────────────
    if f["rot"]:
        body = [_row("", _cyan(f["rot"][0]) + _dim(" — " + _clip(f["rot"][1], 44)))]
        if unused:
            body.append(_row("", _dim(f"아직 안 써본 스킬 {unused}개 중 하나")))
        secs.append(("오늘 열어볼 것", "", body))

    # ── 가지 그리기 ─────────────────────────────────────────────────
    for si, (title, note, body) in enumerate(secs):
        last = si == len(secs) - 1
        L.append(_dim(RAIL))
        L.append(_dim("└─ " if last else "├─ ") + _bold(title)
                 + (_dim("   " + note) if note else ""))
        L += [_unrail(b) for b in body] if last else body

    # 꼬리말. `!` 직접 실행을 먼저 권하는 이유까지 적는다 — 이유를 안 적으면
    # 그냥 /setup:tree 를 쓰게 되고, 그건 출력 전체가 모델 컨텍스트를 거친다.
    tip = "! python3 ~/.claude/bin/setup-tree.py"
    gap = " " * 11
    L += [
        rule,
        " " + _pad(_cyan("전체 지도"), 11) + _bold(tip),
        " " + gap + _dim("↳ 터미널에서 직접 실행 — 색이 살고 컨텍스트를 안 쓴다"),
        " " + gap + _dim("↳ /setup:tree 도 같은 내용이지만 내가 읽어서 토큰을 쓴다"),
        " " + _pad(_cyan("더 보기"), 11) + _cyan("/setup:guide")
        + _dim(" 사용법 · ") + _cyan("/setup:audit") + _dim(" 세팅 점검"),
    ]
    return "\n".join(L)


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
    """(kind, name, why) 로 돌려준다 — 배너와 컨텍스트가 표기를 각자 정하도록."""
    out, seen = [], set()
    for tag in stack:
        for key, items in RECO.items():
            if not tag.startswith(key):
                continue
            for kind, name, why in items:
                if name in seen or not _exists(kind, name, cwd):
                    continue
                seen.add(name)
                out.append((kind, name, why))
    return out[:5]


def fmt_reco(reco):
    return [f"/{n}" if k == "cmd" else f"`{n}`({why})" for k, n, why in reco]


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
            # description 뒤쪽의 TRIGGER/DO NOT TRIGGER 절은 검색용이지 사람이 읽을
            # 문장이 아니다. 화면에 그대로 새면 잘린 영문 조각만 보인다.
            for cut in ("TRIGGER", "DO NOT TRIGGER", "Use this skill", "Use when"):
                i = desc.find(cut)
                if i > 0:
                    desc = desc[:i]
            desc = desc.strip().rstrip(".·-— ")
        return pick, desc[:70], len([n for n in names if n not in used])
    except Exception:
        return None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        data = {}

    cwd = data.get("cwd") or os.getcwd()

    stack = detect_stack(cwd)
    reco = recommend(cwd, stack)
    dom = domain_skills(cwd)
    rot = rotation_skill(stack)

    branch = run(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd)
    dirty, last = 0, ""
    if branch:
        d = run(["git", "status", "--porcelain"], cwd)
        dirty = len([l for l in d.split("\n") if l.strip()]) if d else 0
        last = run(["git", "log", "-1", "--pretty=%s"], cwd)

    distro = os.environ.get("ROS_DISTRO")
    ros = ""
    if distro:
        ros = (f"ROS {distro} · DOMAIN_ID {os.environ.get('ROS_DOMAIN_ID', '0(기본)')}"
               f" · RMW {os.environ.get('RMW_IMPLEMENTATION', '기본')}")

    # cron 개수는 세지 않고 박아두면 낡는다 — 배너가 3개 중 1개만 안내하고 있었다
    ncron = len([l for l in run(["crontab", "-l"], cwd).splitlines()
                 if l.strip() and not l.lstrip().startswith("#")])

    facts = {
        "ncron": ncron,
        "repo": os.path.basename(cwd.rstrip("/")) or cwd,
        "stack": stack, "branch": branch, "dirty": dirty, "last": last,
        "ros": ros, "reco": reco, "dom": dom,
        "rot": (rot[0], rot[1]) if rot else None,
        "counts": (
            _count(os.path.join(HOME, ".claude", "skills")) + _count(os.path.join(cwd, ".claude", "skills")),
            len([f for f in os.listdir(os.path.join(HOME, ".claude", "agents")) if f.endswith(".md")])
            if os.path.isdir(os.path.join(HOME, ".claude", "agents")) else 0,
            _count(os.path.join(HOME, ".claude", "commands"), "md"),
            rot[2] if rot else 0,
        ),
    }

    # Claude 컨텍스트용. 배너와 겹치지만 **기계가 틀리면 안 되는 사실**만 남긴다
    # (배너는 화면 배치가 바뀔 수 있고, 추천 문구는 사람용이다).
    lines = []
    if stack:
        lines.append(f"- 프로젝트 성격: {', '.join(stack)}")
    if branch:
        lines.append(f"- git: `{branch}` ({f'변경 {dirty}개' if dirty else 'clean'})")
        if last:
            lines.append(f"- 최근 커밋: {last[:90]}")
    if ros:
        lines.append(f"- {ros}")
    if reco:
        lines.append(f"- 여기서 쓸 만한 것: {' · '.join(fmt_reco(reco))}")
    if dom:
        lines.append(f"- 이 레포 도메인에 맞는 스킬: {', '.join(dom)}")
    lines.append("- 세팅 전체 사용법: `/setup:guide`")

    print(json.dumps({
        "systemMessage": banner(facts),
        "hookSpecificOutput": {
            "hookEventName": "SessionStart",
            "additionalContext": "## 세션 시작 컨텍스트 (자동 수집)\n" + "\n".join(lines),
        },
    }, ensure_ascii=False))
    sys.exit(0)


if __name__ == "__main__":
    main()
