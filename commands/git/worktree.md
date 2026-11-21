---
description: Set up git worktrees for parallel development on multiple branches simultaneously.
argument-hint: "<branch name> [path]"
---
Set up git worktrees for parallel development on multiple branches simultaneously.

## Step 0: Already isolated?

Check before creating anything:

```bash
GIT_DIR=$(cd "$(git rev-parse --git-dir)" && pwd -P)
GIT_COMMON=$(cd "$(git rev-parse --git-common-dir)" && pwd -P)
git rev-parse --show-superproject-working-tree   # prints a path → submodule, treat as a normal repo
```

- `GIT_DIR != GIT_COMMON` (and not a submodule): you are **already in a linked worktree** — report its path and branch, do not create another one. Skip to step 5.
- If the harness offers a native worktree tool (e.g. `EnterWorktree`), use it instead of `git worktree add`; a manual worktree is state the harness cannot see or clean up.

## Steps

1. Verify the current repository is not a bare clone: `git rev-parse --is-bare-repository`.
2. List existing worktrees with `git worktree list` and display them.
3. If creating a new worktree:
   - Accept a branch name argument (required) and optional base branch (defaults to `main`).
   - Determine the worktree path: `../<repo-name>-<branch-name>`.
   - If the path is **inside** the repo (user chose e.g. `.worktrees/`), it must be ignored first: `git check-ignore -q <dir>`. If not ignored, stop and propose the `.gitignore` line — an unignored worktree dir gets committed into the repo.
   - Create it: `git worktree add ../<repo-name>-<branch> -b <branch> <base>`.
4. Copy essential config files that are gitignored (`.env`, `.env.local`) if they exist.
5. Run the package manager install in the new worktree directory.
6. **Baseline tests right after creation** — run the project's test command in the new worktree. If anything fails, report the failures and ask whether to proceed; a dirty baseline makes every later failure ambiguous.
7. Print the worktree path, baseline result, and instructions for switching to it.
8. If removing a worktree, follow "Finishing" below.

## Format

```
Worktree created:
  Path:     /absolute/path/to/worktree
  Branch:   feature/my-branch
  Base:     main
  Baseline: 142 passed, 0 failed

Next: cd /absolute/path/to/worktree
```

## Finishing

1. Run the **full** test suite in the worktree. Not green → report the failures and stop. No options are offered until it is green.
2. Present exactly these three options and wait for the user's choice:
   ```
   1. Merge back to <base> locally
   2. Push and create a Pull Request
   3. Keep the branch as-is
   ```
   Confirm the base branch if it is not certain — merging into the wrong base is expensive to undo.
3. Merge (option 1): from the main checkout, `git merge <branch>`, **run the tests again on the merged result**, and only when green remove the worktree (`git worktree remove <path>`, `git worktree prune`) and `git branch -d <branch>`. Red after merge → stop, leave the worktree and branch in place.
4. PR (option 2) and keep (option 3): leave the worktree in place — PR feedback is fixed there.
5. Discarding is not an option on the menu. Only if the user explicitly asks to throw the work away, show what will be deleted (branch, commit list, path) and require them to type `discard` before `git worktree remove` + `git branch -D`.
6. `git worktree remove` refused ("contains modified or untracked files") → show `git -C <path> status --porcelain -uall` and ask; never add `--force` on your own.

## Rules

- Never create a worktree inside the current repository directory unless that directory is gitignored.
- Always check that the branch name does not already exist before creating.
- Warn if there are more than 5 active worktrees (potential cleanup needed).
- Do not delete worktrees that have uncommitted changes without confirmation.
- Only clean up worktrees this command created. Harness-managed worktrees (e.g. `.claude/worktrees/`, created by `EnterWorktree` or agent `isolation: worktree`) belong to the harness — leave them, or use its exit tool.
- Do not commit or push unless the user chose an option that does so; never commit directly to the default branch.

<!-- Step 0, check-ignore, baseline, Finishing: obra/superpowers v7.0.2 using-git-worktrees · finishing-a-development-branch (MIT) 요약, 2026-11-21 -->
