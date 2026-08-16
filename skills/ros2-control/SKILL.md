---
name: ros2-control
description: >
  ros2_control 로 하드웨어를 제어. TRIGGER when the user implements a hardware interface
  (SystemInterface/ActuatorInterface/SensorInterface), configures a controller (joint_trajectory,
  diff_drive, effort/velocity/position, admittance), edits controller_manager YAML, writes
  ros2_control URDF tags, or debugs controller loading and the real-time loop.
---

# ros2_control

`references/` 상세:

| 하려는 일 | 파일 |
|---|---|
| 전체 아키텍처 (resource manager, controller manager, 실행 흐름) | `references/architecture.md` |
| 기성 컨트롤러 목록과 파라미터 | `references/controllers-reference.md` |
| 하드웨어 인터페이스 구현 (read/write, export_state/command_interfaces) | `references/hardware-interface.md` |
| 커스텀 컨트롤러 작성 | `references/writing-controllers.md` |
| 공식 데모 구조 참고 | `references/demos.md` |

## 실행 모델 — 이걸 모르면 전부 틀린다

```
controller_manager (실시간 루프, update_rate Hz)
  ├─ read()    ← 하드웨어에서 상태 읽기
  ├─ update()  ← 활성 컨트롤러들 계산
  └─ write()   → 하드웨어로 명령 쓰기
```

이 세 함수는 **같은 스레드에서 주기적으로** 불린다. 여기서의 규칙:

- **할당하지 않는다.** `new`, `std::vector::push_back`, `std::string` 조합, 로그 문자열 포매팅 전부 금지.
  버퍼는 `on_configure()` 에서 미리 잡는다.
- **막지 않는다.** 뮤텍스 경합, 파일 I/O, 네트워크, 서비스 호출 금지.
  ROS 통신이 필요하면 `realtime_tools::RealtimeBuffer` / `RealtimePublisher` 를 쓴다.
- **로그를 남기지 않는다.** 루프 안 `RCLCPP_INFO` 는 지터의 주범이다.
  꼭 필요하면 `RCLCPP_*_THROTTLE` 또는 카운터 후 루프 밖에서.
- `read()` 가 실패하면 `return hardware_interface::return_type::ERROR` — 조용히 이전 값을 쓰지 않는다.
  stale 데이터로 제어를 계속하는 것이 가장 위험한 실패 모드다.

## 수명주기

하드웨어와 컨트롤러 모두 lifecycle 을 따른다.

```
unconfigured → (on_configure) → inactive → (on_activate) → active
                                    ↑                          ↓
                                    └──── (on_deactivate) ─────┘
```

- `on_configure`: 자원 할당, 파라미터 읽기, 통신 연결 — **여기서 실패하게 만든다.**
- `on_activate`: 명령 버퍼를 **현재 상태로 초기화**한다. 이걸 빼면 활성화 순간 로봇이 튄다.
  (가장 흔하고 가장 위험한 버그)
- `on_deactivate`: 안전한 값으로 명령을 정리한다. 속도 컨트롤러면 0.

## 인터페이스 이름 규칙

`<joint_name>/<interface_type>` — 예: `joint1/position`, `joint1/velocity`, `joint1/effort`.
URDF 의 `<ros2_control>` 블록, 하드웨어의 `export_*_interfaces()`, 컨트롤러 YAML의
`joints:` 가 **세 곳 모두 일치**해야 한다. 하나라도 다르면 컨트롤러가 활성화되지 않는다.

## 컨트롤러가 안 뜰 때 순서대로 확인

1. `ros2 control list_hardware_interfaces` — 인터페이스가 export 됐는가, claim 됐는가
2. `ros2 control list_controllers` — 상태가 `unconfigured`/`inactive`/`active` 중 무엇인가
3. 컨트롤러 YAML 의 `type:` 이 pluginlib 에 등록된 이름과 정확히 같은가 (`plugin.xml` 확인)
4. `joints:` 목록이 URDF 의 joint 이름과 철자까지 같은가
5. 두 컨트롤러가 **같은 command interface 를 동시에 claim** 하려 하지 않는가 — 이건 항상 실패한다

## 하드웨어 연동 시 주의

- 통신 주기와 `update_rate` 를 맞춘다. EtherCAT/CAN 주기보다 빠른 update_rate 는 의미가 없다.
- 엔코더 → 관절각 변환의 **부호와 기어비**를 초기에 검증한다. 부호 하나가 뒤집히면
  제어기는 정상인데 로봇이 발산한다. 무부하 상태에서 손으로 돌려보며 확인한다.
- 안전 정지는 컨트롤러가 아니라 **하드웨어 레벨**에도 있어야 한다.
  소프트웨어가 죽으면 `write()` 가 안 불린다 — 그때 로봇이 마지막 명령을 유지하는지
  정지하는지가 드라이버 설정에 달려 있다. 반드시 확인한다.
