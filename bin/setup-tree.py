#!/usr/bin/env python3
"""~/.claude 세팅 전체를 tree 도식으로 그린다.

세션 시작 배너에는 넣지 않는다 — 배너는 매 세션 모델 컨텍스트 비용을 내는데,
이 트리는 한 번 보면 되는 종류의 정보다. 필요할 때만 부른다.

    python3 ~/.claude/bin/setup-tree.py            전체 트리
    python3 ~/.claude/bin/setup-tree.py -d         스킬 설명까지
    python3 ~/.claude/bin/setup-tree.py 로봇        이름·설명에 걸리는 것만
    python3 ~/.claude/bin/setup-tree.py --check    분류 누락·유령 항목만 점검

터미널에서 직접 돌리면(`! python3 ~/.claude/bin/setup-tree.py`) 토큰을 전혀 쓰지 않는다.
출력이 파이프로 나가면 색을 자동으로 끈다.

분류는 이름 목록으로 박아둔다. 대신 **디스크와 대조해서 어긋나면 화면에 띄운다** —
새 스킬이 조용히 사라지거나, 지운 스킬을 계속 안내하는 것을 막는다(`--check`).

스킬을 직접 추가하면 `미분류` 그룹에 모여서 보인다. 이건 정상이고 `--check` 도
통과한다. 제자리에 넣고 싶으면 아래 `SKILL_GROUPS` 에 이름을 추가하면 된다.
"""

import json
import os
import re
import shutil
import sys
import unicodedata

HOME = os.path.expanduser("~")
ROOT = os.path.join(HOME, ".claude")
SKILLS = os.path.join(ROOT, "skills")
AGENTS = os.path.join(ROOT, "agents")
COMMANDS = os.path.join(ROOT, "commands")

# ─────────────────────────── 출력 도구 ───────────────────────────
_ANSI = re.compile(r"\x1b\[[0-9;]*m")
_COLOR = sys.stdout.isatty() and not os.environ.get("NO_COLOR")
W = min(shutil.get_terminal_size((92, 24)).columns, 100)


def _c(code, s):
    return s if not _COLOR or not s else f"\x1b[{code}m{s}\x1b[0m"


def dim(s):    return _c("2", s)
def bold(s):   return _c("1", s)
def cyan(s):   return _c("36", s)
def green(s):  return _c("32", s)
def yellow(s): return _c("33", s)
def red(s):    return _c("31", s)


def dw(s):
    """화면 폭 (한글·CJK 2칸)."""
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in _ANSI.sub("", s))


def pad(s, n):
    return s + " " * max(0, n - dw(s))


def clip(s, n):
    out, w = [], 0
    for ch in s:
        cw = 2 if unicodedata.east_asian_width(ch) in "WF" else 1
        if w + cw > n - 1:
            return "".join(out) + "…"
        out.append(ch)
        w += cw
    return "".join(out)


def flow(items, prefix, sep="  "):
    """이름들을 화면 폭에 맞춰 여러 줄로 흘린다. 손으로 줄바꿈 위치를 정하지 않는다."""
    lines, cur = [], []
    avail = W - dw(prefix)
    for it in items:
        if cur and dw(sep.join(cur + [it])) > avail:
            lines.append(prefix + sep.join(cur))
            cur = [it]
        else:
            cur.append(it)
    if cur:
        lines.append(prefix + sep.join(cur))
    return lines


# ─────────────────────────── 분류 ───────────────────────────
# 순서가 곧 화면 순서다. 로봇 작업 흐름(만든다 → 움직인다 → 본다 → 배운다 →
# 시뮬 → 현장)을 따라 배치했다. 웹/인프라는 이 집의 주 업무가 아니므로 뒤로.
SKILL_GROUPS = [
    ("ROS 2 · 노드 · 제어", [
        "ros2-engineering", "ros2-control", "ros2-web-integration", "nav2",
        "behavior-tree", "robot-bringup", "robot-visualization",
        "robotics-design-patterns", "robotics-software-principles",
        "modern-cpp-robotics", "vda5050", "multi-robot-fleet",
        "docker-ros2-development"]),
    ("운동 · 계획 · 상태추정", [
        "motion-planning", "manipulation-control", "robot-kinematics",
        "state-estimation", "slam-algorithms", "robot-algorithm-design",
        "legged-rl"]),
    ("인지 · 캘리브레이션", [
        "robot-perception", "deep-learning-vision", "robot-calibration"]),
    ("학습 · 정책", [
        "rl-training", "imitation-learning", "vla-vlm-robotics", "ml-pipeline",
        "gpu-optimization", "cloud-gpu-job"]),
    ("시뮬레이션 · sim2real", [
        "mujoco", "gazebo", "nvidia-isaac", "sim-to-real-check"]),
    ("하드웨어 · 통신 · 원격", [
        "fieldbus-comm", "robot-networking", "teleoperation"]),
    ("현장 운영 · 안전 · 데이터", [
        "robot-safety-compliance", "robotics-security", "fleet-ops",
        "incident-analysis", "robot-perf-optimization", "robot-data-pipeline",
        "robotics-testing"]),
    ("연구 · 문서 검토", [
        "arxiv-search", "paper-review", "paper-summarize", "repo-review",
        "notes-review"]),
    ("웹 · 대시보드", [
        "react-expert", "nextjs-developer", "frontend-design",
        "frontend-excellence", "design-system", "ui-ux-design", "typescript-pro",
        "accessibility-wcag", "performance-optimization", "websocket-engineer",
        "playwright-expert"]),
    ("백엔드 · 데이터", [
        "fastapi-expert", "python-pro", "api-designer", "graphql-architect",
        "postgres-pro", "database-optimizer", "redis-patterns",
        "data-engineering"]),
    ("인프라 · 배포 · 운영", [
        "kubernetes-specialist", "terraform-engineer", "docker-best-practices",
        "devops-automation", "ci-cd-pipelines", "cloud-architect",
        "monitoring-expert", "sre-engineer", "microservices-architect",
        "system-architecture", "system-design"]),
    ("보안 · 인증", ["security-hardening", "authentication-patterns"]),
    ("테스트 · 개발 습관", ["tdd-mastery", "testing-strategies", "git-advanced"]),
    ("Claude 세팅 · LLM", ["setup-maintenance", "mcp-development", "llm-integration"]),
]

AGENT_GROUPS = [
    ("로봇", ["ros2-reviewer", "robot-safety-reviewer", "robotics-architect",
              "motion-control-engineer", "perception-ml-engineer",
              "robot-perf-engineer"]),
    ("소프트웨어 · 인프라", ["backend-engineer", "frontend-engineer",
                            "platform-engineer", "test-architect",
                            "performance-engineer", "security-auditor",
                            "error-detective", "research-analyst"]),
]

# CLAUDE.md 가 "이 이름이 적힌 것만 실제로 쓰인다" 고 못박은 3개
PRIMARY_AGENTS = {"ros2-reviewer", "robot-safety-reviewer", "robotics-architect"}

# 하네스는 Claude Code 자체 기능이라 디스크에 파일이 없다 — 여기만 정적 목록이다.
# 그래서 "무엇을 위해 쓰는가"만 적고 정확한 플래그·옵션은 적지 않는다(먼저 낡는다).
HARNESS_GROUPS = [
    ("긴 작업", [
        ("run_in_background", "colcon build · 학습 · rosbag — 120초 타임아웃에 안 잘린다"),
        ("Monitor", "빌드·로그 감시. 실패 시그니처를 걸어야 크래시를 잡는다"),
        ("서브에이전트", "넓게 훑을 일은 Explore 에 넘기고 결론만 받는다"),
    ]),
    ("세션 다루기", [
        ("/rewind", "되돌리기"), ("/resume", "세션 복구"),
        ("/compact", "컨텍스트 압축"), ("/model", "모델 전환"),
        ("/fast", "빠른 출력 토글"), ("/config", "설정"),
    ]),
    ("번들 스킬", [
        ("/code-review", "변경분 리뷰"), ("/security-review", "보안 리뷰"),
        ("/loop", "주기 실행"), ("/schedule", "예약 실행"),
        ("/run", "앱 띄워서 확인"), ("/init", "CLAUDE.md 생성"),
    ]),
]
HARNESS_NOTE = "Claude Code 자체 기능 — 디스크에 파일이 없다"

HOOK_WHAT = {
    "dangerous-command-guard": "rm -rf · 강제푸시 · 하드웨어 구동 명령 차단",
    "secret-scanner": "코드에 들어가는 키·토큰 차단",
    "ros2-workspace-guard": "build/ install/ log/ 편집 차단",
    "session-context": "이 배너 — 프로젝트 감지·git·추천 주입",
    "version-watch": "Claude Code 새 버전 알림",
}


# ─────────────────────────── 수집 ───────────────────────────
def read_desc(path, limit=900, first_sentence=False):
    """프론트매터 description 한 줄. TRIGGER 절은 검색 인덱스라 사람이 읽을 것이 아니다."""
    try:
        with open(path, encoding="utf-8") as f:
            head = f.read(limit)
    except OSError:
        return ""
    i = head.find("description:")
    if i < 0:
        return ""
    d = " ".join(head[i + 12:].split("\n---")[0].split()).lstrip(">|").strip()
    for cut in ("TRIGGER", "DO NOT TRIGGER", "Use this skill", "Use when",
                "Invoke for"):
        j = d.find(cut)
        if j > 0:
            d = d[:j]
    if first_sentence:
        # 에이전트 설명은 "역할 전담. 상세…" 꼴이라 첫 문장만으로 충분하다.
        # 소수점(3.11)에서 끊기지 않도록 뒤에 공백이 오는 마침표만 문장 끝으로 본다.
        m = re.search(r"[.。](\s|$)", d)
        if m and m.start() > 6:
            d = d[:m.start()]
    return d.strip().rstrip(".·-— ")


def nonempty(groups, available):
    """실제로 그려질 그룹만 남긴다 — 빈 그룹이 섞이면 마지막 가지(└─)가 어긋난다."""
    return [(t, [n for n in names if n in available]) for t, names in groups
            if any(n in available for n in names)]


def disk_skills():
    try:
        return sorted(d for d in os.listdir(SKILLS)
                      if os.path.isfile(os.path.join(SKILLS, d, "SKILL.md")))
    except OSError:
        return []


def disk_agents():
    try:
        return sorted(f[:-3] for f in os.listdir(AGENTS) if f.endswith(".md"))
    except OSError:
        return []


def disk_commands():
    out = {}
    try:
        for g in sorted(os.listdir(COMMANDS)):
            p = os.path.join(COMMANDS, g)
            if os.path.isdir(p):
                out[g] = sorted(f[:-3] for f in os.listdir(p) if f.endswith(".md"))
    except OSError:
        pass
    return out


def disk_hooks():
    """settings.json 에 실제로 등록된 우리 훅만 (이벤트별)."""
    out = {}
    try:
        with open(os.path.join(ROOT, "settings.json"), encoding="utf-8") as f:
            cfg = json.load(f)
        for ev, groups in (cfg.get("hooks") or {}).items():
            for g in groups:
                for h in g.get("hooks", []):
                    m = re.search(r"hooks/([a-z0-9-]+)\.py", h.get("command", ""))
                    if m:
                        out.setdefault(ev, []).append(m.group(1))
    except Exception:
        pass
    return out


WEEKDAY = "일월화수목금토"


def _when(m, h, dom, mon, dow):
    """crontab 5필드를 사람 말로. 흔한 꼴만 풀고 나머지는 원문 그대로 둔다."""
    try:
        at = f"{int(h):02d}:{int(m):02d}"
    except ValueError:
        return " ".join((m, h, dom, mon, dow))
    if (dom, mon, dow) == ("*", "*", "*"):
        return f"매일 {at}"
    if dom == "*" and mon == "*" and dow.isdigit():
        return f"매주 {WEEKDAY[int(dow) % 7]} {at}"
    if dom.isdigit() and mon == "*" and dow == "*":
        return f"매월 {dom}일 {at}"
    return " ".join((m, h, dom, mon, dow))


def read_cron():
    """crontab -l 을 실제로 읽는다. 목록을 박아두면 크론을 고칠 때마다 어긋난다.
    (배너는 3개 중 1개만 안내하고 있었다)"""
    import subprocess
    try:
        r = subprocess.run(["crontab", "-l"], capture_output=True, text=True, timeout=5)
        raw = r.stdout if r.returncode == 0 else ""
    except Exception:
        return []
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("@"):
            tag, _, cmd = line.partition(" ")
            out.append((tag, cmd.split()[0] if cmd else "", ""))
            continue
        parts = line.split(None, 5)
        if len(parts) < 6:
            continue
        when = _when(*parts[:5])
        cmd = parts[5]
        script = os.path.basename(cmd.split(">")[0].split()[0])
        m = re.search(r">>?\s*(\S+)", cmd)
        out.append((when, script, m.group(1).replace(HOME, "~") if m else ""))
    return out


def drift():
    """분류표와 디스크의 차이. 조용히 사라지거나 유령이 남는 것을 막는다."""
    on_disk = set(disk_skills())
    listed = {n for _, names in SKILL_GROUPS for n in names}
    a_disk, a_listed = set(disk_agents()), {n for _, ns in AGENT_GROUPS for n in ns}
    return {
        "미분류 스킬": sorted(on_disk - listed),
        "유령 스킬(분류표에만 있음)": sorted(listed - on_disk),
        "미분류 에이전트": sorted(a_disk - a_listed),
        "유령 에이전트": sorted(a_listed - a_disk),
    }


# ─────────────────────────── 그리기 ───────────────────────────
def legend():
    rows = [
        ("스킬", "하려는 일을 말하면 자동으로 열린다", '"보상함수 설계해줘"'),
        ("에이전트", "이름을 불러야 온다", '"ros2-reviewer 로 봐줘"'),
        ("커맨드", "/ 로 직접 친다", "/robot:preflight"),
        ("훅", "안 불러도 자동으로 걸린다", "위험 명령·시크릿 차단"),
    ]
    lw = max(dw(r[0]) for r in rows) + 2
    mw = max(dw(r[1]) for r in rows) + 2
    out = [dim("│"), dim("│  ") + bold("무엇이 어떻게 열리는가")]
    for name, how, ex in rows:
        out.append(dim("│    ") + pad(cyan(name), lw) + pad(how, mw) + dim(ex))
    return out


def _unrail(line):
    """바깥 세로줄(첫 '│')만 공백으로. 안쪽 그룹 마커는 건드리지 않는다."""
    i = line.find("│")
    return line[:i] + " " + line[i + 1:] if i >= 0 else line


def section(mark, title, shown, total, note):
    """├─ 스킬 91   설명   (필터 중이면 '3/91')"""
    n = str(total) if shown == total else f"{shown}/{total}"
    head = f"{dim(mark)} {bold(title)} {green(n)}"
    return pad(head, 34) + dim(note)


def render(show_desc=False, query=None):
    L = []
    sk, ag, cm, hk = disk_skills(), disk_agents(), disk_commands(), disk_hooks()
    ncmd = sum(len(v) for v in cm.values())
    nhook = sum(len(v) for v in hk.values())

    q = (query or "").lower()

    def hit(name, desc=""):
        return not q or q in name.lower() or q in desc.lower()

    L.append(dim("╭─ ") + bold("~/.claude") + dim(" — Claude Code 세팅"))
    L.append(dim("│  ") + f"스킬 {green(str(len(sk)))} · 에이전트 {green(str(len(ag)))}"
             f" · 커맨드 {green(str(ncmd))} · 훅 {green(str(nhook))}"
             + ("" if not q else dim(f"   (필터: {query})")))
    if not q:
        L += legend()

    # 섹션을 (제목, 보인 수, 전체 수, 설명, 본문줄) 로 모아두고 마지막에 가지를
    # 그린다 — 필터로 섹션이 통째로 비면 └─ 위치가 달라지기 때문이다.
    secs = []

    # ── 스킬 ───────────────────────────────────────────────────
    body = []
    descs = {}
    if show_desc or q:
        descs = {n: read_desc(os.path.join(SKILLS, n, "SKILL.md")) for n in sk}
    groups = nonempty(SKILL_GROUPS + [("미분류", drift()["미분류 스킬"])],
                      {n for n in sk if hit(n, descs.get(n, ""))})
    nsk = 0
    for gi, (title, names) in enumerate(groups):
        nsk += len(names)
        last = gi == len(groups) - 1
        body.append(dim("│  " + ("└─ " if last else "├─ ")) + bold(title)
                    + dim(f"  ({len(names)})"))
        bar = "│  " + ("   " if last else "│  ")
        if show_desc or q:
            nw = max(dw(n) for n in names) + 2
            for n in names:
                body.append(dim(bar) + "   " + pad(cyan(n), nw)
                            + dim(clip(descs.get(n, ""), W - dw(bar) - nw - 4)))
        else:
            body += flow([cyan(n) for n in names], dim(bar) + "   ")
    secs.append(("스킬", nsk, len(sk), "~/.claude/skills/<name>/SKILL.md", body))

    # ── 에이전트 ────────────────────────────────────────────────
    body, nag = [], 0
    adesc = {n: read_desc(os.path.join(AGENTS, n + ".md"), first_sentence=True)
             for n in ag}
    agroups = nonempty(AGENT_GROUPS + [("미분류", drift()["미분류 에이전트"])],
                       {n for n in ag if hit(n, adesc.get(n, ""))})
    for gi, (title, names) in enumerate(agroups):
        nag += len(names)
        last = gi == len(agroups) - 1
        body.append(dim("│  " + ("└─ " if last else "├─ ")) + bold(title)
                    + dim(f"  ({len(names)})"))
        bar = "│  " + ("   " if last else "│  ")
        nw = max(dw(n) for n in names) + 3
        for n in names:
            star = yellow("★") if n in PRIMARY_AGENTS else " "
            body.append(dim(bar) + "  " + star + " " + pad(cyan(n), nw)
                        + dim(clip(adesc.get(n, ""), W - dw(bar) - nw - 6)))
    secs.append(("에이전트", nag, len(ag), "이름을 불러야 온다. ★ = 상시 사용", body))

    # ── 커맨드 ──────────────────────────────────────────────────
    body, ncm = [], 0
    keys = [g for g in cm if any(hit(f"/{g}:{n}") for n in cm[g])]
    for gi, g in enumerate(keys):
        names = [n for n in cm[g] if hit(f"/{g}:{n}")]
        ncm += len(names)
        last = gi == len(keys) - 1
        body.append(dim("│  " + ("└─ " if last else "├─ ")) + cyan(f"/{g}:")
                    + dim(f"  ({len(names)})"))
        bar = "│  " + ("   " if last else "│  ")
        body += flow(names, dim(bar) + "   ")
    secs.append(("커맨드", ncm, ncmd, "/<그룹>:<이름> 으로 친다", body))

    # ── 훅 ─────────────────────────────────────────────────────
    body, nhk = [], 0
    evs = [ev for ev in hk if any(hit(n, HOOK_WHAT.get(n, "")) for n in hk[ev])]
    for ei, ev in enumerate(evs):
        names = [n for n in hk[ev] if hit(n, HOOK_WHAT.get(n, ""))]
        nhk += len(names)
        last = ei == len(evs) - 1
        body.append(dim("│  " + ("└─ " if last else "├─ ")) + bold(ev))
        bar = "│  " + ("   " if last else "│  ")
        nw = max(len(n) for n in names) + 3
        for n in names:
            body.append(dim(bar) + "   " + pad(cyan(n), nw)
                        + dim(clip(HOOK_WHAT.get(n, ""), W - dw(bar) - nw - 5)))
    secs.append(("훅", nhk, nhook, "settings.json 에 등록. 자동으로 걸린다", body))

    # ── 하네스 ──────────────────────────────────────────────────
    body, nh, nh_all = [], 0, sum(len(v) for _, v in HARNESS_GROUPS)
    hgroups = [(t, [(n, w) for n, w in items if hit(n, w)])
               for t, items in HARNESS_GROUPS]
    hgroups = [(t, items) for t, items in hgroups if items]
    for gi, (title, items) in enumerate(hgroups):
        nh += len(items)
        last = gi == len(hgroups) - 1
        body.append(dim("│  " + ("└─ " if last else "├─ ")) + bold(title)
                    + dim(f"  ({len(items)})"))
        bar = "│  " + ("   " if last else "│  ")
        if max(dw(w) for _, w in items) <= 18:
            # 설명이 짧으면 한 줄에 여럿 흘린다 — 짧은 항목 6개에 6줄은 낭비다
            body += flow([f"{cyan(n)} {dim(w)}" for n, w in items],
                         dim(bar) + "   ", sep="   ")
        else:
            nw = max(dw(n) for n, _ in items) + 3
            for n, why in items:
                body.append(dim(bar) + "   " + pad(cyan(n), nw)
                            + dim(clip(why, W - dw(bar) - nw - 5)))
    secs.append(("하네스", nh, nh_all, HARNESS_NOTE, body))

    # ── 루프 ────────────────────────────────────────────────────
    cron = read_cron()
    rows = [(w, s, t) for w, s, t in cron if hit(s, w + " " + t)]
    knows = hit("knowledge", "지식 논문 리뷰 로봇분석")
    lgroups = ([("cron", f"  ({len(rows)})  crontab -l")] if rows else []) \
        + ([("지식 저장소", "")] if knows else [])
    body, nl = [], len(rows) + (1 if knows else 0)
    for gi, (title, note) in enumerate(lgroups):
        last = gi == len(lgroups) - 1
        body.append(dim("│  " + ("└─ " if last else "├─ ")) + bold(title) + dim(note))
        bar = "│  " + ("   " if last else "│  ")
        if title == "cron":
            ww = max(dw(w) for w, _, _ in rows) + 2
            sw = max(dw(s) for _, s, _ in rows) + 2
            for when, script, log in rows:
                tail = dim(clip("→ " + log, W - 30)) if log else ""
                body.append((dim(bar) + "   " + pad(yellow(when), ww)
                             + pad(cyan(script), sw) + tail).rstrip())
        else:
            body.append(dim(bar) + "   " + pad(cyan("~/knowledge"), 16)
                        + dim("논문·리뷰·로봇분석. 레포 안에 넣지 않는다"))
    secs.append(("루프", nl, len(cron) + 1, "실제로 돌고 있는 것", body))

    # ── 가지 그리기 ─────────────────────────────────────────────
    secs = [s for s in secs if s[4]]
    if not secs:
        L.append(dim("│"))
        L.append(dim("└─ ") + yellow(f"'{query}' 에 걸리는 것이 없다"))
    for si, (title, shown, total, note, body) in enumerate(secs):
        last = si == len(secs) - 1
        L.append(dim("│"))
        L.append(section("└─" if last else "├─", title, shown, total, note))
        # 마지막 섹션은 세로줄이 끝났으므로 바깥 레일(첫 '│')만 공백으로 바꾼다.
        # 색 코드가 앞에 붙으므로 startswith 로는 못 잡는다 — 첫 등장 위치를 찾는다.
        L += [_unrail(b) for b in body] if last else body

    # ── 어긋난 것 ───────────────────────────────────────────────
    bad = {k: v for k, v in drift().items() if v and "미분류" not in k}
    if bad:
        L.append("")
        for k, v in bad.items():
            L.append(red(f"  ! {k}: ") + ", ".join(v))
        L.append(dim("    setup-tree.py 의 SKILL_GROUPS/AGENT_GROUPS 를 고쳐야 한다"))
    return "\n".join(L)


def main():
    args = [a for a in sys.argv[1:]]
    if "--check" in args:
        d = drift()
        # 미분류(디스크에 있는데 분류표에 없음)는 **정상**이다 — 새로 만든 스킬은
        # 원래 거기 모이고, 이 세팅을 받아 자기 스킬을 추가한 사람도 마찬가지다.
        # 실제 고장은 유령(분류표에만 있고 디스크에 없음)뿐이라 그것만 exit 1.
        ghosts = {k: v for k, v in d.items() if v and "유령" in k}
        info = {k: v for k, v in d.items() if v and "유령" not in k}
        for k, v in info.items():
            print(f"{yellow(k)}: {', '.join(v)}")
        for k, v in ghosts.items():
            print(f"{red(k)}: {', '.join(v)}")
        if not ghosts:
            print(green("유령 항목 없음."))
        return 1 if ghosts else 0
    show_desc = "-d" in args or "--desc" in args
    query = next((a for a in args if not a.startswith("-")), None)
    print(render(show_desc, query))
    return 0


if __name__ == "__main__":
    sys.exit(main())
