#!/usr/bin/env python3
"""PreToolUse(Bash) — 파괴적 명령을 차단하거나 사용자 확인으로 승격시킨다.

설계 원칙
  1) 복합 명령(&&, ||, ;, |, 개행, $(), ``)을 하위 명령으로 분해해 각각 검사한다.
     → `ls && rm -rf /` 처럼 앞에 안전한 명령을 붙여 우회하는 것을 막는다.
  2) DENY = 되돌릴 수 없고 정당한 이유가 거의 없는 것 (직접 터미널에서 실행하면 됨)
     ASK  = 정당할 수 있지만 손실이 큰 것 → 사용자에게 확인창을 띄운다
     그 외 = exit 0 (아무 결정도 하지 않음 → settings.json 의 평소 권한 흐름을 탄다)

입력: stdin JSON / 출력: deny·ask JSON (+ deny 는 exit 2)
"""

import importlib.util
import json
import os
import re
import shlex
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from hooklib import generated_root, log_hook_error  # noqa: E402

HOME = os.path.expanduser("~")

# ── 하위 명령 분해 ───────────────────────────────────────────────────────────
SEPARATORS = ("&&", "||", ";", "|", "\n")


def split_commands(cmd):
    """따옴표 밖의 구분자에서만 자른다. $(...) / `...` 내부도 별도 추출."""
    parts, buf = [], []
    i, n = 0, len(cmd)
    quote = None
    while i < n:
        ch = cmd[i]
        if quote:
            buf.append(ch)
            if ch == quote and (i == 0 or cmd[i - 1] != "\\"):
                quote = None
            i += 1
            continue
        if ch in ("'", '"'):
            quote = ch
            buf.append(ch)
            i += 1
            continue
        matched = None
        for sep in SEPARATORS:
            if cmd.startswith(sep, i):
                matched = sep
                break
        if matched:
            parts.append("".join(buf))
            buf = []
            i += len(matched)
            continue
        buf.append(ch)
        i += 1
    parts.append("".join(buf))

    # 명령 치환 내부도 검사 대상에 추가
    for inner in re.findall(r"\$\(([^()]*)\)", cmd) + re.findall(r"`([^`]*)`", cmd):
        parts.extend(split_commands(inner) if any(s in inner for s in SEPARATORS) else [inner])

    return [p.strip() for p in parts if p.strip()]


# ── heredoc 본문 제거 ────────────────────────────────────────────────────────
# `cat > f <<'EOF' … EOF` 의 본문은 명령이 아니라 자료다. 개행에서 자르는 split_commands 가 본문 줄을
# 명령으로 보고 안의 글자(sudo, rm -r …)에 걸리는 오탐을 막는다 (2026-10-11, PR 본문 쓰다 걸림).
# 구분자에 따옴표가 없으면 본문 안의 $( )·` ` 는 셸이 확장하므로 그 치환 부분만 검사 대상으로 남긴다.
# 종결자를 못 찾으면(가짜 heredoc, 예: echo "<<EOF" 뒤에 진짜 명령) 아무것도 떼지 않는다 — 우회 구멍이 되면 안 된다.
HEREDOC_RE = re.compile(r"(?<![<\w])<<(?!<)(-?)\s*(?:'([^']+)'|\"([^\"]+)\"|\\?([A-Za-z_][\w]*))")


def strip_heredocs(cmd):
    lines = cmd.split("\n")
    out, i = [], 0
    while i < len(lines):
        line = lines[i]
        m = HEREDOC_RE.search(line)
        out.append(line)
        i += 1
        if not m:
            continue
        dash, q1, q2, bare = m.groups()
        word, quoted = (q1 or q2 or bare), bool(q1 or q2)
        body, j, closed = [], i, False
        while j < len(lines):
            l = lines[j]
            j += 1
            if (l.lstrip("\t") if dash else l) == word:
                closed = True
                break
            body.append(l)
        if not closed:
            continue                                   # 종결자 없음 → 본문으로 보지 않고 그대로 검사
        if not quoted:
            text = "\n".join(body)
            out.extend(re.findall(r"\$\(([^()]*)\)", text) + re.findall(r"`([^`]*)`", text))
        i = j
    return "\n".join(out)


# ── 규칙 ─────────────────────────────────────────────────────────────────────
# (정규식, 사유)  — 정규식은 하위 명령 하나에 대해 적용된다.
DENY_RULES = [
    (re.compile(r":\s*\(\s*\)\s*\{.*\|\s*:\s*&.*\}\s*;\s*:"), "fork bomb"),
    (re.compile(r"\bmkfs(\.\w+)?\b"), "파일시스템 포맷(mkfs)"),
    (re.compile(r"\bdd\b[^|]*\bof=/dev/(sd|nvme|hd|mmcblk)"), "블록 디바이스에 직접 dd 쓰기"),
    (re.compile(r">\s*/dev/(sd|nvme|hd|mmcblk)"), "블록 디바이스로 리다이렉트"),
    (re.compile(r"\brm\s+(-[a-zA-Z]*\s+)*-{0,2}[a-zA-Z]*[rR][a-zA-Z]*f?[a-zA-Z]*\s+(/|/\*|~|~/\*|\$HOME|\$\{HOME\})(\s|$)"),
     "루트/홈 디렉토리 전체 삭제"),
    (re.compile(r"\brm\s+.*\s" + re.escape(HOME) + r"/?(\s|$)"), "홈 디렉토리 전체 삭제"),
    (re.compile(r"\bchmod\s+(-R\s+)?(777|a\+rwx)\s+/(\s|$)"), "루트에 chmod 777"),
    (re.compile(r"\bchown\s+-R\s+\S+\s+/(\s|$)"), "루트에 재귀 chown"),
    (re.compile(r"\bhistory\s+-c\b|\brm\s+.*\.bash_history"), "셸 히스토리 삭제"),
    (re.compile(r"\bcat\b[^|;]*(\.ssh/id_(rsa|ed25519|ecdsa)|\.aws/credentials|\.claude/\.credentials\.json)"),
     "개인키/자격증명 파일 출력"),
    # 프로덕션 DB 파기. 프로젝트 훅(.claude/hooks/PreToolUse.sh)에만 있던 규칙을
    # 유저 스코프로 옮겼다 — 중복 훅을 지우면서 보호가 사라지지 않도록 (2026-08-17).
    # 원본은 "DROP DATABASE prod" 리터럴만 잡았으나 prod/production/live 까지 넓혔다.
    (re.compile(r"(?i)\bdrop\s+(database|schema)\s+(if\s+exists\s+)?[\"'`]?\w*(prod|production|live)"),
     "프로덕션 데이터베이스/스키마 삭제"),
]

ASK_RULES = [
    (re.compile(r"\bgit\s+push\b(?=.*(--force|(\s|^)-f(\s|$)))(?!.*--force-with-lease)"),
     "강제 푸시(--force) — 원격 히스토리가 덮어써집니다"),
    (re.compile(r"\bgit\s+clean\b.*-[a-zA-Z]*[dx]"), "git clean -d/-x — 추적되지 않는 파일이 삭제됩니다"),
    (re.compile(r"\bgit\s+reset\s+--hard\b"), "git reset --hard — 커밋되지 않은 변경이 사라집니다"),
    (re.compile(r"\bgit\s+branch\s+-D\b"), "브랜치 강제 삭제"),
    (re.compile(r"\bdocker\s+(system|image|volume)\s+prune\b.*(-a|--all|--volumes)"),
     "docker prune -a/--volumes — 이미지·볼륨이 대량 삭제됩니다"),
    (re.compile(r"\bsudo\b"), "sudo 권한 상승"),
    (re.compile(r"\b(shred|truncate\s+-s\s*0)\b"), "파일 내용 파기"),
    (re.compile(r"(?i)\b(drop\s+(database|schema)|truncate\s+table)\b"),
     "데이터베이스 삭제/비우기 — 복구할 수 없습니다"),
    # 로봇 데이터 보호: 로그·주행 데이터는 재수집 비용이 크다.
    # 이 규칙이 먼저 매칭되어야 아래 일반 재귀 삭제보다 구체적인 사유가 표시된다.
    (re.compile(r"(?i)\brm\b.*(rosbag|_bags?\b|\.db3\b|\.mcap\b|\.bag\b|datasets?\b|"
                r"drives?\b|recordings?\b|/log/|\.pcd\b|\.ply\b|calib)"),
     "rosbag / 데이터셋 / 주행기록 / 캘리브레이션 삭제 — 재수집이 어려운 데이터일 수 있습니다"),
    # 재귀 삭제는 대상과 무관하게 확인을 받는다. 한 글자 오타가 디렉토리 하나를 통째로 날린다.
    (re.compile(r"\brm\s+(-\S*\s+)*-\S*[rR]"), "재귀 삭제(rm -r) — 디렉토리 전체가 사라집니다"),

    # ── 로봇 실기 구동 ─────────────────────────────────────────────────────
    # settings.json 의 ask 규칙과 중복이지만, 훅은 복합 명령을 분해해 검사하므로
    # `cd ws && ros2 launch ...` 처럼 앞에 다른 명령이 붙은 형태까지 잡는다.
    (re.compile(r"\bros2\s+topic\s+pub\b"), "토픽 직접 발행 — 로봇이 실제로 움직일 수 있습니다"),
    (re.compile(r"\bros2\s+service\s+call\b"), "서비스 호출 — 로봇 상태를 변경할 수 있습니다"),
    (re.compile(r"\bros2\s+action\s+send_goal\b"), "액션 목표 전송 — 로봇이 동작을 시작합니다"),
    (re.compile(r"\bros2\s+param\s+(set|load)\b"), "파라미터 변경 — 동작 중인 노드에 즉시 반영됩니다"),
    (re.compile(r"\bros2\s+lifecycle\s+set\b"), "lifecycle 전이 — 컨트롤러가 활성/비활성화됩니다"),
    (re.compile(r"\bros2\s+(run|launch)\b"), "노드/런치 실행 — 하드웨어에 연결될 수 있습니다"),
    (re.compile(r"\bros2\s+control\s+(set_controller_state|switch_controllers|load_controller|unload_controller)\b"),
     "컨트롤러 전환 — 로봇 제어권이 바뀝니다"),
    (re.compile(r"\bros2\s+bag\s+play\b"), "bag 재생 — 기록된 명령이 실기로 나갈 수 있습니다"),

    # 펌웨어·저수준 장치 쓰기
    (re.compile(r"\b(stm32flash|dfu-util|avrdude|esptool(\.py)?|openocd|st-flash)\b"), "펌웨어 플래시"),
    (re.compile(r"\bcansend\b"), "CAN 프레임 직접 송신 — 구동계에 명령이 갈 수 있습니다"),
    (re.compile(r"\bethercat\s+(download|reg_write|foe_write)\b"), "EtherCAT 슬레이브에 직접 쓰기"),
]


# 파이프 자체가 위험 신호인 규칙은 분해 전 '명령 전체' 에 적용해야 한다.
WHOLE_DENY_RULES = [
    (re.compile(r"\b(curl|wget)\b[^|]*\|\s*(sudo\s+)?(ba|z|k|)sh\b"),
     "원격 스크립트를 바로 셸로 파이프 실행"),
]


# ── Bash 로 colcon 생성물을 고치는 경로 (2026-10-18) ─────────────────────────
# ros2-workspace-guard 는 Write/Edit 만 본다. `sed -i install/…`, `cp x build/…`, `> log/…` 는
# 그 훅을 거치지 않았다. 판정은 같은 함수(hooklib.generated_root)를 쓴다.
REDIRECT_RX = re.compile(r"(?<![<0-9&])>{1,2}\|?\s*([^\s;&|<>]+)")


def write_targets(sub):
    """하위 명령 하나가 '내용을 쓰는' 대상 경로들. 삭제(rm)는 대상이 아니다 — 생성물 정리는 정상 작업."""
    targets = [m.group(1).strip("'\"") for m in REDIRECT_RX.finditer(sub)]
    try:
        toks = shlex.split(sub)
    except ValueError:
        toks = sub.split()
    if toks:
        cmd, args = os.path.basename(toks[0]), toks[1:]
        nonopt = [a for a in args if not a.startswith("-")]
        if cmd == "sed" and any(a.startswith(("-i", "--in-place")) for a in args):
            has_script_opt = any(a in ("-e", "--expression", "-f", "--file") for a in args)
            targets += nonopt if has_script_opt else nonopt[1:]
        elif cmd == "tee":
            targets += nonopt
        elif cmd in ("cp", "mv", "install", "rsync") and len(nonopt) >= 2:
            targets.append(nonopt[-1])
    return [x for x in targets if x and not x.startswith("/dev/")]


# ── 외부 요청에 시크릿이 실리는 경로 (2026-10-18) ────────────────────────────
# secret-scanner 는 파일 쓰기만 본다. `curl -H "Authorization: Bearer <실제 토큰>"` 은 그대로 나갔다.
# 패턴은 secret-scanner 의 것을 그대로 쓴다 (두 곳에 따로 두면 한쪽이 낡는다).
EGRESS_RX = re.compile(r"\b(curl|wget|http|https|xh)\b")


def _secret_patterns():
    try:
        spec = importlib.util.spec_from_file_location("secret_scanner", os.path.join(HERE, "secret-scanner.py"))
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod.PATTERNS, mod.PLACEHOLDER
    except Exception:
        return [], None


def egress_secret(sub):
    if not EGRESS_RX.search(sub):
        return None
    patterns, placeholder = _secret_patterns()
    for name, rx in patterns:
        m = rx.search(sub)
        if m and not (placeholder and placeholder.search(m.group(0))):
            return name
    return None


def decide(command, cwd=None):
    command = strip_heredocs(command)
    for rx, why in WHOLE_DENY_RULES:
        if rx.search(command):
            return "deny", why, command
    for sub in split_commands(command):
        for rx, why in DENY_RULES:
            if rx.search(sub):
                return "deny", why, sub
    for sub in split_commands(command):
        for rx, why in ASK_RULES:
            if rx.search(sub):
                return "ask", why, sub
    for sub in split_commands(command):
        name = egress_secret(sub)
        if name:
            return "ask", f"외부 요청에 시크릿으로 보이는 값({name})이 실립니다 — 환경변수로 넘기세요", sub
        for target in write_targets(sub):
            root = generated_root(target, cwd)
            if root:
                return "ask", (f"colcon 생성물({root})을 Bash 로 수정 — 다음 빌드에서 사라집니다. "
                               f"src/ 쪽을 고치세요"), sub
    return None, None, None


def main():
    try:
        data = json.load(sys.stdin)
    except Exception as e:
        log_hook_error("dangerous-command-guard", f"stdin 파싱 실패: {e}")
        sys.exit(0)   # fail-open (의도) — 대신 기록한다

    if data.get("tool_name") != "Bash":
        sys.exit(0)
    command = (data.get("tool_input") or {}).get("command", "")
    if not command.strip():
        sys.exit(0)

    decision, why, sub = decide(command, data.get("cwd"))
    if decision is None:
        sys.exit(0)

    if decision == "deny":
        reason = (f"[dangerous-command-guard] 차단: {why}\n"
                  f"  문제 구간: {sub[:200]}\n"
                  f"  정말 필요하면 터미널에서 직접 실행하세요.")
        print(json.dumps({"hookSpecificOutput": {
            "hookEventName": "PreToolUse",
            "permissionDecision": "deny",
            "permissionDecisionReason": reason}}))
        print(reason, file=sys.stderr)
        sys.exit(2)

    reason = (f"[dangerous-command-guard] 확인 필요: {why}\n"
              f"  문제 구간: {sub[:200]}")
    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "ask",
        "permissionDecisionReason": reason}}))
    sys.exit(0)


if __name__ == "__main__":
    main()
