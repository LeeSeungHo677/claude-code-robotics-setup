"""훅들이 함께 쓰는 판정 함수. 훅이 아니다 — settings.json 에 등록하지 않는다.

- generated_root(): colcon 생성물(build/ install/ log/) 경로인지 판정
- log_hook_error(): 훅이 입력을 못 읽고 통과시킨 경우를 기록 (fail-open 감시)
"""

import os
import re
import time

GENERATED_DIRS = ("build", "install", "log")
_NAME_RX = re.compile(r"(^|/)(build|install|log)/")


def generated_root(path, cwd=None):
    """path 가 colcon 생성물 안이면 그 생성물 디렉토리(…/build 등)를, 아니면 None.

    1) 정규화 먼저: `ws/src/../build/x` 는 build 로, `build/../src/x` 는 src 로 본다.
    2) 생성물 디렉토리가 디스크에 **있으면** colcon 이 만든 `COLCON_IGNORE` 표식이 있을 때만 생성물이다.
       → 웹 프로젝트의 build/, `src/pkg/log/handler.py` 같은 오탐이 사라진다.
    3) 디스크에 **없으면** 표식으로 판단할 수 없으니 이름으로 판단한다 (보수적).
    """
    if not path:
        return None
    p = os.path.expanduser(path)
    if not os.path.isabs(p):
        p = os.path.join(cwd or os.getcwd(), p)
    p = os.path.normpath(p)

    parts = p.split(os.sep)
    for i, name in enumerate(parts[:-1]):
        if name not in GENERATED_DIRS:
            continue
        root = os.sep.join(parts[:i + 1]) or os.sep
        if os.path.isdir(root):
            if os.path.exists(os.path.join(root, "COLCON_IGNORE")):
                return root
            continue                      # 실제로 있지만 colcon 것이 아님 → 더 깊은 후보를 계속 본다
        return root if _NAME_RX.search(p) else None
    return None


def log_hook_error(hook_name, detail=""):
    """입력 파싱 실패 등으로 '검사 없이 통과' 한 경우를 남긴다.

    fail-open 은 의도된 설계다 (훅 버그가 모든 작업을 막으면 안 된다).
    대신 조용히 넘어가지 않도록 기록해 `/setup:audit` 가 볼 수 있게 한다.
    """
    try:
        d = os.path.expanduser("~/.claude/logs")
        os.makedirs(d, exist_ok=True)
        with open(os.path.join(d, "hook-errors.log"), "a", encoding="utf-8") as f:
            f.write(f"{time.strftime('%Y-%m-%dT%H:%M:%S')}\t{hook_name}\t{detail[:200]}\n")
    except Exception:
        pass
