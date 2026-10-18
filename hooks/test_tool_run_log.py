#!/usr/bin/env python3
"""tool-run-log.py 테스트 — 기록 / 시크릿 가림 / 반복 경고.

임시 HOME 에서 돌린다 — 실제 ~/.claude/logs 를 오염시키지 않는다.
실행: python3 ~/.claude/hooks/test_tool_run_log.py   (standalone)
"""
import glob
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
HOOK = os.path.join(HERE, "tool-run-log.py")
HOME = tempfile.mkdtemp(prefix="trl-home-")
ENV = {**os.environ, "HOME": HOME}


def run(tool, ti, sid="s1"):
    payload = json.dumps({"session_id": sid, "cwd": "/w", "tool_name": tool, "tool_input": ti, "tool_response": {}})
    r = subprocess.run([sys.executable, HOOK], input=payload, capture_output=True, text=True, timeout=10, env=ENV)
    return r


def records():
    out = []
    for p in glob.glob(os.path.join(HOME, ".claude", "logs", "tools-*.jsonl")):
        out += [json.loads(l) for l in open(p, encoding="utf-8")]
    return out


def main():
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f"  ({detail})"))
        if not cond:
            fails.append(name)

    tok = "ghp_" + "z" * 36
    r = run("Bash", {"command": f"curl -H 'Authorization: token {tok}' https://api.github.com"})
    check("exit 0, 막지 않음", r.returncode == 0, r.returncode)
    run("Edit", {"file_path": "/w/src/a.py"})
    run("WebFetch", {"url": "https://example.com"})
    recs = records()
    check("3건 기록", len(recs) == 3, len(recs))
    check("Bash 명령의 시크릿은 가림", recs and tok not in recs[0]["target"] and "REDACTED" in recs[0]["target"], recs[:1])
    check("파일 경로 기록", any(x["target"] == "/w/src/a.py" for x in recs), recs)
    mode = oct(os.stat(os.path.join(HOME, ".claude", "logs")).st_mode)[-3:]
    check("로그 디렉토리 권한 700", mode == "700", mode)

    outs = [run("Bash", {"command": "colcon test  --packages-select x"}, sid="s2").stdout for _ in range(3)]
    check("같은 명령 1·2회째는 조용", not outs[0].strip() and not outs[1].strip(), outs[:2])
    check("같은 명령 3회째 경고 (공백 차이 무시)", "3번 연속" in outs[2], outs[2][:80])
    o = run("Bash", {"command": "ls"}, sid="s2").stdout
    check("다른 명령이 끼면 초기화", not o.strip(), o)
    o = run("Bash", {"command": "colcon test --packages-select x"}, sid="s3").stdout
    check("세션이 다르면 따로 센다", not o.strip(), o)

    r = subprocess.run([sys.executable, HOOK], input="not json", capture_output=True, text=True, timeout=10, env=ENV)
    check("깨진 stdin — exit 0", r.returncode == 0, r.returncode)

    shutil.rmtree(HOME, ignore_errors=True)
    total = 10
    print(f"\n{total - len(fails)}/{total} 통과")
    sys.exit(1 if fails else 0)


main()
