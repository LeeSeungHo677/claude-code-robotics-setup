---
name: setup-maintenance
description: >
  이 Claude Code 세팅(~/.claude) 자체를 확장·갱신·검증하는 방법. TRIGGER when the user wants to
  add or update a skill/agent/command/hook, incorporate a newly released technology or library into
  the setup, audit the configuration for drift or breakage, check upstream source repositories for
  updates, or asks "우리 세팅에 X 를 추가해줘" / "세팅 점검해줘" / "이거 스킬로 만들어줘".
---

# 세팅 유지보수

로봇 기술은 계속 바뀐다. 세팅이 한 번 만들고 방치되면 **틀린 지식을 자신 있게 말하는
상태**가 되어 없느니만 못해진다. 이 문서는 그것을 막는 절차다.

전체 구성 내역·출처·라이선스는 **`~/.claude/MANIFEST.md`** 에 있다. 무엇을 바꾸든 먼저 읽는다.

## 구조

```
~/.claude/
├── CLAUDE.md            매 세션 로드. 짧게 유지한다 (규칙만, 지식은 스킬로)
├── MANIFEST.md          구성 내역·출처·미적용 항목
├── settings.json        권한(allow/ask/deny) + 훅 등록
├── skills/<name>/SKILL.md    지식 본체. 호출될 때만 로드 → 개수 제한 없음
│   └── references/*.md       큰 스킬은 라우터 + references 로 분리
├── agents/<name>.md     이름+설명이 항상 컨텍스트에 있음 → 개수를 제한한다
├── commands/<cat>/<x>.md     /cat:x 로 호출
└── hooks/*.py           결정론적 강제. stdin JSON 규격
```

## 무엇을 어디에 넣을지 판단

| 성격 | 넣을 곳 |
|---|---|
| 참조 지식, 패턴, 함정 모음 | **skill** (기본값. 대부분 여기다) |
| 뚜렷한 역할·태도가 필요한 작업 | agent — **신중히**. 개수가 늘면 매 세션 비용이 는다 |
| 반복하는 절차 | command |
| 반드시 막아야 하는 것 | hook |
| 항상 지켜야 하는 짧은 규칙 | CLAUDE.md — **한 줄이라도 아깝다고 생각하고 넣는다** |

**항상 로드되는 파일(CLAUDE.md)에는 날짜·개수·측정치를 쓰지 않는다.** 규칙만 쓴다.
"2026-08-17 기준 에이전트 24개 중 호출 0회" 같은 근거는 시간이 지나면 틀린 말이 되는데,
매 세션 로드되므로 계속 틀린 근거를 주입하게 된다. **근거와 이력은 `MANIFEST.md` 에 둔다.**
통계가 필요하면 훅이 그때 계산하게 한다 (`session-context.py` 가 `skillUsage` 를 매번 읽는 방식).

## 새 기술을 세팅에 반영할지 판단

새로운 것이 나왔다고 다 넣지 않는다. 아래를 통과할 때만 넣는다.

- [ ] **실제로 쓸 것인가** 또는 6개월 내 쓸 가능성이 있는가
- [ ] 기존 스킬에 **한 섹션으로 들어가면 되는가** → 그러면 새 스킬을 만들지 않는다
- [ ] 안정화됐는가. 매달 API 가 바뀌는 것은 스킬로 굳히면 금방 틀린 정보가 된다
      → 이런 것은 "선택 기준과 함정"만 적고 **API 세부는 적지 않는다**
- [ ] 공식 문서를 보면 되는 것을 옮겨 적는 것은 아닌가
      → 스킬의 가치는 **선택 기준·함정·실패 진단**이지 API 나열이 아니다

## 스킬 작성 규칙

```markdown
---
name: <디렉토리명과 동일한 kebab-case>
description: >
  한 줄 요약. TRIGGER when the user ... (언제 이 스킬이 열려야 하는지 구체적으로)
  DO NOT TRIGGER for ... (오발동을 막을 필요가 있으면)
---
```

- **경로는 `~/.claude/skills/<name>/SKILL.md`** — 평면 `.md` 파일은 인식되지 않는다.
  (외부 레포를 가져올 때 이걸 자주 틀린다)
- `description` 이 곧 검색 인덱스다. **사용자가 실제로 쓸 단어**를 넣는다 —
  증상 표현("로봇이 넘어짐"), 도구 이름, 라이브러리 이름.
- 본문 1,000줄이 넘어가면 **라우터 + `references/`** 로 쪼갠다 (`nav2`, `ros2-engineering` 참고).
- 내용 원칙:
  - **함정과 실패 진단을 우선**한다. 정상 경로는 공식 문서에 있다
  - 증상 → 원인 표를 넣는다. 실무에서 가장 많이 쓰이는 형식
  - 선택지가 있으면 **선택 기준 표**를 준다
  - 버전에 민감한 세부(정확한 플래그, 정확한 버전 번호)는 최소화한다 — 먼저 낡는다
  - 다른 스킬과 겹치면 **참조로 넘긴다.** 같은 내용을 두 곳에 쓰면 한쪽이 반드시 낡는다
- 하니스 **번들 스킬**(`dataviz`, `artifact-design`, `code-review`, `security-review` 등)은
  `~/.claude/skills/` 에 없지만 사용 가능하다. 참조할 때 "번들 스킬" 이라고 표기해
  `/setup:audit` 의 오탐을 막는다. 같은 이름으로 스킬을 만들면 번들 것을 덮어쓴다

## 에이전트 작성 규칙

- `name:` 은 파일명과 같아야 한다.
- `description:` 에 **언제 이 에이전트를 부르는지**를 쓴다. 능력 자랑이 아니라 호출 조건.
- `model:` 은 넣지 않는다 — 세션 모델을 상속하게 둔다.
- 본문에는 **태도와 판단 기준**을 쓴다. 지식은 스킬에 있으니 중복하지 않는다.
- 추가 전에 자문한다: 기존 에이전트로 안 되는가? 스킬로 충분하지 않은가?

## 훅 작성 규칙 — 여기서 실수하면 조용히 무동작한다

- **입력은 stdin JSON 이다.** `process.argv` / `sys.argv` 가 아니다.
  (외부 레포 훅의 흔한 결함. `MANIFEST.md` 참고)
- 차단 출력:
  ```json
  {"hookSpecificOutput": {"hookEventName": "PreToolUse",
    "permissionDecision": "deny",            // allow | deny | ask
    "permissionDecisionReason": "사유"}}
  ```
  + stderr 에도 사유를 쓰고 **exit 2**. (JSON 스키마가 안 맞아도 exit 2 + stderr 로 차단된다)
- 아무 결정도 안 할 때는 **출력 없이 exit 0**. 함부로 `allow` 를 반환하지 않는다
  (사용자의 권한 설정을 우회하게 된다).
- 입력 파싱에 실패하면 **조용히 통과**시킨다. 훅 버그가 작업을 막으면 안 된다.
- Bash 훅은 복합 명령(`&&`, `;`, `|`, `$()`)을 **분해해서** 검사한다.
  앞에 안전한 명령을 붙여 우회하는 것을 막는다.
- **반드시 테스트를 작성한다.** 차단 케이스 / 통과 케이스(오탐) 양쪽 모두.
  `~/.claude/hooks/` 의 기존 훅 테스트 방식을 따른다.

## 권한 규칙 추가

- `Bash(cmd *)` 와 `Bash(cmd:*)` 는 같다. 끝의 `*` 앞에 공백이 있으면 단어 경계가 생긴다
  (`Bash(ls *)` 는 `lsof` 에 매칭되지 않음).
- 복합 명령은 **하위 명령이 각각** 매칭돼야 허용된다.
- deny > ask > allow 순으로 우선한다.
- **하드웨어를 움직이는 명령은 절대 allow 에 넣지 않는다.** ask 가 최대다.

## 변경 후 반드시 검증

```bash
cd ~/.claude
# 1) settings.json 유효성 + 훅 경로 존재
python3 -c "import json,os;d=json.load(open('settings.json'));\
[print(('OK ' if os.path.exists(h['command'].split()[-1]) else 'MISSING '),h['command'])\
 for ev in d['hooks'].values() for g in ev for h in g['hooks']]"

# 2) 스킬 프론트매터 전수 파싱
python3 -c "
import os,yaml
b='skills';bad=[]
for d in sorted(os.listdir(b)):
    p=os.path.join(b,d,'SKILL.md')
    if not os.path.isfile(p): bad.append((d,'no SKILL.md')); continue
    t=open(p,encoding='utf-8').read()
    e=t.find('\n---\n',3)
    if not t.startswith('---\n') or e<0: bad.append((d,'frontmatter')); continue
    try:
        m=yaml.safe_load(t[4:e+1]); assert m.get('description')
    except Exception as x: bad.append((d,str(x)[:40]))
print('스킬', len(os.listdir(b)), '개, 문제', len(bad)); [print(' ✗',*x) for x in bad]"

# 3) 에이전트 name == 파일명
for a in agents/*.md; do n=$(grep -m1 '^name:' "$a"|sed 's/name: *//'); f=$(basename "$a" .md);
  [ "$n" = "$f" ] || echo "✗ $f (name=$n)"; done

# 4) 훅 문법
for h in hooks/*.py; do python3 -m py_compile "$h" || echo "✗ $h"; done; rm -rf hooks/__pycache__
```

**훅·권한·스킬 변경은 새 세션부터 적용된다.** 같은 세션에서 확인하려 하지 않는다.

## 정기 점검

`/setup:audit` 로 구성 점검, `/setup:tech-scan <도메인>` 으로 신기술 조사를 돌린다.
분기 1회 정도가 적당하다. 그 외에는:

- 스킬 내용이 **틀렸다는 것을 발견했을 때 즉시 고친다.** 나중에 하면 안 한다.
- 새 프로젝트를 시작할 때 그 도메인 스킬이 최신인지 확인한다.
- 같은 실수를 두 번 하면 그것은 스킬(또는 훅)에 들어갈 신호다.

## 바꾼 뒤

`MANIFEST.md` 를 갱신한다 — 무엇을 추가했고 출처가 어디인지.
이 기록이 없으면 6개월 뒤에 어느 것이 직접 쓴 것이고 어느 것이 외부에서 온 것인지 모른다.
