---
name: paper-summarize
description: >
  가진 논문을 읽고 요약·핵심 추출. TRIGGER on 이 논문 요약해줘, arXiv 링크 내용 정리, 논문 분석. 논문을 찾는 것은 arxiv-search.
license: MIT
metadata:
  version: 1.0.0
allowed-tools: Read, Write
---

# Paper Summarize Skill

## Overview
로봇공학 논문 분석 및 요약. Antigravity CLI(agy)와 협업하여
조사(agy) → 분석/정리(Claude) 역할 분담.

## Antigravity CLI 협업 패턴
Step 1: agy가 논문 검색 (무료, Google Search 내장)
agy --print "2025년 이후 quadruped locomotion 최신 논문 5개 요약"

Step 2: Claude가 심층 분석 및 구현 연결
claude "위 논문 중 Isaac Lab 구현에 적합한 것 분석해줘"

## 주요 검색 카테고리 (arXiv)
- cs.RO: Robotics (핵심)
- cs.AI: Artificial Intelligence
- cs.LG: Machine Learning
- eess.SY: Systems and Control

## 주요 학회
- ICRA, RSS, CoRL, IROS (로봇공학 4대 학회)
- RAL (IEEE Robotics and Automation Letters)
- NeurIPS, ICLR (AI/ML)

## 요약 출력 형식
- 논문 제목
- 저자/기관/연도
- 핵심 기여 (2-3줄)
- 방법론 요약
- 실험 결과 (주요 수치)
- AGIBOT 적용 가능성
- 원문 링크

## Output Protocol
- 저장 위치: ~/knowledge/papers/[카테고리]/YYYYMMDD_제목.md
- 일간 수집본: ~/knowledge/papers/daily/YYYYMMDD.md
- 중요 논문은 해당 카테고리 폴더에 별도 저장

## Common Workflows
1. 특정 주제 최신 논문 검색 및 요약
2. 특정 저자/연구소 논문 추적
3. 학회 논문 일괄 요약 (ICRA, CoRL 등)
4. 논문 → 구현 가능성 분석 (Isaac Lab 연결)
5. 일간 자동 수집 스크립트 실행

## Gotchas
- Antigravity CLI(agy)로 검색 후 Claude로 분석 (비용 최적화)
- 날짜 필터 항상 포함 (2024년 이후)
- AGIBOT 관련성 항상 명시
- 논문 링크 반드시 포함 (arXiv ID 또는 URL)

## References
- ~/knowledge/papers/ — 전체 논문 저장소
- scripts/daily_paper_collection.sh — 자동 수집
