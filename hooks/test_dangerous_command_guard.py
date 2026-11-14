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


def decide(cmd, cwd=None):
    """훅을 1회 실행하고 deny / ask / pass 중 하나를 반환."""
    body = {"tool_name": "Bash", "tool_input": {"command": cmd}}
    if cwd:
        body["cwd"] = cwd
    payload = json.dumps(body)
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

    # ── 2026-10-11 추가: heredoc 본문은 자료다 (PR 본문 파일에 `sudo apt install …` 글자가 있어 걸렸다) ──
    (PASS, "cat > /tmp/pr.md <<'EOF'\n노트북 한 번: `sudo apt install ros-humble-foo`\nrm -rf / 라고 쓰지 마세요\nEOF"),
    (PASS, "cat <<-EOF > /tmp/x\n\tsudo ls\n\tEOF"),
    (ASK,  "cat > /tmp/x <<EOF\nhi $(sudo ls) there\nEOF"),          # 따옴표 없는 구분자 → $( ) 는 확장된다
    (ASK,  "cat <<'EOF'\nhello\nEOF\nsudo apt install x"),            # heredoc 뒤의 진짜 명령은 그대로 검사
    (ASK,  'echo "<<EOF"\nsudo ls'),                                   # 종결자 없는 가짜 heredoc 으로 우회 못 함
    (ASK,  "cat <<<word\nsudo ls"),                                    # here-string 은 heredoc 이 아니다

    # ── 2026-11-14 추가: 플래시·프린트 경로 보강 ──
    (ASK,  "pyocd flash -t stm32f411re build/fw.hex"),
    (ASK,  "probe-rs download --chip RP2040 fw.elf"),
    (ASK,  "cargo flash --release --chip nRF52840_xxAA"),
    (ASK,  "JLinkExe -CommandFile flash.jlink"),
    (ASK,  "STM32_Programmer_CLI -c port=SWD -w fw.bin 0x08000000"),
    (ASK,  "nrfjprog --program fw.hex --verify"),
    (ASK,  "cd app && west flash"),
    (ASK,  "idf.py -p /dev/ttyUSB0 flash monitor"),
    (ASK,  "picotool load fw.uf2 -f"),
    (ASK,  "pio run -t upload"),
    (ASK,  "arduino-cli upload -p /dev/ttyACM0 --fqbn arduino:avr:uno sketch"),
    (ASK,  "make -C firmware flash"),
    (ASK,  "cp build/fw.uf2 /media/user/RPI-RP2/"),
    (ASK,  'curl -X POST http://printer.local/printer/print/start?filename=part.gcode'),
    (ASK,  'curl -X POST -H "Content-Type: application/json" http://octopi/api/job -d \'{"command":"start"}\''),
    (ASK,  "echo G28 > /dev/ttyUSB0"),
    (PASS, "pyocd list"),
    (PASS, "probe-rs list"),
    (PASS, "nrfjprog --ids"),
    (PASS, "west build -b nrf52840dk_nrf52840 app"),
    (PASS, "idf.py build"),
    (PASS, "pio run"),
    (PASS, "make host-test"),
    (PASS, "make flash-test"),                                 # 이름에 flash 가 들어간 다른 타깃
    (PASS, "curl -s http://printer.local/printer/info"),
    (PASS, "cat /dev/ttyACM0"),

    # ── 통과해야 하는 것 (오탐 방지) ──
    (PASS, "ls -la"),
    (PASS, "git status --short"),
    (PASS, "ros2 topic list"),
    (PASS, "ros2 topic echo /joint_states --once"),
    (PASS, "colcon build --symlink-install"),
    (PASS, "rm build.log"),
    (PASS, "python3 -m pytest -q"),
]


def extra_cases():
    """2026-10-18 추가: Bash 로 colcon 생성물 수정 / 외부 요청에 시크릿.

    실제 임시 워크스페이스를 만든다 — 생성물 판정이 COLCON_IGNORE 표식을 보기 때문.
    가짜 토큰은 런타임에 조립한다 (소스에 완성형으로 쓰면 secret-scanner 가 이 파일 저장을 막는다).
    """
    import tempfile
    tmp = tempfile.mkdtemp(prefix="dcguard-")
    ws = os.path.join(tmp, "ws")
    for d in ("build", "install", "log"):
        os.makedirs(os.path.join(ws, d, "pkg"))
        open(os.path.join(ws, d, "COLCON_IGNORE"), "w").close()
    os.makedirs(os.path.join(ws, "src", "pkg"))
    web = os.path.join(tmp, "web")
    os.makedirs(os.path.join(web, "build"))
    tok = "ghp_" + "b" * 36
    return tmp, [
        (ASK,  "sed -i 's/a/b/' install/pkg/share/pkg/config.yaml", ws),
        (ASK,  "cp fix.py build/pkg/fix.py", ws),
        (ASK,  "echo x > log/pkg/note.txt", ws),
        (ASK,  "cd ws && cat a | tee install/pkg/a.yaml", ws),
        (PASS, "sed -i 's/a/b/' src/pkg/config.yaml", ws),
        (PASS, "colcon build 2>/dev/null > build_output.txt", ws),
        (PASS, "cp out.js build/out.js", web),                       # 표식 없는 웹 build/
        (PASS, "ls build/pkg && cat install/pkg/x", ws),             # 읽기는 막지 않는다
        (ASK,  f'curl -H "Authorization: Bearer {tok}" https://api.github.com/user', None),
        (PASS, 'curl -H "Authorization: Bearer $GITHUB_TOKEN" https://api.github.com/user', None),
        (PASS, "curl -s https://example.com/api?q=ros2", None),
    ]


def main():
    fails = 0
    tmp, extra = extra_cases()
    for want, cmd, cwd in extra:
        got = decide(cmd, cwd)
        if got == want:
            print(f"  PASS  [{want:4}] {cmd[:90]}")
        else:
            print(f"  FAIL  [{want:4}→{got}] {cmd[:90]}")
            fails += 1
    import shutil
    shutil.rmtree(tmp, ignore_errors=True)
    for want, cmd in CASES:
        got = decide(cmd)
        if got == want:
            print(f"  PASS  [{want:4}] {cmd}")
        else:
            print(f"  FAIL  [{want:4}→{got}] {cmd}")
            fails += 1
    # 2026-11-10: 실기 명령의 확인 사유에는 '다음 할 일' 이 붙고, 일반 확인에는 안 붙는다
    def reason_of(cmd):
        r = subprocess.run([sys.executable, HOOK], capture_output=True, text=True, timeout=10,
                           input=json.dumps({"tool_name": "Bash", "tool_input": {"command": cmd}}))
        return json.loads(r.stdout)["hookSpecificOutput"]["permissionDecisionReason"]
    hint_cases = [("cd ws && ros2 launch bringup robot.launch.py", True),
                  ("cansend can0 123#DEADBEEF", True),
                  ("rm -r old_dir", False)]
    for cmd, want in hint_cases:
        got = "다음 할 일" in reason_of(cmd)
        print(f"  {'PASS' if got == want else 'FAIL'}  [hint={want}] {cmd}")
        fails += got != want
    total = len(CASES) + len(extra) + len(hint_cases)
    print(f"\n{total - fails}/{total} 통과")
    sys.exit(1 if fails else 0)


main()
