---
name: sim-to-real-check
description: >
  시뮬→실기 이관 검증 — domain randomization 설정 점검, sim-to-real 갭 분석, 실기 투입 전 체크리스트. TRIGGER on
  sim-to-real, 시뮬과 실제가 다름, 도메인 랜덤화, 실기 투입 전 검증.
license: MIT
metadata:
  version: 1.0.0
allowed-tools: Bash, Read, Write
---

# Sim-to-Real Check Skill

## Overview
시뮬레이션 학습 정책을 실제 AGIBOT 로봇에 배포하기 전
sim-to-real 갭 검증 및 체크리스트 실행.

## Sim-to-Real 갭 주요 원인
1. 물리 모델 불일치 (마찰, 관성, 댐핑)
2. 센서 노이즈 차이 (카메라, IMU, 힘 센서)
3. 액추에이터 지연 (모터 응답 시간)
4. 환경 조명/배경 차이 (시각 정책)
5. 접촉 모델 불일치 (그리퍼, 발바닥)

## 도메인 랜덤화 설정 (Isaac Lab)
# 물리 파라미터 랜덤화
randomization:
  friction: [0.5, 1.5]
  mass_scale: [0.8, 1.2]
  damping_scale: [0.8, 1.2]
  motor_strength_scale: [0.9, 1.1]

# 센서 노이즈 추가
observation_noise:
  joint_pos: 0.01
  joint_vel: 0.05
  imu: 0.02

# 외란 추가
push_robots: true
push_interval: 10
push_force: [0, 5]

## 배포 전 체크리스트
1. 시뮬레이션 성공률 > 90% 확인
2. 도메인 랜덤화 설정 검토
3. Policy Server 연결 테스트
4. 로봇 관절 한계값 확인
5. 비상 정지(E-stop) 동작 확인
6. 저속 모드에서 첫 실행
7. 센서 데이터 정상 수신 확인
8. 실제 환경 데이터로 재학습 계획 수립

## AGIBOT 배포 프로세스
Isaac Lab 학습
  → 체크리스트 통과
  → Policy Server 배포 (클라우드)
  → AGIBOT 로봇 연결 (AimRT)
  → 저속 테스트 실행
  → 성능 데이터 수집
  → AWS S3 저장 → SageMaker 재학습

## 실제 환경 데이터 수집
- 실패 케이스 원인 분석 필수
- 센서 데이터 MQTT → AWS IoT Core → S3
- 수집 데이터로 sim 환경 보정

## Common Workflows
1. 도메인 랜덤화 설정 검토 및 보강
2. 시뮬레이션 성공률 분석
3. 배포 전 체크리스트 실행
4. 실제 로봇 저속 테스트
5. 실패 케이스 분석 및 시뮬 보정

## Gotchas
- 처음 실제 로봇 실행은 반드시 저속 모드
- E-stop 항상 준비된 상태에서 실행
- 시뮬 성공률 90% 이하면 재학습 필요
- 실제 환경 데이터 수집 후 반드시 재학습
- robotics-testing 스킬과 함께 사용 권장

## References
- ~/knowledge/concepts/sim-to-real.md
- ~/knowledge/papers/rl/ — sim-to-real 논문
- 현재 작업 레포 — 로봇별 배포 기록
