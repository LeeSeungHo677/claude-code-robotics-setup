#!/usr/bin/env python3
"""design_lint.py 테스트 — 잡아야 할 것(tell)과 잡으면 안 되는 것(오탐) 양쪽.

실행: python3 ~/.claude/skills/design-system/scripts/test_design_lint.py
"""
import json
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
LINT = os.path.join(HERE, "design_lint.py")

SLOP = """<!doctype html><html><head>
<link href="https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@400;700" rel="stylesheet">
<style>
.card{border-radius:24px;box-shadow:0 0 24px rgba(99,102,241,.6);border-left:4px solid #6366f1;transition:all .3s}
.title{background:linear-gradient(135deg,#667eea,#764ba2);-webkit-background-clip:text;background-clip:text}
.eyebrow{text-transform:uppercase;letter-spacing:.1em}
.panel{backdrop-filter:blur(12px)}
.blob{filter:blur(80px)}
.live{animation:pulse 2s ease-in-out infinite}
.card:hover { transform: scale(1.03) }
@media (prefers-color-scheme: dark){ body{background:#0b0b0b} }
</style></head><body>
<h1 class="bg-clip-text text-transparent bg-gradient-to-r from-indigo-500 to-purple-600">차세대 로봇 관제 플랫폼</h1>
<div class="rounded-2xl shadow-lg border-l-4 uppercase tracking-wider">🚀 빠른 배포</div>
<a href="/start">시작하기 →</a>
<p>12 robots · 99.9% uptime · 24/7</p>
<blockquote>Seamless fleet ops. — Jane Doe, Acme</blockquote>
<h2>다시 오신 것을 환영합니다 👋</h2><p>지금 바로 시작하세요!</p>
</body></html>
"""

CLEAN = """<!doctype html><html lang="ko"><head><style>
:root{
  color-scheme: light dark;
  --bg: oklch(0.97 0.005 80); --text: oklch(0.25 0.01 80); --accent: oklch(0.62 0.15 45);
  --font-sans: "Pretendard", system-ui, sans-serif;
  --t-sm: 12px; --t-md: 14px; --t-lg: 16px; --s-2: 8px; --s-4: 16px; --r-md: 8px;
}
body{background:var(--bg);color:var(--text);font-family:var(--font-sans);word-break:keep-all;overflow-wrap:anywhere}
.row{padding:var(--s-2) var(--s-4);border-radius:var(--r-md);transition:background-color 150ms ease-out}
.row:hover{background:var(--surface-2)}
.spinner{animation:spin 1s linear infinite}
.shade{filter:blur(6px)}
@media (prefers-color-scheme: dark){ :root{ --bg: oklch(0.2 0.01 80); --text: oklch(0.92 0.01 80); } }
</style></head><body>
<h1>로봇 상태</h1>
<a href="/logs">로그 열기</a>
<script>if (!ok && a !== b) { x = !y; }</script><p>{!loading && <span>완료</span>}</p>
<!-- TODO: 차세대 문구 나중에 -->
<table><tr><td>배터리</td><td class="num">87%</td></tr></table>
</body></html>
"""


def run(paths, *flags):
    r = subprocess.run([sys.executable, "-I", "-B", LINT, *paths, "--json", *flags], capture_output=True, text=True, timeout=30)
    return r.returncode, json.loads(r.stdout or "[]")


def rules(findings):
    return {f["rule"] for f in findings}


def main():
    fails = []

    def check(name, cond, detail=""):
        print(f"  {'PASS' if cond else 'FAIL'}  {name}" + ("" if cond else f" — {str(detail)[:400]}"))
        if not cond:
            fails.append(name)

    with tempfile.TemporaryDirectory() as d:
        w = lambda name, text: (open(os.path.join(d, name), "w", encoding="utf-8").write(text), os.path.join(d, name))[1]

        # 1) AI 티 샘플 — 대표 tell 을 전부 잡고 fail 로 끝난다
        code, f = run([w("slop.html", SLOP)])
        want = {"framework-default-palette", "gradient-text", "transition-all", "glassmorphism", "glow-shadow",
                "side-stripe", "oversized-radius", "caps-label", "arrow-cta", "emoji-icon",
                "raw-color", "ai-default-font", "hangul-break", "color-scheme-missing",
                "blob-decor", "infinite-motion", "hover-scale", "placeholder-copy", "hype-copy",
                "exclaim-copy", "greeting-copy"}
        check("tell 샘플 — 21개 규칙 모두 검출", want <= rules(f), sorted(want - rules(f)))
        check("tell 샘플 — fail 이 있으면 exit 1", code == 1, code)

        # 2) 깨끗한 샘플 — 토큰 블록 안 색·한글+keep-all·color-scheme·문장형 링크 → 0건
        code, f = run([w("clean.html", CLEAN)])
        check("깨끗한 샘플 — 0건, exit 0", code == 0 and not f, f)

        # 3) :root 블록 안 색은 정의라 정상, 밖은 raw-color
        p = w("a.css", ":root{--accent:#d9480f}\n.btn{color:#d9480f}\n")
        _, f = run([p])
        raw = [x["line"] for x in f if x["rule"] == "raw-color"]
        check("raw-color — :root 안은 무시, 밖(2행)만", raw == [2], f)
        _, f = run([w("tokens.css", ".x{color:#123456}\n")])
        check("raw-color — 토큰 파일(tokens*.css)은 검사 안 함", "raw-color" not in rules(f), f)

        # 4) waiver — 이유가 있으면 빠지고, 이유가 없으면 그대로
        p = w("w.css", ".m{\n  /* design-lint: allow glassmorphism — 지도 위 오버레이, 뒤 지도가 비쳐야 위치를 잃지 않는다 */\n"
                       "  backdrop-filter: blur(8px);\n}\n.n{\n  /* design-lint: allow glassmorphism */\n  backdrop-filter: blur(8px);\n}\n")
        _, f = run([p])
        lines = [x["line"] for x in f if x["rule"] == "glassmorphism"]
        check("waiver — 이유 있는 allow 는 제외, 이유 없는 allow 는 무시", lines == [7], f)

        # 5) 오탐 — 흔한 정상 코드
        ok = w("ok.tsx", 'export const A = () => <div className="text-slate-700 rounded-md tracking-tight" style={{gap: 8}}>'
                         '{items.length} items</div>;\nconst intersection = new IntersectionObserver(cb);\n'
                         'const x = setInterval(f, 1000);\n')
        _, f = run([ok])
        check("오탐 없음 — slate·rounded-md·tracking-tight·IntersectionObserver·setInterval", not f, f)

        # 5b) 실제 프로젝트에서 나온 오탐 (2026-11-26, 실제 사내 웹앱 대조) — 고정
        fp = w("fp.html", '<style>\n.cmp td.b{border-left:3px solid var(--series-2)}\n'
                          '.tree .children{border-left:2px solid var(--line);padding-left:var(--s-3)}\n</style>\n'
                          '<button class="close" aria-label="닫기">✕</button><span>✓ 완료</span><span>★</span>\n'
                          '<div aria-label="${steps.join(" → ")}"></div>\n'
                          '<p style="word-break:keep-all">수집 19/33 · 오늘 마감 · 평균 2분</p>\n')
        _, f = run([fp])
        check("오탐 없음 — 표 칸·트리의 border-left, ✕✓★ 기호, aria-label 의 →, 가운뎃점 메타",
              not ({"side-stripe", "emoji-icon", "arrow-cta"} & rules(f)), [x for x in f if x["rule"] in {"side-stripe", "emoji-icon", "arrow-cta"}])
        os.makedirs(os.path.join(d, "hid", ".claude", "worktrees"))
        open(os.path.join(d, "hid", ".claude", "worktrees", "m.css"), "w").write(".x{transition:all 1s}\n")
        os.makedirs(os.path.join(d, "hid", ".venv", "lib"))
        open(os.path.join(d, "hid", ".venv", "lib", "m.css"), "w").write(".x{transition:all 1s}\n")
        _, f = run([os.path.join(d, "hid")])
        check("숨김 폴더(.claude/worktrees, .venv) 건너뜀", not f, f)

        # 5c) keep-all·color-scheme 이 <link> 로 부르는 CSS 에 있으면 HTML 은 통과 (절대 경로 /static/... 포함)
        os.makedirs(os.path.join(d, "site", "static"))
        open(os.path.join(d, "site", "static", "app.css"), "w").write(
            ":root{color-scheme:light dark}\nbody{word-break:keep-all}\n[data-theme=dark]{--bg:oklch(.2 .01 80)}\n")
        page = os.path.join(d, "site", "static", "index.html")
        open(page, "w", encoding="utf-8").write('<link rel="stylesheet" href="/static/app.css"><html data-theme="dark"><h1>로봇 상태</h1></html>\n')
        _, f = run([page])
        check("linked CSS — 부르는 CSS 의 keep-all·color-scheme 인정", not ({"hangul-break", "color-scheme-missing"} & rules(f)), f)

        # 6) next/font 의 2세대 대체 폰트 호출도 잡는다
        _, f = run([w("layout.tsx", 'import { Space_Grotesk } from "next/font/google";\nconst f = Space_Grotesk({ subsets: ["latin"] });\n')])
        hits = [x["line"] for x in f if x["rule"] == "ai-default-font"]
        check("ai-default-font — next/font 호출(2행)만, import 줄은 아님", hits == [2], f)

        # 7) 척도 — font-size 8종, 4 배수 아닌 간격, radius 4종
        css = "".join(f".a{i}{{font-size:{s}px}}\n" for i, s in enumerate([11, 12, 13, 14, 15, 17, 20, 28]))
        css += ".p{padding:13px 10px}\n" + "".join(f".r{i}{{border-radius:{r}px}}\n" for i, r in enumerate([4, 6, 8, 10]))
        _, f = run([w("scale.css", css)])
        check("척도 — type-scale·spacing-grid·radius-scale", {"type-scale", "spacing-grid", "radius-scale"} <= rules(f), rules(f))

        # 8) --strict 는 warn 만 있어도 exit 1, 기본은 0
        p = w("warn.css", ".panel{backdrop-filter:blur(4px)}\n")
        c1, _ = run([p])
        c2, _ = run([p], "--strict")
        check("exit — warn 만: 기본 0 / --strict 1", (c1, c2) == (0, 1), (c1, c2))

        # 9) 디렉터리 순회 — node_modules 는 건너뛴다
        os.makedirs(os.path.join(d, "proj", "node_modules", "lib"))
        open(os.path.join(d, "proj", "node_modules", "lib", "x.css"), "w").write(".x{transition:all 1s}\n")
        open(os.path.join(d, "proj", "app.css"), "w").write(".y{transition:all 1s}\n")
        _, f = run([os.path.join(d, "proj")])
        files = sorted({os.path.basename(x["file"]) for x in f})
        check("디렉터리 — node_modules 제외", files == ["app.css"], files)

    print(f"\n실패 {len(fails)}건" + (f": {fails}" if fails else " — 전부 통과"))
    sys.exit(1 if fails else 0)


if __name__ == "__main__":
    main()
