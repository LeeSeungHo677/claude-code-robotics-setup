---
name: robot-perf-optimization
description: >
  로봇 온보드 CPU·메모리·지연 최적화와 용량 설계. TRIGGER when the user profiles CPU, sets thread
  affinity/isolcpus/cgroups/RT priority, measures latency and jitter, cuts memory allocation in
  hot paths, budgets compute across nodes, handles thermal throttling — or hits '로봇에서만 느리다 / 제어
  주기를 놓친다 / CPU 100% / 데스크톱에선 되는데 로봇에선 안 된다'.
---

# 온보드 성능 · 용량 최적화

로봇의 컴퓨팅은 **고정 예산**이다. 데스크톱처럼 "느리면 더 좋은 CPU" 가 안 된다.
정해진 CPU/전력/열 안에서 마감시간을 지키는 것이 목표다.

## 순서: 측정 → 예산 → 배치 → 최적화

**측정하지 않고 최적화하지 않는다.** 로봇 성능 문제의 절반은 엉뚱한 곳을 고치고 있다.

### 1. 측정

```bash
# 전체 부하와 어느 코어가 포화됐는지
htop            # 코어별 사용률 (평균이 아니라 코어별로 봐야 한다)
pidstat -t 1    # 스레드 단위 CPU
uptime          # load average vs 코어 수

# 지연·지터
cyclictest -m -p 80 -i 1000 -l 100000 -h 400   # RT 커널 지터 측정의 표준
ros2 topic hz /topic --window 1000              # 실제 주기와 표준편차
ros2 topic delay /topic                         # 발행~수신 지연

# 프로파일링
perf top / perf record -g / perf report          # 어느 함수가 먹는지
py-spy top --pid <PID>                           # 파이썬 노드
valgrind --tool=callgrind                        # 정밀하지만 매우 느림

# 메모리
smem / pmap -x <PID>                             # 실제 RSS
```

**중요**: 평균 CPU 사용률은 거의 쓸모없다. 봐야 할 것은
**코어별 사용률**, **최악값(p99)**, **마감시간 초과 횟수**다.
평균 40% 인데 주기적으로 100% 를 치면 제어는 실패한다.

### 2. 예산 배분

노드별로 "이만큼의 CPU 를 쓴다" 를 명시적으로 정한다.

| 계층 | 특성 | 예산 |
|---|---|---|
| 안전·제어 루프 | 마감시간 엄격, 놓치면 사고 | 전용 코어, RT 우선순위 |
| 상태추정·로컬라이제이션 | 마감시간 있음 | 고정 예산 |
| 인지(비전/포인트클라우드) | 무겁고 변동 큼 | 나머지, 제한 필요 |
| 로깅·기록·원격 | 최저 우선순위 | 남는 것만 |

**핵심 원칙: 인지가 제어를 굶기지 않게 한다.** 이것을 보장하는 것이 배치 설계의 목적이다.

### 3. 배치 (CPU 격리)

```bash
# 커널 부팅 파라미터로 코어 격리 (가장 확실한 방법)
isolcpus=2,3 nohz_full=2,3 rcu_nocbs=2,3

# 프로세스/스레드를 특정 코어에 고정
taskset -c 2,3 ros2 run my_pkg control_node
# 코드 내부: pthread_setaffinity_np()

# RT 우선순위 (PREEMPT_RT 커널에서)
chrt -f 80 ./control_node

# 무거운 노드를 cgroup 으로 제한
systemd 서비스에 CPUQuota=200% CPUAffinity=4-7
```

- 격리한 코어에는 **커널 타이머와 IRQ 도 오지 않게** 한다 (`nohz_full`, IRQ affinity).
  안 하면 격리 효과가 반감된다.
- RT 우선순위를 99 로 주지 않는다. 커널 스레드보다 높으면 시스템이 멈출 수 있다.
  80 전후가 관례.
- **RT 스레드는 반드시 유한 시간에 반환**해야 한다. 무한 루프면 시스템 전체가 굳는다.
  `RLIMIT_RTTIME` 으로 보호막을 둔다.

### 4. 코드 레벨 최적화

**핫 패스(제어 루프, 콜백)에서 금지:**
- 동적 할당 (`new`, `malloc`, `std::vector` 확장, `std::string` 조합)
- 락 경합 (뮤텍스 대신 lock-free 링버퍼 / `realtime_tools::RealtimeBuffer`)
- 파일·네트워크 I/O, 로그 출력
- 예외 던지기, 동적 캐스팅
- 페이지 폴트 → `mlockall(MCL_CURRENT | MCL_FUTURE)` 로 메모리 잠금

**효과 큰 순서로:**
1. **알고리즘 복잡도** — O(n²)를 O(n log n) 으로 바꾸는 것이 미세 최적화 100개보다 크다
2. **데이터 양 줄이기** — 포인트클라우드 다운샘플, 이미지 해상도, 발행 주기
3. **복사 제거** — ROS 2 intra-process comm, 제로카피, `std::move`, 참조 전달
4. **캐시 지역성** — SoA vs AoS, 순차 접근
5. **병렬화** — 마지막 수단. 병렬화는 지터를 늘린다

### ROS 2 특유의 비용
- 노드를 프로세스로 나눌수록 직렬화·전송 비용이 든다.
  같은 데이터를 주고받는 노드는 **컴포지션으로 한 프로세스에** 넣고 intra-process 를 켠다.
  포인트클라우드/이미지에서 효과가 가장 크다.
- QoS `history depth` 를 크게 잡으면 메모리를 먹고 지연이 쌓인다. 센서는 depth 1~5.
- 콜백 그룹과 executor 설계가 지연을 좌우한다 (`ros2-engineering/references/nodes-executors.md`).
- 파이썬 노드는 GIL 때문에 멀티스레드 이득이 제한적이다. 무거운 처리는 C++ 로 옮기거나
  별도 프로세스로 분리한다.

## 열·전력

- 성능 측정 전에 **전력 모드와 클럭을 고정**한다. 안 하면 측정이 재현되지 않는다.
  Jetson: `nvpmodel -m <mode>`, `jetson_clocks`.
- **5분 벤치마크는 현장 성능이 아니다.** 30분 이상 돌려 thermal throttling 후 값을 본다.
  `tegrastats`, `sensors`, `/sys/class/thermal/` 로 온도를 함께 기록한다.
- 팬·방열이 부족하면 소프트웨어 최적화로 메울 수 없다. 열 문제는 열로 푼다.

## 용량 설계 (현장 투입 전)

- **최악 시나리오**로 검증한다: 전 센서 가동 + 로깅 + 원격 스트리밍 + 최대 속도 주행 동시에.
  평시에만 테스트하면 현장에서 터진다.
- 여유율을 남긴다. 정상 운용 시 CPU 70% 이하를 목표로 한다.
  90% 로 맞춰 놓으면 예외 상황에서 마감시간을 놓친다.
- 디스크 I/O 를 잊지 않는다. rosbag 기록이 초당 수백 MB 를 쓰면 그 자체가 병목이 된다.
  기록 토픽을 선별하고, 가능하면 별도 디스크에 쓴다.
- 메모리 누수는 장시간 운용에서만 드러난다. **8시간 이상 연속 구동 테스트**를 반드시 한다.
  RSS 추이를 기록해 우상향하면 누수다.

## 증상 → 확인

| 증상 | 확인 |
|---|---|
| 제어 주기를 놓침 | 코어별 사용률, cyclictest 지터, 격리 여부 |
| 간헐적으로만 느림 | 로깅/기록, GC(파이썬), 페이지 폴트, thermal |
| 시간이 지날수록 느려짐 | 메모리 누수, 로그 파일 누적, 그래프/버퍼 무한 증가 |
| 데스크톱은 되는데 로봇에서 안 됨 | 코어 수·클럭 차이, 아키텍처(ARM), 열 제약 |
| 토픽 지연이 큼 | QoS depth, executor 설계, 직렬화 비용, 네트워크 |
| 특정 노드만 CPU 100% | 그 노드의 알고리즘 — perf 로 함수 단위 확인 |
