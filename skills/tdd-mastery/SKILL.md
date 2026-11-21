---
name: tdd-mastery
description: Test-driven development workflow with Red-Green-Refactor cycle across languages
---

# TDD Mastery

## Core Cycle: Red-Green-Refactor

1. **Red** - Write a failing test that defines the desired behavior
2. **Green** - Write the minimum code to make the test pass
3. **Refactor** - Clean up while keeping tests green

Never write production code without a failing test first. Each cycle should take 2-10 minutes.

## Test Structure

Use the Arrange-Act-Assert pattern consistently:

```
Arrange: Set up test data and dependencies
Act:     Execute the behavior under test
Assert:  Verify the expected outcome
```

Name tests as `test_<unit>_<scenario>_<expected_result>` or `it("should <behavior> when <condition>")`.

## Jest / Vitest Patterns

```typescript
describe("OrderService", () => {
  it("should apply discount when order exceeds threshold", () => {
    const order = createOrder({ items: [{ price: 150, qty: 1 }] });
    const result = applyDiscount(order, { threshold: 100, percent: 10 });
    expect(result.total).toBe(135);
  });

  it("should throw when applying discount to empty order", () => {
    const order = createOrder({ items: [] });
    expect(() => applyDiscount(order, defaultDiscount)).toThrow(EmptyOrderError);
  });
});
```

Use `vi.fn()` / `jest.fn()` for mocks. Prefer dependency injection over module mocking. Use `beforeEach` for shared setup, never share mutable state between tests.

## pytest Patterns

```python
@pytest.fixture
def db_session():
    session = create_test_session()
    yield session
    session.rollback()

def test_create_user_stores_hashed_password(db_session):
    user = UserService(db_session).create(email="a@b.com", password="secret")
    assert user.password_hash != "secret"
    assert verify_password("secret", user.password_hash)

@pytest.mark.parametrize("input,expected", [
    ("", False),
    ("short", False),
    ("ValidPass1!", True),
])
def test_password_validation(input, expected):
    assert validate_password(input) == expected
```

Use `pytest.raises` for exceptions. Use `conftest.py` for shared fixtures. Mark slow tests with `@pytest.mark.slow`.

## Go Testing Patterns

```go
func TestParseConfig(t *testing.T) {
    tests := []struct {
        name    string
        input   string
        want    Config
        wantErr bool
    }{
        {"valid yaml", "port: 8080", Config{Port: 8080}, false},
        {"empty input", "", Config{}, true},
        {"invalid port", "port: -1", Config{}, true},
    }
    for _, tt := range tests {
        t.Run(tt.name, func(t *testing.T) {
            got, err := ParseConfig([]byte(tt.input))
            if (err != nil) != tt.wantErr {
                t.Errorf("ParseConfig() error = %v, wantErr %v", err, tt.wantErr)
                return
            }
            if !tt.wantErr && got != tt.want {
                t.Errorf("ParseConfig() = %v, want %v", got, tt.want)
            }
        })
    }
}
```

Use table-driven tests by default. Use `t.Helper()` in test utility functions. Use `testify/assert` only if the team already uses it.

## Test Levels

| Level | Scope | Speed | Dependencies |
|-------|-------|-------|-------------|
| Unit | Single function/class | <100ms | None (mock all) |
| Integration | Module boundaries | <5s | Real DB, real FS |
| E2E | Full user flow | <30s | Full stack |

Ratio target: 70% unit, 20% integration, 10% e2e.

## Coverage Rules

- Enforce **80% line coverage minimum** in CI
- Track branch coverage, not just line coverage
- Exclude generated code, type definitions, and config files
- Never write tests just to hit coverage numbers; test behavior

```bash
# Jest/Vitest
vitest run --coverage --coverage.thresholds.lines=80 --coverage.thresholds.branches=75

# pytest
pytest --cov=src --cov-fail-under=80 --cov-branch

# Go
go test -coverprofile=cover.out -coverpkg=./... ./...
go tool cover -func=cover.out
```

## Mocking Guidelines

- Mock at boundaries: HTTP clients, databases, file systems, clocks
- Never mock the unit under test
- Prefer fakes (in-memory implementations) over mocks for repositories
- Assert on behavior, not on mock call counts
- Use `t.Cleanup` / `afterEach` to reset shared mocks

## Judging a Good Test

Before writing the test body, answer: **which production change should make this test fail — and is that change a bug or a decision?** If you cannot name one, the test has no job.

- **Hand-written literal expectations.** Derive `want` by hand (literal or hand-checked fixture). An expected value computed by the code under test or its helpers is a *mirror assertion* — it passes whatever the code does.
  ```python
  # ❌ mirror: both sides come from the same builder
  assert build_query(tag="urgent") == build_query(tag="urgent")
  # ✅ literal
  assert build_query(tag="urgent") == 'tag:"urgent"'
  ```
- **No change detectors.** A test that only fails on intentional decisions (a constant's value, exact message wording, private structure) fires on redesign and sleeps through bugs. Not `assert MAX_RETRIES == 5` but "a failing call is retried 5 times and the 6th never happens".
- **Run it, don't grep it.** Asserting that a script, config, or skill file *contains* a line proves only that the source is the source. Execute it against controlled input and assert output, side effects, or exit code.
- **Your boundary, not the framework.** Test the route you register, the query you emit, the payload you produce — not that the router calls a registered handler.
- **Mental mutation check** before finishing: for each realistic mutation — wrong constant/argument, wrong branch, missing side effect, empty/default return, missing validation for zero/empty/None/unauthorized/malformed — at least one test must fail. A mutation nothing catches means the behavior is unprotected or the test is tautological.

When a bug came from invalid data, a test plus one check at the entry point is not enough: validate at each layer the data passes (entry → business logic → **environment guard**, e.g. refuse `git init`/`rm` outside a temp dir while running under test → debug log before the dangerous call) so the bug becomes structurally impossible.

<!-- 출처: obra/superpowers v7.0.2 (MIT) test-driven-development/writing-good-tests.md, systematic-debugging/defense-in-depth.md 요약, 2026-11-21 -->

## Anti-Patterns to Avoid

- Testing implementation details instead of behavior
- Tests that pass when code is deleted (tautological tests)
- Shared mutable state between test cases
- Ignoring flaky tests instead of fixing them
- Testing private methods directly
- Giant test setup that obscures intent

## Verify Before Claiming Done

Run the command that proves the claim in this turn and read its output. A previous run or "should pass" is not evidence.

| Claim | Proof | Not proof |
|-------|-------|-----------|
| Tests pass | Test run output: 0 failures | Earlier run, partial subset |
| Build succeeds | Build command exit 0 | Linter clean, logs look fine |
| Bug fixed | Original symptom re-run, now passes | Code changed |
| Regression test works | Revert the fix → test fails → restore → passes | Test passes once |
| Subagent finished | `git diff` shows the change, you ran its tests | Agent says "success" |
| Requirements met | Each requirement checked one by one | Tests pass |
| Change is done | **Full** suite run on the final tree, output pristine (no new warnings/errors) | Only the tests you touched |

Report every failure the full run shows — including ones you did not cause. "Pre-existing, not mine" goes in the report with the output; it is not a reason to omit it.

Words like "should", "probably", "seems to" in a completion report mean verification was skipped.

<!-- 출처: obra/superpowers verification-before-completion (MIT), 2026-10-25 요약 반영. 전체 suite·내 탓 아닌 실패 보고·경고 없음 행은 v7.0.2 test-driven-development 「Verify GREEN」, 2026-11-21 -->

