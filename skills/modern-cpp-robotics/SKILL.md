---
name: modern-cpp-robotics
description: >
  로봇 코드를 위한 현대 C++ (17/20). TRIGGER when the user writes or reviews C++ for robotics —
  rclcpp nodes, real-time control code, Eigen usage, memory ownership and lifetime, concurrency
  and lock-free patterns, templates, CMake for ROS 2 packages, or debugging undefined behavior,
  segfaults, data races, and performance issues in C++ robot code.
---

# 로봇을 위한 현대 C++

로봇 C++ 는 일반 서버 C++ 와 제약이 다르다.
**결정론 > 추상화**, **명시적 > 영리함**.

## 실시간 경로에서 금지

제어 루프, `update()`, 고주파 콜백 안에서:

| 금지 | 이유 | 대안 |
|---|---|---|
| `new` / `malloc` / 컨테이너 확장 | 할당 시간이 비결정적 | `reserve()` 를 미리, 고정 크기 배열, 메모리 풀 |
| `std::string` 조합 | 힙 할당 | 사전 할당 버퍼, `std::string_view` |
| `std::mutex` 경합 | 우선순위 역전, 무한 대기 | lock-free 링버퍼, `RealtimeBuffer` |
| 예외 던지기 | 비결정적 비용 | 오류 코드, `std::expected`(C++23)/`tl::expected` |
| `dynamic_cast`, RTTI | 비결정적 | 정적 다형성, 방문자 패턴 |
| 파일/네트워크 I/O, 로그 | 블로킹 | 별도 스레드로 큐잉 |
| `std::shared_ptr` 복사 | 원자적 참조 카운트 경합 | 참조/생포인터 전달, 소유권은 루프 밖에서 |

```cpp
// 나쁨 — 매 사이클 할당
void update() {
  std::vector<double> q(n_joints_);          // 할당
  RCLCPP_INFO(get_logger(), "q=%f", q[0]);   // 포매팅 + I/O
}

// 좋음 — 미리 잡고 재사용
class Ctrl {
  std::vector<double> q_;                    // on_configure 에서 resize
  void update() {
    // q_ 재사용, 로그 없음
  }
};
```

## 소유권과 수명

- **소유권을 타입으로 표현한다**: `unique_ptr`(단독 소유), `shared_ptr`(공유 소유),
  생포인터/참조(비소유). 함수 시그니처만 보고 누가 지우는지 알 수 있어야 한다.
- 비소유 인자는 `const T&` 또는 `T*` 로 받는다. **`shared_ptr` 을 습관적으로 넘기지 않는다.**
- 콜백에 `this` 를 캡처할 때 수명을 확인한다. 노드가 파괴됐는데 콜백이 살아 있으면
  use-after-free 다. `weak_ptr` 로 방어하거나 파괴 전에 명시적으로 구독을 해제한다.
- 람다에서 `[&]` 전체 캡처를 피한다. 비동기로 넘어가는 람다에서는 특히 위험하다.
  필요한 것만 명시적으로 캡처한다.

## Eigen 사용 시 함정

- **`auto` 를 Eigen 표현식에 쓰지 않는다.**
  ```cpp
  auto x = A * b;        // 표현식 템플릿 — A, b 가 죽으면 dangling
  Eigen::VectorXd x = A * b;   // 즉시 평가
  ```
  이건 조용히 틀린 값을 내거나 크래시한다. 로봇 코드에서 실제로 자주 나온다.
- 고정 크기 Eigen 멤버를 가진 클래스는 정렬 문제가 생길 수 있다.
  C++17 이상에서는 대체로 완화되지만, 컨테이너에 담을 때는 확인한다.
- `.noalias()` 로 불필요한 임시 객체를 없앤다: `C.noalias() += A * B;`
- 실시간 경로에서 동적 크기 행렬(`MatrixXd`)은 할당한다. 크기를 아는 곳에서는
  고정 크기(`Matrix3d`, `Matrix<double,6,1>`)를 쓴다 — 빠르고 할당이 없다.
- 행렬 곱 순서로 연산량이 크게 달라진다. `(A*B)*v` 보다 `A*(B*v)` 가 훨씬 싸다.

## 동시성

- **데이터 경합은 정의되지 않은 동작이다.** "가끔 이상하다" 의 대부분이 이것.
  `-fsanitize=thread` 로 CI 에서 검사한다.
- 공유 상태는 원자적이거나 락으로 보호되거나 **아예 공유하지 않는다**.
  가장 좋은 것은 세 번째다 — 메시지 전달로 설계한다.
- `std::atomic` 은 단일 변수에만 유효하다. 두 변수의 일관성이 필요하면 원자성만으로 부족하다.
- ROS 2 콜백은 executor/callback group 설정에 따라 병렬 실행될 수 있다.
  같은 멤버를 만지는 콜백들의 동시성 가정을 명시한다
  (`ros2-engineering/references/nodes-executors.md`).
- 조건 변수는 항상 술어(predicate)와 함께 쓴다 — spurious wakeup.

## rclcpp 관용구

```cpp
// 파라미터: 선언 → 읽기 → 변경 콜백
this->declare_parameter<double>("max_speed", 1.0);
max_speed_ = this->get_parameter("max_speed").as_double();
param_cb_ = this->add_on_set_parameters_callback(
    [this](const std::vector<rclcpp::Parameter>& params) {
      // 검증 후 수락/거부 — 범위 밖 값을 그냥 받지 않는다
      rcl_interfaces::msg::SetParametersResult r; r.successful = true;
      return r;
    });

// 로그는 throttle 을 기본으로
RCLCPP_WARN_THROTTLE(get_logger(), *get_clock(), 1000, "sensor stale");
```

- 타이머 콜백이 주기보다 오래 걸리면 밀린다. 실행 시간을 측정해 주기 안에 드는지 확인한다.
- 메시지는 `std::move` 로 발행해 복사를 줄인다. intra-process 에서 특히 효과가 크다.
- 콜백에서 예외를 던지면 executor 가 죽을 수 있다. 콜백 경계에서 잡는다.

## 오류 처리

- 실시간 경로: 오류 코드 / `expected` 패턴. 예외 금지.
- 비실시간 경로: 예외 사용 가능. 다만 ROS 콜백 밖으로 새지 않게.
- **실패를 조용히 삼키지 않는다.** `if (!ok) return;` 만 있고 로그도 상태 보고도 없으면
  현장에서 원인을 찾을 수 없다.
- 하드웨어 읽기 실패 시 **이전 값을 그대로 쓰지 않는다.** stale 데이터로 제어를 계속하는 것이
  가장 위험한 실패 모드다.

## 빌드 (ROS 2 / CMake)

```cmake
add_compile_options(-Wall -Wextra -Wpedantic)
# 릴리스 빌드에서 최적화 확인 — 디버그 빌드로 성능을 논하지 않는다
# colcon build --cmake-args -DCMAKE_BUILD_TYPE=Release
```

- `ament_target_dependencies` 대신 최신 방식(`target_link_libraries` + `::` 타깃)을
  프로젝트 내에서 **일관되게** 쓴다. 섞으면 링크 오류가 난다.
- 헤더 의존을 줄인다. 전방 선언과 pimpl 로 빌드 시간을 줄일 수 있다.
- **디버그 빌드로 실시간 성능을 측정하지 않는다.** 수 배 차이가 난다.

## 디버깅 도구

```bash
# 정의되지 않은 동작 / 메모리
g++ -fsanitize=address,undefined -g
valgrind --leak-check=full

# 데이터 경합
g++ -fsanitize=thread

# 크래시 후
gdb <bin> core.<pid>        # coredump 활성화 필요: ulimit -c unlimited
```

- 로봇 현장 크래시는 재현이 어렵다. **coredump 를 남기도록 설정**해 두면
  한 번의 크래시로 원인을 찾을 수 있다.
- `-g` 는 릴리스 빌드에도 넣는다. 성능에 영향 없이 스택트레이스를 얻는다.

## 리뷰 체크리스트

- [ ] 실시간 경로에 할당·락·I/O·로그가 없는가
- [ ] Eigen 표현식에 `auto` 를 쓰지 않았는가
- [ ] 소유권이 시그니처로 드러나는가
- [ ] 콜백 캡처의 수명이 안전한가
- [ ] 병렬 실행 가능한 콜백이 공유 상태를 안전하게 다루는가
- [ ] 하드웨어/외부 호출 실패가 조용히 무시되지 않는가
- [ ] 단위·부호·좌표계가 주석 또는 타입으로 명시돼 있는가
