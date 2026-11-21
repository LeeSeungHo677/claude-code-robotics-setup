---
description: Run a multi-step workflow by breaking a complex task into coordinated sub-tasks.
argument-hint: "<end goal>"
---
Run a multi-step workflow by breaking a complex task into coordinated sub-tasks.

## Steps

1. Parse the workflow specification from the argument:
   - Accept a natural language description of the end goal.
   - Or accept a structured plan with explicit steps.
2. Decompose into ordered sub-tasks:
   - Identify dependencies between tasks (which must complete before others start).
   - Determine which tasks can run in parallel.
   - Estimate complexity of each task (small, medium, large).
3. For each sub-task, define:
   - Clear objective and success criteria.
   - Input requirements (files, data, prior task outputs).
   - Expected output (files created, changes made, results).
   - Verification method (test, manual check, build success).
4. Execute tasks in dependency order:
   - Mark each task as pending, in-progress, or complete.
   - Capture output and errors from each step.
   - If a task fails, determine if downstream tasks should be skipped or can proceed.
5. After all tasks complete, run a final verification:
   - Build passes.
   - Tests pass.
   - No regressions introduced.
6. Report the full execution summary.

## Implementation tasks: implement → review → fix loop

When a sub-task **changes code**, run it as this loop instead of a single dispatch. Tasks run one at a time — never two implementers in parallel (they conflict on the same tree).

1. **Brief as a file.** Write the task's requirements (exact values, files, `Done when:` check) to `<scratch>/task-N-brief.md`. Record `BASE=$(git rev-parse HEAD)` before dispatching. The dispatch holds: one line of context, the brief path ("read this first — it is your requirements"), interfaces from earlier tasks, and the report path `<scratch>/task-N-report.md`. Never paste earlier tasks' history into it.
2. **Fresh implementer per task.** It implements, runs the focused tests and then the full suite once, reads its own diff, writes the full report to the report file, and returns only: status (`DONE` / `DONE_WITH_CONCERNS` / `NEEDS_CONTEXT` / `BLOCKED`), a one-line test summary, concerns. It never dispatches subagents (no helper, no reviewer of its own). It does **not commit** unless the user asked for commits in this workflow.
   - `NEEDS_CONTEXT` → give the missing context and re-dispatch. `BLOCKED` → change something (more context, a stronger model, a smaller task, or a ruling on a plan defect); never re-send the same thing.
3. **Review package as a file.** `{ git status --porcelain; git diff --stat $BASE; git diff -U10 $BASE; } > <scratch>/task-N-diff.txt` (uncommitted work included; for new untracked files `git add -N <file>` first so they appear). The package never enters this context.
4. **Task reviewer — a separate agent that reads code, not conclusions.** Give it three paths: brief, report, diff file, plus the binding constraints copied verbatim. Read-only (`Explore` or tools without Write/Edit). Its instructions:
   - "The implementer's report is unverified claims. Verify every claim against the diff. A stated rationale ('kept it simple', 'YAGNI') never lowers a finding's severity."
   - **Part 1 — spec compliance first:** ✅ / ❌ with Missing · Extra · Misunderstood, each with `file:line`; ⚠️ for what cannot be verified from the diff (the controller checks those).
   - **Part 2 — code quality:** error handling, edge cases, tests that verify behavior (not mocks, not mirror assertions — `tdd-mastery` "Judging a Good Test"), warnings in test output count as findings. Issues as Critical / Important / Minor with `file:line`; verdict `Approved` / `Needs fixes`.
   - Do not re-run the whole suite; run one focused test only for a specific doubt. Do not spawn subagents.
   - Do not pre-judge for it: never write "don't flag X" or "at most Minor" in the reviewer's prompt.
5. **Fix loop** when spec ❌, any Critical/Important, or a ⚠️ you confirmed as real. Send the open findings verbatim back to the **same implementer** (`SendMessage` to its agent ID) → it fixes, re-runs the covering tests, appends a fix report → regenerate the diff from the previous review's head → **scoped re-review** (each finding ADDRESSED / NOT ADDRESSED, new breakage in the fix diff only). Minor findings do not enter the loop — list them for the final review.
   **Cap: 3 rounds** (CLAUDE.md: same symptom fixed 3 times → stop). After round 3 with findings still open, stop and report: what was tried, the best attempt and its evidence, what was ruled out, the open findings. Never fix findings yourself in this context — controller fixes skip review.
6. **Complete** only when review is clean: mark the task done with `<BASE7>` and the review verdict, then the next task. Never start the next task over open Critical/Important findings.
7. After the last task: one whole-change review (most capable model) over `git diff <first BASE>`, then the final verification of "Steps" item 5.

Between tasks, do not stop to ask "continue?" — the user asked for the plan to run. Stop only for: destructive/irreversible operations, security-sensitive actions, anything that moves hardware (show the command, the user runs it), commits/pushes/merges the user has not asked for, or a plan so broken that every path is a guess. Progress lines stay one line each (CLAUDE.md answer style); the per-task table in Format is the report.

<!-- 출처: obra/superpowers v7.0.2 (MIT) subagent-driven-development — SKILL.md, implementer-prompt.md, task-reviewer-prompt.md, references/fix-loop.md·handling-reports.md 요약, 2026-11-21.
     원본과 다르게 한 것: 작업마다 커밋(→ 사용자 요청 시만, diff 는 작업 트리 기준) · fix loop 5회(→ 3회, CLAUDE.md 「3번 고쳐도 안 되면 멈추고 보고」) · 상한 도달 시 controller 가 판정하고 계속(→ 멈추고 보고) ·
     ledger 파일·sdd 스크립트(→ 이 커맨드의 진행 저장 규칙과 작업 표로 충분, 길어지면 /workflow:checkpoint) · v7 은 명세+품질을 한 리뷰어가 두 판정으로 낸다(1차 명세 → 2차 품질 순서를 지키되 같은 diff 를 두 번 읽히지 않음). -->

## Format

```
Workflow: <description>
Tasks: <total> (<completed>/<total>)

| # | Task | Status | Duration | Notes |
|---|------|--------|----------|-------|
| 1 | <task> | done | 2m | <notes> |
| 2 | <task> | done | 5m | <notes> |
| 3 | <task> | failed | 1m | <error> |

Overall: <success/partial/failed>
Duration: <total time>
```

## Rules

- Never execute destructive operations (delete, force push) without explicit confirmation.
- If a critical task fails, stop and report rather than continuing blindly.
- Keep each sub-task focused and independently verifiable.
- End every sub-agent brief with a `Done when:` line — a check you can run (command + expected result), not a description. Before marking the task done, **re-run that check yourself**; a sub-agent's "done" is not evidence.
- A reviewer sub-agent must not edit the artifact it judges — give it read-only tools, and send fixes back to the implementer.
- Save progress after each completed task so work is not lost on failure.
- Limit workflow to 10 tasks maximum; break larger workflows into phases.
- Tier sub-agents by task: broad scans (file audits, pattern search, fan-out) → `Explore` or a light model; edits → `isolation: "worktree"`; a verify step (lint/test/cross-check) must pass before a worktree change reaches the main tree.
- Read summaries from sub-agents, not their raw output. Filter scan results before they enter this context.
- Never downgrade the model for `ros2-reviewer` or `robot-safety-reviewer` — they inherit the session model.
