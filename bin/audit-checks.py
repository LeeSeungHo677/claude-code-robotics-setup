#!/usr/bin/env python3
"""/setup:audit 의 결정적 점검 — 사람이 매번 눈으로 하면 빠뜨리는 것들.

  1. 정책 ↔ 강제 일치   CLAUDE.md 가 "실행하지 않는다" 고 한 하드웨어 명령이
                         실제로 settings ask/deny 나 dangerous-command-guard 에 걸리는가, allow 에 섞이지 않았는가
  2. 고정 컨텍스트 크기  CLAUDE.md · 스킬/에이전트 description · MEMORY.md — 매 세션 내는 비용
  3. 안 쓰는 스킬        ~/.claude.json skillUsage 기준
  4. 우리 것이 아닌 훅   ~/.claude/hooks 밖을 가리키는 훅과, 그 스크립트의 네트워크 호출
  5. 훅 fail-open 기록   ~/.claude/logs/hook-errors.log (최근 30일)
  6. 낡은 메모리         project/reference 유형인데 90일 넘게 갱신 안 된 것

자동으로 고치지 않는다. 보고만 한다.   실행: python3 ~/.claude/bin/audit-checks.py
"""

import glob
import importlib.util
import json
import os
import re
import time

C = os.path.expanduser("~/.claude")
NOW = time.time()

BUDGET = {                       # 넘으면 경고. 기준선은 2026-10-18 실측 + 여유
    "CLAUDE.md bytes": 12_000,
    "skill descriptions chars": 40_000,
    "agent descriptions chars": 6_000,
    "MEMORY.md lines": 60,
}


def load_guard():
    spec = importlib.util.spec_from_file_location("dcg", os.path.join(C, "hooks", "dangerous-command-guard.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def frontmatter(path):
    try:
        t = open(path, encoding="utf-8").read()
    except OSError:
        return {}
    if not t.startswith("---\n"):
        return {}
    end = t.find("\n---\n", 4)
    try:
        import yaml
        return yaml.safe_load(t[4:end]) or {}
    except Exception:
        return {}


def check_policy(settings):
    out = []
    text = open(os.path.join(C, "CLAUDE.md"), encoding="utf-8").read()
    # 규칙 문장 바로 뒤의 괄호 목록만 읽는다 (다음 줄의 '조회 명령' 목록까지 읽으면 안 된다)
    m = re.search(r"하드웨어를 실제로 움직이는 명령[^\n]*\n\s*\(([^)]*)\)", text)
    cmds = re.findall(r"`([^`]+)`", m.group(1)) if m else []
    expanded = []
    for c in cmds:                                   # `ros2 run/launch` → 두 개
        mm = re.match(r"^(.*\s)(\w+)/(\w+)$", c)
        expanded += [mm.group(1) + mm.group(2), mm.group(1) + mm.group(3)] if mm else [c]
    perms = settings.get("permissions", {})
    guard = load_guard()
    for c in expanded:
        in_allow = [a for a in perms.get("allow", []) if c in a]
        in_ask = any(c in a for a in perms.get("ask", []) + perms.get("deny", []))
        g, _, _ = guard.decide(f"cd /tmp && {c} x")
        status = "OK" if (in_ask or g in ("ask", "deny")) and not in_allow else "✗"
        out.append(f"| `{c}` | {'O' if in_ask else '-'} | {g or '-'} | {'**' + str(in_allow) + '**' if in_allow else '-'} | {status} |")
    if not expanded:
        return ["- ✗ CLAUDE.md 에서 하드웨어 명령 목록을 찾지 못함 (문구가 바뀌었나?)"]
    return ["| 명령 | settings ask/deny | guard | allow 에 섞임 | 판정 |", "|---|---|---|---|---|"] + out


def check_budget():
    skills = glob.glob(os.path.join(C, "skills", "*", "SKILL.md"))
    sdesc = [(os.path.basename(os.path.dirname(p)), str(frontmatter(p).get("description", ""))) for p in skills]
    adesc = [str(frontmatter(p).get("description", "")) for p in glob.glob(os.path.join(C, "agents", "*.md"))]
    mem = glob.glob(os.path.join(C, "projects", "*", "memory", "MEMORY.md"))
    vals = {
        "CLAUDE.md bytes": os.path.getsize(os.path.join(C, "CLAUDE.md")),
        "skill descriptions chars": sum(len(d) for _, d in sdesc),
        "agent descriptions chars": sum(len(d) for d in adesc),
        "MEMORY.md lines": max((sum(1 for _ in open(p, encoding="utf-8")) for p in mem), default=0),
    }
    out = ["| 항목 | 현재 | 예산 | |", "|---|---|---|---|"]
    for k, v in vals.items():
        out.append(f"| {k} | {v:,} | {BUDGET[k]:,} | {'✗ 초과' if v > BUDGET[k] else 'OK'} |")
    top = sorted(sdesc, key=lambda x: -len(x[1]))[:5]
    out.append("\n가장 긴 스킬 description: " + ", ".join(f"`{n}`({len(d)})" for n, d in top))
    return out


def check_unused():
    try:
        su = json.load(open(os.path.expanduser("~/.claude.json"), encoding="utf-8")).get("skillUsage") or {}
    except Exception:
        return ["- skillUsage 를 읽지 못함"]
    mine = sorted(os.path.basename(os.path.dirname(p)) for p in glob.glob(os.path.join(C, "skills", "*", "SKILL.md")))
    unused = [s for s in mine if (su.get(s) or {}).get("usageCount", 0) == 0]
    return [f"- 사용 기록 0회: {len(unused)}/{len(mine)}개 — description 이 실제 요청 단어와 안 맞을 수 있다",
            "  " + ", ".join(f"`{s}`" for s in unused)]


def check_foreign_hooks(settings):
    out, seen = [], set()
    for ev, groups in settings.get("hooks", {}).items():
        for g in groups:
            for h in g.get("hooks", []):
                cmd = h.get("command", "")
                if "/.claude/hooks/" in cmd:
                    continue
                scripts = sorted(set(re.findall(r"[\"']?(\$\{?HOME-?\}?/[^\"'\s;]+\.(?:sh|py|js))", cmd)))
                key = (tuple(scripts) or (cmd[:60],))
                if key in seen:
                    continue
                seen.add(key)
                net = []
                for s in scripts:
                    p = os.path.expanduser(re.sub(r"\$\{?HOME-?\}?", "~", s))
                    try:
                        body = open(p, encoding="utf-8", errors="replace").read()
                        net = sorted(set(re.findall(r"\b(curl|wget|nc|https?://[\w.:-]+)", body)))
                    except OSError:
                        net = ["(스크립트 없음)"]
                events = [e for e, gs in settings["hooks"].items()
                          if any(s in hh.get("command", "") for gg in gs for hh in gg.get("hooks", []) for s in scripts)]
                out.append(f"- {', '.join(scripts) or cmd[:60]} — 이벤트 {len(events)}개 — 네트워크: {', '.join(net[:6]) or '없음'}")
    return ([f"- 우리 것이 아닌 훅 스크립트 {len(out)}종"] + out) if out else ["- 없음"]


def check_hook_errors():
    p = os.path.join(C, "logs", "hook-errors.log")
    if not os.path.exists(p):
        return ["- 기록 없음 (훅이 입력을 못 읽고 통과한 적 없음)"]
    recent = []
    for line in open(p, encoding="utf-8"):
        ts = line.split("\t", 1)[0]
        try:
            if NOW - time.mktime(time.strptime(ts, "%Y-%m-%dT%H:%M:%S")) < 30 * 86400:
                recent.append(line.rstrip())
        except ValueError:
            pass
    return [f"- 최근 30일 {len(recent)}건" + (" — 쌓이면 fail-open 설계를 재검토할 신호" if recent else "")] + \
           [f"  {r}" for r in recent[-5:]]


def check_memory():
    out = []
    for p in glob.glob(os.path.join(C, "projects", "*", "memory", "*.md")):
        if p.endswith("MEMORY.md"):
            continue
        md = frontmatter(p).get("metadata") or {}
        typ, mod = md.get("type"), str(md.get("modified", ""))
        if typ not in ("project", "reference") or not mod:
            continue
        try:
            age = (NOW - time.mktime(time.strptime(mod[:19], "%Y-%m-%dT%H:%M:%S"))) / 86400
        except ValueError:
            continue
        if age > 90:
            out.append(f"- `{os.path.basename(p)}` ({typ}, {age:.0f}일 전) — 아직 맞는지 확인")
    return out or ["- 90일 넘은 project/reference 메모리 없음"]


def main():
    settings = json.load(open(os.path.join(C, "settings.json"), encoding="utf-8"))
    sections = [
        ("1. 정책 ↔ 강제 일치 (하드웨어 명령)", check_policy(settings)),
        ("2. 고정 컨텍스트 크기", check_budget()),
        ("3. 안 쓰는 스킬", check_unused()),
        ("4. 우리 것이 아닌 훅", check_foreign_hooks(settings)),
        ("5. 훅 fail-open 기록", check_hook_errors()),
        ("6. 낡은 메모리", check_memory()),
    ]
    for title, lines in sections:
        print(f"### {title}")
        print("\n".join(lines))
        print()


if __name__ == "__main__":
    main()
