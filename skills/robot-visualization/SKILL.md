---
name: robot-visualization
description: >
  로봇 시스템을 눈으로 확인하고 진단하는 도구 전반 — RViz2, rqt, PlotJuggler, Foxglove.
  TRIGGER when the user visualizes robot state, debugs TF trees visually, sets up RViz displays
  or custom RViz plugins, uses rqt_graph/rqt_plot/rqt_reconfigure/rqt_console/rqt_tf_tree,
  plots time series from topics or rosbags, builds a Foxglove layout, streams robot data to a
  browser viewer, or asks "why is nothing showing up in RViz".
---

# 로봇 시각화 · 진단 도구

도구별로 잘하는 게 다르다. **문제 유형에 맞는 도구를 고르는 것이 절반이다.**

| 알고 싶은 것 | 도구 |
|---|---|
| 공간 상에서 무슨 일이 일어나는가 (TF, 센서, 경로, 코스트맵) | RViz2 |
| 노드/토픽 연결이 어떻게 돼 있는가 | `rqt_graph` |
| 값이 시간에 따라 어떻게 변하는가 | PlotJuggler (rqt_plot 보다 우월) |
| 파라미터를 실시간으로 바꿔가며 보고 싶다 | `rqt_reconfigure` |
| 로그를 필터링해서 보고 싶다 | `rqt_console` |
| 원격/브라우저에서 보고 싶다, 팀과 공유하고 싶다 | Foxglove |
| 기록된 rosbag 을 나중에 분석 | PlotJuggler 또는 Foxglove (둘 다 bag 직접 읽음) |

## RViz2

### "아무것도 안 보인다" 체크리스트 (순서대로)

1. **Fixed Frame** 이 실제로 존재하는 frame 인가. 기본값 `map` 인데 map 이 없으면 전부 안 보인다.
   → `odom` 이나 `base_link` 로 바꿔본다.
2. **TF 가 연결돼 있는가.** TF 디스플레이를 켠다. 끊긴 트리에서는 센서 데이터가 변환되지 못해 사라진다.
3. **토픽이 실제로 나오는가.** `ros2 topic hz <topic>` — RViz 를 의심하기 전에 데이터부터 확인.
4. **QoS 가 맞는가.** 이게 가장 자주 놓치는 원인이다. 퍼블리셔가 BEST_EFFORT 인데
   RViz 디스플레이가 RELIABLE 이면 **아무 에러 없이 조용히 안 보인다.**
   디스플레이의 Reliability Policy 를 퍼블리셔에 맞춘다.
   맵처럼 한 번만 발행되는 토픽은 Durability 를 `Transient Local` 로.
5. **timestamp 가 미래거나 너무 과거인가.** `use_sim_time` 불일치가 대표적이다.
   시뮬레이션 중이면 RViz 도 `use_sim_time:=true` 여야 한다.
6. **Decay Time / 크기 / 색.** PointCloud2 가 점 크기 0.001 이면 사실상 안 보인다.

### 설정 관리

- `.rviz` 설정 파일을 **패키지에 커밋**하고 launch 에서 `-d $(find-pkg-share pkg)/rviz/x.rviz` 로 연다.
  각자 손으로 디스플레이를 추가하는 팀은 매번 다른 것을 보게 된다.
- 용도별로 나눈다 — `navigation.rviz`, `manipulation.rviz`, `perception.rviz`.
  하나에 전부 넣으면 무거워서 프레임이 떨어지고, 떨어진 프레임을 데이터 문제로 오해한다.

### 성능

- PointCloud2 를 그대로 띄우면 RViz 가 병목이 된다. `voxel_grid` 로 다운샘플한 별도 토픽을 만들어 띄운다.
- 원격 RViz(로봇의 데이터를 개발 PC 에서)는 네트워크를 포화시킨다.
  이때는 Foxglove 나 압축 이미지(`image_transport` compressed)를 쓴다.

## rqt

- `rqt_graph`: 노드/토픽 연결 확인. **Dead sinks / Leaf topics 체크박스를 꺼야** 실제 구조가 보인다.
  이름이 겹치거나 네임스페이스가 잘못 붙은 것을 찾는 데 가장 빠르다.
- `rqt_reconfigure`: 실행 중 파라미터 조정. 단, ROS 2 에서는 노드가 파라미터 콜백을 구현해야
  실제로 반영된다. 값은 바뀌는데 동작이 안 바뀌면 콜백 미구현을 의심한다.
- `rqt_console`: 로그 레벨·노드별 필터링. 현장 이슈 재현 시 `ros2 run rqt_console rqt_console`.
- `rqt_tf_tree`: TF 트리 스냅샷. 정적 확인용. 끊김 추적은 `ros2 run tf2_ros tf2_echo A B` 가 더 정확하다.
- `rqt_plot` 은 가볍지만 기능이 빈약하다 — 실제 분석은 PlotJuggler 를 쓴다.

## PlotJuggler

시계열 분석의 기본 도구. 제어 튜닝·지연 분석에서 가장 많이 쓴다.

- rosbag2 를 직접 열 수 있다. 실시간 스트리밍도 지원(ROS2 Topic Subscriber 플러그인).
- **여러 신호를 같은 축에 겹쳐 보는 것**이 핵심 — 명령값 vs 실측값, 목표 속도 vs 실제 속도.
- 커스텀 수식(Transform)으로 미분·차이·필터를 즉석에서 만들 수 있다.
  예: `/cmd_vel.linear.x` 와 `/odom.twist.twist.linear.x` 의 차이 → 추종 오차.
- 레이아웃을 저장해두면 같은 분석을 반복할 수 있다. 튜닝 세션마다 새로 만들지 않는다.

## Foxglove

- 브라우저/데스크톱에서 동작하고 **원격·팀 공유**에 강하다. 현장 로봇 진단에 적합.
- 연결 방식: `foxglove_bridge`(권장, WebSocket) 또는 MCAP 파일 직접 열기.
- rosbag2 를 MCAP 으로 기록해두면 Foxglove·PlotJuggler 양쪽에서 다 열린다.
  장기 보관 포맷은 MCAP 을 기본으로 잡는 편이 낫다.
- 대시보드를 만들어 두면 비개발자(운영/납품 담당)도 상태를 볼 수 있다.

## 시각화로 디버깅할 때의 원칙

- **보이지 않는 것을 근거로 결론 내리지 않는다.** RViz 에 안 보이는 것은 "데이터가 없다"가 아니라
  대개 "QoS/frame/시간이 안 맞는다" 이다. 위 체크리스트를 먼저 통과시킨다.
- 시각화는 가설을 세우는 도구지 증명하는 도구가 아니다. 수치로 확인한다 —
  `ros2 topic hz`, `ros2 topic delay`, PlotJuggler 의 실제 값.
- 실기에서 본 현상은 **rosbag 으로 기록**한다. 기록되지 않은 현상은 논의할 수 없다.
