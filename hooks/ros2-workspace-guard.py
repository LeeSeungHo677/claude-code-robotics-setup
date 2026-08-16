#!/usr/bin/env python3
"""PreToolUse(Write|Edit|MultiEdit) — colcon 생성물 편집을 차단한다.

왜 필요한가:
  colcon 워크스페이스의 build/ install/ log/ 는 빌드가 만들어내는 산출물이다.
  여기 있는 파일을 고치면 그 순간에는 동작하는 것처럼 보이지만
  다음 `colcon build` 에서 조용히 사라진다.
  ament_cmake 의 심볼릭 링크 install 때문에 install/ 안의 파일이 src/ 를 가리키는 경우도 있어
  더 헷갈린다. 그래서 사람도 AI 도 실제로 자주 저지르는 실수다.

  또 하나: src/ 밖의 site-packages 안 ROS 패키지를 직접 고치는 것도 같은 종류의 함정이다.

입력: stdin JSON / 출력: deny JSON + exit 2
"""

import json
import os
import re
import sys

# colcon/ament 가 생성하는 디렉토리
GENERATED = re.compile(r"(^|/)(build|install|log)/")

# ROS 설치본 / 파이썬 site-packages 안의 ROS 패키지
SYSTEM_ROS = re.compile(r"^/opt/ros/|(^|/)site-packages/(rclpy|rcl_interfaces|geometry_msgs|"
                        r"sensor_msgs|nav_msgs|std_msgs|tf2_ros|launch|launch_ros)/")


def workspace_hint(path):
    """생성물 경로에서 대응하는 src/ 경로를 추정해 알려준다."""
    m = re.search(r"^(.*?)/(build|install)/([^/]+)/(.*)$", path)
    if not m:
        return ""
    ws, _, pkg, rest = m.groups()
    return f"\n  대신 소스를 고치세요: {ws}/src/{pkg}/... (해당 파일: .../{os.path.basename(rest)})"


def main():
    try:
        data = json.load(sys.stdin)
    except Exception:
        sys.exit(0)

    if data.get("tool_name") not in ("Write", "Edit", "MultiEdit", "NotebookEdit"):
        sys.exit(0)

    ti = data.get("tool_input") or {}
    path = ti.get("file_path") or ti.get("notebook_path") or ""
    if not path:
        sys.exit(0)

    reason = None
    if GENERATED.search(path):
        reason = (f"[ros2-workspace-guard] colcon 생성물은 편집해도 다음 빌드에서 사라집니다.\n"
                  f"  경로: {path}" + workspace_hint(path))
    elif SYSTEM_ROS.search(path):
        reason = (f"[ros2-workspace-guard] 시스템에 설치된 ROS 패키지를 직접 수정하려 합니다.\n"
                  f"  경로: {path}\n"
                  f"  워크스페이스에 오버레이 패키지를 만들어 덮어쓰는 방식을 쓰세요.")

    if reason is None:
        sys.exit(0)

    print(json.dumps({"hookSpecificOutput": {
        "hookEventName": "PreToolUse",
        "permissionDecision": "deny",
        "permissionDecisionReason": reason}}))
    print(reason, file=sys.stderr)
    sys.exit(2)


if __name__ == "__main__":
    main()
