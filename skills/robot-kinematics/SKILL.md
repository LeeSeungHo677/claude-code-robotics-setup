---
name: robot-kinematics
description: >
  로봇 기구학·동역학 계산. TRIGGER when the user computes forward/inverse kinematics, Jacobians, inverse
  dynamics (RNEA/ABA/CRBA), uses Pinocchio/KDL/RBDL, handles singularities and null-space
  redundancy, computes collision distance (FCL), works on floating-base humanoid/quadruped
  centroidal dynamics — or hits 'IK has no solution / arm behaves oddly near this pose'.
---

# 기구학 · 동역학

## 라이브러리 선택

| | Pinocchio | KDL (orocos) | RBDL |
|---|---|---|---|
| 속도 | 매우 빠름 (C++ 템플릿, 해석적 미분) | 보통 | 빠름 |
| 자동미분 | 지원 (CasADi/CppAD 연동) | 없음 | 제한적 |
| 부동베이스 | 1급 지원 (휴머노이드/사족) | 약함 | 지원 |
| ROS 통합 | `pinocchio` + urdf 파서 | MoveIt 기본 | 별도 |
| 추천 | **최적화·MPC·학습·부동베이스** | 단순 팔 FK/IK, MoveIt 안에서 | 레거시 |

새로 짜는 코드라면 **Pinocchio 를 기본**으로 본다. 특히 최적화 기반 제어(MPC, WBC),
강화학습 환경, 휴머노이드/사족처럼 부동베이스가 있는 경우 사실상 표준이다.

## Pinocchio 사용 패턴

```python
import pinocchio as pin
import numpy as np

model = pin.buildModelFromUrdf("robot.urdf")          # 고정베이스
# 부동베이스(휴머노이드/사족)는 반드시 JointModelFreeFlyer 를 붙인다
# model = pin.buildModelFromUrdf("robot.urdf", pin.JointModelFreeFlyer())
data = model.createData()

q = pin.neutral(model)                                 # 설정 벡터
pin.forwardKinematics(model, data, q)                  # FK
pin.updateFramePlacements(model, data)                 # frame 자세 갱신 (이걸 빼면 stale)

frame_id = model.getFrameId("tool0")
oMf = data.oMf[frame_id]                               # world → tool0 (SE3)

J = pin.computeFrameJacobian(model, data, q, frame_id,
                             pin.ReferenceFrame.LOCAL_WORLD_ALIGNED)
```

**함정:**
- `forwardKinematics` 만 부르고 `updateFramePlacements` 를 안 부르면 `data.oMf` 가 갱신되지 않는다.
  가장 흔한 버그.
- Jacobian 의 **기준 프레임**을 명시한다. `LOCAL`, `WORLD`, `LOCAL_WORLD_ALIGNED` 는 전부 다르다.
  속도 명령이 이상하면 여기부터 본다.
- 부동베이스에서 `q` 의 앞 7개는 위치(3) + 쿼터니언(4) 이다. `nq != nv` 이므로
  `q` 와 `v` 의 차원이 다르다. 이걸 혼동하면 조용히 틀린 결과가 나온다.
  설정 공간 연산은 `pin.integrate` / `pin.difference` 를 쓴다. 단순 덧셈이 아니다.

## 동역학

```
M(q) v̇ + C(q,v) v + g(q) = τ + Jᵀ f
```

| 필요한 것 | 함수 |
|---|---|
| 역동역학 (궤적 → 토크) | `pin.rnea(model, data, q, v, a)` |
| 순동역학 (토크 → 가속도) | `pin.aba(model, data, q, v, tau)` |
| 질량행렬 M | `pin.crba(model, data, q)` (상삼각만 채움 — 대칭 복사 필요) |
| 중력 보상 g(q) | `pin.computeGeneralizedGravity(model, data, q)` |
| 중심 동역학 (CoM, 각운동량) | `pin.ccrba`, `pin.centerOfMass` |

- **URDF 의 관성 파라미터가 엉터리면 동역학은 전부 무의미하다.** 많은 URDF 가
  질량은 대충, 관성 텐서는 단위 행렬로 채워져 있다. 동역학 기반 제어를 하기 전에
  `pin.computeTotalMass` 와 각 링크 관성을 실물과 대조한다.
- 관성 텐서는 **양의 정부호**여야 하고 삼각 부등식을 만족해야 한다. 검증 코드를 넣는다.

## 역기구학 (IK)

### 수치적 IK (권장)
자코비안 기반 반복. 여유자유도(7축 이상)나 부동베이스에서는 사실상 유일한 선택.

```
while not converged:
    err = log6(oMf.actInv(oMdes))     # SE3 오차 → 6D twist
    J   = frame_jacobian(q, frame)
    dq  = J⁺ · err                     # 유사역행렬 (damped least squares 권장)
    q   = integrate(q, α·dq)
```

- **Damped least squares (Levenberg-Marquardt)** 를 쓴다. 순수 유사역행렬은 특이점 근처에서 발산한다.
  `J⁺ = Jᵀ(JJᵀ + λ²I)⁻¹`, λ 를 조건수에 따라 조절.
- 관절 한계를 매 반복 clamp 하고, 수렴 실패 시 **명확히 실패로 반환**한다.
  적당히 근접한 해를 성공으로 반환하면 상위에서 충돌이 난다.
- 초기값이 결과를 지배한다. 현재 자세에서 시작하면 연속적인 해를 얻는다.
  랜덤 재시작은 궤적이 튄다.

### 해석적 IK
6축 산업용 팔처럼 구조가 정해져 있으면 해석해가 있다 (IKFast). 빠르고 **모든 해**를 준다.
여러 해 중 현재 자세와 가장 가까운 것을 고르는 로직이 반드시 필요하다.

### "IK 해가 없다" 진단
1. 목표가 작업공간 밖인가 — 도달 거리를 먼저 계산해본다.
2. 방향(orientation)까지 요구했는가 — 위치만 필요하면 자유도를 풀어준다.
3. 관절 한계에 걸렸는가.
4. 특이점 근처인가.
5. 목표 frame 이 맞는가 — `tool0` 인지 `flange` 인지 `tcp` 인지. **가장 흔한 원인.**

## 특이점 · 여유자유도

- 특이점 판정은 자코비안의 **최소 특이값** 또는 조건수로 한다.
  `manipulability = sqrt(det(J Jᵀ))` 가 0 에 가까우면 특이점.
- 특이점 근처에서는 작은 작업공간 속도가 거대한 관절 속도를 요구한다.
  관절 속도 상한을 걸고, 초과하면 **감속하거나 정지**한다. 그냥 보내면 하드웨어가 상한다.
- 여유자유도(7축+)는 null-space 로 부가 목적을 넣는다:
  `dq = J⁺·v + (I - J⁺J)·dq_null` — 관절 한계 회피, 자세 유지, 장애물 회피 등.

## 충돌 계산

- Pinocchio + **HPP-FCL(coal)** 로 거리·충돌 질의. `pin.computeCollisions`, `pin.computeDistances`.
- 충돌 모델은 시각 모델과 **분리**한다. 시각용 메시를 충돌에 그대로 쓰면 느리고 불안정하다.
  볼록 분해(convex decomposition)하거나 단순 도형(캡슐/구/박스)으로 근사한다.
- **자기 충돌(self-collision)** 페어를 명시적으로 관리한다. 인접 링크는 항상 닿아 있으므로
  SRDF 의 `disable_collisions` 로 제외한다. 안 하면 항상 충돌 상태가 된다.
- 안전 여유(margin)를 둔다. 거리 0 을 기준으로 계획하면 실제로는 스친다.

## 단위와 규약 — 틀리면 전부 틀린다

- 각도는 **라디안**. URDF, Pinocchio, ROS 메시지 전부 rad. degree 를 섞는 순간 끝난다.
- 쿼터니언 순서: ROS 메시지는 `(x, y, z, w)`, Eigen 생성자는 `Quaterniond(w, x, y, z)`.
  **순서가 다르다.** 여기서 나는 버그는 "가끔 이상하다" 로 나타나 추적이 어렵다.
- 회전 표현 변환(RPY ↔ 쿼터니언 ↔ 행렬)은 한 유틸리티에 모아두고 그것만 쓴다.
- SE3 보간은 선형 보간이 아니다. `pin.SE3.Interpolate` 또는 exp/log 를 쓴다.
