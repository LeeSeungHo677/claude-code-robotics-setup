#!/usr/bin/env python3
"""secret-scanner.py 테스트 — 차단(deny) / 통과(pass) 두 갈래.

이 훅은 **디스크의 파일이 아니라 "앞으로 기록될 내용"** 을 본다.
그래서 테스트도 실제 파일을 만들지 않고 tool_input 페이로드만 넘긴다.

⚠ 이 파일 안의 '키' 는 전부 형태만 맞춘 가짜다. 실제 자격증명이 아니다.
   그리고 **소스에 완성된 형태로 적지 않고 런타임에 조립**한다 —
   그렇지 않으면 이 파일을 저장하려는 순간 secret-scanner 가 스스로를 차단한다.
   (실제로 처음 작성할 때 차단됐다. 훅이 제대로 동작한다는 증거이기도 하다)

오탐 케이스를 차단 케이스만큼 넣는 이유: 이 훅이 과하게 막으면
사용자가 훅 자체를 꺼버린다. 플레이스홀더·환경변수 참조·문서 예제는 반드시 통과해야 한다.

실행: python3 ~/.claude/hooks/test_secret_scanner.py
      (pytest 로 돌리지 않는다 — standalone 스크립트다)
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))   # 설치 위치와 무관하게 옆의 훅을 테스트한다
HOOK = os.path.join(HERE, "secret-scanner.py")

DENY, PASS = "deny", "pass"

# ── 형태만 진짜인 가짜 값 (전부 조립식) ──────────────────────────────────
FAKE_AWS = "AKIA" + "Q" * 16
FAKE_GH = "ghp_" + "b" * 36
FAKE_ANTHROPIC = "sk-ant-" + "c" * 30
FAKE_GOOGLE = "AIza" + "d" * 35
FAKE_JWT = "eyJ" + "a" * 12 + ".eyJ" + "b" * 12 + "." + "c" * 12
FAKE_PRIVKEY = "-----BEGIN OPENSSH " + "PRIVATE KEY" + "-----"
FAKE_DBURL = "postgresql://robot:" + "hunter2pass" + "@10.0.0.5:5432/fleet"
FAKE_SECRET = "s7Kd" + "0fJq2mZa9Lp4"


def decide(tool_name, tool_input):
    """훅을 1회 실행하고 deny / pass 중 하나를 반환."""
    payload = json.dumps({"tool_name": tool_name, "tool_input": tool_input})
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


def write(path, content):
    return ("Write", {"file_path": path, "content": content})


def edit(path, new_string):
    return ("Edit", {"file_path": path, "new_string": new_string})


CASES = [
    # ── 차단해야 하는 것 ──────────────────────────────────────────────
    (DENY, "AWS 액세스 키",
     write("deploy.py", 'AWS_KEY = "%s"' % FAKE_AWS)),
    (DENY, "GitHub 토큰",
     write("ci.sh", "export GH_TOKEN=%s" % FAKE_GH)),
    (DENY, "Anthropic API 키",
     write("client.py", 'client = Anthropic(api%skey="%s")' % ("_", FAKE_ANTHROPIC))),
    (DENY, "Google API 키",
     write("maps.js", 'const k = "%s";' % FAKE_GOOGLE)),
    (DENY, "개인키 블록",
     write("id_rsa", "%s\nb3BlbnNzaC1rZXk=\n" % FAKE_PRIVKEY)),
    (DENY, "JWT 토큰",
     write("session.json", '{"token": "%s"}' % FAKE_JWT)),
    (DENY, "비밀번호 박힌 DB URL",
     write("config.py", 'DB = "%s"' % FAKE_DBURL)),
    (DENY, "일반 시크릿 대입",
     write("settings.py", 'client%ssecret = "%s"' % ("_", FAKE_SECRET))),
    (DENY, "Edit 의 new_string 도 검사한다",
     edit("app.py", 'headers = {"Authorization": "Bearer %s"}' % FAKE_GH)),
    (DENY, "MultiEdit 의 edits 도 검사한다",
     ("MultiEdit", {"file_path": "a.py",
                    "edits": [{"new_string": "x = 1"},
                              {"new_string": 'k = "%s"' % FAKE_AWS}]})),

    # ── 통과해야 하는 것 (오탐 방지) ─────────────────────────────────
    (PASS, "환경변수 참조",
     write("config.py", 'API_KEY = os.environ["ANTHROPIC_API_KEY"]')),
    (PASS, "os.getenv 참조",
     write("config.py", 'token = os.getenv("GITHUB_TOKEN", "")')),
    (PASS, "플레이스홀더",
     write("README.md", "export ANTHROPIC_API_KEY=sk-ant-YOUR_KEY_HERE")),
    (PASS, "AWS 공식 문서 예제값",
     write("docs.md", 'aws_access_key: "AKIAIOSFODNN7EXAMPLE"')),
    (PASS, "꺾쇠 플레이스홀더",
     write("guide.md", 'curl -H "Authorization: Bearer <your-token>" https://api.example.com')),
    (PASS, ".env.example 은 경로 자체를 건너뛴다",
     write(".env.example", "GITHUB_TOKEN=%s" % FAKE_GH)),
    (PASS, "빌드 산출물 경로는 건너뛴다",
     write("ws/install/pkg/config.py", 'K = "%s"' % FAKE_AWS)),
    (PASS, "바이너리 확장자는 건너뛴다",
     write("model.onnx", FAKE_AWS)),
    (PASS, "스캐너 자신의 정규식 (패턴 문자열은 키가 아니다)",
     write("scan.py", r'AWS = re.compile(r"\bAKIA[0-9A-Z]{16}\b")')),
    (PASS, "평범한 ROS 2 노드 코드",
     write("node.py", "self.pub = self.create_publisher(Twist, '/cmd_vel', 10)")),
    (PASS, "짧은 password 대입 (12자 미만은 시크릿으로 안 본다)",
     write("test_login.py", 'password = "abc"')),
    (PASS, "내용이 비어 있으면 통과",
     write("empty.txt", "")),
    (PASS, "관련 없는 도구는 검사 대상이 아니다",
     ("Bash", {"command": "echo %s" % FAKE_AWS})),
]


def main():
    fails = 0
    for want, label, (tool, ti) in CASES:
        got = decide(tool, ti)
        if got == want:
            print("  PASS  [%-4s] %s" % (want, label))
        else:
            print("  FAIL  [%s→%s] %s" % (want, got, label))
            fails += 1
    print("\n%d/%d 통과" % (len(CASES) - fails, len(CASES)))
    sys.exit(1 if fails else 0)


main()
