#!/usr/bin/env python3
"""design_lint — "AI 가 만든 것 같은" UI 의 결정적 신호를 소스에서 찾는다.

사용:
    python3 design_lint.py <파일|디렉터리> [...] [--json] [--strict]

판정:
    fail  — 거의 항상 고른 게 아니라 그냥 나온 것 (exit 1)
    warn  — 맥락에 따라 맞을 수 있다. 남기려면 이유를 적는다 (--strict 면 warn 도 exit 1)

남기기(waiver): 같은 줄이나 바로 윗줄에
    /* design-lint: allow <rule> — 이유 */   또는   <!-- design-lint: allow <rule> — 이유 -->
이유 없는 allow 는 무시한다.

렌더해야 아는 것(대비·accent 면적·가로 스크롤)은 여기서 보지 않는다 — SKILL.md §11 렌더 확인 루프.
외부 의존성 없음 (Python 3.8+ 표준 라이브러리).
"""
import json
import os
import re
import sys

EXTS = {".css", ".scss", ".html", ".htm", ".jsx", ".tsx", ".js", ".ts", ".vue", ".svelte", ".astro"}
SKIP_DIRS = {"node_modules", ".git", "dist", "build", ".next", "out", "coverage", "vendor", "__pycache__"}

# (rule, severity, pattern, 대신)
LINE_RULES = [
    ("framework-default-palette", "fail",
     re.compile(r"\b(?:bg|text|from|via|to|border|ring|fill|stroke|shadow|outline|decoration|accent)-(?:indigo|violet|purple|fuchsia)-\d{2,3}\b"
                r"|#(?:6366f1|4f46e5|818cf8|8b5cf6|7c3aed|a855f7|667eea|764ba2)\b", re.I),
     "제품 accent 토큰. Tailwind 는 theme.colors 를 extend 가 아니라 교체해 기본 팔레트가 컴파일되지 않게"),
    ("gradient-text", "fail", re.compile(r"background-clip\s*:\s*text|\bbg-clip-text\b", re.I),
     "단색 텍스트. 강조는 굵기·크기로"),
    ("transition-all", "fail", re.compile(r"transition\s*:\s*all\b|\btransition-all\b", re.I),
     "바뀌는 속성만 나열 (transition: background-color 150ms ease-out)"),
    ("glassmorphism", "warn", re.compile(r"backdrop-filter\s*:|\bbackdrop-blur(?:-\w+)?\b", re.I),
     "불투명 표면 토큰. 오버레이처럼 이유가 있을 때만, 페이지당 1곳"),
    ("glow-shadow", "warn",
     re.compile(r"box-shadow\s*:\s*0(?:px)?\s+0(?:px)?\s+[1-9]\d*px[^;]*(?:#|rgba?\(|hsla?\(|oklch\()(?!\s*0\s*,\s*0\s*,\s*0)"
                r"|\bshadow-\[0_0_|\bshadow-(?:indigo|violet|purple|blue|cyan|emerald|green|pink)-\d{3}", re.I),
     "그림자는 깊이(offset+blur)만. 색 번짐(halo) 금지"),
    ("oversized-radius", "warn", re.compile(r"\brounded-(?:2xl|3xl)\b|border-radius\s*:\s*(?:1[6-9]|[2-9]\d)px", re.I),
     "radius 3단계 토큰(--r-sm/md/lg). 위계별로 다르게"),
    ("caps-label", "warn", re.compile(r"text-transform\s*:\s*uppercase|\buppercase\b(?=[^\"'\n]*\btracking-)|\btracking-(?:wide|wider|widest)\b", re.I),
     "문장형 라벨. 위계는 크기·색으로"),
    ("arrow-cta", "warn", re.compile(r"(?:\u2192|-&gt;)\s*</(?:a|button)>", re.I),
     "동사로 무엇이 일어나는지 (\"로그 열기\")"),
    ("blob-decor", "warn", re.compile(r"filter\s*:\s*blur\(\s*(?:[3-9]\d|\d{3,})px|\bblur-(?:2xl|3xl)\b|\bblur-\[(?:[3-9]\d|\d{3,})px\]", re.I),
     "흐린 색 덩어리(blob·glow) 장식 빼기. 배경은 표면 토큰 단색"),
    ("infinite-motion", "warn",
     re.compile(r"animation\s*:(?![^;]*(?:spin|rotat|load|progress|skel|shimmer))[^;]*\binfinite\b|\banimate-(?:pulse|ping|bounce)\b", re.I),
     "무한 반복 모션은 ack 안 된 알람·진행 중 표시에만. 상태와 무관한 'LIVE' 깜빡임 금지"),
    ("hover-scale", "warn", re.compile(r"\bhover:(?:scale-\d|-translate-y-)|:hover\s*\{[^}]*transform\s*:\s*(?:scale|translateY\(-)", re.I),
     "hover 는 배경·테두리 한 단계 변화로. 카드가 떠오르거나 커지지 않게"),
]

# 문구 — 마크업 파일에서만 (코드 주석·테스트 fixture 는 보지 않는다)
COPY_RULES = [
    ("placeholder-copy", "warn", re.compile(r"\b(?:Jane|John) Doe\b|\bAcme(?: Corp| Inc)?\b|lorem ipsum|홍길동", re.I),
     "실제 데이터·실제 문구로. 없으면 {{name}} 처럼 비어 있음을 드러낸다 — 지어낸 숫자·후기·로고도 금지"),
    ("hype-copy", "warn",
     re.compile(r"\b(?:seamless(?:ly)?|revolutioni[sz]\w*|next-gen(?:eration)?|cutting-edge|game-?chang\w*|supercharg\w*|unleash\w*|effortless(?:ly)?)\b"
                r"|혁신적|차세대|획기적|원활한|손쉽게", re.I),
     "무엇을 하는지 제품 자신의 명사·동사로 (\"로봇 12대 상태를 한 표에서\")"),
    ("exclaim-copy", "warn", re.compile(r">[^<>{}\n]*[가-힣A-Za-z][^<>{}\n]*[!！]\s*<"),
     "화면 문구에 느낌표 없이 평서문으로"),
    ("greeting-copy", "warn", re.compile(r"\bwelcome back\b|다시 오신 것을 환영|환영합니다|반가워요", re.I),
     "제목은 맥락 이름(페이지·기간 — \"11월 수집 현황\")으로"),
]
MARKUP_EXTS = {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".astro"}

AI_FONTS = ["Inter", "Roboto", "Geist", "Space Grotesk", "Instrument Serif", "Syne", "Fraunces",
            "Plus Jakarta Sans", "DM Sans", "Manrope", "Outfit"]
FONT_RE = re.compile(r"font-family\s*:\s*([^;}\n]+)|fonts\.googleapis\.com/css2?\?family=([^\"'&)\s]+)|from\s+[\"']next/font/google[\"'];?|\b(?:" +
                     "|".join(re.escape(f).replace(r"\ ", "_") for f in AI_FONTS) + r")\s*\(", re.I)
EMOJI_RE = re.compile("[\U0001F300-\U0001FAFF\u2728\u2B50\u26A1\u2705\u274C]")  # 그림 이모지만 — ✕ ✓ ★ ▾ ⚠ 같은 UI 기호는 정상
HANGUL_RE = re.compile("[가-힣]")
COLOR_LIT_RE = re.compile(r"#[0-9a-fA-F]{3,8}\b|\b(?:rgba?|hsla?|oklch|oklab|lab|lch)\(")
WAIVE_RE = re.compile(r"design-lint:\s*allow\s+([\w,-]+)\s*(?:—|--|-|:)\s*\S")
TOKEN_BLOCK_RE = re.compile(r"(:root|\[data-theme[^\]]*\]|\.theme-[\w-]+|@theme)\s*[^{]*\{", re.I)


def linked_css(path, text):
    """HTML 이 <link rel=stylesheet> 로 부르는 로컬 CSS 내용 — 파일 전체 성질(keep-all·color-scheme)은 거기 있을 수 있다."""
    out = []
    base = os.path.dirname(os.path.abspath(path))
    for tag in re.findall(r"<link\b[^>]*>", text, re.I):
        if not re.search(r"rel\s*=\s*[\"']?stylesheet", tag, re.I):
            continue
        m = re.search(r"href\s*=\s*[\"']([^\"']+)", tag, re.I)
        if not m or re.match(r"[a-z]+:|//", m.group(1), re.I):
            continue
        href = m.group(1).split("?")[0].lstrip("/")
        d, cands = base, []
        for _ in range(6):  # "/static/app.css" 같은 절대 경로는 위로 올라가며 찾는다
            cands.append(os.path.join(d, href))
            d = os.path.dirname(d)
        cands.append(os.path.join(base, os.path.basename(href)))
        for c in cands:
            if os.path.isfile(c):
                try:
                    out.append(open(c, encoding="utf-8", errors="replace").read())
                except OSError:
                    pass
                break
    return "\n".join(out)


def strip_token_blocks(text):
    """:root·[data-theme]·.theme-*·@theme 블록 안은 토큰 정의라 색 리터럴이 정상이다 — 공백으로 지운다(줄 번호 유지)."""
    out = list(text)
    for m in TOKEN_BLOCK_RE.finditer(text):
        depth, i = 0, m.end() - 1
        while i < len(text):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    break
            i += 1
        for j in range(m.end(), min(i, len(text))):
            if out[j] != "\n":
                out[j] = " "
    return "".join(out)


def waived(lines, idx, rule):
    for k in (idx, idx - 1):
        if 0 <= k < len(lines):
            m = WAIVE_RE.search(lines[k])
            if m and (rule in m.group(1).split(",") or m.group(1) == "all"):
                return True
    return False


def is_token_file(path):
    b = os.path.basename(path).lower()
    return b.startswith(("tokens", "theme", "variables", "design-tokens")) or b == "tailwind.config.js" or b == "tailwind.config.ts"


def lint_text(path, text):
    findings = []
    lines = text.split("\n")
    ext = os.path.splitext(path)[1].lower()

    def add(rule, sev, i, snippet, fix):
        if not waived(lines, i, rule):
            findings.append({"rule": rule, "severity": sev, "file": path, "line": i + 1,
                             "snippet": snippet.strip()[:120], "instead": fix})

    for i, line in enumerate(lines):
        for rule, sev, pat, fix in LINE_RULES:
            m = pat.search(line)
            if m:
                add(rule, sev, i, line, fix)
        if ext in MARKUP_EXTS:
            for rule, sev, pat, fix in COPY_RULES:
                if pat.search(re.sub(r"<!--.*?-->|//.*$|/\*.*?\*/", "", line)):
                    add(rule, sev, i, line, fix)
        if ext in MARKUP_EXTS and EMOJI_RE.search(line):
            add("emoji-icon", "fail", i, line, "아이콘은 동작·상태를 구분할 때만, 라이브러리 1개·stroke 1종. 장식이면 빼기")

    # 둥근 카드의 한쪽 색띠 — 같은 규칙 블록(또는 같은 class 문자열)에 radius 와 한쪽 두꺼운 테두리가 함께 있을 때만.
    # 표 칸·트리 들여쓰기의 border-left 는 정상이라 줄 단위로 보지 않는다.
    stripe_fix = "전체 테두리·옅은 배경 tint·앞쪽 상태 모양+문장"
    for m in re.finditer(r"\{([^{}]*)\}", text):
        body = m.group(1)
        s = re.search(r"border-(?:left|top)\s*:\s*[2-8]px\s+solid", body, re.I)
        if s and re.search(r"border-radius\s*:\s*(?!0(?:px)?\s*[;}]|0$)[\d.]+", body, re.I):
            add("side-stripe", "warn", text.count("\n", 0, m.start(1) + s.start()), body, stripe_fix)
    for i, line in enumerate(lines):
        for cls in re.findall(r"class(?:Name)?\s*=\s*[\"'`{]([^\"'`}]*)", line):
            if re.search(r"\bborder-[lt]-(?:[2-8]|\[[2-8]px\])\b", cls) and re.search(r"\brounded(?!-none)\b", cls):
                add("side-stripe", "warn", i, line, stripe_fix)

    # 토큰 밖 색 리터럴
    if not is_token_file(path):
        body = strip_token_blocks(text)
        for i, line in enumerate(body.split("\n")):
            if COLOR_LIT_RE.search(line) and not re.search(r"design-lint|url\(|&#|\bhref=|\bsrc=", line):
                add("raw-color", "warn", i, lines[i], "역할 토큰(var(--text-dim) 등). 없으면 토큰을 추가")

    # 흔한 AI 폰트 — 첫 번째 family 가 목록에 있을 때만
    for i, line in enumerate(lines):
        for m in FONT_RE.finditer(line):
            fam = (m.group(1) or m.group(2) or m.group(0) or "")
            first = re.split(r"[,:]", fam.replace("_", " ").replace("+", " ").strip())[0].strip(" \"'(")
            if m.group(0).lower().startswith("from") or first.lower() in {"system-ui", "-apple-system", "sans-serif", "arial"} \
                    or any(re.fullmatch(re.escape(f) + r"(?:\s+(?:var|variable|display))?", first, re.I) for f in AI_FONTS):
                if m.group(0).lower().startswith("from"):
                    continue  # next/font import 줄 자체는 판단하지 않는다 — 실제 호출(Inter(…))에서 잡는다
                add("ai-default-font", "warn", i, line,
                    "제품 맥락(폭·숫자 형태·한글 지원)에서 고르고 이유를 DESIGN.md 에. 2세대 대체 폰트(Geist·Space Grotesk·Instrument Serif·Syne·Fraunces)도 이미 흔하다")

    linked = linked_css(path, text) if ext in {".html", ".htm"} else ""

    # 한글 줄바꿈 — 파일(과 부르는 CSS)에 한글 문구가 있는데 keep-all 이 없음
    if ext in {".html", ".htm", ".jsx", ".tsx", ".vue", ".svelte", ".astro"} and HANGUL_RE.search(re.sub(r"<!--.*?-->|//[^\n]*|/\*.*?\*/", "", text, flags=re.S)):
        if not re.search(r"word-break\s*:\s*keep-all|\bbreak-keep\b", text + linked):
            first = next(i for i, l in enumerate(lines) if HANGUL_RE.search(l))
            add("hangul-break", "warn", first, lines[first],
                "word-break: keep-all (Tailwind break-keep) + overflow-wrap: anywhere — 한글이 단어 중간에서 끊기지 않게")

    # 다크 테마인데 color-scheme 없음 → 스크롤바·폼 컨트롤이 밝게 남는다
    if ext in {".css", ".scss", ".html", ".htm"} and re.search(r"prefers-color-scheme\s*:\s*dark|data-theme\s*=?\s*[\"']?dark|\.dark\b", text) \
            and not re.search(r"(?<![\w-])color-scheme\s*:", text + linked):
        add("color-scheme-missing", "warn", 0, "(파일 전체)", ":root{color-scheme: light dark} — 스크롤바·폼 컨트롤·선택색이 테마를 따른다")
    return findings


def scale_findings(path, text):
    """척도 진단 — 파일 단위. 값 종류 수만 센다."""
    out = []
    body = strip_token_blocks(text)
    sizes = set(re.findall(r"font-size\s*:\s*([\d.]+(?:px|rem|em))", body))
    radii = set(re.findall(r"border-radius\s*:\s*([\d.]+px)", body))
    off_grid = sorted({v for v in re.findall(r"(?:padding|margin|gap)[\w-]*\s*:\s*([^;]+)", body)
                       for v in re.findall(r"\b(\d+)px", v) if int(v) % 4 and int(v) not in (1, 2)}, key=int)
    if len(sizes) > 7:
        out.append({"rule": "type-scale", "severity": "warn", "file": path, "line": 0,
                    "snippet": f"font-size {len(sizes)}종: {', '.join(sorted(sizes))}"[:120], "instead": "6~8단계 스케일 토큰(--t-*) 밖의 값 금지"})
    if len(radii) > 3:
        out.append({"rule": "radius-scale", "severity": "warn", "file": path, "line": 0,
                    "snippet": f"border-radius {len(radii)}종: {', '.join(sorted(radii))}", "instead": "--r-sm/md/lg 3단계"})
    if off_grid:
        out.append({"rule": "spacing-grid", "severity": "warn", "file": path, "line": 0,
                    "snippet": f"4px 배수 아닌 간격: {', '.join(off_grid[:8])}px", "instead": "--s-* 간격 토큰(4px 배수)"})
    return out


def iter_files(paths):
    for p in paths:
        if os.path.isfile(p):
            yield p
        else:
            for root, dirs, files in os.walk(p):
                dirs[:] = [d for d in dirs if d not in SKIP_DIRS and not d.startswith(".") and not d.startswith("venv") and d != "site-packages"]
                for f in sorted(files):
                    if os.path.splitext(f)[1].lower() in EXTS and not f.endswith((".min.css", ".min.js")):
                        yield os.path.join(root, f)


def main(argv):
    args = [a for a in argv if not a.startswith("--")]
    as_json, strict = "--json" in argv, "--strict" in argv
    if not args:
        print(__doc__.strip())
        return 2
    findings = []
    for f in iter_files(args):
        try:
            text = open(f, encoding="utf-8", errors="replace").read()
        except OSError as e:
            print(f"읽기 실패: {f}: {e}", file=sys.stderr)
            continue
        findings += lint_text(f, text) + scale_findings(f, text)
    if as_json:
        print(json.dumps(findings, ensure_ascii=False, indent=1))
    else:
        for x in findings:
            loc = f"{x['file']}:{x['line']}" if x["line"] else x["file"]
            print(f"{x['severity'].upper():4}  {x['rule']:<26} {loc}\n      {x['snippet']}\n      → 대신: {x['instead']}")
        nf = sum(x["severity"] == "fail" for x in findings)
        nw = len(findings) - nf
        print(f"\nfail {nf} · warn {nw}" + ("" if findings else " — 결정적 tell 없음 (렌더 확인은 §11)"))
    bad = any(x["severity"] == "fail" for x in findings) or (strict and findings)
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
