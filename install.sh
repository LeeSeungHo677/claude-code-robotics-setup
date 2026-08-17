#!/usr/bin/env bash
# claude-code-robotics-setup 설치 스크립트
#
# 설계 원칙:
#   - 기존 ~/.claude 를 절대 조용히 덮어쓰지 않는다. 반드시 백업을 먼저 만든다.
#   - settings.json 은 기존 파일이 있으면 건드리지 않고 .new 로 떨궈 직접 병합하게 한다.
#     (권한 목록은 사람마다 다르다 — 덮어쓰면 상대의 허용 목록이 사라진다)
#   - 대화 기록·자격증명이 있는 경로(projects/, .credentials.json 등)는 아예 만지지 않는다.
#   - --dry-run 으로 무엇이 바뀌는지 먼저 볼 수 있다.
set -euo pipefail

CLAUDE_DIR="${CLAUDE_DIR:-$HOME/.claude}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
STAMP="$(date +%Y%m%d-%H%M%S)"
BACKUP="$CLAUDE_DIR/backups/pre-install-$STAMP"

DRY=0
MODE=copy   # copy | link
for arg in "$@"; do
  case "$arg" in
    --dry-run) DRY=1 ;;
    --link)    MODE=link ;;
    -h|--help)
      cat <<'EOF'
사용법: ./install.sh [옵션]

  (옵션 없음)  ~/.claude 로 복사 설치. 기존 파일은 backups/ 로 백업.
  --link       복사 대신 심볼릭 링크. 이 레포를 git pull 하면 바로 반영된다.
               (레포 디렉토리를 지우면 세팅도 같이 죽는다는 뜻이기도 하다)
  --dry-run    실제로 바꾸지 않고 무엇이 바뀔지만 출력.

환경변수:
  CLAUDE_DIR   설치 대상 (기본 ~/.claude)
EOF
      exit 0 ;;
    *) echo "알 수 없는 옵션: $arg (--help 참고)" >&2; exit 1 ;;
  esac
done

say()  { printf '%s\n' "$*"; }
run()  { if [ "$DRY" = 1 ]; then say "  [dry-run] $*"; else "$@"; fi; }

say "설치 대상 : $CLAUDE_DIR"
say "모드      : $MODE$([ "$DRY" = 1 ] && echo ' (dry-run)')"
say ""

# ── 사전 점검 ────────────────────────────────────────────────────────────────
if ! command -v python3 >/dev/null 2>&1; then
  say "✗ python3 가 필요합니다 (훅이 python3 로 실행됩니다)."; exit 1
fi
python3 -c 'import yaml' 2>/dev/null || \
  say "! PyYAML 이 없습니다. 검증 스크립트에만 필요합니다 (pip install pyyaml)."

run mkdir -p "$CLAUDE_DIR"

# ── 1) 기존 구성 백업 ────────────────────────────────────────────────────────
NEED_BACKUP=0
for d in skills agents commands hooks bin CLAUDE.md; do
  [ -e "$CLAUDE_DIR/$d" ] && NEED_BACKUP=1
done
if [ "$NEED_BACKUP" = 1 ]; then
  say "── 기존 구성 백업 → $BACKUP"
  run mkdir -p "$BACKUP"
  for d in skills agents commands hooks bin CLAUDE.md settings.json; do
    [ -e "$CLAUDE_DIR/$d" ] && run cp -a "$CLAUDE_DIR/$d" "$BACKUP/"
  done
  say ""
fi

# ── 2) 구성 설치 ─────────────────────────────────────────────────────────────
say "── 구성 설치"
# bin/ 은 세션 시작 배너가 경로로 안내하는 스크립트가 들어 있다.
# 빼면 배너가 없는 파일을 광고하게 된다.
for d in skills agents commands hooks bin; do
  if [ "$MODE" = link ]; then
    run rm -rf "$CLAUDE_DIR/$d"
    run ln -s "$SRC/$d" "$CLAUDE_DIR/$d"
    say "  링크  $d/"
  else
    run mkdir -p "$CLAUDE_DIR/$d"
    # 같은 이름의 기존 항목은 백업에 남아 있으므로 덮어쓴다
    run cp -a "$SRC/$d/." "$CLAUDE_DIR/$d/"
    say "  복사  $d/"
  fi
done
run chmod +x "$CLAUDE_DIR"/hooks/*.py "$CLAUDE_DIR"/bin/*.py

# CLAUDE.md — 있으면 덮어쓰지 않는다. 개인 규칙이 들어 있는 파일이다.
if [ -e "$CLAUDE_DIR/CLAUDE.md" ]; then
  run cp "$SRC/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md.new"
  say "  보존  CLAUDE.md (새 버전은 CLAUDE.md.new — 직접 비교해서 병합하세요)"
else
  run cp "$SRC/CLAUDE.md" "$CLAUDE_DIR/CLAUDE.md"
  say "  복사  CLAUDE.md"
fi

# settings.json — 권한 목록은 사람마다 다르다. 절대 덮어쓰지 않는다.
if [ -e "$CLAUDE_DIR/settings.json" ]; then
  run cp "$SRC/settings.json" "$CLAUDE_DIR/settings.json.new"
  say "  보존  settings.json (새 버전은 settings.json.new)"
  say "        → 최소한 hooks 블록은 옮겨야 훅이 동작합니다."
else
  run cp "$SRC/settings.json" "$CLAUDE_DIR/settings.json"
  say "  복사  settings.json"
fi
say ""

# ── 3) 검증 ──────────────────────────────────────────────────────────────────
if [ "$DRY" = 1 ]; then
  say "dry-run 이라 검증은 건너뜁니다."
  exit 0
fi

say "── 검증"
python3 - "$CLAUDE_DIR" <<'PY'
import json, os, sys, glob
d = sys.argv[1]
ok = True

# 훅 경로가 실제로 존재하는지 ($HOME 확장 후)
sp = os.path.join(d, "settings.json")
if os.path.isfile(sp):
    s = json.load(open(sp, encoding="utf-8"))
    for ev in s.get("hooks", {}).values():
        for g in ev:
            for h in g["hooks"]:
                p = os.path.expandvars(h["command"].split(None, 1)[1].strip('"'))
                if not os.path.isfile(p):
                    print("  ✗ 훅 없음: %s" % p); ok = False
    print("  훅 경로 확인 완료")

# 세션 시작 배너가 경로로 안내하는 스크립트 — 없으면 배너가 유령을 광고한다
tree = os.path.join(d, "bin", "setup-tree.py")
if not os.path.isfile(tree):
    print("  ✗ bin/setup-tree.py 없음 (배너가 이 경로를 안내합니다)"); ok = False
else:
    print("  bin/setup-tree.py 확인 완료")

print("  skills   %d" % len(glob.glob(os.path.join(d, "skills", "*", "SKILL.md"))))
print("  agents   %d" % len(glob.glob(os.path.join(d, "agents", "*.md"))))
print("  commands %d" % len(glob.glob(os.path.join(d, "commands", "*", "*.md"))))
sys.exit(0 if ok else 1)
PY

say ""
say "── 테스트"          # 개수는 박지 않는다 — 늘 때마다 낡는다
fail=0
for t in "$CLAUDE_DIR"/hooks/test_*.py "$CLAUDE_DIR"/bin/test_*.py; do
  [ -e "$t" ] || continue
  if out=$(python3 "$t" 2>&1); then
    say "  PASS  $(basename "$t")  $(printf '%s' "$out" | tail -1)"
  else
    say "  FAIL  $(basename "$t")"; printf '%s\n' "$out" | tail -5; fail=1
  fi
done
rm -rf "$CLAUDE_DIR/hooks/__pycache__" "$CLAUDE_DIR/bin/__pycache__"

say ""
if [ "$fail" = 0 ]; then
  say "✅ 설치 완료."
else
  say "⚠️  설치는 됐지만 훅 테스트가 실패했습니다. 위 출력을 확인하세요."
fi
say ""
say "다음:"
say "  1) settings.json 을 병합했는지 확인 (hooks 블록이 없으면 훅이 안 돕니다)"
say "  2) ~/.claude/CLAUDE.md 의 「이 환경」 절을 당신 환경에 맞게 고치세요"
say "  3) **새 세션을 여세요** — 훅·권한·스킬 변경은 현재 세션에 적용되지 않습니다"
[ "$NEED_BACKUP" = 1 ] && say "  되돌리기: $BACKUP"
exit $fail
