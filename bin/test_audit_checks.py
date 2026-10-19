#!/usr/bin/env python3
"""audit-checks.py 테스트 — 지금은 7단계(배포판 drift)만 다룬다. 1~6단계는 실제 환경을 읽기만 한다.

7단계의 실패 모드는 둘이다: 의도적 차이를 매번 경고해서 결국 무시하게 되는 것(오탐),
그리고 허용목록이 낡아 실제 drift 를 가리는 것. 임시 디렉터리로 양쪽을 검사하고,
마지막에 실제 설정의 허용목록 키가 전부 실재하는 경로인지(오타) 본다.

실행: python3 ~/.claude/bin/test_audit_checks.py
"""
import importlib.util
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
AUDIT = os.path.join(HERE, "audit-checks.py")

_spec = importlib.util.spec_from_file_location("audit_checks", AUDIT)
ac = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(ac)


def w(root, rel, text="x\n"):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, "w", encoding="utf-8") as f:
        f.write(text)
    return p


def main():
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f" — {str(detail)[:300]}"))
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as tmp:
        local, dist = os.path.join(tmp, "local"), os.path.join(tmp, "dist")
        os.makedirs(local)
        os.makedirs(dist)
        cfg = os.path.join(local, "dist-sync.json")

        # 1) 설정 파일 없음 → SKIP 이고 ✗ 가 없다 (배포판 없는 세팅에서 경고가 뜨면 안 된다)
        out = ac.check_dist_drift(local, cfg)
        check("설정 없음 → SKIP, ✗ 없음", any("SKIP" in l for l in out) and not any("✗" in l for l in out), out)

        # 2) 배포판 경로가 없음 → SKIP
        json.dump({"dist": os.path.join(tmp, "nope")}, open(cfg, "w"))
        out = ac.check_dist_drift(local, cfg)
        check("배포판 경로 없음 → SKIP", any("SKIP" in l for l in out) and not any("✗" in l for l in out), out)

        # 3) 깨진 설정 → ✗ 한 줄, 예외는 아님
        open(cfg, "w").write("{not json")
        out = ac.check_dist_drift(local, cfg)
        check("깨진 설정 → ✗ 보고 (예외 없음)", any("✗" in l and "읽지 못함" in l for l in out), out)

        # 4) 트리: 동일 / 허용된 차이 / 허용 외 차이 / 디렉터리 허용 / 로컬 전용 / 배포판 전용 / 무시 대상 / 낡은 허용
        w(local, "bin/same.py", "a\n");          w(dist, "bin/same.py", "a\n")
        w(local, "bin/allowed.py", "L\n");       w(dist, "bin/allowed.py", "D\n")
        w(local, "bin/drift.py", "L\n");         w(dist, "bin/drift.py", "D\n")
        w(local, "skills/private/SKILL.md");     w(local, "skills/private/references/x.md")
        w(local, "skills/orphan/SKILL.md")
        w(dist, "hooks/new-in-dist.py")
        w(local, "hooks/__pycache__/junk.pyc");  w(local, "bin/drift.py.orig"); w(local, "hooks/.pytest_cache/v")
        w(local, "agents/stale.md", "s\n");      w(dist, "agents/stale.md", "s\n")
        w(local, "commands/x/y.md");             w(dist, "commands/x/y.md")        # dirs 밖 → 비교 안 함
        conf = {"dist": dist, "dirs": ["bin", "hooks", "agents", "skills"],
                "intentional": {"bin/allowed.py": "의도적", "skills/private/": "내부 전용",
                                "agents/stale.md": "예전엔 달랐음"}}
        json.dump(conf, open(cfg, "w"))
        out = ac.check_dist_drift(local, cfg)
        txt = "\n".join(out)
        flagged = [l for l in out if l.startswith("  ✗")]
        check("동일 파일은 안 나옴", "same.py" not in txt, txt)
        check("허용된 내용 차이는 안 나옴", "allowed.py" not in txt, txt)
        check("허용 외 내용 차이 → ✗ 내용 다름 (+최신 쪽 힌트)",
              any("내용 다름" in l and "`bin/drift.py`" in l and "최신" in l for l in flagged), txt)
        check("디렉터리 허용(끝 /)은 하위 전체에 적용", "private" not in txt, txt)
        check("허용 외 로컬 전용 → ✗ 로컬에만", any("로컬에만" in l and "skills/orphan/SKILL.md" in l for l in flagged), txt)
        check("배포판 전용 → ✗ 배포판에만", any("배포판에만" in l and "hooks/new-in-dist.py" in l for l in flagged), txt)
        check("__pycache__ · .pytest_cache · .orig 무시", not any(x in txt for x in ("junk.pyc", ".orig", ".pytest_cache")), txt)
        check("dirs 밖 디렉터리는 비교 안 함", "commands/x" not in txt, txt)
        check("낡은 허용 항목 표시", any("지금은 차이 없음" in l and "agents/stale.md" in l for l in out), txt)
        check("허용 외 차이 개수 = 3", any("허용 외 차이 3개" in l for l in out), txt)
        check("요약 줄에 차이·허용 수 (허용 디렉터리의 파일 2개 포함)", any("차이 6개 중 허용 3개" in l for l in out), txt)

        # 5) 설정 ignore — 이름 매칭과 상대경로 글롭 매칭 둘 다
        for pat in ("orphan", "skills/orph*", "*/orphan/*"):
            conf["ignore"] = [pat]
            json.dump(conf, open(cfg, "w"))
            out = ac.check_dist_drift(local, cfg)
            check(f"설정 ignore {pat!r} 로 제외", "orphan" not in "\n".join(out) and any("허용 외 차이 2개" in l for l in out), out)

        # 6) 전부 허용되면 '허용 외 차이 없음'
        conf["intentional"].update({"bin/drift.py": "x", "hooks/new-in-dist.py": "x"})
        json.dump(conf, open(cfg, "w"))
        out = ac.check_dist_drift(local, cfg)
        check("전부 허용 → '허용 외 차이 없음'", any("허용 외 차이 없음" in l for l in out) and not any(l.startswith("  ✗") for l in out), out)

    # 7) 실제 설정이 있으면: 허용목록 키가 전부 실재하는 경로인가 (오타·지운 파일)
    real_cfg = os.path.join(ac.C, "dist-sync.json")
    if os.path.isfile(real_cfg):
        conf = json.load(open(real_cfg, encoding="utf-8"))
        dist = os.path.expanduser(conf.get("dist") or "")
        if os.path.isdir(dist):
            missing = [k for k in conf.get("intentional") or {}
                       if not (os.path.exists(os.path.join(ac.C, k)) or os.path.exists(os.path.join(dist, k)))]
            check("실제 허용목록 키가 전부 실재", not missing, missing)
        else:
            print("  SKIP  실제 배포판 경로 없음 — 허용목록 실재 검사 생략")
    else:
        print("  SKIP  실제 dist-sync.json 없음 — 허용목록 실재 검사 생략")

    # 8) 스크립트 전체가 돌고 7단계 헤더가 찍힌다
    r = subprocess.run([sys.executable, AUDIT], capture_output=True, text=True, timeout=120)
    check("audit-checks.py exit 0", r.returncode == 0, r.stderr[-300:])
    check("'### 7. 배포판 drift' 헤더", "### 7. 배포판 drift" in r.stdout, r.stdout[-300:])

    print(f"\n실패 {len(fails)}건" + (f": {fails}" if fails else " — 전부 통과"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
