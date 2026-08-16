---
name: cloud-gpu-job
description: >
  원격 GPU 학습 — 로컬에 GPU 가 없거나 VRAM 이 모자랄 때 RunPod/Vast.ai 로 보낸다. 인스턴스 생성, 잡 실행, 비용 관리. TRIGGER on
  RunPod, 클라우드 GPU, A100/H100, 원격 학습 서버, GPU 비용.
license: MIT
metadata:
  version: 1.0.0
allowed-tools: Bash, Read, Write
---

# Cloud GPU Job Skill

## Overview
RunPod/Vast.ai 클라우드 GPU 잡 설정 및 관리.

**먼저 로컬 워크스테이션으로 되는지 확인한다.** 이 스킬은 로컬 VRAM 을 넘는
대규모 학습(80GB+ 멀티 GPU)이거나 로컬에 GPU 가 아예 없을 때만 쓴다 —
클라우드 GPU 는 시간당 과금이라 **켜두고 잊으면 그대로 비용**이다.

## 플랫폼 비교
| 플랫폼 | A100 80GB | 특징 |
|--------|-----------|------|
| RunPod | ~$1.5/시간 | UI 편리, 안정적 |
| Vast.ai | ~$0.66/시간 | 저렴, 가용성 변동 |
| AWS EC2 | ~$3.0/시간 | 회사 계정 사용 가능 |

## 작업별 GPU 권장 사양
| 작업 | 최소 | 권장 |
|------|------|------|
| GO-1 추론 | RTX 4090 16GB | A100 40GB |
| LoRA 파인튜닝 | A100 40GB | A100 80GB |
| 풀 파인튜닝 | A100 80GB x2 | A100 80GB x4 |
| Isaac Lab RL | RTX 3090 | A100 80GB |

## RunPod 기본 워크플로우
# 1. Pod 생성 (RunPod CLI)
runpodctl create pod --gpu A100 --image pytorch/pytorch:2.0-cuda11.7

# 2. SSH 접속
ssh root@[pod-ip] -p [port]

# 3. 작업 실행
python train_go1.py --config config.yaml

# 4. 결과 S3 백업 (종료 전 필수)
aws s3 sync ./outputs s3://bucket/experiments/$(date +%Y%m%d)/

# 5. Pod 종료
runpodctl remove pod [pod-id]

## 비용 최적화
- Spot 인스턴스 활용 (최대 70% 절약, 중단 위험 있음)
- 학습 중간 체크포인트 S3 저장 필수
- 필요한 시간만 켜고 즉시 종료
- Vast.ai는 짧은 실험용, RunPod은 장기 학습용

## Common Workflows
1. GPU 잡 생성 및 환경 설정
2. 학습 코드 업로드 및 실행
3. 학습 모니터링 (TensorBoard, WandB)
4. 결과 S3 백업
5. Pod 종료 및 비용 확인

## Gotchas
- 잡 종료 전 반드시 결과 백업 (데이터 손실 위험)
- Spot 인스턴스 중단 대비 체크포인트 주기적 저장
- 환경 변수(API 키 등) 코드에 하드코딩 금지
- 비용 알람 설정 필수 (예상치 못한 과금 방지)
- 파인튜닝 파이프라인 스킬과 함께 사용

## References
- scripts/ — GPU 잡 자동화 스크립트
- ~/knowledge/experiments/ — 실험 결과 로그
