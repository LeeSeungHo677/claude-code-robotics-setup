---
name: behavior-tree
description: >
  로봇 작업 제어를 Behavior Tree 로 설계·구현·디버깅. TRIGGER when the user works with BehaviorTree.CPP v4/v3,
  writes BT XML, creates action/condition/decorator/control nodes, uses the blackboard and typed
  ports, integrates with ROS 2 (behaviortree_ros2, BtActionNode), edits the Nav2 behavior tree,
  uses Groot2, or chooses between BT and a state machine.
---

# Behavior Tree

`references/` 상세:

| 하려는 일 | 파일 |
|---|---|
| BT.CPP v4 코어 (노드 계층, NodeStatus, 팩토리, 블랙보드, 스크립팅, 로거) | `references/btcpp-v4-core.md` |
| ROS 2 연동 (BtActionNode, BtServiceNode, 수명주기) | `references/bt-ros2-integration.md` |
| 커스텀 노드 새로 작성 | `references/writing-nodes.md` |
| Nav2 가 제공하는 BT 노드 목록 | `references/nav2-bt-nodes.md` |

## BT 를 쓸지 State Machine 을 쓸지

먼저 이걸 정한다. 잘못 고르면 나중에 전부 다시 쓴다.

| | Behavior Tree | State Machine (SMACH/YASMIN/직접 구현) |
|---|---|---|
| 강점 | 재사용·조합, 실패 시 fallback 이 구조로 표현됨 | 상태가 적고 전이 규칙이 명확할 때 읽기 쉬움 |
| 약점 | "지금 어떤 상태인가" 가 불명확해짐 | 상태 수가 늘면 전이가 폭발함 |
| 적합 | 작업 시퀀스 + 회복 동작이 많은 자율 주행/조작 | 모드 관리(대기/충전/수동/자율), 하드웨어 상태 관리 |

실무에서는 **둘을 계층으로 나눈다** — 상위 모드는 상태기계, 모드 안의 작업 시퀀스는 BT.

## 설계 원칙

- **틱은 논블로킹이다.** 액션 노드의 `tick()` 안에서 절대 기다리지 않는다.
  `RUNNING` 을 반환하고 다음 틱에 진행 상황을 확인한다. `sleep`/동기 서비스 호출은 트리 전체를 멈춘다.
- **상태를 블랙보드에만 둔다.** 노드 멤버 변수에 진행 상태를 숨기면 재사용도 테스트도 불가능해진다.
  포트는 타입을 명시한다 (`InputPort<geometry_msgs::msg::PoseStamped>`).
- **halt() 를 반드시 구현한다.** 상위에서 중단될 때 진행 중이던 액션(모터 명령, 액션 goal)을
  실제로 취소하지 않으면 로봇이 계속 움직인다. 이건 안전 문제다.
- **실패를 삼키지 않는다.** 모든 것을 Fallback 으로 감싸면 트리는 항상 성공하고 문제는 숨겨진다.
  회복이 실패했으면 실패로 올려보낸다.
- **트리 깊이보다 폭을 얕게.** 5단계 넘게 중첩되면 Groot2 로도 읽기 어렵다. 서브트리로 쪼갠다.
- **재시도 횟수와 타임아웃을 명시한다.** `RetryUntilSuccessful` 무한 재시도는 현장에서 로봇을
  그 자리에 영원히 묶어두는 가장 흔한 원인이다.

## 자주 나오는 버그

| 증상 | 원인 |
|---|---|
| 중단해도 로봇이 계속 움직임 | `halt()` 미구현 또는 액션 goal cancel 누락 |
| 트리가 멈춤(hang) | `tick()` 안에서 블로킹 호출 |
| 회복 동작 무한 루프 | Fallback 이 실패를 전부 흡수, 재시도 상한 없음 |
| 포트 값이 안 넘어감 | 블랙보드 키 이름 오타 / 서브트리 remapping 누락 |
| 조건 노드가 항상 참 | 조건 노드에서 부수효과를 냄 — 조건은 순수 조회여야 한다 |
| 재시작 시 이전 상태가 남음 | 블랙보드 초기화 누락 |

## 디버깅

- Groot2 로 실시간 틱을 본다. 어느 노드에서 `RUNNING` 이 고착되는지가 대부분의 답이다.
- `FileLogger` / `StdCoutLogger` 로 틱 전이를 기록해 rosbag 시각과 대조한다.
- 트리를 실기에 붙이기 전에 **가짜 액션 서버로 단위 테스트**한다. BT 로직 버그와
  하드웨어 문제를 동시에 디버깅하지 않는다.
