#!/usr/bin/env python3
"""dangerous-command-guard.py 테스트 — 차단/확인/통과 세 갈래.

훅 입력은 stdin JSON 이다. 명령 문자열을 이 파일 안에 두는 이유:
Bash 로 직접 테스트하면 훅이 테스트 명령 자체를 차단한다.

실행: python3 ~/.claude/hooks/test_dangerous_command_guard.py
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))   # 설치 위치와 무관하게 옆의 훅을 테스트한다
HOOK = os.path.join(HERE, "dangerous-command-guard.py")

DENY, ASK, PASS = "deny", "ask", "pass"


def decide(cmd):
    """훅을 1회 실행하고 deny / ask / pass 중 하나를 반환."""
    payload = json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}})
    r = subprocess.run([sys.executable, HOOK], input=payload,
                       capture_output=True, text=True, timeout=10)
    for line in r.stdout.splitlines():
        line = line.strip()
        if not line.startswith("{"):
            continue
        try:
            o = json.loads(line)
            return o["hookSpecificOutput"]["permissionDecision"]
        except Exception:
            continue
    return PASS


CASES = [
    # ── 2026-08-17 추가: 프로젝트 PreToolUse.sh 에서 옮겨온 DB 규칙 ──
    (DENY, 'psql -c "DROP DATABASE prod_main"'),
    (DENY, 'mysql -e "drop database production"'),
    (DENY, 'psql -c "DROP SCHEMA prod_live CASCADE"'),
    (ASK,  'psql -c "DROP DATABASE test_tmp"'),
    (ASK,  'psql -c "TRUNCATE TABLE users"'),

    # ── 회귀: 기존 보호가 살아 있는지 ──
    (DENY, "rm -rf /"),
    (DENY, "rm -rf ~"),
    (DENY, "mkfs.ext4 /dev/sda1"),
    (ASK,  "git push --force origin main"),
    (ASK,  "git reset --hard HEAD~3"),
    (ASK,  "sudo apt install ros-humble-nav2-bringup"),
    (ASK,  "ros2 topic pub /cmd_vel geometry_msgs/msg/Twist"),
    (ASK,  "ros2 launch g2_web bringup.launch.py"),
    (ASK,  "cansend can0 123#DEADBEEF"),
    (ASK,  "rm -rf robot/ros2_ws/build"),
    (ASK,  "rm -r datasets/episode_0001"),

    # ── 통과해야 하는 것 (오탐 방지) ──
    (PASS, "ls -la"),
    (PASS, "git status --short"),
    (PASS, "ros2 topic list"),
    (PASS, "ros2 topic echo /joint_states --once"),
    (PASS, "colcon build --symlink-install"),
    (PASS, "rm build.log"),
    (PASS, "python3 -m pytest -q"),
]


def main():
    fails = 0
    for want, cmd in CASES:
        got = decide(cmd)
        if got == want:
            print(f"  PASS  [{want:4}] {cmd}")
        else:
            print(f"  FAIL  [{want:4}→{got}] {cmd}")
            fails += 1
    print(f"\n{len(CASES) - fails}/{len(CASES)} 통과")
    sys.exit(1 if fails else 0)


main()
