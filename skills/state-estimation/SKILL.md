---
name: state-estimation
description: >
  로봇 상태추정·로컬라이제이션·센서 융합. TRIGGER when the user fuses odometry/IMU/GPS/LiDAR with
  an EKF/UKF/ESKF or particle filter, configures robot_localization, tunes AMCL or Monte Carlo
  localization, handles covariance and noise models, implements dead reckoning, does map-based
  localization or global relocalization (kidnapped robot), or debugs "the pose jumps / covariance
  explodes / the robot thinks it is somewhere else" problems.
---

# 상태추정 · 로컬라이제이션

SLAM 이 지도를 만드는 것이라면, 로컬라이제이션은 **주어진 지도 안에서 내가 어디인지**를 푸는 것이다.
운영 중인 로봇은 대부분 후자다.

## 필터 선택

| 상황 | 필터 |
|---|---|
| 근사적으로 선형, 단봉 분포 | **EKF** (가장 흔한 선택) |
| 강한 비선형 (자세 추정, 3D 회전) | UKF 또는 **ESKF**(error-state KF) |
| 다봉 분포, 전역 재측위 필요 | **파티클 필터** (AMCL/MCL) |
| 지연·비동기 측정이 많음 | 팩터 그래프 (고정 랙 스무딩) |

- 3D 자세를 다룰 때는 **ESKF** 를 권장한다. 쿼터니언을 상태에 직접 넣으면
  정규화·공분산 처리가 지저분해진다. 오차 상태로 다루면 깔끔하다.
- 파티클 필터는 전역 재측위가 가능한 대신 고차원에서 파티클 수가 폭증한다.
  2D 평면 이동(x, y, θ)까지가 실용 한계다.

## 공분산 — 여기서 대부분 실패한다

- **공분산은 튜닝 노브가 아니라 센서의 물리적 특성이다.**
  값을 아무렇게나 넣고 "잘 되게" 맞추면 다른 환경에서 무너진다.
- 프로세스 노이즈 Q: 모델이 얼마나 틀릴 수 있는가. 크면 필터가 측정을 더 믿는다.
- 측정 노이즈 R: 센서가 얼마나 부정확한가. 스펙시트 + 실측(정지 상태 분산)으로 정한다.
- IMU 는 Allan variance 로 바이어스 불안정성과 랜덤워크를 구한다 (`robot-calibration` 스킬).
- **메시지의 covariance 필드를 채운다.** 많은 드라이버가 0 또는 −1 로 둔다.
  0 은 "완벽히 정확"을 의미하므로 필터가 그 측정만 믿고 발산한다.
  `robot_localization` 은 이 값을 실제로 사용한다.

진단: **NIS/NEES 일관성 검사**를 한다. 정규화된 혁신(innovation)의 통계가
카이제곱 분포 범위를 벗어나면 노이즈 모델이 틀린 것이다. 눈으로 궤적만 보지 않는다.

## robot_localization 사용 시

- 두 개의 인스턴스를 쓰는 것이 표준 구성이다:
  - **연속(local)**: `odom → base_link`. 휠+IMU. 점프 없음, 드리프트 있음. 제어에 사용.
  - **전역(global)**: `map → odom`. + GPS/SLAM. 점프 가능, 드리프트 없음. 계획에 사용.
- **제어 루프는 절대 `map` 프레임을 직접 쓰면 안 된다.** 로컬라이제이션 보정이 들어올 때
  자세가 순간 이동하고, 그러면 컨트롤러가 급격한 명령을 낸다.
- `_config` 행렬(어떤 센서의 어떤 상태를 쓸지)을 신중히 설정한다.
  같은 정보를 두 센서에서 중복으로 넣으면 필터가 과신(overconfident)한다.
  예: 휠 오도메트리의 yaw 와 IMU 의 yaw 를 둘 다 넣으면 안 되는 경우가 많다.
- `two_d_mode: true` 를 평면 로봇에서 켜면 z/roll/pitch 드리프트를 없앨 수 있다.
- `differential` 과 `relative` 옵션의 의미를 정확히 이해하고 쓴다. 잘못 쓰면 조용히 틀린다.

## AMCL / 파티클 필터 튜닝

- **초기 자세가 중요하다.** 초기 추정이 크게 틀리면 수렴하지 않는다.
  RViz `2D Pose Estimate` 또는 초기 자세 서비스로 명시적으로 준다.
- 파티클 수: `min_particles`/`max_particles`. 적으면 수렴 실패, 많으면 CPU 부담.
  KLD 샘플링이 자동 조절한다.
- 모션 모델 노이즈(`alpha1~alpha5`)는 로봇의 실제 주행 오차 특성이다.
  차동구동은 `odom_model_type: diff-corrected` 를 쓴다.
- 갱신 임계(`update_min_d`, `update_min_a`)를 너무 크게 잡으면 갱신이 드물어 드리프트한다.
- **납치 로봇(kidnapped)** 대응: `recovery_alpha_slow/fast` 로 무작위 파티클 주입.
  기본값 0 이면 재측위가 절대 안 된다. 현장 로봇이면 반드시 설정한다.
- 레이저 모델: `likelihood_field` 가 일반적으로 빠르고 안정적. `beam` 은 느리지만
  좁은 공간에서 더 정확할 수 있다.

## 시간과 프레임 — 조용한 실패의 주범

- 모든 측정에 **취득 시각** 타임스탬프가 있어야 한다. 필터는 시간 순서대로 융합해야 한다.
- 지연된 측정(예: 늦게 도착한 GPS)을 그냥 현재 시각으로 넣으면 필터가 왜곡된다.
  지연 보상이 필요하면 버퍼를 두고 과거 시점에 적용 후 재전파한다.
- REP-105 프레임 규약을 지킨다: `map → odom → base_link`.
  **한 프레임을 두 노드가 동시에 발행하면** TF 가 진동한다. 발행자는 항상 하나여야 한다.
- `use_sim_time` 불일치는 모든 것을 깨뜨린다. 시뮬레이션 시 전 노드에 일관되게 적용한다.

## 증상 → 원인

| 증상 | 원인 |
|---|---|
| 자세가 순간 이동 | 정상 동작일 수 있음(map→odom 보정). 제어가 map 을 직접 쓰는지 확인 |
| 공분산이 계속 커짐 | 측정이 반영되지 않음 — 토픽 이름/프레임/타임스탬프 확인 |
| 공분산이 비현실적으로 작음 | 중복 정보 융합 또는 covariance 필드 0 |
| 필터 발산 | R 이 0 이거나 이상치 미제거. 마할라노비스 거리로 이상치 기각 추가 |
| 회전 시에만 오차 급증 | IMU-베이스 외부 파라미터 회전, 또는 각속도 부호 |
| 정지 중인데 위치가 흐름 | IMU 바이어스 미추정, 정지 감지(ZUPT) 미적용 |
| 재측위가 안 됨 | AMCL recovery_alpha 미설정, 또는 초기 자세 미제공 |
| 실외에서 갑자기 튐 | GPS 멀티패스 — GPS 품질(fix type, HDOP)로 게이팅 필요 |

## 설계 권고

- **이상치 기각을 필수로 넣는다.** 마할라노비스 거리 임계로 걷어낸다.
  한 번의 이상 측정이 필터 전체를 망친다.
- 상태 추정의 **건강 상태를 발행**한다: 공분산 트레이스, 혁신 크기, 사용된 센서 목록.
  이게 없으면 현장에서 "로봇이 이상하다" 이상의 진단이 불가능하다.
- 로컬라이제이션 신뢰도가 임계 이하로 떨어지면 **자율 주행을 중단**하는 정책을 명시한다.
  위치를 모르는 채로 계속 움직이는 것이 가장 위험하다.
- 정지 시 ZUPT(zero velocity update)를 적용하면 드리프트가 크게 준다.
