#!/usr/bin/env python3
"""PreToolUse(Write|Edit|Bash) — 프로젝트가 지정한 check 파일을 에이전트가 고치지 못하게 한다.

왜 필요한가:
  "test 가 실패하면 test 를 고쳐서 통과시키기" 를 막는다. 판정 기준(test·grader·한도 파일)은
  고치는 쪽이 아니라 사람이 소유해야 초록불을 믿을 수 있다.

켜는 법 (프로젝트 단위 opt-in):
  프로젝트 루트에 `.claude/protected-checks` 를 만들고 한 줄에 글롭 하나씩 쓴다.
    tests/test_*.py      '/' 가 있으면 프로젝트 루트 기준 상대 경로와 비교
    *.kicad_dru          '/' 가 없으면 파일 이름과 비교 (어느 폴더든)
    sim/grader/          '/' 로 끝나면 그 디렉토리 아래 전부
    # 주석
  목록 파일 자체도 항상 보호된다. 파일이 없는 프로젝트에서는 아무것도 하지 않는다.

규칙:
  - **이미 있는** 보호 파일의 수정·삭제·이동만 막는다. 새 check 파일 만들기는 허용 → 그 뒤로는 사람만 고친다.
  - Bash 는 '쓰기 대상 경로' 를 뽑아서 본다 (리다이렉트·sed -i·tee·cp/mv·rm·chmod·git rm/checkout/restore …).
    읽기(`cat`, `pytest tests/`)·`2>&1`·heredoc 본문 속 파일 이름은 막지 않는다.
    분해·heredoc 처리는 dangerous-command-guard 의 함수를 그대로 쓴다 (두 곳에 두면 한쪽이 낡는다).

한계 (보안 경계가 아니다):
  - Claude 의 도구 호출만 본다. 사람·다른 프로그램의 편집은 막지 않는다.
  - `python -c "open(...).write()"` 처럼 인터프리터 안의 쓰기는 경로를 못 뽑는다 → 통과한다.

입력: stdin JSON / 출력: deny JSON + exit 2
"""

import fnmatch
import importlib.util
import json
import os
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hooklib import log_hook_error  # noqa: E402

LIST_NAME = os.path.join(".claude", "protected-checks")
HOME = os.path.realpath(os.path.expanduser("~"))
EDIT_TOOLS = ("Write", "Edit", "MultiEdit", "NotebookEdit")


def _dcg():
    spec = importlib.util.spec_from_file_location("dcg", os.path.join(HERE, "dangerous-command-guard.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)          # main() 은 __name__ 가드 안이라 실행되지 않는다
    return mod


# ── 보호 목록 ────────────────────────────────────────────────────────────────
def find_root(path):
    """path 에서 위로 올라가며 `.claude/protected-checks` 가 있는 디렉토리를 찾는다. 홈(~/.claude)은 제외."""
    d = path if os.path.isdir(path) else os.path.dirname(path)
    while True:
        if d != HOME and os.path.isfile(os.path.join(d, LIST_NAME)):
            return d
        parent = os.path.dirname(d)
        if parent == d:
            return None
        d = parent


def load_globs(root):
    try:
        with open(os.path.join(root, LIST_NAME), encoding="utf-8") as f:
            lines = [l.strip() for l in f]
    except OSError:
        return []
    return [l for l in lines if l and not l.startswith("#")]


def matches(rel, globs):
    if rel == LIST_NAME:
        return True
    name = os.path.basename(rel)
    for g in globs:
        if g.endswith("/"):
            if rel.startswith(g) or fnmatch.fnmatch(rel, g + "*"):
                return True
        elif "/" in g:
            if fnmatch.fnmatch(rel, g.lstrip("./")):
                return True
        elif fnmatch.fnmatch(name, g):
            return True
    return False


def protected(path, cwd):
    """보호 대상이면 (root 기준 상대경로) 를, 아니면 None. 존재하지 않는 파일은 보호하지 않는다."""
    if not path:
        return None
    p = os.path.expanduser(path)
    if not os.path.isabs(p):
        p = os.path.join(cwd or os.getcwd(), p)
    p = os.path.realpath(p)
    if not os.path.exists(p):
        return None
    root = find_root(p)
    if not root:
        return None
    rel = os.path.relpath(p, root).replace(os.sep, "/")
    if os.path.isdir(p):
        # 디렉토리 통째 삭제·이동 — 안에 보호 파일이 하나라도 있으면 막는다
        globs = load_globs(root)
        for dp, _, files in os.walk(p):
            for fn in files:
                r = os.path.relpath(os.path.join(dp, fn), root).replace(os.sep, "/")
                if matches(r, globs):
                    return r
        return None
    return rel if matches(rel, load_globs(root)) else None


# ── Bash 쓰기 대상 ───────────────────────────────────────────────────────────
WRAPPERS = {"sudo", "env", "command", "nohup", "time", "xargs"}
ALL_ARGS = {"rm", "unlink", "chmod", "chown", "truncate", "shred", "mv", "touch"}
GIT_WRITES = {"rm", "mv", "checkout", "restore"}


def extra_targets(sub):
    """dangerous-command-guard.write_targets 가 안 보는 '파일을 바꾸거나 없애는' 명령의 대상."""
    try:
        toks = shlex.split(sub)
    except ValueError:
        toks = sub.split()
    while toks and (toks[0] in WRAPPERS or ("=" in toks[0] and not toks[0].startswith("-"))):
        toks = toks[1:]
    if not toks:
        return []
    cmd, args = os.path.basename(toks[0]), toks[1:]
    nonopt = [a for a in args if not a.startswith("-")]
    if cmd in ALL_ARGS:
        return nonopt
    if cmd == "ln" and nonopt:
        return nonopt[-1:]
    if cmd == "git" and nonopt and nonopt[0] in GIT_WRITES:
        return nonopt[1:]
    if cmd == "perl" and any(a.startswith("-") and "i" in a for a in args):
        return nonopt[1:]
    if cmd == "dd":
        return [a[3:] for a in args if a.startswith("of=")]
    return []


def bash_hit(command, cwd):
    dcg = _dcg()
    cur = cwd
    for sub in dcg.split_commands(dcg.strip_heredocs(command)):
        try:
            toks = shlex.split(sub)
        except ValueError:
            toks = sub.split()
        if toks[:1] == ["cd"] and len(toks) == 2:          # `cd dir && rm x` 의 상대 경로를 맞춘다
            nxt = os.path.expanduser(toks[1])
            cur = nxt if os.path.isabs(nxt) else os.path.join(cur or os.getcwd(), nxt)
            continue
        for t in dcg.write_targets(sub) + extra_targets(sub):
            rel = protected(t, cur)
            if rel:
                return rel, sub
    return None, None


def deny(reason):
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    print(reason, file=sys.stderr)
    sys.exit(2)


HINT = ("\n  check 는 통과시키려고 고치지 않습니다. 설계·데이터·코드를 고치세요.\n"
        "  check 자체가 틀렸다고 보면 무엇이 왜 틀렸는지 사용자에게 보고하고, 사용자가 직접 고치게 하세요.")


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as e:
        log_hook_error("protected-checks-guard", f"stdin 파싱 실패: {e}")
        sys.exit(0)   # fail-open (의도) — 대신 기록한다

    tool = data.get("tool_name")
    ti = data.get("tool_input") or {}
    cwd = data.get("cwd")
    try:
        if tool in EDIT_TOOLS:
            rel = protected(ti.get("file_path") or ti.get("notebook_path") or "", cwd)
            if rel:
                deny(f"[protected-checks-guard] 차단: 보호된 check 파일 {tool} — {rel}" + HINT)
        elif tool == "Bash":
            rel, sub = bash_hit(ti.get("command", ""), cwd)
            if rel:
                deny(f"[protected-checks-guard] 차단: 보호된 check 파일을 바꾸는 셸 명령 — {rel}\n"
                     f"  문제 구간: {sub[:200]}" + HINT)
    except SystemExit:
        raise
    except Exception as e:
        log_hook_error("protected-checks-guard", f"{type(e).__name__}: {e}")
    sys.exit(0)


if __name__ == "__main__":
    main()
