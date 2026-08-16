---
name: mujoco
description: >
  MuJoCo 물리 시뮬레이터 — 모델링, 제어, 대규모 병렬 학습. TRIGGER when the user writes or edits
  MJCF XML, converts URDF to MJCF, tunes contact/solver parameters, uses mujoco python bindings,
  runs batched simulation with MJX (JAX) or MuJoCo Warp, uses MuJoCo Playground, integrates MuJoCo
  with ROS 2 (mujoco_ros2_control), or debugs "the simulation explodes / objects sink through the
  floor / contacts jitter / sim is too slow" problems.
---

# MuJoCo

접촉이 많은 강체 시뮬레이션(매니퓰레이터, 사족, 휴머노이드, 손)에서 사실상 표준.
**학습용 대규모 병렬 시뮬레이션**이 주 용도이고, ROS 2 통합은 부차적이다.

## 언제 MuJoCo 를 쓰고 언제 안 쓰는가

| 상황 | 선택 |
|---|---|
| RL/IL 학습, 수천 환경 병렬 | **MuJoCo (MJX / Warp)** |
| 접촉 역학이 중요한 조작·보행 | **MuJoCo** |
| 센서(카메라/LiDAR) 사실성이 중요 | Isaac Sim (MuJoCo 렌더링은 제한적) |
| ROS 2 스택 전체를 시뮬레이션 | Gazebo 또는 Isaac Sim |
| 대규모 환경·다중 로봇 씬 | Isaac Sim |

MuJoCo 는 **물리가 강점, 씬/센서 생태계가 약점**이다. ROS 2 전체 브링업을 시뮬레이션하려는
목적이면 잘못 고른 것이다.

## 모델링 (MJCF)

- URDF → MJCF 변환은 자동 도구(`mujoco.MjModel.from_xml_path` 의 URDF 지원,
  또는 별도 변환 스크립트)로 시작하되 **결과를 반드시 손본다.**
  변환기가 채우지 못하는 것: 접촉 파라미터, 액추에이터 정의, 센서, 감쇠.
- 계층 구조: `<worldbody>` → `<body>` → `<joint>` / `<geom>` / `<site>`.
  `<site>` 는 질량이 없는 기준점 — 센서 부착과 좌표 참조에 쓴다.
- **충돌 geom 과 시각 geom 을 분리한다.** `contype`/`conaffinity` 로 충돌 그룹을 관리하고,
  시각용은 `contype="0" conaffinity="0"` 으로 물리에서 뺀다. 안 하면 느리고 불안정하다.
- 액추에이터를 명시한다 — `<motor>`(토크), `<position>`(위치 PD), `<velocity>`.
  `<position>` 의 `kp` 와 joint 의 `damping` 이 실제 제어 특성을 결정한다.
- 관성은 `<inertial>` 로 직접 주거나 geom 밀도(`density`)로 자동 계산시킨다.
  **자동 계산에 의존할 때는 총 질량을 반드시 검증한다.**

## 안정성 — "시뮬이 터진다" 해결 순서

1. **timestep 을 줄인다.** `<option timestep="0.002">` → `0.001` 또는 `0.0005`.
   대부분의 폭발은 여기서 해결된다. 단 느려진다.
2. **solver 를 바꾼다.** `solver="Newton"` (정확, 기본 권장), `"CG"`, `"PGS"`.
   `iterations` 를 늘리면 안정적이지만 느리다.
3. **접촉 파라미터**: `solref`(시간상수, 감쇠비)와 `solimp`(임피던스 곡선).
   물체가 바닥을 뚫으면 `solref` 의 시간상수를 timestep 의 2배 이상으로 잡는다.
4. **질량비**를 확인한다. 매우 가벼운 물체가 매우 무거운 물체와 접촉하면 수치적으로 불안정하다.
   질량비 1:1000 을 넘지 않게 조정하거나 armature 를 준다.
5. **armature** 를 관절에 추가한다 (`<joint armature="0.01">`). 모터 회전 관성을 모사해
   고이득 제어에서의 진동을 크게 줄인다. 실기와 맞추는 데도 중요하다.
6. 초기 자세가 이미 관통(penetration) 상태인지 확인한다. 시작부터 겹쳐 있으면 튕겨 나간다.

## 대규모 병렬 (MJX / Warp)

- **MJX**: 같은 물리를 JAX 로 포팅. GPU/TPU 에서 수천 환경 배치 실행.
  RL 학습 처리량이 CPU 대비 수 자릿수 빨라진다.
- **MuJoCo Warp**: NVIDIA 와의 협업 결과물. 복잡한 조작 태스크에서 추가 가속.
- **MuJoCo Playground**: 사족·휴머노이드·손·팔에 대해 zero-shot sim-to-real 을 목표로 한
  학습 환경 모음. 새 태스크를 만들 때 여기 구조를 따라가면 시행착오가 준다.

주의:
- MJX 는 MuJoCo 의 **모든 기능을 지원하지 않는다.** 특정 접촉 타입·제약이 빠져 있을 수 있으므로
  모델을 옮기기 전에 지원 여부를 확인한다. CPU MuJoCo 와 결과가 미세하게 다를 수 있다.
- JAX 특성상 **모델 구조가 배치 내에서 동일**해야 한다. 환경마다 다른 오브젝트 수를 두면 안 된다.
  도메인 랜덤화는 파라미터 값만 바꾸는 방식으로 설계한다.
- `jit` 컴파일 시간이 길다. 반복 실험에서는 컴파일 캐시를 활용한다.

## ROS 2 연동

- `mujoco_ros2_control` 계열 하드웨어 인터페이스를 쓰면 `ros2_control` 컨트롤러를
  MuJoCo 위에서 그대로 돌릴 수 있다. 실기 컨트롤러를 시뮬에서 검증하는 데 유용하다.
- 이때 `use_sim_time:=true` 와 시계 발행을 반드시 맞춘다. 안 맞으면 TF 가 전부 깨진다.
- 렌더링/센서는 기대치를 낮춘다. 카메라 기반 인지를 검증하려면 Isaac Sim 이 낫다.

## sim-to-real 을 위한 실무

- **실기 데이터로 모델을 보정한다.** 관절에 스텝 입력을 주고 실기와 시뮬 응답을 겹쳐 보며
  `damping`, `armature`, `frictionloss` 를 맞춘다. 이 작업 없이 sim2real 을 기대하지 않는다.
- 마찰은 재질 조합마다 다르다. `<geom friction="slide spin roll">` 세 값을 구분해서 본다.
- 도메인 랜덤화 대상: 질량, 마찰, 액추에이터 이득, 지연(latency), 관측 노이즈, 지형.
  **지연을 빼먹는 경우가 많은데** 실기 제어 루프 지연은 sim2real 실패의 큰 원인이다.
- 시뮬에서만 되는 정책은 대개 접촉을 착취(exploit)하고 있다. 접촉력을 로그로 확인한다.
