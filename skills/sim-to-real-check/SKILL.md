---
name: sim-to-real-check
description: >
  시뮬→실기 이관 검증 — domain randomization 설정 점검, sim-to-real 갭 분석, 실기 투입 전 체크리스트. TRIGGER on
  sim-to-real, 시뮬과 실제가 다름, 도메인 랜덤화, 실기 투입 전 검증.
license: MIT
metadata:
  version: 1.0.0
allowed-tools: Bash, Read, Write
---

# Sim-to-Real Check Skill

## Overview
시뮬레이션 학습 정책을 실제 로봇에 배포하기 전
sim-to-real 갭 검증 및 체크리스트 실행.

## Sim-to-Real 갭 주요 원인
1. 물리 모델 불일치 (마찰, 관성, 댐핑)
2. 센서 노이즈 차이 (카메라, IMU, 힘 센서)
3. 액추에이터 지연 (모터 응답 시간)
4. 환경 조명/배경 차이 (시각 정책)
5. 접촉 모델 불일치 (그리퍼, 발바닥)

## 도메인 랜덤화 설정 (Isaac Lab)

Isaac Lab 에는 `randomization:` 같은 YAML 키가 없다. 랜덤화는 `EventTermCfg`(이벤트 = 언제 무엇을 흔들지),
센서 노이즈는 관측 항목의 `noise=` 로 건다. 아래는 isaac-sim/IsaacLab v3.0.0 (main @2d2efe1)
`isaaclab_tasks/core/velocity/velocity_env_cfg.py` 와 `envs/mdp/events.py` 시그니처 기준이다 —
버전이 다르면 먼저 그 버전의 `events.py` 에서 인자 이름을 확인한다.

```python
from isaaclab.managers import EventTermCfg as EventTerm, ObservationTermCfg as ObsTerm, SceneEntityCfg
from isaaclab.utils.noise import UniformNoiseCfg as Unoise
import isaaclab.envs.mdp as mdp

@configclass
class EventCfg:
    # mode: "startup"(시작 1회) · "reset"(에피소드마다) · "interval"(주기)
    physics_material = EventTerm(func=mdp.randomize_rigid_body_material, mode="startup", params={
        "asset_cfg": SceneEntityCfg("robot", body_names=".*"),
        "static_friction_range": (0.5, 1.5), "dynamic_friction_range": (0.4, 1.2),   # 무차원
        "restitution_range": (0.0, 0.1), "num_buckets": 64})
    base_mass = EventTerm(func=mdp.randomize_rigid_body_mass, mode="startup", params={
        "asset_cfg": SceneEntityCfg("robot", body_names="base"),
        "mass_distribution_params": (0.8, 1.2), "operation": "scale"})              # 배율
    actuator_gains = EventTerm(func=mdp.randomize_actuator_gains, mode="reset", params={
        "asset_cfg": SceneEntityCfg("robot", joint_names=".*"),
        "stiffness_distribution_params": (0.9, 1.1), "damping_distribution_params": (0.8, 1.2),
        "operation": "scale"})
    push_robot = EventTerm(func=mdp.push_by_setting_velocity, mode="interval",
        interval_range_s=(10.0, 15.0),                                              # s
        params={"velocity_range": {"x": (-0.5, 0.5), "y": (-0.5, 0.5)}})            # m/s, 루트 속도에 더함

# 관측 노이즈 — ObservationsCfg 의 PolicyCfg 안에서 (단위 = 그 관측의 단위)
joint_pos = ObsTerm(func=mdp.joint_pos_rel, noise=Unoise(n_min=-0.01, n_max=0.01))   # rad
joint_vel = ObsTerm(func=mdp.joint_vel_rel, noise=Unoise(n_min=-1.5, n_max=1.5))     # rad/s
base_ang_vel = ObsTerm(func=mdp.base_ang_vel, noise=Unoise(n_min=-0.2, n_max=0.2))   # rad/s (IMU)
```

점검할 것: 범위가 **실측**(마찰·질량·게인 식별값, 센서 노이즈 실측 표준편차)을 감싸는가 ·
`push_robot` 이 팔 작업(고정 베이스 매니퓰레이터)에는 해당 없는지 · 액추에이터 **지연**은 이벤트가 아니라
액추에이터 모델(`DelayedPDActuatorCfg` 등) 쪽이다. 보행 RL 세부는 `legged-rl` 스킬.

<!-- 2026-11-21: 이전 YAML(randomization:/observation_noise:/push_robots:)은 Isaac Lab 에 없는 키라 교체. 근거 = 위 두 파일 -->

## 배포 전 체크리스트
1. 시뮬레이션 성공률 > 90% 확인
2. 도메인 랜덤화 설정 검토
3. Policy Server 연결 테스트
4. 로봇 관절 한계값 확인
5. 비상 정지(E-stop) 동작 확인
6. 저속 모드에서 첫 실행
7. 센서 데이터 정상 수신 확인
8. 실제 환경 데이터로 재학습 계획 수립

## 배포 프로세스 (예시)
Isaac Lab 학습
  → 체크리스트 통과
  → Policy Server 배포 (클라우드 또는 온보드)
  → 로봇 연결 (사용 중인 미들웨어)
  → 저속 테스트 실행
  → 성능 데이터 수집
  → 데이터 저장 → 재학습

## 실제 환경 데이터 수집
- 실패 케이스 원인 분석 필수
- 센서 데이터 MQTT → AWS IoT Core → S3
- 수집 데이터로 sim 환경 보정

## Common Workflows
1. 도메인 랜덤화 설정 검토 및 보강
2. 시뮬레이션 성공률 분석
3. 배포 전 체크리스트 실행
4. 실제 로봇 저속 테스트
5. 실패 케이스 분석 및 시뮬 보정

## Gotchas
- 처음 실제 로봇 실행은 반드시 저속 모드
- E-stop 항상 준비된 상태에서 실행
- 시뮬 성공률 90% 이하면 재학습 필요
- 실제 환경 데이터 수집 후 반드시 재학습
- robotics-testing 스킬과 함께 사용 권장

## References
- ~/knowledge/concepts/sim-to-real.md
- ~/knowledge/papers/rl/ — sim-to-real 논문
- 현재 작업 레포 — 로봇별 배포 기록
