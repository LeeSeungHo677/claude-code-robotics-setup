#!/usr/bin/env python3
"""setup-tree.py 테스트.

이 도구의 실패 모드는 **분류표가 디스크와 어긋나는 것**이다 — 새로 만든 스킬이
트리에서 조용히 빠지거나, 지운 스킬을 계속 안내한다. 그것을 먼저 검사한다.

실행: python3 ~/.claude/bin/test_setup_tree.py
"""
import os
import re
import subprocess
import sys
import unicodedata

HERE = os.path.dirname(os.path.abspath(__file__))
TREE = os.path.join(HERE, "setup-tree.py")
SKILLS = os.path.expanduser("~/.claude/skills")
AGENTS = os.path.expanduser("~/.claude/agents")
MAX_W = 100          # setup-tree.py 의 W 상한

ANSI = re.compile(r"\x1b\[[0-9;]*m")


def dw(s):
    return sum(2 if unicodedata.east_asian_width(c) in "WF" else 1
               for c in ANSI.sub("", s))


def run(*args):
    r = subprocess.run([sys.executable, TREE, *args],
                       capture_output=True, text=True, timeout=30)
    return r.stdout, r.returncode


def main():
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f" — {detail}"))
        if not cond:
            fails.append(name)

    # 1) 분류표 ↔ 디스크 — 이 도구의 핵심 불변식
    out, rc = run("--check")
    check("분류표와 디스크 일치 (--check)", rc == 0, out.strip()[:200])

    full, rc = run()
    check("전체 출력 exit 0", rc == 0, f"exit {rc}")

    # 2) 디스크의 스킬·에이전트가 하나도 안 빠져야 한다.
    #    분류표에 없으면 '미분류' 로라도 나와야 한다 — 조용히 사라지면 안 된다.
    on_disk = sorted(d for d in os.listdir(SKILLS)
                     if os.path.isfile(os.path.join(SKILLS, d, "SKILL.md")))
    missing = [n for n in on_disk if not re.search(rf"(?<![a-z0-9-]){re.escape(n)}(?![a-z0-9-])", full)]
    check(f"스킬 {len(on_disk)}개 전부 출력", not missing, f"빠짐: {missing[:5]}")

    ag_disk = sorted(f[:-3] for f in os.listdir(AGENTS) if f.endswith(".md"))
    ag_missing = [n for n in ag_disk if n not in full]
    check(f"에이전트 {len(ag_disk)}개 전부 출력", not ag_missing, f"빠짐: {ag_missing}")

    # 3) 파이프로 나가면 색을 끈다 (모델이 읽을 때 토큰 낭비)
    check("파이프 출력에 ANSI 없음", "\x1b" not in full, repr(full[:80]))

    # 4) 줄 폭
    over = [(dw(l), l) for l in full.split("\n") if dw(l) > MAX_W]
    check(f"모든 줄 ≤ {MAX_W}칸", not over,
          "; ".join(f"{w}칸 {l[:40]}" for w, l in over[:3]))

    # 5) 트리가 닫혀야 한다 — 빈 그룹 때문에 마지막 가지가 어긋난 적이 있다
    check("마지막 최상위 가지가 └─", "\n└─ " in full, full[-300:])
    tops = re.findall(r"^[├└]─ ", full, re.M)
    check("최상위 가지 중 └─ 는 하나", tops.count("└─ ") == 1, f"{tops}")

    # 5-1) 하위 그룹도 닫혀야 한다. 섹션마다 마지막 그룹은 정확히 하나여야 한다
    #      (마커를 하드코딩했다가 필터를 걸면 안 닫히는 일이 있었다)
    for sec, nxt in (("하네스", "루프"), ("루프", None)):
        blk = full.split(f"─ {sec} ")[-1]
        if nxt:
            blk = blk.split(f"─ {nxt} ")[0]
        groups = re.findall(r"^.{0,6}[├└]─ ", blk, re.M)
        check(f"{sec} 하위 그룹이 └─ 로 닫힘",
              sum(1 for g in groups if "└─" in g) == 1, f"{groups}")

    # 5-2) cron 은 crontab -l 을 실제로 읽는다 (목록을 박아두면 어긋난다)
    import subprocess as sp
    real = [l for l in sp.run(["crontab", "-l"], capture_output=True, text=True)
            .stdout.splitlines() if l.strip() and not l.startswith("#")]
    shown = [l for l in full.split("\n") if "cron.log" in l or "@reboot" in l]
    check(f"crontab {len(real)}줄이 전부 나옴", len(shown) >= len(real) - 1,
          f"crontab {len(real)}줄 / 출력 {len(shown)}줄")

    # 6) 범례 — '의미·사용법' 이 이 도식의 목적이다
    for must in ("무엇이 어떻게 열리는가", "하려는 일을 말하면", "이름을 불러야 온다"):
        check(f"범례에 '{must}'", must in full, full[:200])

    # 7) 필터
    # 6-1) 하네스·루프 섹션
    for must in ("하네스", "루프", "run_in_background", "/rewind", "crontab -l",
                 "~/knowledge"):
        check(f"'{must}' 포함", must in full, full[-400:])

    one, rc = run("캘리브레이션")
    check("필터 — 걸린 것만 나옴", "robot-calibration" in one and "nav2" not in one,
          one[:200])
    check("필터 — 개수를 '보인수/전체' 로 표기", re.search(r"스킬 \d+/\d+", one) is not None,
          one[:200])
    check("필터 — 트리가 닫힘", one.count("\n└─ ") >= 1, one[:200])

    none, rc = run("zzzznotathing")
    check("없는 검색어 — 안내 문구", "걸리는 것이 없다" in none, none[:200])
    check("없는 검색어 — exit 0", rc == 0, f"exit {rc}")

    # 8) -d 는 설명을 붙인다. TRIGGER 절이 새면 안 된다
    d, _ = run("-d")
    check("-d 설명 표시", "ros2_control 로 하드웨어를 제어" in d, d[:200])
    check("-d 에 TRIGGER 절이 안 샘", "TRIGGER when" not in d,
          next((l for l in d.split("\n") if "TRIGGER when" in l), "")[:120])

    print(f"\n실패 {len(fails)}건" + (f": {fails}" if fails else " — 전부 통과"))
    sys.exit(1 if fails else 0)


main()
