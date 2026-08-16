---
name: gazebo
description: >
  Gazebo (gz-sim / Ignition / Classic) 시뮬레이션. TRIGGER when the user edits SDF worlds, spawns
  robots, bridges topics with ros_gz_bridge, uses gz_ros2_control, adds sensor plugins, simulates
  warehouses with dynamic obstacles or multiple robots, or hits 'robot falls through the floor /
  sensors publish nothing / real-time factor 0.2'.
---

# Gazebo

API·브리지·플러그인 세부는 이미 정리돼 있다 —
**`~/.claude/skills/ros2-engineering/references/simulation.md` (724줄)** 를 먼저 읽는다.
거기 있는 것: 버전 매트릭스, `ros_gz_bridge` 문법과 YAML 설정, `gz_ros2_control`,
`use_sim_time`, 센서 플러그인(카메라/GPU LiDAR/IMU/GPS/깊이), sim-to-real, headless CI, 결정론.

이 문서는 **거기 없는 것** — 월드 저작, 다중 로봇, 성능, 현장형 환경 구성 — 을 다룬다.

## 버전을 먼저 정한다

- **ROS distro 가 Gazebo 버전을 결정한다.** 임의 조합은 `ros_gz` 를 깨뜨린다.
  `ros_gz` 패키지가 알아서 맞는 Gazebo 를 당겨오게 두는 것이 안전하다.
- Gazebo Classic(gazebo11)은 유지보수 종료 방향이다. 신규는 **gz-sim** 계열로 간다.
- 명령·패키지 이름이 세대별로 다르다 (`gazebo` / `ign` / `gz`). 문서를 검색할 때
  **자기 버전 문서인지 확인**한다. 옛 튜토리얼을 따라 하다 막히는 경우가 대부분이다.

## 언제 Gazebo 를 쓰는가

| 목적 | 선택 |
|---|---|
| **ROS 2 스택 전체 통합 시험** (nav2, ros2_control, 런치, TF) | **Gazebo** — 가장 잘 맞는다 |
| CI 회귀 시험 (headless, 결정론) | **Gazebo** |
| 사실적 센서·합성 데이터 생성 | Isaac Sim |
| 접촉 역학 위주 RL/IL 대규모 학습 | MuJoCo / MJX |
| 다중 로봇 물류 시뮬레이션 | Gazebo (+ Open-RMF 데모가 Gazebo 기반) |

Gazebo 의 강점은 **ROS 2 생태계와의 밀착**이지 물리 정밀도나 렌더링이 아니다.

## 월드 저작 (SDF)

```xml
<sdf version="1.9">
  <world name="warehouse">
    <physics name="default" type="dart">
      <max_step_size>0.001</max_step_size>       <!-- 작을수록 안정, 느림 -->
      <real_time_factor>1.0</real_time_factor>
    </physics>

    <!-- 필수 시스템 플러그인들 — 빠지면 조용히 아무것도 동작하지 않는다 -->
    <plugin filename="gz-sim-physics-system"        name="gz::sim::systems::Physics"/>
    <plugin filename="gz-sim-sensors-system"        name="gz::sim::systems::Sensors">
      <render_engine>ogre2</render_engine>
    </plugin>
    <plugin filename="gz-sim-user-commands-system"  name="gz::sim::systems::UserCommands"/>
    <plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
    <plugin filename="gz-sim-imu-system"            name="gz::sim::systems::Imu"/>
  </world>
</sdf>
```

**가장 흔한 실수**: 센서를 URDF 에 정의했는데 월드에 `Sensors` 시스템 플러그인이 없어서
토픽이 아예 안 나온다. 에러도 안 난다. 센서가 안 보이면 여기부터 확인한다.

### 현장형 환경 만들기
- 실제 창고·공장 도면(CAD/DWG)이 있으면 그것을 기준으로 만든다. 눈대중 월드에서 튜닝한
  파라미터는 현장에서 쓸모없다.
- **바닥 마찰**을 실제와 맞춘다. 기본값 그대로면 로봇이 미끄러지거나 반대로 너무 붙는다.
- 선반·팔레트는 **충돌 형상을 단순 박스**로 준다. 시각 메시를 충돌에 쓰면 시뮬이 기어간다.
- **동적 장애물**: `<actor>` 로 사람 이동을 넣는다. 정적 환경에서만 검증한 내비게이션은
  현장에서 반드시 실패한다.
- 조명을 현장과 비슷하게 — 비전 알고리즘을 검증할 거면 특히.

### 자산 관리
- 모델을 `GZ_SIM_RESOURCE_PATH` 로 찾게 하고, **패키지 안에 넣어 버전 관리**한다.
  온라인 모델 저장소(Fuel)에 의존하면 폐쇄망에서 월드가 안 열린다 (`robot-networking` 스킬).
- 월드 파일을 xacro 로 만들면 파라미터화(로봇 수, 장애물 배치)가 쉬워진다.

## 다중 로봇 스폰

플릿 시뮬레이션의 기본 골격:

- 로봇마다 **고유 이름 + 네임스페이스**를 준다. TF 프리픽스도 함께 분리한다
  (`ros2-engineering/references/multi-robot.md` §2).
- 브리지도 로봇 수만큼 네임스페이스를 붙여 띄운다. 하나의 전역 브리지로 묶으면 토픽이 충돌한다.
- `/clock` 은 **하나만** 브리지한다. 여러 개 띄우면 시간이 튄다.
- 스폰 위치가 겹치면 로봇들이 서로를 밀어낸다. 초기 배치를 파라미터로 관리한다.
- 10대를 넘어가면 실시간 배수가 급락한다. **headless + 센서 최소화**로 돌리고,
  필요한 센서만 켠다.

## 성능 — "시뮬이 너무 느리다"

실시간 배수(RTF)가 0.2 면 10분 시나리오가 50분 걸린다. 원인 순서대로:

1. **GPU LiDAR / 카메라 개수와 해상도** — 압도적 1위 원인. 업데이트 주기와 해상도를 낮춘다.
   포인트 수는 수평×수직 해상도의 곱이다
2. **충돌 메시 복잡도** — 시각 메시를 충돌로 쓰고 있지 않은지 확인
3. **물리 스텝 크기** — 작을수록 안정적이지만 느리다. 필요한 최소로
4. **GUI** — 학습·CI 는 headless (`gz sim -s -r`)
5. **모델 수** — 안 쓰는 장애물·장식 제거

측정: `gz topic -e -t /stats` 로 RTF 를 본다. 감으로 판단하지 않는다.

## 결정론 — CI 회귀 시험의 전제

- 기본 설정에서 Gazebo 는 **실행마다 결과가 다르다.** 그대로 CI 회귀 시험을 만들면
  실패가 코드 문제인지 잡음인지 구분할 수 없다.
- 고정 스텝 + 서버 모드로 돌리고, 난수 시드를 고정한다.
  세부는 `simulation.md` §9 (결정론) 참고.
- 성공 판정을 **명시적 조건**으로 만든다 (목표 도달 여부, 소요 시간 상한, 충돌 0회).
  영상 확인은 회귀 시험이 아니다.

## 자주 터지는 것

| 증상 | 원인 |
|---|---|
| 로봇이 바닥을 뚫고 내려감 | 충돌 형상 없음, 물리 스텝 과대, 초기 위치가 지면 아래 |
| 센서 토픽이 안 나옴 | 월드에 `Sensors`(또는 Imu 등) 시스템 플러그인 누락 |
| ROS 쪽에 토픽이 안 보임 | `ros_gz_bridge` 미실행 또는 타입 매핑 오타 |
| TF 가 전부 깨짐 | `use_sim_time` 이 일부 노드에만 적용됨 |
| 로봇이 명령에 반응 없음 | `gz_ros2_control` 플러그인 미로드, 컨트롤러 미활성 |
| 관절이 흐물거림 | 관절 damping/stiffness 미설정, 관성값 비현실적 |
| 시뮬은 되는데 실기에서 실패 | 지연·액추에이터 모델 차이 — `simulation.md` §7 sim-to-real |
| 월드가 안 열림 (현장) | Fuel 온라인 모델 의존 — 로컬로 내려받아 패키지에 포함 |
