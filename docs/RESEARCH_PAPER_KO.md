# Semantic Graybox: 의미 기반 그레이박스를 활용한 인간 주도형 생성형 3D 에셋 제작 파이프라인 설계 및 예비 평가

**Semantic Graybox: Design and Preliminary Evaluation of a Human-Guided Generative 3D Asset Pipeline**

> **Independent Research — Preliminary Technical Report**  
> 언어: 한국어 · 문서 버전: 0.1 · 작성 기준일: 2026-10-09  
> 시스템 기준선: Semantic Graybox v0.3.1  
> 상태: 공개 연구 초고 / 동료심사 전 (not peer-reviewed)  
> 저장소: [semantic-graybox](https://github.com/ang9089098-cpu/semantic-graybox)

**설계 원칙: Structure = Human Guidance; Form = Generative Freedom.**

## 초록

생성형 인공지능을 통한 3D 형상 제작은 단일 객체의 생성 가능성을 확대하고 있으나, 생성된 형상이 아티스트의 의도한 부품 정체성, 반복 관계 및 공간 배치를 충족하는지는 별도의 문제다. 본 연구는 아티스트가 Blender의 단순 그레이박스를 통해 구조적 의도를 지정하고, 생성형 모델이 구체적인 형상을 제작하도록 분업하는 **Semantic Graybox** 파이프라인을 제안한다. 시스템은 컬렉션 및 오브젝트 정보로부터 의미·치수·앵커·반복 관계를 추출한 Semantic Blueprint를 구성하고, 이를 생성기 독립적인 요청으로 변환한다. 이어서 순차 생성 큐, 자동 배치·인스턴싱, 인간에 의한 부품별 의미 검토를 수행한다.

예비 실험에서는 가이드 비율에 따른 출력 형상의 반응, Cube3D VQ 계층의 통제 메시 복원, 반복 부품 클러스터링, 의미 역할 임베딩, 자기회귀 조건 전달 및 샘플링 다양성을 조사하였다. 상대적 비율 제어와 구조적 요청·배치 파이프라인의 구현 가능성은 확인했으나, 내부 조건화 지표의 개선이 최종 생성 메시의 부품 의미 정확도로 일관되게 이어지지 않았으며 결정적 샘플링으로 인한 평가상 중복 표본 문제가 확인되었다. 본 연구는 **구조적 제작 제어의 시스템 구현**과 **생성 의미 충실도의 미해결 문제**를 구분하여 보고한다.

**주요어:** Semantic Graybox, Generative 3D, Human-in-the-loop, Semantic Control, Blender, Technical Art, Asset Pipeline

---

## 1. 서론

### 1.1 문제 배경

게임 환경 제작은 개별 모델링뿐 아니라 객체의 부품 구성, 반복 부품의 일관성, 배치, 최적화와 수정 가능성을 요구한다. 자연어 기반 3D 생성에서 “침대의 다리 하나”를 요청하는 것과 “침대 전체”를 요청하는 것은 다르지만, 실제 연결한 Cube3D v0.5 생성 경로에서는 독립 부품 대신 전체 가구에 가까운 메시가 출력되는 사례가 관찰되었다.

이 관찰을 모든 생성형 3D 모델의 일반적 한계라고 주장하지는 않는다. 본 연구는 **생성기에 맡겨야 할 형상 제작**과 **사람이 보존해야 할 구조·의미·배치 정보**를 분리하면 어떤 제작 제어가 가능한지 살펴본다.

### 1.2 연구 질문

- **RQ1 — 표현:** Blender 그레이박스에서 의미 및 공간 구조를 추출하여 생성 요청으로 변환할 수 있는가?
- **RQ2 — 실행:** 반복 형상과 고유 형상을 구분해 생성 호출과 배치를 구조 단위로 제어할 수 있는가?
- **RQ3 — 생성:** 상대 비율 및 부품 역할 조건화는 최종 메시 형상에 어떻게 반영되는가?
- **RQ4 — 평가:** 실행 성공과 사람이 판정하는 의미적 적합성을 별개로 기록할 수 있는가?

### 1.3 기여와 범위

본 연구는 새로운 3D 기초 모델보다 **생성기 독립적 제작 제어 계층**의 설계와 예비 평가에 초점을 둔다.

1. Blender 컬렉션 기반의 **Semantic Blueprint** 표현
2. 고유 부품과 반복 **Master/Slot**의 분해
3. **GenerationRequest — Adapter — FIFO Queue**의 분리
4. Blender 결과 배치 및 공유 메시 인스턴싱
5. **Human Semantic Review**와 불변 요청 스냅샷 및 추가형 로그
6. Cube3D 기반 기하학·표현 계층·의미 조건화의 실험적 진단

구현 성공, 실험에서 관찰된 변화, 일반화 가능한 성능 개선을 서로 구분하여 기술한다.

## 2. 관련 기술

### 2.1 3D 생성 및 형상 표현

NeRF[1] 및 3D Gaussian Splatting[2]은 3차원 장면 표현과 새로운 시점 렌더링의 대표적 접근이다. 다만 본 연구는 **편집 가능한 메시 부품과 조립 구조**에 중점을 두므로 두 기술의 영상 합성 품질을 직접 평가하지 않는다.

Roblox Cube[3]는 3D 형상 토큰화 및 생성을 다룬다. 본 연구는 로컬에 설치된 **Cube3D v0.5**를 외부 생성기로 사용하며, 그 모델·가중치·소스는 Semantic Graybox 고유 기여에 포함하지 않는다.

### 2.2 부품 수준 구조

PartNet[4]은 3D 객체에 부품 수준의 세밀한 의미 주석과 계층 구조를 제공한다. Semantic Graybox는 부품 표현의 중요성을 공유하지만, 완성 메시를 사후 분할하기보다는 **아티스트가 생성 이전에 부품·배치 정보를 그레이박스로 작성한다**는 접근을 취한다. PartNet 기반 학습 및 실험은 아직 수행하지 않았다.

## 3. 제안 시스템

### 3.1 설계 원칙

**Structure = Human Guidance; Form = Generative Freedom.**

아티스트는 무엇이 어떤 부품이며 어디에 놓이는지 지정하고, 생성기는 각 부품의 구체적인 형태를 제안한다. 그레이박스는 크기·방향·관계에 대한 **soft guidance**로 취급하며, 생성 결과를 해당 박스에 강제로 맞추는 hard fitting을 기본 원리로 사용하지 않는다.

### 3.2 전체 구조

~~~text
Blender Graybox / Collection
             ↓
Semantic Graybox Extractor
             ↓
Semantic Blueprint
  ├─ Entity / Part Identity
  ├─ Transform / Anchors / Dimensions
  ├─ Topology / Constraints
  └─ Unique Parts / Masters / Slots
             ↓
GenerationRequest[]
             ↓
Prompt Builder + FIFO Queue
             ↓
Generator Adapter → External Cube3D
             ↓
OBJ Import → Placement / Shared Instancing
             ↓
Human Semantic Review → JSONL Events
~~~

생성기별 호출은 Adapter에 격리한다. 현 구현은 Cube3D를 별도 Python subprocess로 실행하므로 Blender의 Python 환경과 GPU 모델 런타임을 분리한다. 이는 **확장 가능한 인터페이스**를 뜻하며, 다른 모든 생성기와의 실제 호환성까지 검증했다는 뜻은 아니다.

### 3.3 Semantic Blueprint

| 구성 | 추출 정보 | 사용 목적 |
|---|---|---|
| Entity | 컬렉션 이름·메타데이터 | 상위 객체 문맥 |
| Part | 오브젝트 이름·그룹 키·방향 정보 | 부품 정체성 후보 |
| Transform | 위치·회전·스케일 | 결과 배치 |
| Anchor | 원점·바운딩박스 중심·범위·치수 | 공간 가이드 |
| Topology | 부모-자식 연결 | 구조 관계 |
| Master | 반복 그룹 및 대표 치수 | 공유 형상 생성 |
| Slot | 원본 가이드별 배치 위치 | 인스턴싱 |
| Constraint | 동등 치수 및 일부 비율 관계 | 구조 제약 |

현재 의미 해석은 일부 오브젝트 이름에 의존한다. 예를 들어 Bed의 일반적 명칭인 “Back” 또는 “Front”가 다른 가구에 맞는 역할로 해석되는 문제가 확인되었으므로, 상위 엔티티 문맥을 반영하는 매핑 개선이 필요하다.

### 3.4 반복 부품의 생성 단위화

기하학적 동일성과 배치 동일성을 구분한다. 같은 의미 그룹과 치수 유사성을 만족하는 가이드는 하나의 Master로 처리하고 개별 위치·방향은 Slot에 보존한다.

~~~text
Leg_01 ─┐
Leg_02 ─┼─→ Master A → 1회 생성 → 3개 Slot에 배치
Leg_03 ─┘

Leg_04 ───→ Master B → 1회 생성 → 1개 Slot에 배치
~~~

방향 접미사는 기하학적 그룹을 임의로 쪼개는 기준이 아니라 배치 및 명명 정보로 사용한다. 단, 같은 그레이박스 치수가 최종 생성 메시의 실제 호환성을 보장하지는 않는다.

### 3.5 순차 큐와 배치

GPU 메모리 사용량을 고려해 생성은 FIFO 방식으로 순차 실행한다. 생성 단위별 결과 경로를 분리하고, 일부 요청이 실패하더라도 이전 성공 결과를 일괄 삭제하지 않는다. 원본 그레이박스를 보존하며, 도구가 생성한 미보존 결과에만 삭제 기능을 적용한다.

### 3.6 Human Semantic Review

**실행 상태:** PENDING, GENERATING, DONE, ERROR, KEPT  
**의미 검토 상태:** UNREVIEWED, ACCEPTED, REJECTED

거절 사유는 WRONG_PART, WHOLE_OBJECT, BROKEN_MESH, WRONG_PROPORTION, OTHER로 기록한다. 평가 이벤트에는 생성 당시 요청과 최종 프롬프트, 치수·비율, 결과 식별자와 진단 정보를 포함하며 JSONL 파일에 append-only 방식으로 추가한다. 의미 검토는 **사람의 판정**이지 자동 분류기나 즉시 학습 피드백이 아니다.

## 4. 실험 설계 및 결과

### 4.1 실행 환경과 평가 구분

주요 검증 환경은 Blender 5.2.2 LTS, Cube3D v0.5 및 NVIDIA RTX 5070 Ti 16GB GPU였다. 실험은 **시스템 동작 검증**, **기하학·생성기 분석**, **인간의 의미 적합성 평가**로 구분한다.

OBJ 출력, 연결 컴포넌트 수, 기하학적 비율 또는 teacher-forced margin은 사람의 의미적 수용 판정과 같은 지표가 아니다.

### 4.2 E1: Guide Ratio의 기하학적 조건 반응

고정된 프롬프트 “A rococo carved furniture leg for a desk”로 bbox 전달 비율만 바꾸었다. 생성 후 비균일 스케일 맞춤은 적용하지 않았다.

| 조건 | 입력 비율 | 관측 장축/기준축 비율 | 생성 시간 |
|---|---|---:|---:|
| A0 | bbox 미전달 | 약 1.64 | 72.1초 |
| A1 | 1:1:4 | 약 4.11 | 75.5초 |
| A2 | 1:1:8.75 | 약 9.72 | 72.4초 |
| A3 | 1:1:12 | 약 11.07 | 80.9초 |

조건별 생성이 정상 완료되었고, 출력의 세장비는 입력 비율의 증가 순서를 따랐다. **해당 환경에서 기하학적 조건이 결과 형상에 영향을 주었다**는 관찰을 지지한다.

그러나 **조건당 단일 생성**, **시각적 의미 판정 미실시**, **동일 조건 생성 다양성 미평가**라는 한계가 있다. 비율 제어는 정확한 가구 부품 생성과 동의어가 아니다.

### 4.3 E2: VQ 형상 표현의 통제 메시 복원

자체 제작한 다리형 메시 5개와 완성형 책상 메시 1개를 Cube3D의 **원본 VQ 인코더·디코더**로 round-trip 처리했다. 텍스트·bbox 생성 조건이나 모델 추가 학습을 사용하지 않았다.

| 형상 | 결과 | 관찰 |
|---|---|---|
| L0 단순 다리 | PASS | 기본 실루엣 유지 |
| L1 테이퍼형 다리 | DEGRADED | 컴포넌트 1→10 및 단면 왜곡 |
| L2 곡선 다리 | PASS | 곡선 실루엣 유지 |
| L3 장식 다리 | PASS | 곡선·장식 윤곽 유지 |
| L4 극단적 세장비 | PASS | 가는 실루엣 유지 |
| 완성형 책상 | PASS | 전체 구조 식별 가능 |

모든 6개 샘플이 기계적 인코딩·디코딩에 성공했고, 통제 평가에서는 **5 PASS / 1 DEGRADED**로 분류됐다. L1의 결함을 테이퍼 형상 일반의 문제로 단정할 수 없다.

이 결과는 **제한된 통제 형상의 표현 가능성**을 보여주지만, 자유 생성에서 텍스트·의미 조건을 따라 독립 부품을 선택적으로 생성할 수 있음을 입증하지 않는다.

### 4.4 E3: Master Clustering 수정 및 실생성

Desk 통제 씬에 같은 치수 다리 3개와 다른 치수 다리 1개를 설정했다. 초기 구현은 기대와 다른 **2:2 분할**을 만들었으며, 이를 치수 유사성을 우선하는 그룹화로 수정하여 **3:1** 분할을 확인했다.

| 지표 | 수정 후 실험 결과 |
|---|---|
| Master 그룹 | 2개(3개 Slot + 1개 Slot) |
| 실제 Cube3D 생성 호출 | 2회 |
| Blender 결과 배치 | 4개 |
| 같은 그룹 메시 공유 | 3개 배치가 하나의 메시 데이터 공유 |
| 다른 치수 다리 | 별도 생성 메시 |
| 원본 가이드 | 모두 보존 |
| 생성 시간 | 80.27초 / 81.11초 |

결과 덮어쓰기를 피하기 위해 각 Master의 출력 디렉터리도 분리했다. 이 결과는 **생성 호출 수와 배치 인스턴스 수의 분리**를 검증한다. 네 다리를 모두 독립 생성하는 대조군의 총 제작 시간을 측정하지 않았으므로 실제 속도 향상 배율은 주장하지 않는다.

### 4.5 E4: 다중 생성 큐 및 Human Review 회귀 테스트

v0.3에서는 다중 생성 요청의 순차 실행과 Blender 배치를 구현했고, v0.3.1은 부품별 Accept/Reject와 생성 당시 요청 스냅샷을 추가했다.

최종 기록에서 **Python 테스트 59개**, Blender 기존 워크플로우·다중 큐·의미 검토 스모크 테스트가 통과했다. v0.3.1 수동 UI 검증은 **모의 Bed 씬 및 mock generator**를 사용했고 그 단계에서 실제 GPU 생성 품질을 다시 평가하지 않았다.

기존 실제 Bed E2E에서는 요청·배치 자체가 완료되었더라도 개별 부품 대신 전체 가구형 메시가 출력되는 사례가 관찰되었다. 따라서 **execution success ≠ semantic success**를 명시적으로 구분하였다.

### 4.6 E5: T0 Semantic Role Embedding

기존 Cube3D 백본을 고정하고 LEG와 TOP를 구별하는 작은 역할 임베딩의 학습 및 검증을 진행했다. 초기 plumbing 전용 README보다 **후속 R0/R1/R2 실험 보고서**를 최신 근거로 사용했다.

| 실행 | Holdout teacher-forced mean margin | 자유 생성 관찰 |
|---|---:|---|
| R0 | +0.3016 | 역할 방향의 명확한 대비 부족 |
| R1 | +0.1581 | 상대적으로 가장 뚜렷한 형태 대비 |
| R2 | +0.1031 | 일부 차이 있으나 모호함 |

내부 teacher-forced margin은 **R0 > R1 > R2**였으나 최종 메시의 의미적 형태 대비는 같은 순서가 아니었다. 이는 학습 지표를 최종 자유 생성의 의미적 성공률로 대체할 수 없다는 제한된 증거다.

실험에는 **13개 로컬 합성 형상**, LEG/TOP 이진 역할 및 제한된 생성 조건이 사용되었다. 일반적인 가구 부품 생성 성능이나 생산용 안정성을 보여준 것은 아니다.

### 4.7 E6: KV-cache와 역할 조건 재처리

자기회귀 생성 진단에서 조건 정보를 담는 텐서가 캐시 경로에서는 주로 prefill 단계에 반영되는 구조를 분석했다. 이를 확인하기 위한 **no-cache 대조 실험**은 매 토큰에서 기존 조건을 다시 처리하는 경로를 실행했다.

- no-cache 생성은 기존 캐시 경로보다 약 **3.2~3.3배 느렸다**.
- R1 LEG/TOP elongation gap은 **1.0464 → 0.4236**으로 감소했다.
- R2 TOP의 연결 컴포넌트는 **2 → 254**로 증가했다.
- 첫 토큰 동일성 및 결정적 재실행을 확인하여 대조 경로를 검증했다.

이 실험에서는 **조건을 더 자주 다시 전달하는 것만으로 의미적 역할 제어가 개선되지 않았다**. 판정은 **NC-C**였으며, 후속 학습형 **T1-A 어댑터는 만들거나 학습하지 않고 중단**했다.

체크포인트 3개, 단일 seed/bbox 조건의 기술적 대조이므로 결과를 전체 생성기로 일반화하지 않는다.

### 4.8 E7: 생성 다양성·표본 타당성 점검

GCR-A0-S0에서 생산용 Adapter는 기본적으로 top_p=None을 전달하고, 설치된 Cube3D 경로는 이를 **argmax 기반 결정적 토큰 선택**으로 처리함을 확인했다.

동일한 LEG 요청을 두 번 실행한 최종 OBJ는 **바이트와 기하학 데이터가 모두 동일**했다. 따라서 중복 결과를 독립 표본으로 취급하지 않고 원래 계획한 역할별 5회 반복 평가를 중단했다.

실제 GPU 호출은 **LEG 2회 + HEADBOARD 1회 + SIDE_FRAME 1회 = 총 4회**였다. 모든 호출의 실행은 완료되었으나 이 진단의 결과물에는 **인간의 의미적 승인·거절 판정이 기록되지 않았다**.

**중요한 한계:** 이 GCR의 Bed는 사용자의 실제 작업 파일이 아니라 **v0.3 합성 테스트 fixture**다. 실제 Bed.blend의 의미적 baseline으로 간주하지 않는다. 결정적 결과도 해당 설치 경로와 프롬프트·설정에서 관찰한 현상으로 한정된다.

## 5. 논의

### 5.1 구조 제어와 형상 의미 충실도의 분리

본 연구가 실제 검증한 내용은 (a) 구조 데이터의 추출, (b) 반복·고유 부품별 요청 구성, (c) 자동 배치·공유 인스턴싱, (d) 실행과 의미 검토의 분리, (e) 제한된 기하학적 비율 조건 반응이다.

반면 **요청한 독립 부품을 신뢰성 있게 생성하는 능력**, 다양한 자산에 대한 일반화, 최종 에셋 품질 개선 및 수작업 대비 제작 시간 단축은 아직 입증되지 않았다.

### 5.2 표현 가능성과 조건부 생성의 구분

VQ round-trip 성공은 모델 표현 계층이 부품형 메시를 **재구성**할 수 있다는 관찰이다. 이것만으로 텍스트나 역할 임베딩을 통해 그 부품을 **올바르게 선택·생성**할 수 있다고 결론내릴 수 없다. 마찬가지로 bbox 비율이 맞더라도 그 메시가 실제로 ‘가구 다리’인지 ‘기둥’인지는 인간의 의미 평가가 필요하다.

### 5.3 부정적 결과의 연구 가치

클러스터링의 2:2 오분할, teacher-forced 지표와 자유 생성의 불일치, no-cache 대조군의 악화, 중복 표본 위험은 모두 실험 설계의 수정 근거가 됐다. 시스템 관점에서 **실패 기록의 보존과 명시적 stop gate**는 유효한 제작·연구 판단을 지원한다.

### 5.4 장기 확장 방향

Blender 이후 메시 정리, UV·PBR 머티리얼, USD 교환, Unreal 연계 및 PCG 배치는 향후 연구 방향이다. **InstaMAT, VIGA, 3DGS, NeRF, USD, Unreal PCG를 잇는 전체 E2E 파이프라인은 본 보고서의 실증 범위에 포함되지 않는다.**

## 6. 연구의 한계와 후속 과제

1. **적은 표본:** 단일 실험자의 제한된 객체 유형과 통제 메시를 사용했다.
2. **실제 작업 자산 검증 부족:** GCR-A0-S0는 합성 Bed fixture에서 실행됐다.
3. **인간 의미 평가의 미완료:** 해당 GCR의 실제 GPU 생성 4회에는 인간 리뷰 판정이 없다.
4. **결정적 출력:** argmax 경로의 반복 결과를 독립적으로 세면 안 된다.
5. **이름의 모호성:** Back/Front처럼 상위 엔티티에 따라 의미가 바뀌는 파트 매핑을 개선해야 한다.
6. **효율 대조군 부족:** 제작 시간, 반복 수정, 최종 품질을 수작업·비구조적 생성과 비교하지 않았다.
7. **자료 공개의 제한:** 핵심 제어 코드는 공개하지만 서드파티 모델, 가중치, 일부 내부 실험 코드, .blend 및 대용량 메시 산출물은 공개 저장소에 포함하지 않는다.

후속 검증의 우선순위는 **실제 Bed.blend의 객체·요청 매핑 감사 → 통제 가능한 확률적 샘플링 조건 정립 → 부품별 실제 인간 검토 → 생성기 비교**다. 새로운 학습 구조 설계는 이 평가 이후에 판단한다.

## 7. 결론

본 연구는 아티스트가 구조를 지정하고 생성형 AI가 구체 형상을 생산하는 **Human-Guided Semantic Graybox** 파이프라인을 제안했다. Semantic Blueprint, 반복 Master/Slot, 생성기 Adapter, 순차 큐, Blender 배치 및 인간의 의미 검토 시스템은 동작하는 프로토타입으로 구현·검증됐다.

하지만 출력 비율 제어, 메시 표현 가능성 또는 내부 조건화 지표의 개선은 **의미적으로 정확한 부품의 안정적인 생성**을 자동으로 보장하지 않았다. 따라서 현재 기여는 새로운 생성 모델의 우수성이 아닌, **인간의 구조적 의도를 독립적으로 보존하고 실행 성공과 의미적 성공을 구분해 검증하는 제작 아키텍처**에 있다.

---

## 참고문헌

[1] B. Mildenhall et al., “NeRF: Representing Scenes as Neural Radiance Fields for View Synthesis,” *ECCV*, 2020. https://doi.org/10.1007/978-3-030-58452-8_24

[2] B. Kerbl, G. Kopanas, T. Leimkühler, and G. Drettakis, “3D Gaussian Splatting for Real-Time Radiance Field Rendering,” *ACM Transactions on Graphics*, 42(4), Article 139, 2023. https://doi.org/10.1145/3592433

[3] Roblox Foundation AI Team et al., “Cube: A Roblox View of 3D Intelligence,” *arXiv:2503.15475*, 2025. https://arxiv.org/abs/2503.15475

[4] K. Mo et al., “PartNet: A Large-Scale Benchmark for Fine-Grained and Hierarchical Part-Level 3D Object Understanding,” *CVPR*, pp. 909–918, 2019. https://doi.org/10.1109/CVPR.2019.00100

## 실험 근거·재현성 고지

아래 문서는 본 보고서의 실험 수치와 관찰 범위를 확인할 수 있는 **로컬 프로젝트 기록의 경로**다. 일부는 제3자 라이선스, 개인 작업 자산, 대용량 생성물 등의 이유로 GitHub 저장소에 포함되지 않아 **외부 독자의 재현 검증 자료가 완전하지 않다**.

| 항목 | 원본 기록 (로컬, 일부 미공개) |
|---|---|
| Guide Ratio | experiments/guide_ratio/RESULTS.md |
| VQ Round-trip | experiments/vq_part_roundtrip/CONTROL_ROUNDTRIP_RESULTS.md |
| Master Clustering | experiments/master_clustering/RESULTS.md |
| Multi-part Queue | WORKLOG_2026-10-02_v03.md |
| Human Review | MILESTONE_SEMANTIC_GRAYBOX_v0.3.1.md; WORKLOG_2026-10-02_v031.md |
| T0 Generalization | experiments/semantic_role_t0/generalization/GENERALIZATION_RESULTS.md |
| T0 Free Generation | experiments/semantic_role_t0/free_generation/phase12/report.md |
| Autoregressive Diagnostic | experiments/semantic_role_t0/autoregressive_diagnostic/T0-D1/report.md |
| No-cache Control | experiments/semantic_role_t1/report.md |
| GCR-A0-S0 | experiments/generator_capability_review/stock_cube3d/report.md; sampling_audit.md |

본 문서는 동료심사를 거치지 않은 **예비 기술 보고서**다. 저장소의 원본 Semantic Graybox 소스는 MIT 정책에 따라 공개되며, Cube3D/CubePart 소스·모델·가중치 등 외부 의존성에는 각각의 원 라이선스가 적용된다. 상세 사항은 [Third-Party Notices](../THIRD_PARTY_NOTICES.md)를 참고한다.
