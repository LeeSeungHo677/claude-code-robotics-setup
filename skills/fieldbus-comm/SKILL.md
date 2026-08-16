---
name: fieldbus-comm
description: >
  로봇 하드웨어 계층의 실시간 통신. TRIGGER when the user works with EtherCAT (SOEM/IgH, PDO/SDO,
  DC sync), CANopen or CAN FD, Modbus RTU/TCP, RS-485/serial device drivers, PROFINET, SPI/I2C
  sensors, PTP/gPTP time synchronization, or debugs "the drive drops out / CAN bus errors / cycle
  time is unstable / device does not enter operational state" problems. ROS 2/DDS 레벨 통신은
  ros2-engineering 스킬을 본다.
---

# 필드버스 · 하드웨어 통신

ROS 2/DDS 위가 아니라 **아래쪽 통신**을 다룬다.
여기의 실패는 조용하고 간헐적이라 진단이 어렵다 — 계측을 먼저 갖춰야 한다.

## 선택

| 프로토콜 | 특징 | 적합 |
|---|---|---|
| **EtherCAT** | 마이크로초급 주기, 분산 클럭 동기, 이더넷 물리계층 | 다축 서보, 고성능 모션 제어 |
| **CANopen / CAN FD** | 견고, 배선 단순, 대역폭 낮음 | 모바일 로봇 구동계, 센서, 배터리 |
| **Modbus RTU/TCP** | 단순, 느림, 광범위 지원 | PLC, 산업용 주변기기, 상태 폴링 |
| **PROFINET** | 산업 표준, 공장 인프라와 통합 | 기존 공장 라인 연동 |
| **RS-485/serial** | 가장 단순, 벤더 독자 프로토콜 | 저가 센서, 그리퍼 |
| **SPI/I2C** | 보드 내부, 짧은 거리 | IMU, 소형 센서 |

## EtherCAT

- 마스터 스택: **SOEM**(경량, 사용자공간) 또는 **IgH EtherCAT Master**(커널, 고성능).
  ros2_control 하드웨어 인터페이스로 감싸 쓴다 (`ros2-control` 스킬).
- **PDO** = 주기적 프로세스 데이터(실시간), **SDO** = 비주기 설정 데이터.
  **SDO 를 실시간 루프에서 호출하지 않는다.** 지연이 불규칙하고 주기를 깬다. 설정은 초기화 때.
- **상태 머신**: INIT → PRE-OP → SAFE-OP → OP. 슬레이브가 OP 로 안 가면
  대개 PDO 매핑 불일치 또는 워킹 카운터 오류다. 어느 슬레이브에서 멈췄는지부터 확인한다.
- **DC(Distributed Clock) 동기**를 쓰면 축 간 동기 오차가 크게 준다. 다축 보간에 필수.
- 마스터 주기는 **RT 스레드**에서 돌린다. 일반 스레드로 1 kHz 를 안정적으로 못 친다
  (`robot-perf-optimization` 스킬의 CPU 격리 참고).
- 워킹 카운터(WKC)를 매 사이클 확인한다. 기대값과 다르면 슬레이브가 응답하지 않은 것이다.
  이걸 무시하면 **명령이 안 갔는데 갔다고 믿는** 상태가 된다.

## CAN / CANopen

- 비트레이트와 종단 저항(120Ω × 2)을 먼저 확인한다. **버스 문제의 다수가 물리계층**이다.
- 버스 부하율을 계산한다. 60~70% 를 넘으면 지연과 우선순위 역전이 심해진다.
  주기 메시지 수와 주기를 설계 단계에서 계산한다.
- **에러 프레임과 버스 오프**를 모니터링한다. `ip -details -statistics link show can0`.
  에러 카운터가 증가하는 상태를 방치하면 어느 순간 버스 오프로 전체가 멈춘다.
- CANopen: NMT 상태(Pre-operational → Operational), PDO/SDO 구분은 EtherCAT 과 개념이 같다.
  하트비트/노드가드로 노드 생존을 감시한다.
- 리눅스에서는 SocketCAN 을 쓴다. 송신 큐가 차면 블로킹되므로 논블로킹 + 큐 감시가 필요하다.
- CAN FD 는 데이터 필드가 크고 빨라 여유가 생기지만 트랜시버·드라이버 지원을 확인해야 한다.

## Modbus

- RTU(시리얼)는 반이중이라 요청-응답이 순차적이다. **폴링 주기 × 장치 수**가 곧 지연이다.
  장치가 많으면 실시간 제어에 쓰면 안 된다. 상태 감시 용도로 한정한다.
- 레지스터 주소 오프셋(0-based vs 1-based)과 워드 순서(big/little endian, word swap)가
  벤더마다 다르다. **첫 통합 시 반드시 실측으로 확인**한다. 문서만 믿으면 값이 이상하게 나온다.
- 타임아웃과 재시도를 설정하되, 재시도가 무한히 늘어지지 않게 상한을 둔다.

## 시리얼 / 벤더 독자 프로토콜

- 프레이밍(시작바이트, 길이, 체크섬)을 정확히 구현한다. **부분 수신**을 처리해야 한다 —
  `read()` 가 프레임 하나를 통째로 준다고 가정하는 코드는 반드시 깨진다.
- 체크섬을 검증하고 실패한 프레임은 버린다. 조용히 쓰면 이상한 명령이 나간다.
- 재연결 로직을 넣는다. USB 시리얼은 뽑혔다 꽂히면 장치명이 바뀐다 —
  **udev 규칙으로 고정 심볼릭 링크**를 만든다 (`/dev/robot_gripper` 등).
  `/dev/ttyUSB0` 를 코드에 박으면 부팅 순서에 따라 다른 장치를 연다.

## 시간 동기화

- 여러 컴퓨터·장치가 있으면 **PTP(IEEE 1588)** 를 쓴다. NTP 는 ms 급이라 부족하다.
  `ptp4l` + `phc2sys` 로 시스템 클럭과 NIC 하드웨어 클럭을 맞춘다.
- EtherCAT DC 는 버스 내부 동기이고, PTP 는 네트워크 전체 동기다. 목적이 다르다.
- 동기 상태를 모니터링한다. 오프셋이 커지면 센서 융합이 조용히 망가진다
  (`robot-calibration` 스킬의 시간 동기화).

## 진단 — 계측 없이 추측하지 않는다

```bash
# CAN
candump can0 -td              # 타임스탬프 포함 덤프
cansniffer can0               # 변화하는 바이트만 강조
ip -s -d link show can0       # 에러 카운터, 버스 상태

# 시리얼
stty -F /dev/ttyUSB0 -a       # 현재 설정 확인 (보드레이트/패리티)
interceptty / socat           # 통신 내용 스니핑

# EtherCAT
ethercat slaves / ethercat pdos     # IgH
# SOEM 은 WKC, 상태, DC 오프셋을 직접 로깅하도록 코드에 넣는다

# PTP
pmc -u -b 0 'GET TIME_STATUS_NP'    # 오프셋 확인
```

- **주기 지터를 항상 기록**한다. 통신 주기의 표준편차와 최악값이 문제를 가장 먼저 드러낸다.
- 통신 오류 카운터를 ROS `/diagnostics` 로 발행한다. 현장에서 이게 없으면
  "가끔 로봇이 멈춘다" 이상의 진단이 불가능하다.

## 설계 원칙

- **통신 계층과 제어 로직을 분리**한다. 프로토콜 세부가 제어 코드에 스며들면
  장치 교체 시 전부 다시 써야 한다 (`robotics-software-principles` 스킬의 의존성 역전).
- 통신 실패 시 동작을 명시한다: 마지막 명령 유지 / 즉시 정지 / 안전 자세.
  **기본값은 정지**여야 한다.
- 실시간 루프에서 통신이 블로킹되면 안 된다. 별도 스레드 + 논블로킹 버퍼.
- 장치 초기화 순서와 대기 시간을 문서화한다. 전원 인가 후 준비까지 시간이 필요한 장치가 많고,
  이걸 안 지키면 부팅할 때마다 확률적으로 실패한다.
