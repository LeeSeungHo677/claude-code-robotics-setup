<!-- 로컬 추가 파일 (2026-11-21) — 업스트림 dbwls99706/ros2-engineering-skills 에 없음. 재동기화 때 지우지 말 것.
     근거: 업스트림 v1.8.1 references/engineering-principles.md 「Distro-specific migration notes」,
     hardware-interface.md·navigation.md·simulation.md·workspace-build.md 의 배포판 비교표. 아래는 그 요약 + 순서. -->

# Humble → Jazzy / Lyrical 이관 점검표

이 세팅의 워크스페이스는 대부분 **Humble**(Ubuntu 22.04, EOL 2027-05)이다. 이관 대상은 두 가지다.

| 목표 | 언제 | 비고 |
|---|---|---|
| **Jazzy** (Ubuntu 24.04, EOL 2029-05) | 로봇 PC 가 24.04 이거나, 벤더 로봇 SDK 가 Jazzy 까지만 지원할 때 | 한 단계. 가장 흔한 경로 |
| **Lyrical** (Ubuntu 26.04, EOL 2031-05) | 새 프로젝트, OS 를 새로 깔 수 있을 때 | Humble 에서 **LTS 두 단계** — 아래 Jazzy 항목 + Kilted·Lyrical 항목 전부 해당 |

**원칙**: 기존 워크스페이스를 "최신 LTS" 로 자동으로 올리지 않는다. 벤더 SDK·드라이버·HAL 이 그 배포판 빌드를
내주는지 **먼저** 확인한다 (설치본 `ros2 pkg xml <pkg>`, `dpkg-query -W 'ros-*'`). 실기 PC 는 시뮬/개발 PC 에서
다 통과한 뒤 마지막에 올린다.

## 순서 (아래 계층부터)

1. **OS·빌드 기반** — Ubuntu 버전, Python 버전(배포판마다 다름 — 설치본에서 `python3 --version`), `rosdep` 키 재해결.
   Docker 이미지·CI·문서의 배포판 이름을 **한 곳에서** 고정한다.
2. **CMake** — Kilted 부터 `ament_target_dependencies()` deprecated → `target_link_libraries(tgt PUBLIC dep::dep)`.
   Jazzy 는 둘 다 되지만 **섞지 않는다**(링크 오류). Lyrical 까지 갈 거면 Jazzy 단계에서 미리 바꾼다.
3. **통신·발견** — `ROS_LOCALHOST_ONLY` → `ROS_AUTOMATIC_DISCOVERY_RANGE`(`LOCALHOST`/`SUBNET`/`OFF`) +
   `ROS_STATIC_PEERS`. 시뮬 격리(domain·localhost)를 이 변수로 다시 설정했는지 확인. 기본 RMW 는 계속 Fast DDS.
   Zenoh(`rmw_zenoh_cpp`)는 Kilted 부터 Tier 1 — 바꾸는 건 별도 결정.
4. **rosbag2** — 기본 저장 형식 sqlite3 → **MCAP**. 녹화 스크립트·importer 가 `.db3` 를 가정하면 깨진다.
   `storage_id` 를 명시하고, 기존 `.db3` 는 변환하지 말고 그대로 읽는 경로를 남긴다 (재수집 비용).
5. **ros2_control** — Humble 2.x → Jazzy 4.x → Kilted 5.x → Lyrical 6.x(설치본 확인).
   - 인터페이스 export 자동 생성 (`<ros2_control>` URDF 태그 기준) — 수동 `export_*_interfaces()` 정리
   - `get_value()` → `get_optional<T>()`, `set_value()` 는 `bool` 반환 — 반환값 무시하면 지령 실패를 놓친다
   - lifecycle `get_state()` → `get_lifecycle_state()`; controller `init()` 인자 형태 변경(Kilted 에서 옛 형태 삭제)
   - Kilted: hardware `on_init(const HardwareComponentInterfaceParams &)`
   - spawner `--param-file`; `<ros2_control>` 의 joint 는 URDF 에 전부 있어야 한다
   - 세부 표: `references/hardware-interface.md` 「ros2_control API: distro comparison」
6. **Nav2·BT** — 커스텀 BT XML 이 BT.CPP v3 문법이면 v4 로 (`behavior-tree` 스킬).
   Kilted+: `enable_stamped_cmd_vel: true`(안 하면 로봇이 cmd_vel 을 못 받는다), `error_code_names` →
   `error_code_name_prefixes`, 플러그인은 `nav2::LifecycleNode`(`nav2_ros_common`)로. 세부: `references/navigation.md`.
7. **시뮬** — Gazebo 짝: Humble=Fortress, Jazzy=Harmonic, Kilted=Ionic, Lyrical 은 설치본 `ros-<distro>-ros-gz-*` 로 확인.
   `ros_gz_bridge` 설정·월드 파일 재검증 (`references/simulation.md`).
8. **실행기·메시지 (Lyrical)** — 비실험 `rclcpp::executors::EventsCBGExecutor` 신설(기존 experimental EventsExecutor 와 별개),
   rclpy `rclpy.experimental.AsyncNode`. C++ `uint8[]` 필드가 `rosidl::Buffer<uint8_t>` — 대부분 암묵 변환으로 되지만
   이미지·포인트클라우드 처리 코드는 빌드·테스트로 확인. Jetson 은 Isaac ROS 릴리스 노트의 JetPack 짝을 먼저 본다.
9. **launch·파라미터** — `launch_ros` 파라미터 처리 변경 → launch 파일 전부 다시 띄워 파라미터 값을 `ros2 param get` 으로 대조.

## 검증 (실기 전)

- 빌드 경고 0 → `colcon test` 통과 → 시뮬에서 기존 시나리오 N회 → **녹화한 bag 을 이전 배포판 결과와 비교**(토픽 목록·주기·QoS).
- 실기 첫 구동은 저속, 사용자가 직접 실행. 하드웨어 인터페이스(ros2_control)가 바뀐 경우 `robot-safety-reviewer` 를 먼저 부른다.
- 무엇을 어떤 순서로 바꿨는지 커밋을 계층별로 나눈다 (한 커밋 = 한 계층).
