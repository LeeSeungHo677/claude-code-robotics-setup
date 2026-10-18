---
name: drawio
description: >
  draw.io(diagrams.net) `.drawio` 파일을 **직접 작성·수정**한다. TRIGGER when the user asks for a
  drawio/diagrams.net file, edits `.drawio`/`.drawio.png`/`.drawio.svg`, hand-places a diagram
  (배선도·버스 토폴로지·랙/셀 배치·E-stop 체인·네트워크 구성도·공정도), converts a diagram to
  PDF/PNG/SVG from the command line, or says "다이어그램이 안 열린다 / 도형이 안 보인다 /
  선이 엉뚱하게 돌아간다". 코드와 함께 변하는 다이어그램은 Mermaid 가 낫다 → `system-architecture`.
---

# draw.io (`.drawio`) 직접 작성

**핵심 전제: `.drawio` 는 mxGraph XML 이다.** 손으로 쓸 수 있고, 그래야 diff 가 읽힌다.
GUI 가 기본으로 저장하는 **압축본은 쓰지 않는다** — base64+deflate 라 리뷰가 불가능하다.

## 먼저 — drawio 인가 Mermaid 인가

| 상황 | 선택 | 왜 |
|---|---|---|
| README·설계문서 안, 코드와 같이 바뀜 | **Mermaid** (`system-architecture`) | 텍스트 한 줄 고치면 끝. 배치를 신경 안 써도 됨 |
| 노드/엣지 관계만 중요 | **Mermaid** | 자동 배치가 충분하다 |
| **위치 자체가 정보** (랙 배치, 셀 레이아웃, 배선 경로, 평면도) | **drawio** | 자동 배치는 이 정보를 파괴한다 |
| 비개발자에게 넘김 (현장·고객·안전 검토) | **drawio** | 받는 사람이 GUI 로 고칠 수 있다 |
| 아이콘·사진·치수 표기가 필요 | **drawio** | Mermaid 로는 못 한다 |

**둘을 섞지 않는다.** 같은 그림이 두 곳에 있으면 한쪽은 반드시 낡는다.

## 최소 골격 — 이대로 시작한다

```xml
<mxfile host="app.diagrams.net">
  <diagram name="개요" id="page1">
    <mxGraphModel dx="800" dy="600" grid="1" gridSize="10" page="1"
                  pageWidth="1169" pageHeight="826" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>

        <mxCell id="vr" value="Pico 4 VR" style="rounded=1;whiteSpace=wrap;html=1;"
                vertex="1" parent="1">
          <mxGeometry x="40" y="40" width="160" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="drv" value="gripper driver&#10;(RS485)" style="rounded=1;whiteSpace=wrap;html=1;"
                vertex="1" parent="1">
          <mxGeometry x="280" y="40" width="160" height="60" as="geometry"/>
        </mxCell>

        <mxCell id="e1" value="90.9 Hz" style="edgeStyle=orthogonalEdgeStyle;html=1;"
                edge="1" parent="1" source="vr" target="drv">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
      </root>
    </mxGraphModel>
  </diagram>
</mxfile>
```

**`id="0"` 과 `id="1"` 은 생략할 수 없다.** 모든 도형의 `parent` 는 `"1"`(또는 그룹 id)이다.

## 반드시 지키는 것 — 여기서 대부분 깨진다

- **`vertex="1"` / `edge="1"` 을 빼면 셀이 렌더링되지 않는다.** 파일은 열리는데 화면이 빈다.
- **`<mxGeometry ... as="geometry"/>` 의 `as="geometry"` 를 빼면 무시된다.** 도형이 (0,0)에 겹친다.
- 엣지의 geometry 는 `relative="1"` 이어야 한다. 좌표는 주지 않는다(양 끝이 정한다).
- **라벨의 XML 이스케이프.** `<` → `&lt;`, `&` → `&amp;`, `"` → `&quot;`.
  `value="a < b"` 한 글자로 파일 전체가 안 열린다.
- **줄바꿈은 `&#10;`** (또는 `html=1` 에서 `&lt;br&gt;`). 실제 개행 문자는 무시된다.
- **좌표계: 원점 좌상단, y 는 아래로 증가.** 수학 좌표로 생각하면 그림이 뒤집힌다.
- `id` 는 파일 안에서 유일해야 한다. 복붙으로 중복되면 **뒤의 것이 조용히 사라진다.**

## 증상 → 원인

| 증상 | 원인 |
|---|---|
| 파일이 안 열린다 / "not a valid file" | 라벨의 `<`·`&` 미이스케이프. 또는 `<mxCell id="0"/>` 누락 |
| 열리는데 **아무것도 안 보인다** | `vertex="1"`/`edge="1"` 누락, 또는 `parent` 가 존재하지 않는 id |
| 도형이 전부 좌상단에 겹친다 | `as="geometry"` 누락 |
| 글자가 도형 밖으로 넘친다 | style 에 `whiteSpace=wrap;html=1;` 없음 |
| 선이 엉뚱하게 크게 돌아간다 | `exitX/exitY/entryX/entryY` 미지정 → 라우터가 임의 선택 |
| 선이 도형 뒤로 숨는다 | z-order = XML 순서. 엣지를 도형보다 **뒤에** 썼다 |
| 컨테이너 안 도형이 엉뚱한 곳에 | 자식 geometry 는 **부모 기준 상대 좌표**다 |
| GUI 로 저장했더니 diff 가 깨진다 | 압축 저장. Extras → Edit Diagram 또는 설정에서 압축 끄기 |
| PNG 로 export 했는데 나중에 편집이 안 된다 | `.drawio.png`(XML 내장)가 아니라 순수 PNG 로 저장 |

## 자주 쓰는 style

```
# 상자
rounded=1;whiteSpace=wrap;html=1;fillColor=#dae8fc;strokeColor=#6c8ebf;
# 강조(위험·주의)
rounded=1;whiteSpace=wrap;html=1;fillColor=#f8cecc;strokeColor=#b85450;
# 점선 상자(범위·경계)
rounded=0;whiteSpace=wrap;html=1;dashed=1;fillColor=none;
# 컨테이너(레인)
swimlane;horizontal=0;startSize=30;html=1;
# 엣지 — 포트를 고정한다 (라우터에 맡기지 않는다)
edgeStyle=orthogonalEdgeStyle;rounded=0;html=1;exitX=1;exitY=0.5;entryX=0;entryY=0.5;
# 점선 엣지(선택적·미확인 경로)
edgeStyle=orthogonalEdgeStyle;dashed=1;html=1;
```

`exitX/entryX` 는 도형 기준 **0..1 상대값**이다 (`0,0.5` = 왼쪽 가운데).
**선이 지저분하면 십중팔구 이걸 안 준 것이다.**

## 배치는 사람이 한다

drawio 파일에는 자동 배치가 없다. 좌표를 직접 쓴다 → **격자를 미리 정한다.**

- `gridSize=10` 에 맞춰 좌표를 10의 배수로. 손으로 고칠 때 스냅이 맞는다
- 열 간격은 도형 폭 + 80\~120, 행 간격은 높이 + 60\~80 정도가 읽힌다
- 한 페이지가 넘치면 `<diagram>` 을 하나 더 만든다. 줄여 넣지 않는다
- 신호가 왼→오른쪽, 계층이 위→아래. **한 그림에서 방향을 섞지 않는다**

## 로봇 작업에서 쓸 곳

Mermaid 로는 안 되는 것만 drawio 로 그린다.

| 그림 | 왜 drawio 인가 |
|---|---|
| **E-stop 체인 / 안전 회로** | 접점이 어디에 물리는지가 위치로 표현된다. 안전 검토자가 GUI 로 고친다 |
| 버스 토폴로지 (RS485·CAN·EtherCAT) | 종단저항·분기·슬레이브 주소를 물리 배치대로 |
| 배선·커넥터 핀아웃 | 핀 번호와 색을 표로 붙여야 한다 |
| 작업 셀 레이아웃 | 로봇 도달범위·펜스·작업대 위치가 곧 정보다 |
| 랙/PC 구성 | 어느 포트가 어디에 꽂히는지 |

**단위와 좌표계를 그림 안에 쓴다** (mm/m, 어느 frame 기준). 그림은 코드보다 오래 남는데
단위가 없으면 6개월 뒤에 못 읽는다.

## 파일 형식 선택

| 확장자 | 편집 가능 | 쓸 곳 |
|---|---|---|
| `.drawio` | ✅ | **기본값.** 저장소에 넣는 원본 |
| `.drawio.png` | ✅ (XML 내장) | 문서에 바로 붙이면서 원본도 유지 |
| `.drawio.svg` | ✅ (XML 내장) | 웹·확대가 필요한 곳 |
| `.png` / `.pdf` | ❌ | 최종 산출물만. 저장소의 단일 원본으로 쓰지 않는다 |

## 명령줄 export

```bash
# drawio-desktop 필요. 헤드리스(CI·서버)에서는 xvfb 와 --no-sandbox 가 필요하다
drawio -x -f pdf -o docs/architecture.pdf docs/architecture.drawio
xvfb-run -a drawio -x -f png --scale 2 -o out.png in.drawio --no-sandbox
```

헤드리스에서 **아무 메시지 없이 종료되면** 거의 항상 디스플레이(`xvfb-run`) 아니면
샌드박스(`--no-sandbox`) 문제다. 버전 플래그는 자주 바뀌므로 `drawio --help` 로 확인한다.

## 편집 수단

- **VS Code**: `hediet.vscode-drawio` — `.drawio` 를 에디터에서 바로 연다. XML 과 GUI 를 오간다
- **GUI 에서 XML 보기**: Extras → Edit Diagram. 여기에 통째로 붙여넣는 것이 가장 빠르다
- **압축 끄기**: 파일 → 속성 → Compressed 해제 (또는 `<mxfile compressed="false">`)

## 끝내기 전 확인

- [ ] 라벨의 `<`·`&` 를 이스케이프했는가
- [ ] 모든 도형에 `vertex="1"` + `as="geometry"` 가 있는가
- [ ] `id` 가 유일한가
- [ ] 엣지에 `exitX/entryX` 를 줬는가 (안 주면 선이 돌아간다)
- [ ] 단위·좌표계·날짜를 그림 안에 적었는가
- [ ] 같은 내용이 Mermaid 로도 있지 않은가 (한쪽이 반드시 낡는다)
