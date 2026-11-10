# CAN / CAN FD — 진단과 함정

출처: 『CAN 통신의 이해』(인사이드임베디드) — 내용을 재구성했고 문장은 옮기지 않았다. 괄호는 장 번호.

## 현장 점검 순서 (아래 계층부터)

종단 저항 → 파형 → bitrate·sample point → TEC/REC·상태 → 필터 → DBC 해석. (13장 표)
`CLAUDE.md` 의 "아래 계층부터 배제" 와 같은 순서다. 해석(DBC)부터 의심하지 않는다.

**종단 측정 (모든 전원 OFF, CAN_H–CAN_L)**: ≈60 Ω 정상 · ≈120 Ω 하나 누락 또는 한쪽 단선 ·
≈40 Ω 과잉 · ≈0 Ω 단락 · kΩ 이상 둘 다 누락. 전원이 켜져 있으면 값이 왜곡된다.
split termination(60+60 Ω + 중점 C)도 H–L 로는 120 Ω 으로 보인다 — 정상. (3)

## 증상 → 원인 → 확인

| 증상 | 원인 | 확인 / 조치 | 장 |
|---|---|---|---|
| 노드 하나로 시험하면 같은 프레임이 끝없이 재전송 | **ACK 해 줄 노드가 없음** → error passive 후 멈추지 않고 반복(bus-off 로도 안 감) | 노드를 하나 더 붙이거나 내부 loopback 모드(트랜시버·배선은 검증 안 됨) | 8 |
| 특정 노드가 붙으면 에러 프레임 반복 | bitrate 불일치 또는 **sample point 가 크게 다름** | 전 노드의 bitrate·SP 를 표로 대조 | 9 |
| 같은 ID 를 두 노드가 송신 → 데이터 구간 bit error → bus-off | 중재에서 구분이 안 됨. 데이터가 같으면 결함이 숨는다 | **ID 하나에 송신 노드 하나** | 5 |
| 저우선 메시지가 계속 지연되는데 에러 카운터는 0 | babbling idiot — 고우선 ID 를 쉬지 않고 송신 | 주기·버스 부하 측정, SW 송신 제한 | 8 |
| 버스 전체 정지 | TXD dominant 고착 또는 H/L 단락 — 장애 격리로 못 막음 | TXD dominant timeout 있는 트랜시버 | 1, 8 |
| bus-off 뒤 STM32 FDCAN 이 영영 복귀 안 함 | FDCAN 은 bus-off 시 HW 가 `CCCR.INIT` 을 세트, **SW 가 지워야** 복귀 절차(128×11 열성 비트) 시작. bxCAN 은 ABOM 이면 자동 | 에러 상태 콜백에서 BusOff 확인 → 지연 후 INIT 클리어 | 8, 11 |
| FDCAN 필터를 걸었는데 모든 ID 가 들어옴 (bxCAN 은 반대로 아무것도 안 들어옴) | FDCAN 기본 global filter 는 비매칭 프레임도 FIFO0 에 받음. bxCAN 은 활성 필터 없으면 전부 거부 | `HAL_FDCAN_ConfigGlobalFilter(REJECT, REJECT, REJECT_REMOTE, REJECT_REMOTE)` | 2, 11 |
| 두 번째 필터 ID 가 안 들어옴 | Init 의 `StdFiltersNbr` < 실제 필터 수 (global reject 를 켜야 드러남) | 개수 대조 | 11 |
| FD 수신 후 메모리 깨짐 / 엉뚱한 ID 가 64 B FD 로 나감 | 수신 버퍼 8 B 인데 FD 는 64 B 복사 / static TxHeader 재사용 | `rx[64]`, 메시지별 TxHeader, 수신 시 IdType·DataLength 검사 | 11 |
| 메시지가 조용히 유실 / 급한 ID 가 늦게 나감 | Tx 버퍼 가득 → `AddMessageToTxFifoQ` 가 에러(반환값 무시 시 유실). FIFO 모드는 저장 순서라 우선순위 역전. Rx FIFO 가득 → 새 프레임 손실 | 반환값 검사, Tx **queue** 모드, ISR 에서 fill level 0 까지 비우기 | 11 |
| FD 데이터 구간(고속)에서 송신 노드만 bit error | 트랜시버 루프 지연(최대 수백 ns)이 데이터 SP 보다 김. **디지털 아이솔레이터·레벨시프터가 지연을 더한다** | data > 1 Mbit/s 면 **TDC**(송신 지연 보상) 켜기. STM32 는 DataPrescaler 1 또는 2 여야 함 | 10, 11 |
| FD 버스에서 에러 프레임·재전송 반복 | FD 미지원 클래식 노드·**클래식 USB-CAN 어댑터**가 FD 프레임마다 에러 플래그 | 전 노드 FD 또는 FD-tolerant 확인. 분석용 어댑터는 listen-only | 10, 13 |
| FD 노드끼리도 CRC/form 에러 | ISO CAN FD 와 non-ISO(Bosch 2012) 혼용 | ISO/non-ISO 설정 통일 | 10 |
| FD 2 Mbit/s 에서도 간헐 에러 | 스타 배선·긴 스텁의 반사, 클래식 전용 트랜시버 | 선형 배선·짧은 스텁, FD(또는 SIC) 정격 트랜시버 | 4, 10 |
| 물리값이 엉뚱함 (예: 36.5 V 가 169.1 V) | DBC 바이트 순서 오류 — **Motorola(@0) start bit 는 MSB 위치** (`16\|16@0` 이 아니라 `23\|16@0`) | DBC 편집기의 비트 배치 그림으로 확인, 송신 ECU 사양과 대조 | 12 |
| 음수 물리값이 이상함 | `+`/`-` 는 raw 의 부호 여부. 오프셋으로 만든 음수(−40 °C 등)는 `+` 가 맞다. 확장 ID 는 DBC 에서 값+0x80000000 | `SG_` 의 `@n±` 와 `(factor,offset)` 검토 | 12 |
| 수신 노드가 꺼졌는데 송신 측은 정상(ACK OK) | **ACK 는 누가 받았는지 알려주지 않는다** — 필터로 버리는 노드도 ACK | 수신 측에서 주기 메시지 timeout 감시. 안전 신호는 alive counter + CRC(E2E) | 7, 13 |

## 수치 규칙 (책 기준)

- Sample point 75–87.5 %, 자동차 ≈80 %. CiA 301: ≤500k 87.5 %, 800k 80 %, 1M 75 %. J1939 87.5 %.
  SJW 는 두 phase segment 어느 쪽보다도 길 수 없다. 공칭·데이터 구간에 같은 tq 권장. (9, 10)
- 길이 경험칙: 1M ≈ 40 m(CiA 301 은 25 m), 500k ≈ 100 m, 125k ≈ 500 m. FD 2 Mbit/s 는 버스 전체 수 m 수준. (9, 10)
- 에러 카운터: TEC 에러 +8 / 성공 −1. ≥128 error passive, >255 bus-off (연속 실패 시 16회째 passive, 32회째 bus-off).
  복귀 = 11 열성 비트 × 128회, 500k 에서 최소 약 2.8 ms. (8)
- 8 B 표준 프레임 108 bit, **스터핑 포함 최악 135 bit**(500k 에서 270 µs), 확장 최악 160 bit.
  **버스 부하는 최악 길이로 계산한다.** (7, 13)
- FD: 데이터 64 B 에서 이득 5배 이상이지만 8 B 에서는 약 2배 — 약 30 bit 는 항상 공칭 속도라
  8 B 를 5 Mbit/s 로 올려도 108→79 µs 정도. 작은 메시지를 FD 로 바꾸는 이득은 작다. (10)
- 같은 기본 ID 면 표준 > 확장, 데이터 > 리모트. **선점 없음** — 최고 우선순위도 전송 중인 가장 긴 프레임만큼 기다린다. (5, 6)

## Linux / SocketCAN 메모 (13장)

- vcan 에서 FD 를 시험하려면 `ip link set vcan0 mtu 72`.
- `cansend` 의 `##` 는 FD 프레임, 그 뒤 플래그 1 은 BRS. (`cansend` 는 실 버스에 나가므로 `dangerous-command-guard` 가 ask 로 막는다)
- cantools `decode_message` 는 DBC 에 없는 ID 에서 KeyError — 수신 루프에서 예외 처리.
- python-can `send_periodic` 에 `modifier_callback` 을 주면 커널 BCM 대신 **스레드 송신**으로 바뀌어 지터가 커진다.

## 상위 프로토콜 ID 계산 (14장)

- CANopen predefined connection set: 11 bit ID = 4 bit function code + 7 bit node ID (예: TPDO1 = 0x180 + node, SDO 응답 = 0x580 + node, heartbeat = 0x700 + node).
- J1939: 29 bit = 우선순위(3) / PGN / 송신 주소. PF < 240 이면 PS 가 목적지 주소.
