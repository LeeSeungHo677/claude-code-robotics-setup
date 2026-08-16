---
name: nvidia-isaac
description: >
  NVIDIA Isaac 플랫폼 — Isaac Sim, Isaac Lab(isaaclab), Isaac ROS. TRIGGER when the user works with
  Isaac Sim (USD scenes, URDF importer, ROS 2 bridge, Replicator synthetic data), Isaac Lab RL/IL
  environments and parallel training, Isaac ROS GEMs (Visual SLAM, nvblox, AprilTag), Omniverse
  assets, or Jetson Orin/Thor deployment. Also 'Isaac Sim is slow / ROS 2 bridge shows nothing'.
---

# NVIDIA Isaac

세 가지가 이름만 비슷하고 **용도가 완전히 다르다.** 먼저 무엇이 필요한지 구분한다.

| 제품 | 무엇인가 | 언제 쓰는가 |
|---|---|---|
| **Isaac Sim** | Omniverse/USD 기반 로봇 시뮬레이터 | 사실적 센서 시뮬, 합성 데이터 생성, 씬 구성, ROS 2 통합 테스트 |
| **Isaac Lab** | Isaac Sim 위의 로봇 학습 프레임워크 | RL/IL 정책 학습, 수천 환경 GPU 병렬, sim-to-real |
| **Isaac ROS** | ROS 2 패키지 모음 (GPU 가속 GEM) | **실기 온보드**에서 인지·SLAM 을 Jetson 으로 가속 |

"Isaac 을 쓴다" 는 말은 이 셋 중 무엇인지 정하기 전까지는 의미가 없다.

## Isaac Sim

### 기본 워크플로
1. **URDF Importer** 로 로봇을 가져와 USD 로 변환한다.
2. 조인트 드라이브(stiffness/damping)를 설정한다 — **임포트 기본값은 대부분 부적절하다.**
   드라이브가 0이면 로봇이 중력에 무너지고, 과도하면 진동한다.
3. 물리 씬(중력, solver iteration, timestep)을 확인한다.
4. ROS 2 Bridge 확장을 켜고 퍼블리셔/서브스크라이버 액션 그래프를 구성한다.
5. `use_sim_time:=true` 와 `/clock` 발행을 맞춘다.

### ROS 2 브리지가 "아무것도 안 나올 때"
1. ROS 2 Bridge 확장이 **활성화**돼 있는가
2. `RMW_IMPLEMENTATION` 이 Isaac Sim 쪽과 ROS 2 쪽에서 **동일**한가 (가장 흔한 원인)
3. `ROS_DOMAIN_ID` 가 같은가
4. 액션 그래프의 OnPlaybackTick 이 연결돼 있고 시뮬레이션이 **재생 중**인가
5. QoS 가 맞는가 — 센서는 대개 BEST_EFFORT
6. 컨테이너로 돌린다면 네트워크 모드와 멀티캐스트 허용 여부

### 합성 데이터 생성 (Replicator)
- 라벨이 공짜로 나온다 — 바운딩박스, 세그멘테이션, 깊이, 포즈. 수작업 라벨링 비용을 없앤다.
- **도메인 랜덤화**: 조명, 텍스처, 카메라 자세, 물체 배치, 재질. 이걸 안 하면
  합성 데이터로 학습한 모델이 실기에서 무너진다.
- 실기 데이터와 **혼합**하는 것이 대개 최선이다. 합성 100%로 가는 경우는 드물다.
- 합성/실기 도메인 갭을 줄이는 방향으로 Cosmos Transfer 같은 도구가 쓰인다.

### 성능
- Isaac Sim 은 무겁다. RTX 급 GPU 와 충분한 VRAM 이 필요하다.
- 렌더링이 필요 없는 학습이면 headless 로 돌리고 렌더 해상도를 낮춘다.
- 씬의 물리 오브젝트 수와 충돌 복잡도가 지배적이다. 시각 메시를 충돌에 그대로 쓰지 않는다.

## Isaac Lab

- GPU 에서 **수천 환경 병렬**로 RL/IL 학습. 수렴이 며칠 → 몇 시간 단위로 줄어든다.
- 환경 정의는 매니저 기반 구성(observation / action / reward / termination / event)으로 나뉜다.
  기존 환경을 복사해 수정하는 방식이 가장 빠르다.
- 학습 알고리즘은 외부 라이브러리(rsl_rl, skrl, RL-Games, Stable-Baselines3)를 붙여 쓴다.
  Isaac Lab 자체는 환경·시뮬 쪽을 담당한다.
- 멀티 GPU 스케일링을 지원한다.

**설계 주의:**
- 관측(observation)에 시뮬에서만 얻을 수 있는 값(정확한 물체 자세, 접촉력)을 넣으면
  실기에서 그대로 쓸 수 없다. **실기에서 측정 가능한 것만** 관측에 넣거나,
  teacher-student(특권 정보로 학습 후 증류) 구조를 명시적으로 설계한다.
- 보상 항이 많아지면 튜닝이 불가능해진다. 항마다 기여도를 로깅해 어떤 항이 지배하는지 본다.
- 에피소드 종료 조건(넘어짐, 시간 초과, 목표 도달)을 명확히. 종료 없이 학습하면 정책이 이상해진다.

## Isaac ROS (실기 온보드)

Jetson 에서 ROS 2 노드를 GPU 로 가속한다. 대표 GEM:
- **Visual SLAM** (cuVSLAM) — 스테레오/RGB-D 기반 VIO/SLAM
- **nvblox** — 실시간 3D 재구성 + 코스트맵 연동
- **DNN Inference** — TensorRT/Triton 기반 추론 노드
- **AprilTag**, **Stereo Depth**, **Image Pipeline** 가속판

**주의:**
- Isaac ROS 는 **Jetson 또는 x86+dGPU** 를 전제한다. 일반 CPU 환경에서는 이점이 없다.
- 노드 간 데이터 전달에서 GPU↔CPU 복사가 발생하면 가속 효과가 사라진다.
  NITROS(type adaptation/negotiation)로 GPU 메모리를 유지하는 경로를 쓴다.
  **파이프라인 중간에 일반 ROS 노드를 하나 끼우면 그 지점에서 복사가 강제된다.**
- 버전 호환(JetPack ↔ Isaac ROS ↔ ROS 2 distro)이 까다롭다. 조합표를 먼저 확인하고 시작한다.

## 배포

- 학습(Isaac Lab) → 정책 export(ONNX/TorchScript) → **TensorRT 변환** → Jetson(Orin/Thor) 배포.
- Jetson 에서는 전력 모드(`nvpmodel`)와 클럭(`jetson_clocks`)이 성능을 크게 바꾼다.
  벤치마크 전에 고정한다. 안 하면 측정값이 재현되지 않는다.
- 추론 지연을 **끝단에서** 측정한다. 모델 forward 시간만 재면 전처리/복사/후처리를 놓친다.
- 열 제약을 확인한다. 장시간 구동 시 thermal throttling 으로 성능이 떨어진다 —
  5분 벤치마크는 현장 성능을 대표하지 않는다.

## 선택 가이드

- **인지 모델 학습용 데이터가 부족하다** → Isaac Sim + Replicator (합성 데이터)
- **보행/조작 정책을 RL 로 학습한다** → Isaac Lab
- **온보드 인지가 CPU 로는 안 된다** → Isaac ROS + Jetson
- **ROS 2 스택 전체를 시뮬로 검증한다** → Isaac Sim (또는 더 가벼운 Gazebo)
- **접촉 역학 위주 학습만 필요하다** → MuJoCo/MJX 가 더 가볍고 빠를 수 있다
