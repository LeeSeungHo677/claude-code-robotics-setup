---
name: arxiv-search
description: >
  arXiv 논문 검색 — 로봇·VLA·RL·manipulation·locomotion 최신 연구를 찾을 때. TRIGGER on 논문 찾아줘, arXiv 검색,
  ICRA/RSS/CoRL 최신 연구. 이미 가진 논문을 읽고 요약하는 것은 paper-summarize.
license: MIT
metadata:
  version: 1.0.0
allowed-tools: Bash, Read, Write
---

# arXiv Search Skill

## Overview
최신 로봇공학 논문 검색 및 분류.
Antigravity CLI(agy)의 Google Search 활용 (무료, OAuth 인증).
paper-summarize 스킬과 함께 사용.

## 역할 분담
- Antigravity CLI(agy): 검색 및 1차 요약 (무료, Google Search 내장)
- Claude: 심층 분석, 구현 연결, 지식베이스 정리

## 검색 카테고리 (arXiv)
- cs.RO: Robotics (핵심)
- cs.AI: Artificial Intelligence
- cs.LG: Machine Learning
- eess.SY: Systems and Control

## 주요 학회 일정
| 학회 | 분야 | 시기 |
|------|------|------|
| ICRA | 로봇공학 종합 | 매년 5-6월 |
| RSS | 로봇 시스템 | 매년 7월 |
| CoRL | 로봇 학습 | 매년 11월 |
| IROS | 지능 로봇 | 매년 10월 |
| NeurIPS | AI/ML | 매년 12월 |

## Antigravity(agy) 검색 명령어 패턴
# 최신 논문 검색
agy --print "2025년 이후 quadruped locomotion arXiv 논문 5개 요약"

# VLA 특화 검색
agy --print "최근 VLA Vision-Language-Action 로봇 manipulation 논문 정리"

# sim-to-real 특화
agy --print "2025 sim-to-real transfer robotics 최신 연구 동향"

# AGIBOT 관련
agy --print "AgiBot GO-1 GO-2 ViLLA 관련 최신 논문 및 인용 연구"

## 저장 구조
~/knowledge/papers/
├── daily/        ← 일간 자동 수집
├── rl/           ← 강화학습
├── vla/          ← VLA 모델
├── manipulation/ ← 로봇 팔/조작
├── navigation/   ← AMR/AGV
├── humanoid/     ← 휴머노이드
└── quadruped/    ← 4족 보행

## 자동 수집 — 이미 돌고 있다. 새로 만들지 않는다

```
crontab        0 6 * * *   ~/knowledge/scripts/daily_paper_collection.sh
~/.anacrontab  1  5        같은 스크립트 (노트북이 꺼져 있던 날 보충 실행)
```

결과는 `~/knowledge/papers/<카테고리>/YYYYMMDD.md`, 로그는 `~/knowledge/papers/daily/cron.log`.

## Common Workflows
1. 특정 주제 최신 논문 검색
2. 주간 동향 정리
3. 특정 저자/연구소 추적
4. 학회별 주요 논문 수집
5. AGIBOT 관련 인용 논문 추적

## Gotchas
- 검색은 Antigravity CLI(agy), 분석은 Claude (비용 최적화)
- 날짜 필터 항상 포함 (2024년 이후)
- 결과는 ~/knowledge/papers/ 에 반드시 저장
- paper-summarize 스킬과 함께 사용 권장

## References
- ~/knowledge/papers/ — 전체 논문 저장소
- scripts/daily_paper_collection.sh — 자동 수집
