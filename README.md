# claude-code-robotics-setup

**로봇(ROS 2) 개발자를 위한 Claude Code `~/.claude` 세팅.**
스킬 86 · 에이전트 14 · 커맨드 46 · 훅 5(테스트 98종).

실제 로봇 프로젝트(휴머노이드·4족·매니퓰레이터, 공장 자동화)에서 쓰면서 다듬은 것이다.
스킬 카탈로그가 아니라 **한 벌로 동작하는 세팅**이라 그대로 설치해도 되고 필요한 것만 골라도 된다.

> 💡 이 세팅의 성격: 지식은 **스킬**에, 강제는 **훅**에, 판단 기준은 **CLAUDE.md** 에 둔다.
> 항상 로드되는 것(CLAUDE.md·에이전트 설명)은 짧게 유지하고, 나머지는 필요할 때만 열리게 한다.

<sub>English: A Claude Code configuration for robotics/ROS 2 development — 86 skills, 14 agents,
46 commands, and 5 tested hooks. Documentation is in Korean; skill trigger descriptions are
bilingual, so skill routing works with English prompts too.</sub>

---

## 뭐가 들어 있나

| | 무엇 | 언제 로드되나 |
|---|---|---|
| **skills/** 86 | ROS 2·Nav2·SLAM·매니퓰레이션·인지/학습·시뮬·안전·플릿 운영 + 웹/백엔드/인프라 | 필요할 때만 (개수가 늘어도 비용 없음) |
| **agents/** 14 | `ros2-reviewer` `robot-safety-reviewer` `robotics-architect` 등 | 이름을 불러야 옴 |
| **commands/** 47 | `/robot:diagnose` `/robot:preflight` `/ros2:new-node` `/setup:tree` … | 슬래시로 호출 |
| **hooks/** 5 | 위험 명령 차단, 시크릿 차단, colcon 생성물 편집 차단, 세션 시작 배너, 버전 감시 | 매 도구 호출 |
| **bin/** | `setup-tree.py` — 세팅 전체를 tree 도식으로 (터미널에서 직접 실행) | 부를 때만 |
| **CLAUDE.md** | 항상 지켜야 하는 규칙 (반론 제기, 실기/시뮬 구분, 계층별 진단 순서 …) | 매 세션 |

로봇 쪽에서 특히 손이 많이 간 스킬:
`ros2-engineering`(라우터 + references 25편, 약 16,800줄) · `nav2` · `robot-calibration` · `robot-kinematics` ·
`motion-planning` · `manipulation-control` · `slam-algorithms` · `state-estimation` ·
`imitation-learning` · `legged-rl` · `vla-vlm-robotics` · `robot-safety-compliance` ·
`multi-robot-fleet` · `robot-networking` · `fieldbus-comm` · `incident-analysis`

---

## 설치

```bash
git clone https://github.com/LeeSeungHo677/claude-code-robotics-setup.git
cd claude-code-robotics-setup

./install.sh --dry-run   # 무엇이 바뀌는지 먼저 본다
./install.sh             # 설치
```

**설치 스크립트가 지키는 것:**

- 기존 `~/.claude/{skills,agents,commands,hooks,CLAUDE.md,settings.json}` 을
  `~/.claude/backups/pre-install-<타임스탬프>/` 로 **먼저 백업**한다.
- 이미 `CLAUDE.md` / `settings.json` 이 있으면 **덮어쓰지 않고** `.new` 로 떨군다.
  권한 목록과 개인 규칙은 사람마다 다르다 — 덮어쓰면 당신 설정이 사라진다.
- `projects/` `history.jsonl` `.credentials.json` 등 **대화 기록·자격증명 경로는 건드리지 않는다.**
- 설치 후 훅 경로 확인 + **훅 테스트 98종**을 돌리고 결과를 보여준다.

옵션:

```bash
./install.sh --link      # 복사 대신 심볼릭 링크 (git pull 하면 바로 반영)
CLAUDE_DIR=/tmp/try ./install.sh   # 다른 위치에 시험 설치
```

### settings.json 을 이미 쓰고 있다면

`settings.json.new` 가 생긴다. **최소한 `hooks` 블록은 옮겨야 훅이 동작한다.**

```jsonc
"hooks": {
  "PreToolUse": [
    { "matcher": "Bash",
      "hooks": [{ "type": "command",
                  "command": "python3 \"$HOME/.claude/hooks/dangerous-command-guard.py\"",
                  "timeout": 10 }] },
    { "matcher": "Write|Edit|MultiEdit|NotebookEdit",
      "hooks": [{ "type": "command",
                  "command": "python3 \"$HOME/.claude/hooks/secret-scanner.py\"", "timeout": 10 },
                { "type": "command",
                  "command": "python3 \"$HOME/.claude/hooks/ros2-workspace-guard.py\"", "timeout": 10 }] }
  ],
  "SessionStart": [
    { "matcher": "",
      "hooks": [{ "type": "command",
                  "command": "python3 \"$HOME/.claude/hooks/session-context.py\"", "timeout": 10 },
                { "type": "command",
                  "command": "python3 \"$HOME/.claude/hooks/version-watch.py\"", "timeout": 5 }] }
  ]
}
```

> 경로는 `~` 가 아니라 `$HOME` 을 쓴다 — `~` 는 따옴표 안에서 확장되지 않는다.

### 설치 후

1. `~/.claude/CLAUDE.md` 의 **「이 환경」 절만** 당신 환경에 맞게 고친다. 나머지는 그대로 써도 된다.
2. **새 세션을 연다.** 훅·권한·스킬 변경은 현재 세션에 적용되지 않는다.
3. 아무 로봇 문제나 평소 말투로 물어본다 — 스킬 이름을 외울 필요 없다.

### 요구사항

- Claude Code
- **Python 3.8+** (훅이 python3 로 실행된다. 이것만 필수다)
- PyYAML — 검증 스크립트에만 필요 (`pip install pyyaml`)
- ROS 2 는 **없어도 된다.** ROS 2 스킬이 안 열릴 뿐 나머지는 그대로 동작한다.

### 제거

```bash
rm -rf ~/.claude/{skills,agents,commands,hooks}
cp -a ~/.claude/backups/pre-install-<타임스탬프>/. ~/.claude/
```

---

## 쓰는 법

### 1. 그냥 말한다 — 스킬은 알아서 열린다

```
"nav2에서 로봇이 좁은 통로를 못 지나가"        → nav2
"포인트클라우드가 이미지랑 안 겹쳐"             → robot-calibration
"ACT랑 diffusion policy 중에 뭐 써야 돼?"      → imitation-learning
"공장이 폐쇄망인데 어떻게 배포하지"             → robot-networking
"sim에선 되는데 실기에서 넘어져"                → legged-rl
```

**증상을 그대로 말하는 것이 가장 잘 걸린다.** 스킬 이름은 몰라도 된다.
확실히 열고 싶으면 `/nav2` 처럼 직접 호출한다.

### 2. 에이전트는 이름을 불러야 온다

```
"ros2-reviewer로 이 PR 검수해줘"
"robot-safety-reviewer 돌려서 실기 투입 전 점검해줘"
"robotics-architect로 이 워크스페이스 구조 파악해줘"
```

목록에 있다고 자동으로 불리지 않는다. 실제로 이 셋을 가장 많이 쓴다.

### 3. 자주 쓰는 커맨드

```
/robot:diagnose     로봇이 이상할 때 계층별 진단 (프로세스→토픽→QoS→시간→TF→좌표계)
/robot:preflight    실기 투입 전 점검
/robot:bag-analyze  rosbag 분석
/robot:tuning-log   파라미터 튜닝 기록·비교
/setup:tree         무엇이 있는지 전체 도식 (스킬 카테고리·에이전트·커맨드·훅)
/setup:audit        이 세팅 자체의 구조·참조 무결성 점검
```

### 4. 무엇이 있는지 보기 — `bin/setup-tree.py`

스킬이 86개라 목록만으로는 안 잡힌다. 카테고리별 트리로 본다.

```bash
python3 ~/.claude/bin/setup-tree.py            # 전체 (약 110줄)
python3 ~/.claude/bin/setup-tree.py 캘리브레이션 # 이름·설명에 걸리는 것만
python3 ~/.claude/bin/setup-tree.py -d         # 스킬마다 설명 한 줄까지
python3 ~/.claude/bin/setup-tree.py --check    # 분류표 ↔ 디스크 대조
```

Claude 안에서는 `/setup:tree` 로도 같은 것이 나오지만, **그냥 훑어볼 거면
터미널에서 직접 실행하는 쪽이 낫다** — 색이 살아 있고 출력이 모델 컨텍스트를
거치지 않는다. 세션 시작 배너도 이 명령을 이유와 함께 안내한다.

스킬을 직접 추가하면 `미분류` 그룹에 모여서 보인다. 정상이고 `--check` 도 통과한다.
제자리에 넣으려면 `bin/setup-tree.py` 의 `SKILL_GROUPS` 에 이름을 추가하면 된다.

---

## 훅 — 무엇이 자동으로 막히나

미리 알아두면 당황하지 않는다.

| 훅 | 차단(deny) | 확인(ask) |
|---|---|---|
| `dangerous-command-guard` | `rm -rf /`·`~`, mkfs, `dd` to `/dev/`, `curl \| sh`, 개인키 출력, `DROP DATABASE prod*` | **로봇 실기 구동 명령 전부**, `rm -r`, rosbag/데이터셋 삭제, `sudo`, `git push --force`, docker prune |
| `secret-scanner` | 시크릿이 든 파일 쓰기 (AWS/GitHub/Anthropic/Google 키, 개인키, JWT, DB URL) | — |
| `ros2-workspace-guard` | `build/`·`install/`·`log/`·`/opt/ros`·site-packages 의 ROS 패키지 편집 | — |
| `session-context` | (차단 없음 — 세션 시작 시 프로젝트 정보 주입) | — |
| `version-watch` | (차단 없음 — Claude Code 버전이 올랐을 때만 알림) | — |

**복합 명령도 분해해서 검사한다.** `cd ws && source install/setup.bash && ros2 launch ...`
처럼 앞에 안전한 명령을 붙여도 실기 구동은 잡힌다.

**`secret-scanner` 는 디스크의 파일이 아니라 "앞으로 기록될 내용"을 본다.**
`Write.content` / `Edit.new_string` / `MultiEdit.edits` 를 검사하므로 파일에 쓰이기 **전에** 막힌다.

### 왜 훅을 직접 썼나

기존 공개 세팅의 훅을 가져다 쓰려다 그만뒀다.
어떤 저장소의 훅 20개 중 10개가 입력을 `process.argv[2]` 로 읽고 있었다.
**Claude Code 는 훅에 stdin 으로 JSON 을 넘긴다.** 그대로 설치하면 **조용히 아무 동작도 안 한다** —
보호되고 있다고 믿는데 실제로는 아무것도 막히지 않는 상태가 제일 나쁘다.
출력 포맷도 구식(`{"decision":"block"}`)이라 현재 규격
(`hookSpecificOutput.permissionDecision`)과 맞지 않았다.

그래서 5개 전부 직접 쓰고 **테스트 98종**을 붙였다.

```bash
for t in ~/.claude/hooks/test_*.py; do python3 "$t"; done
```

> **pytest 로는 안 돌아간다.** 모듈 레벨에서 `main()` 을 호출하는 standalone 스크립트라
> 수집 단계에서 `INTERNALERROR` 가 난다. `python3` 로 직접 실행할 것.
> 훅이 자기 자신을 stdin JSON 으로 실행해 판정을 받아오는 구조다
> (Bash 로 테스트하면 훅이 테스트 명령 자체를 차단한다).

오탐 방지 케이스를 차단 케이스만큼 넣었다. 과하게 막는 훅은 결국 꺼지기 때문이다 —
`build_map.py`, `install_deps.sh`, `logger_utils.py`, `.env.example`,
`AKIAIOSFODNN7EXAMPLE`(AWS 공식 예제값), `os.getenv(...)` 는 전부 통과해야 한다.

---

## 권한 정책

| 분류 | 대상 |
|---|---|
| **자동 허용 (98)** | 읽기 계열 전부, `colcon build/test`, `pytest`, `ros2` **조회** 명령(list/info/echo/hz/get), git 읽기 |
| **확인 (17)** | `ros2 run/launch/topic pub/param set/service call/action send_goal/bag record·play`, `sudo`, `git push`, `docker run/rm` |
| **차단 (6)** | `~/.ssh/**`, `~/.aws/credentials`, `~/.claude/.credentials.json`, gcloud/docker/netrc 자격증명 읽기 |

원칙 하나: **하드웨어를 실제로 움직이는 명령은 절대 자동 허용하지 않는다.** 최대가 "확인" 이다.

---

## CLAUDE.md 가 강제하는 것

매 세션 로드되므로 짧게 유지한다. 요점:

- **반론 제기** — 더 나은 방법이 있거나 문제가 보이면 작업 **전에** 짚는다. Yes-man 금지.
  (한 번 짚고 사용자가 그대로 가겠다고 하면 그 결정을 따르고 전체를 완성한다)
- **실기와 시뮬을 구분한다.** 모호하면 먼저 확인한다.
- **실기 구동 명령은 실행하지 않는다** — 명령어를 보여주고 사용자가 실행한다.
- **계층부터 배제한다** — 프로세스 생존 → 토픽 흐름 → QoS → 시간 → TF → 좌표계·단위 →
  캘리브레이션 → **그 다음이** 알고리즘. 알고리즘부터 의심하면 대부분 시간을 버린다.
- **단위·좌표계·부호를 명시한다** — rad/deg, m/mm, 어느 frame.
  쿼터니언 순서는 ROS `(x,y,z,w)` / Eigen 생성자 `(w,x,y,z)` 로 **다르다**.
- **파라미터는 한 번에 하나씩** 바꾸고 기록한다. 물리적 의미를 말할 수 없으면 바꾸지 않는다.
- **성능은 N회 측정치로** 말한다. 1회 성공은 근거가 아니다.
- 긴 명령(`colcon build`, 학습 스크립트)은 백그라운드로 돌린다.

---

## 세팅을 고치거나 확장할 때

**`setup-maintenance` 스킬을 먼저 연다.** 거기에 있는 것:
무엇을 스킬/에이전트/커맨드/훅 중 어디에 넣을지, 스킬·훅 작성 규칙, 변경 후 검증 스크립트.

핵심 규칙 몇 가지:

- **스킬 경로는 반드시 `skills/<name>/SKILL.md`.** 평면 `.md` 는 인식되지 않는다.
- **`description` 이 곧 검색 인덱스다.** 사용자가 실제로 칠 단어를 넣는다 — 증상 표현, 도구 이름.
- **훅 입력은 stdin JSON.** 함부로 `allow` 를 반환하지 않는다(사용자 권한 설정을 우회하게 된다).
  파싱 실패 시 조용히 통과시킨다 — 훅 버그가 작업을 막으면 안 된다.
- **항상 로드되는 파일에 날짜·개수·측정치를 쓰지 않는다.** 계속 낡은 근거를 주입하게 된다.
  (이 규칙은 실제로 이 세팅이 자기 문서에서 세 번 어겨서 생겼다)
- **에이전트는 신중히 추가한다.** 이름+설명이 항상 컨텍스트에 상주한다. 스킬은 그렇지 않다.

변경 후 검증:

```bash
cd ~/.claude
python3 -c "import json,os,sys; d=json.load(open('settings.json')); \
[print('OK' if os.path.isfile(os.path.expandvars(h['command'].split(None,1)[1].strip('\"'))) else 'MISSING', h['command']) \
 for ev in d['hooks'].values() for g in ev for h in g['hooks']]"
for t in hooks/test_*.py; do python3 "$t" >/dev/null && echo "OK $t" || echo "FAIL $t"; done
```

**훅·권한·스킬 변경은 새 세션부터 적용된다.** 같은 세션에서 확인하려 하지 않는다.

---

## 알아둘 것

| 증상 | 확인 |
|---|---|
| 스킬이 안 열림 | `description` 에 그 상황 단어가 있는지. `/스킬이름` 으로 직접 호출해보기 |
| 훅이 과하게 막음 | 사유 메시지를 읽는다. 반복되면 `hooks/*.py` 의 패턴을 조정하고 **테스트를 추가**한다 |
| 훅 테스트가 pytest 에서 `INTERNALERROR` | 정상이다. `python3 hooks/test_*.py` 로 직접 실행 |
| 권한 확인이 너무 자주 뜸 | 안전한 명령이면 `settings.json` 의 `allow` 에 추가 (**실기 구동은 제외**) |
| 다른 머신에서 훅이 무동작 | `settings.json` 의 훅 경로가 절대경로인지 확인 (`$HOME` 기준이어야 한다) |
| 되돌리고 싶음 | `~/.claude/backups/pre-install-<타임스탬프>/` |

**이 세팅은 한국어 기준이다.** `CLAUDE.md` 의 「응답 언어」 절을 지우면 영어로 답한다.
스킬 트리거 설명은 한국어·영어가 섞여 있어 영어로 물어도 라우팅은 동작한다.

---

## 라이선스

MIT ([LICENSE](LICENSE)).
단, 여러 오픈소스에서 가져온 파일이 포함되어 있고 **해당 파일은 원 라이선스를 따른다.**
출처 전체 목록은 [NOTICE](NOTICE) 를 볼 것 —
`awesome-claude-code-toolkit`(Apache-2.0) · `Jeffallan/claude-skills`(MIT) ·
`ros2-engineering-skills`(Apache-2.0) · `robotics-agent-skills`(Apache-2.0) 등.

출처 표기가 틀렸거나 라이선스 조건이 맞지 않는 부분이 있으면 **이슈로 알려주면 즉시 고치거나
해당 파일을 제거하겠다.**

## 기여

이슈·PR 환영. 특히:

- **스킬 내용이 틀렸다** — 가장 중요하다. 틀린 지식을 자신 있게 말하는 세팅은 없느니만 못하다.
- 훅 오탐 사례 (막히면 안 되는 것이 막혔다)
- 다른 로봇 플랫폼·다른 ROS 배포판에서의 차이

훅을 고치는 PR 은 **테스트를 함께** 넣어주면 좋다.
