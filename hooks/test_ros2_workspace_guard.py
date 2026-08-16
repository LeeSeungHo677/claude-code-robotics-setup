#!/usr/bin/env python3
"""ros2-workspace-guard.py 테스트 — 차단(deny) / 통과(pass) 두 갈래.

이 훅의 실패 모드는 두 방향 모두 실질적인 손해다:
  - 놓치면(false negative): colcon 생성물을 고치고 다음 빌드에서 조용히 날아간다
  - 과하면(false positive): `build_map.py` 같은 정상 소스 파일을 못 고친다

그래서 오탐 케이스에 **경로 문자열에 build/install/log 가 들어가지만
생성물이 아닌 것들**을 집중적으로 넣었다.

실행: python3 ~/.claude/hooks/test_ros2_workspace_guard.py
      (pytest 로 돌리지 않는다 — standalone 스크립트다)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))   # 설치 위치와 무관하게 옆의 훅을 테스트한다
HOOK = os.path.join(HERE, "ros2-workspace-guard.py")

DENY, PASS = "deny", "pass"


def decide(path, tool_name="Write"):
    """훅을 1회 실행하고 deny / pass 중 하나를 반환."""
    payload = json.dumps({"tool_name": tool_name,
                          "tool_input": {"file_path": path, "content": "x = 1\n"}})
    r = subprocess.run([sys.executable, HOOK], input=payload,
                       capture_output=True, text=True, timeout=10)
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            return json.loads(line)["hookSpecificOutput"]["permissionDecision"]
        except Exception:
            continue
    return PASS


CASES = [
    # ── 차단: colcon 생성물 ───────────────────────────────────────────
    (DENY, "build/ 안의 파일", "/home/u/ws/build/my_pkg/CMakeCache.txt"),
    (DENY, "install/ 안의 파일", "/home/u/ws/install/my_pkg/share/my_pkg/config.yaml"),
    (DENY, "log/ 안의 파일", "/home/u/ws/log/latest_build/events.log"),
    (DENY, "중첩 워크스페이스의 install/", "robot/ros2_ws/install/g2_bringup/lib/node.py"),
    (DENY, "상대경로 build/", "build/nav2_controller/config.h"),

    # ── 차단: 시스템 ROS 설치본 ──────────────────────────────────────
    (DENY, "/opt/ros 직접 편집", "/opt/ros/humble/share/nav2_bringup/launch/bringup.launch.py"),
    (DENY, "site-packages 의 rclpy", "/usr/lib/python3/dist-packages/site-packages/rclpy/node.py"),
    (DENY, "site-packages 의 launch_ros", "/home/u/.venv/lib/python3.10/site-packages/launch_ros/actions.py"),

    # ── 차단: 다른 편집 도구도 동일하게 ──────────────────────────────
    (DENY, "Edit 도구도 검사한다", "/home/u/ws/install/pkg/x.py"),

    # ── 통과: 정상 소스 ──────────────────────────────────────────────
    (PASS, "src/ 아래 소스", "/home/u/ws/src/my_pkg/my_pkg/node.py"),
    (PASS, "패키지 매니페스트", "/home/u/ws/src/my_pkg/package.xml"),
    (PASS, "CMakeLists 원본", "/home/u/ws/src/my_pkg/CMakeLists.txt"),
    (PASS, "런치 파일 원본", "/home/u/ws/src/my_pkg/launch/bringup.launch.py"),

    # ── 통과: 이름에 build/install/log 가 들어가지만 생성물이 아닌 것 ──
    (PASS, "build 로 시작하는 파일명", "/home/u/ws/src/my_pkg/build_map.py"),
    (PASS, "install 이 들어간 스크립트명", "scripts/install_deps.sh"),
    (PASS, "log 가 들어간 모듈명", "src/my_pkg/my_pkg/logger_utils.py"),
    (PASS, "logs (복수형) 디렉토리", "tools/logs_viewer/index.html"),
    (PASS, "빌드 문서", "docs/building.md"),

    # ── 통과: ROS 와 무관한 파일 ─────────────────────────────────────
    (PASS, "프로젝트 루트 문서", "/home/u/proj/README.md"),
    (PASS, "웹 대시보드 소스", "/home/u/proj/tools/web_dashboard/static/index.html"),
    (PASS, "site-packages 지만 ROS 패키지가 아님",
     "/home/u/.venv/lib/python3.10/site-packages/numpy/core/x.py"),
    (PASS, "경로가 비어 있으면 통과", ""),
]


def main():
    fails = 0
    for i, (want, label, path) in enumerate(CASES):
        # 한 케이스는 Edit 도구로도 걸리는지 확인한다
        tool = "Edit" if label.startswith("Edit") else "Write"
        got = decide(path, tool)
        if got == want:
            print("  PASS  [%-4s] %s" % (want, label))
        else:
            print("  FAIL  [%s→%s] %s  (%s)" % (want, got, label, path))
            fails += 1
    print("\n%d/%d 통과" % (len(CASES) - fails, len(CASES)))
    sys.exit(1 if fails else 0)


main()
