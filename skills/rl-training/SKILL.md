---
name: rl-training
description: >
  RL 학습 파이프라인 — 보상함수 설계, PPO/SAC/TD3 설정, 학습 불안정 진단, 학습 곡선 분석. TRIGGER on 강화학습, 보상함수, PPO, SAC,
  학습이 발산함, gymnasium, Isaac Lab 학습.
license: MIT
metadata:
  version: 1.0.0
allowed-tools: Bash, Read, Write
---

# RL Training Skill

## Overview
Isaac Lab 기반 강화학습 파이프라인 설계 및 실행.
AGIBOT D1(4족), X2(휴머노이드), G2(매니퓰레이션) 대응.
클라우드 GPU 기반 학습 (cloud-gpu-job 스킬 연동).

## 지원 알고리즘
| 알고리즘 | 특징 | 사용 시나리오 |
|---------|------|-------------|
| PPO | 안정적, 범용 | 기본값, 보행 제어 |
| SAC | 샘플 효율, 연속 액션 | 매니퓰레이션 |
| TD3 | 결정론적 정책 | 로봇 팔 정밀 제어 |

## 보상함수 설계 원칙
def reward_function(obs, action):
    reward = 0
    # 1. 목표 달성 보상 (sparse or dense)
    reward += goal_reward(obs)
    # 2. 자연스러운 동작
    reward -= joint_velocity_penalty(obs) * 0.01
    # 3. 에너지 효율
    reward -= energy_penalty(action) * 0.001
    # 4. 안전 제약 패널티
    if collision_detected(obs):
        reward -= 10.0
    return reward

## Isaac Lab 핵심
- Isaac Gym 공식 후속작 (직접 호환 안됨)
- GPU 병렬 물리 시뮬레이션 (수천 개 환경 동시)
- RL + IL 동시 지원
- 도메인 랜덤화 도구 내장
- AGIBOT Genie Sim 3.0과 병행 사용 가능

## 학습 파이프라인
Isaac Lab 환경 설계
  → 보상함수 정의
  → 하이퍼파라미터 설정
  → 클라우드 GPU 학습 (cloud-gpu-job)
  → 학습 곡선 분석
  → sim-to-real 검증 (sim-to-real-check 스킬)
  → 실제 로봇 배포

## 하이퍼파라미터 기본값 (PPO)
- num_envs: 4096 (GPU 메모리에 따라 조정)
- learning_rate: 3e-4
- max_epochs: 1000
- batch_size: 4096
- clip_range: 0.2

## Common Workflows
1. 환경 설계 (observation/action space, reward)
2. Isaac Lab 환경 생성
3. 클라우드 GPU 잡 실행
4. 학습 곡선 모니터링 (TensorBoard)
5. 하이퍼파라미터 튜닝
6. sim-to-real 검증

## Gotchas
- Isaac Gym 코드는 Isaac Lab으로 마이그레이션 필요
- GPU 메모리 부족 시 num_envs 먼저 줄이기
- sim-to-real: 도메인 랜덤화 필수
- 학습 불안정 시 learning rate 먼저 확인
- 중간 체크포인트 S3 저장 필수 (클라우드 중단 대비)

## References
- ~/knowledge/papers/rl/ — RL 관련 논문
- ~/knowledge/concepts/reinforcement-learning.md
- scripts/ — 학습 자동화 스크립트
