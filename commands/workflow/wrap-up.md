---
description: End the current session with a structured handoff (.claude/HANDOFF.md) and memory update.
allowed-tools: ["Bash", "Read", "Write", "Grep", "Glob"]
---
End the current session with a structured handoff the next session can pick up.

## Steps

1. Review what changed this session:
   - `git diff --stat` for uncommitted changes, `git log --oneline --since="4 hours ago"` for commits.
   - Scan for TODO/FIXME comments added during the session.
2. Write (or update) `<project>/.claude/HANDOFF.md` using the template below.
   - **Not `RESUME.md`** — Claude Code writes that file itself as an automatic checkpoint and overwrites it.
   - Keep the `고정` section short: the SessionStart hook re-injects it after every compaction.
     It holds session facts that must not be lost: real robot vs sim, target robot / namespace,
     parameters changed (before → after, why).
   - `다음 1개` is a single concrete next action, not a list.
3. Durable learnings (not tied to this session) go to auto-memory, not HANDOFF.md.
   Propose CLAUDE.md changes to the user instead of editing it directly.
4. Commits: follow the global rule — **commit only if the user asked**. Otherwise list the
   uncommitted changes in HANDOFF.md and *suggest* a commit.
5. If tests are failing, record which ones and why in `남은 질문` — do not hide it.

## Template — `.claude/HANDOFF.md`

```markdown
# HANDOFF — <YYYY-MM-DD>

## 고정 (압축 후에도 다시 주입된다 — 짧게)
- 대상: 실기 | 시뮬   로봇/네임스페이스: <…>
- 바꾼 파라미터 (이전 → 이후, 이유): <…>

## 목표
- <이 작업의 목표 한두 줄>

## 결정 (이유)
- <결정> — <왜. 기각한 대안이 있으면 같이>

## 남은 질문
- <미해결 문제, 실패 중인 테스트와 이유>

## 식별자
- 경로 / 브랜치 / 토픽 / run id / bag 파일: <…>

## 건드린 파일
- <path> — <무엇을>   (미커밋이면 표시)

## 다음 1개
- <다음 세션이 바로 시작할 구체적 행동 하나>

## 마지막 확인
- <smoke test 명령과 결과, 예: colcon build --packages-select X && colcon test … → 12/12 pass>
```

## Rules

- Actionable, not narrative. The next session reads `고정` + `목표` + `다음 1개` automatically.
- Write measured facts with units and N (e.g. "성공률 7/10"), not impressions.
- Flag time-sensitive items (expiring tokens, pending reviews) in `남은 질문`.
