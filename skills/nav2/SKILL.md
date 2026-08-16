---
name: nav2
description: >
  Nav2 (ROS 2 Navigation) 튜닝·플러그인·디버깅. TRIGGER when the user edits nav2_params.yaml, works with
  costmaps, controllers (MPPI/DWB/Regulated Pure Pursuit), planners
  (NavFn/SMAC/Hybrid-A*/ThetaStar), AMCL, recovery servers, collision monitor, or the Nav2
  behavior tree — or hits 'robot oscillates / cannot pass a narrow gap / path hugs walls /
  recovery loops / goal not reached'.
---

# Nav2

`references/` 에 소스 기반 상세 문서가 있다. **파라미터를 만지기 전에 먼저 어느 계층의 문제인지
확정한다** — 대부분의 "튜닝" 요청은 실제로는 잘못된 계층을 만지고 있다.

## 라우팅

| 하려는 일 | 읽을 파일 |
|---|---|
| 전체 구조·서버 구성·lifecycle 순서 | `references/architecture.md` |
| 파라미터 값·기본값·단위 확인 | `references/parameters.md` |
| 코스트맵 레이어, 인플레이션, 필터, 풋프린트 | `references/costmap.md` |
| MPPI / DWB / RPP 컨트롤러 튜닝 | `references/controllers.md` |
| NavFn / SMAC(Hybrid-A*, State Lattice) / ThetaStar | `references/planners.md` |
| BT Navigator, Controller/Planner/Behavior Server, Waypoint Follower | `references/servers.md` |
| AMCL, 초기 위치, 파티클 필터 | `references/localization.md` |
| 네비게이션 BT XML 구조·노드 | `references/behavior-tree.md` |
| `nav2_core` 플러그인 인터페이스 (Controller/Planner/Behavior/Goal Checker/Progress Checker) | `references/core-interfaces.md` |
| 커스텀 플러그인 새로 만들기 (pluginlib 등록까지) | `references/writing-plugins.md` |
| action/msg 타입, 목표 전달 형식 | `references/msgs.md` |

## 진단 먼저: 어느 계층이 문제인가

증상만 보고 컨트롤러 파라미터부터 만지지 않는다. 순서대로 배제한다.

1. **TF / 로컬라이제이션** — `ros2 run tf2_tools view_frames`, `map→odom→base_link` 가 끊기지 않는가.
   AMCL 공분산이 발산하면 그 아래 모든 계층이 무의미하다.
2. **센서 → 코스트맵** — RViz 에서 local/global costmap 을 켜고 **장애물이 실제로 찍히는지** 본다.
   안 찍히면 `observation_sources` 의 토픽·frame·`expected_update_rate` 문제다.
3. **글로벌 플래너** — 경로가 나오는가, 그 경로가 물리적으로 통과 가능한가.
4. **로컬 컨트롤러** — 경로는 맞는데 추종이 안 되는가.
5. **속도 → 하드웨어** — `/cmd_vel` 이 나가는데 안 움직이면 `velocity_smoother`, `collision_monitor`,
   또는 베이스 드라이버 쪽이다. `ros2 topic echo /cmd_vel` 로 실제 값을 본다.

## 증상별 첫 수 (상세는 references)

| 증상 | 가장 흔한 원인 | 먼저 볼 것 |
|---|---|---|
| 좁은 통로를 못 지나감 | inflation_radius 가 통로 반폭보다 큼 | `inflation_radius`, `cost_scaling_factor`, footprint |
| 벽에 붙어서 주행 | inflation 이 약하거나 cost_scaling_factor 가 큼 | InflationLayer |
| 제자리 진동(oscillation) | 목표 허용오차 vs 제어 주기 불일치 | goal checker `xy_goal_tolerance`, `yaw_goal_tolerance` |
| 회복 동작 무한 반복 | 플래너가 계속 실패 → BT 가 recovery 루프 | 글로벌 코스트맵에 로봇이 갇혔는지 |
| 장애물이 안 지워짐 | raytrace 범위·센서 max range 설정 | `raytrace_max_range`, `obstacle_max_range` |
| 코스트맵이 갱신 안 됨 | `expected_update_rate` 초과 → 소스 무효화 | 센서 실제 Hz vs 설정값 |
| 후진 못 함 | 컨트롤러/플래너가 전진 전용 | RPP `allow_reversing`, SMAC `reverse_penalty` |
| 목표 근처에서 멈춤 | progress checker 가 정지로 판단 | `required_movement_radius`, `movement_time_allowance` |

## 컨트롤러 선택

- **MPPI** (현재 기본): 샘플링 기반, 동적 장애물·비홀로노믹에 강함. CPU 를 많이 쓴다.
  `batch_size` × `time_steps` 가 연산량을 직접 결정한다 — 온보드 CPU 예산부터 확인.
- **DWB**: 가볍고 예측 가능. critic 가중치로 동작을 명시적으로 설계할 수 있다.
- **Regulated Pure Pursuit**: 경로 추종이 목적이고 회피는 플래너에 맡길 때. 튜닝이 가장 단순.
- **Rotation Shim**: 위 컨트롤러 앞에 붙여 "먼저 제자리 회전 후 주행" 을 만든다. 차동구동에 유용.

## 플래너 선택

- **NavFn / Theta\***: 2D 원형 풋프린트, 홀로노믹에 가까운 로봇.
- **SMAC Hybrid-A\***: 아커만/차동 + 비원형 풋프린트, 후진 필요, 회전 반경 제약이 있을 때.
- **SMAC State Lattice**: 운동학적으로 실행 가능한 궤적이 필수일 때.
- **SMAC 2D**: 격자 기반이지만 SMAC 스무더를 쓰고 싶을 때.

## 튜닝 원칙

- **한 번에 하나씩 바꾸고 기록한다.** 여러 파라미터를 동시에 만지면 무엇이 효과였는지 알 수 없다.
- 파라미터를 바꾸기 전에 **그 값이 물리적으로 무엇을 의미하는지** 말할 수 있어야 한다.
  단위(m, m/s, rad, Hz)를 확인한다 — `references/parameters.md` 에 단위가 명시돼 있다.
- 실기 전에 **같은 rosbag 으로 재현**한다. 실기에서 튜닝하면 재현이 안 돼 튜닝이 아니라 도박이 된다.
- footprint 는 실제 치수 + 여유로 잡는다. footprint 가 틀리면 inflation 튜닝은 전부 헛수고다.
- `controller_frequency` 를 올리기 전에 실제 달성 주기를 먼저 잰다. 설정값이 아니라 실측이 기준이다.

## 안전

`collision_monitor` 는 컨트롤러와 **독립된 경로**로 동작해야 의미가 있다.
컨트롤러가 죽었을 때도 정지시킬 수 있는 구조인지 확인한다.
E-stop 체인은 소프트웨어 레이어에만 의존하면 안 된다 — `ros2-engineering/references/safety-estop.md` 를 함께 본다.
