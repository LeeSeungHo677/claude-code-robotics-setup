---
name: vda5050
description: >
  VDA5050 — AGV/AMR 플릿과 상위 관제 간 표준 통신 프로토콜. TRIGGER when the user integrates robots with a fleet
  manager over VDA5050, implements order/state/visualization/connection/instantAction/factsheet
  topics, works with its MQTT topic structure, maps VDA5050 nodes·edges·actions to Nav2 goals, or
  builds a VDA5050 adapter for customer compliance.
---

# VDA5050

현장 납품에서 상위 관제 시스템(WMS/MES/FMS)과 로봇을 붙일 때 요구되는 표준.
"우리 로봇 프로토콜"로 붙이면 통합 비용이 매번 새로 발생한다. 규격을 따르면 관제 교체가 가능해진다.

| 하려는 일 | 파일 |
|---|---|
| 프로토콜 개요, MQTT 토픽 구조, 상태 머신 | `references/protocol.md` |
| 메시지 스키마 전체 (order, state, connection, visualization, instantActions, factsheet) | `references/messages.md` |
| 구현 포맷·직렬화 세부 | `references/formats.md` |
| ROS 2 연동 커넥터 구현 | `references/integration.md` |

## 핵심 개념

- **Order**: 관제 → 로봇. `nodes` + `edges` 로 된 그래프. 각 노드/엣지에 `actions` 가 붙는다.
- **State**: 로봇 → 관제. 주기 발행 + 변화 시 즉시 발행. 여기가 관제의 유일한 진실 소스다.
- **InstantActions**: 순서를 무시하고 즉시 실행 (정지, 일시정지, 픽업 취소 등).
- **Connection**: MQTT Last-Will 로 로봇 연결 끊김을 관제가 즉시 감지하게 한다.
- **Factsheet**: 로봇의 능력·치수·속도 한계 선언. 관제가 작업 배정에 사용한다.

## 통합 시 자주 터지는 것

| 문제 | 원인 |
|---|---|
| 관제가 로봇을 죽은 것으로 판단 | Connection 토픽 Last-Will/retain 설정 누락 |
| 오더가 중복 실행됨 | `orderId`/`orderUpdateId` 비교 로직 오류 — 갱신과 신규를 구분해야 한다 |
| 로봇이 엉뚱한 곳으로 감 | 노드 좌표계와 로봇 map frame 불일치. `mapId` 와 TF 를 명시적으로 매핑한다 |
| 상태가 튐 | State 를 주기 발행만 하고 변화 시 즉시 발행을 안 함 |
| 액션이 끝나도 관제가 모름 | `actionStates` 를 `FINISHED` 로 갱신 안 함 |
| 버전 불일치 | `version` 필드를 관제와 사전 합의하지 않음 — 2.x 와 1.x 는 호환되지 않는다 |

## 설계 권고

- VDA5050 커넥터는 **별도 노드**로 분리한다. 주행 스택 안에 프로토콜을 섞지 않는다.
  관제 규격이 바뀔 때 주행 스택을 건드리지 않아도 되게 만드는 것이 목적이다.
- 노드/엣지 → Nav2 goal 변환은 한 곳에만 둔다. 이 변환이 흩어지면 좌표 버그를 추적할 수 없다.
- 관제와 붙이기 전에 **MQTT 브로커 + 모의 관제**로 전 시나리오를 통과시킨다.
  현장에서 처음 붙이면 납품 일정이 무너진다.
- 모든 수신 오더와 발신 상태를 로깅한다. 관제 벤더와의 책임 소재 분쟁은 로그로만 해결된다.
