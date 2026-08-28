# V4_1.ChargeGuard_기술 백서(F3를 옵션으로-SCI목표)

생성자: 정미 김
생성 일시: 2026년 6월 29일 오후 9:33
최종 편집자:: 정미 김
최종 업데이트 시간: 2026년 6월 30일 오후 1:12

# ChargeGuard-HVVD 기술 백서 v4

## OCPP-aware 소스코드 분석, Type-specific LLM 후보 분류, External Exposure 분리, Evidence-aware HVVD 생성 및 Reference Pattern 기반 보강 체계

---

# 1. 문서 목적과 위치

본 백서는 ChargeGuard-HVVD의 전체 기술 기준을 정의하는 상위 아키텍처 문서이다. 이 문서는 특정 Detector의 세부 prompt, label space, JSON schema, post-processing rule을 모두 상세히 기술하는 문서가 아니라, ChargeGuard-HVVD가 어떤 문제를 해결하고, 어떤 기능 블록으로 구성되며, 각 기능이 어떤 책임 경계를 갖는지 정의하는 기준 문서이다.

특히 F2-B Type-specific LLM Candidate Classification은 별도 상세 문서인 「F2-B Type-specific Detector 개념 설계」에서 확장한다. 본 백서에서는 F2-B의 역할, 입력, 출력, 책임 경계, 후속 기능과의 연결만 정의한다. 이를 통해 ChargeGuard 기술 백서는 전체 시스템의 일관성을 유지하고, F2-B 상세 백서는 Detector Package, LLM_REQUEST, Detector Control Input, Analysis Target Evidence Input, detector_specific_rules, Post-Processor를 독립적으로 심화할 수 있도록 한다.

또한 F2-A. OCPP-aware Static Analysis는 별도 상세 문서인 「F2-A. OCPP-aware Static Analysis 상세 개념설계」에서 확장한다. 본 백서에서는 F2-A의 역할, 입력, 출력, 책임 경계, F1/F2-B/F2-C/F6와의 연결을 정의하고, 세부 모듈인 OCPP Source Map Builder, Handler Mapper, Field Source Extractor, Observed Check Detection, Expected Check Matching, Missing Check Candidate Generation은 F2-A 상세 문서에서 심화한다.

특히 F2-A의 LLM 사용은 취약점 확정이 아니라 observed check evidence가 F1 Expected Check Profile의 어떤 expected check에 대응하는지 판정하는 LLM-assisted Validation Checker로 제한된다.

본 백서의 최종 목적은 다음과 같다.

```
1. OCPP 기반 EV 충전 인프라 소스코드 분석 문제를 정의한다.
2. ChargeGuard-HVVD의 전체 아키텍처와 기능 책임을 고정한다.
3. F1, F2-A, F2-B, F2-C, F6의 핵심 결합 구조를 정리한다.
4. F3/F4/F5/F7의 위치를 핵심 기능 또는 선택적 확장 기능으로 구분한다.
5. C 기반 충전기 controlled validation과 Java 기반 CSMS 확장 전략을 제시한다.
6. 논문·프로토타입·상용화 확장을 위한 기준선을 제공한다.
```

---

# 2. 배경

전기차 충전 인프라는 단순한 전력 공급 장치가 아니라 Charge Point, CSMS, 사용자 인증, 결제, 원격 제어, 펌웨어 업데이트, 운영 정책이 결합된 사이버-물리 시스템이다. 이 환경에서 OCPP는 Charge Point와 CSMS 사이의 핵심 통신 프로토콜로 사용되며, 충전 서비스의 상태 관리, 원격 명령, 설정 변경, 펌웨어 업데이트, 트랜잭션 처리, 계량 데이터 전송을 담당한다.

OCPP는 단순 메시지 교환 프로토콜이 아니라 충전기의 보안, 안전, 서비스 가용성에 영향을 미치는 원격 제어 채널이다. CSMS는 OCPP를 통해 충전기에 펌웨어 다운로드 위치를 전달하고, 운영 파라미터를 변경하며, 충전 세션을 원격으로 시작하거나 종료할 수 있다. 따라서 OCPP 구현체의 취약성은 소프트웨어 결함에 그치지 않고 충전 서비스 중단, 원격 장악, 과금 조작, 전력 설비 오작동으로 이어질 수 있다.

EV 충전 인프라의 취약성은 단순한 코드 결함 하나로만 발생하지 않는다. 하나의 취약 후보는 OCPP action, payload field, handler, 내부 service 함수, validation 로직, authorization/state check, dangerous sink, 운영 정책이 결합된 형태로 나타난다. 따라서 EV 충전 인프라 소스코드 분석에는 일반 정적 분석, 도메인 지식, LLM 기반 의미 해석, 근거 추적형 결과 생성이 결합된 체계가 필요하다.

---

# 3. 보안 위협과 분석 대상

## 3.1 OCPP 프로토콜 기반 위협

OCPP는 Charge Point와 CSMS 사이의 원격 제어 채널이다. 주요 위협은 다음과 같다.

```
UpdateFirmware:
  - location field가 firmware download URL로 사용됨
  - URL scheme/host validation, signature verification, install block 누락 시 위험

ChangeConfiguration:
  - 보안 설정, 운영 설정 변경 가능
  - allowed key/value validation, authorization, state check 누락 시 위험

RemoteStartTransaction / RemoteStopTransaction:
  - 충전 세션 원격 제어
  - idTag, transaction ownership, connector state check 누락 시 위험

UnlockConnector:
  - 물리적 커넥터 잠금 해제
  - operator permission, station ownership, safety state check 누락 시 위험

DataTransfer:
  - vendor-specific payload 처리
  - custom command bridge, oversized payload, unsafe backend routing 위험

GetDiagnostics:
  - 진단 데이터 전송 위치 지정
  - unsafe URL, path traversal, 민감 정보 외부 전송 위험
```

## 3.2 비OCPP 컴포넌트 기반 위협

OCPP handler 외부에도 취약 후보가 존재한다.

```
Charge Point 측:
  - OTA update manager
  - firmware installer
  - diagnostic command module
  - local CLI / maintenance script
  - configuration parser
  - certificate/key management module

CSMS 측:
  - WebSocket / JSON-RPC dispatcher
  - action handler
  - service/repository layer
  - authorization policy layer
  - tenant/station ownership logic
  - URL fetch / file access / DB query / process execution sink
```

ChargeGuard-HVVD는 OCPP handler 내부 취약 후보뿐 아니라, OCPP 경로에서 도달 가능한 일반 코드 취약 후보와 OCPP 경로와 무관한 일반 코드 취약 후보를 구분한다.

---

# 4. 기존 접근의 한계

## 4.1 일반 정적 분석의 한계

일반 정적 분석은 source-sink 흐름, 위험 API, 입력 검증 누락을 탐지할 수 있다. 그러나 OCPP 구현체에서는 다음 질문에 답해야 한다.

```
- 이 source는 어떤 OCPP action/field에서 유래했는가?
- 해당 field의 보안 의미는 무엇인가?
- 어떤 expected check가 있어야 하는가?
- observed check가 의미 있는 방어인가?
- 위험 sink가 OCPP handler에서 도달 가능한가?
- 이 후보는 충전 서비스에 어떤 영향을 갖는가?
```

일반 정적 분석만으로는 이러한 도메인 의미를 충분히 해석하기 어렵다.

## 4.2 Raw-code LLM 분석의 한계

LLM은 코드 의미를 설명하는 데 유용하지만, 원시 코드를 자유롭게 입력받아 취약점을 판정하게 하면 다음 위험이 있다.

```
- 코드에 없는 flow를 추론할 수 있음
- 함수명만 보고 검증 충분성을 오판할 수 있음
- runtime exploitability를 과잉 단정할 수 있음
- OCPP remote exploit 가능성을 성급히 주장할 수 있음
- CWE 매핑이나 root cause 설명이 evidence와 불일치할 수 있음
```

따라서 ChargeGuard-HVVD는 LLM을 취약점 확정기로 사용하지 않는다. LLM은 정적 분석 evidence와 Detector Package에 의해 제어되는 후보 분류기로 제한된다.

## 4.3 결과 설명의 한계

기존 도구의 출력은 대부분 경고 목록 또는 자연어 설명에 머문다. 그러나 EV 충전 인프라 보안 분석 결과는 다음을 보존해야 한다.

```
- source action/field
- source-to-sink flow
- observed check
- missing or weak check
- root cause candidate
- related CWE
- External exposure status
- evidence_id 기반 추적성
- limitation
- lifecycle state
```

ChargeGuard-HVVD는 이를 HVVD라는 구조화된 취약 후보 서술자로 표현한다.

---

# 5. ChargeGuard-HVVD 접근법

ChargeGuard-HVVD는 OCPP 도메인 지식, 정적 분석 evidence, type-specific LLM candidate classification, external exposure classification, evidence-aware HVVD generation을 결합한다. 본 백서에서 기본 연구 경로는 F1, F2-A, F2-B, F2-C, F6이며, F3/F4/F7은 후보의 설명성, 우선순위, 보고서 품질을 높이는 보강 경로로 배치한다.

```
Core Evidence-to-HVVD Pipeline:

F1. OCPP-centric Knowledge Layer
  ↓
F2-0. Common Code Fact Layer
  ↓
F2-A / F2-B / F2-C
  ├─ F2-A. OCPP-aware Static Analysis
  ├─ F2-B. Type-specific LLM Candidate Classification
  └─ F2-C. External Exposure Classification
  ↓
F2-R. Candidate HVVD Finalization
  ↓
F6. Evidence-aware HVVD Generation
```

이 핵심 경로는 다음을 목표로 한다.

```
ChargeGuard-HVVD는 F2-0 Common Code Fact Layer를 기준으로
OCPP action/field에서 출발하는 OCPP-native evidence extraction,
취약 유형별 LLM-controlled generic candidate classification,
generic 후보의 external exposure classification을 병렬적으로 수행한다.

이후 F2-R은 F2-A/F2-B/F2-C 결과를 통합하여
F6에서 evidence-aware Candidate HVVD로 구조화한다
```

논문성과 시스템 완성도를 높이기 위한 보강 경로는 다음과 같이 둔다.

```
Enrichment and Reporting Pipeline:

F6 Candidate HVVD
  ↓
F3. Evidence-aware Similarity Enrichment
  - 초기에는 Reference Pattern Repository 기반
  - 장기적으로 Reference HVVD Repository로 확장
  - root cause, missing check, impact, remediation 근거 보강
  ↓
F4. KB/Rule-based Risk Scoring
  - action risk, sink severity, missing check, exposure status, similarity evidence 반영
  ↓
F7. LLM-based Explainable Reporting
  - F6 HVVD와 F3/F4 보강 근거를 기반으로 grounded report 생성
```

F5는 다음과 같이 별도 확장 경로로 둔다.

```
Future Runtime Extension:

F5. OCPP Context-aware Targeted Validation
  - protocol behavior validation 또는 fuzzing 기반 runtime evidence 수집
  - CONFIRMED_HVVD 상태 전이는 F5 또는 별도 runtime evidence가 있을 때만 허용
```

따라서 ChargeGuard-HVVD의 연구 포지셔닝은 다음과 같다.

```
필수 핵심:
  OCPP-aware evidence extraction + LLM-controlled candidate classification + exposure separation + HVVD generation

논문성 강화:
  Reference Pattern 기반 similarity enrichment + risk scoring + grounded reporting
```

---

# 6. 설계 원칙

ChargeGuard-HVVD의 핵심 설계 원칙은 다음과 같다.

```
1. LLM은 취약점 확정기가 아니다.
   - LLM은 evidence-bounded candidate classifier로 사용된다.

2. External exposure와 vulnerability candidate classification은 분리한다.
   - 위험 코드 후보가 존재해도 EXTERNAL_EXPOSED 또는 OCPP_EXPOSED라고 단정하지 않는다.

3. 모든 결과는 evidence_id로 추적 가능해야 한다.
   - HVVD의 주요 field는 source evidence, flow evidence, check evidence와 연결된다.

4. Guarded label은 안전 확정이 아니다.
   - 의미 있는 방어 근거가 관찰되었음을 의미할 뿐 충분성은 별도 검토 대상이다.

5. Reference similarity는 확정 근거가 아니다.
   - F3는 유사 패턴 기반 설명 보강이며 취약점 확정 단계가 아니다.

6. F5 runtime validation은 선택적 확장이다.
   - F2/F6 결과는 confirmed vulnerability가 아니라 candidate descriptor이다.

7. 백서는 기준 문서이고, 세부 Detector 설계는 별도 문서로 확장한다.
```

---

# 7. 전체 아키텍처

## 7.1 기능 블록 개요

```
F1. OCPP-centric Knowledge Layer

* OCPP action/field 보안 의미 정의
* expected check, dangerous sink domain, root cause, CWE, impact, HVVD rule 제공

F2-A. OCPP-aware Static Analysis

* OCPP action/field와 코드 분석 시작점 연결
  - inbound handler mapping
  - outbound command path mapping
* payload field / command input binding
* source-flow-sink extraction
* rule-based observed check detection
* optional LLM-assisted check semantics classification
* expected check matching 및 missing/weak check candidate 생성
* OCPP-native candidate HVVD fragment 생성

F2-A의 LLM-assisted check semantics classification은 선택 기능이며,
원시 코드 전체를 자유 분석하지 않는다.
입력은 F2-0이 추출한 제한된 code evidence package와 F1 Expected Check Profile로 제한된다.

F2-B. Type-specific LLM Candidate Classification

* 정적 evidence를 취약 유형별 Detector Package로 분류
* 일반 LLM 엔진을 evidence-bounded candidate classifier로 제어
* GENERIC_CODE_CANDIDATE_HVVD fragment 생성

F2-C. External Exposure Classification

* F2-B에서 생성된 generic code vulnerability candidate의 외부 입력면 노출 여부 분류
* OCPP handler/action/field path, REST API, Admin UI, CLI, OTA channel, MQTT 등 external entrypoint 연결성 분석
* 초기 구현에서는 OCPP entry/handler 기반 노출성을 우선 판정하고, 향후 다른 충전 인프라 입력면으로 확장
* EXTERNAL_EXPOSED / INTERNAL_ONLY / UNKNOWN_EXPOSURE 분류

F6. Evidence-aware HVVD Generation

* F1/F2-A/F2-B/F2-C 결과를 통합
* evidence traceable Candidate HVVD 생성

F7. LLM-based Explainable Reporting

* HVVD를 개발자/분석가/평가자/관리자 관점의 설명형 보고서로 변환

```

## 7.2 핵심 경로와 선택적 보강 경로

```
Core Pipeline:
  F1 → F2-0 → F2-A / F2-B / F2-C → F2-R → F6

	F2-0:
	  Common Code Fact Layer
	
	F2-A:
	  OCPP action/field에서 출발하는 OCPP-native evidence extraction
	
	F2-B:
	  취약 유형별 source-code evidence에서 출발하는 type-specific candidate classification
	
	F2-C:
	  F2-B generic candidate의 external exposure classification
	
	F2-R:
	  F2-A/F2-B/F2-C 결과를 통합하여 finalized candidate HVVD set 생성

Enrichment Pipeline:
  F6 Candidate HVVD → F3 Evidence-aware Similarity Enrichment → F4 KB/Rule-based Risk Scoring

Reporting Pipeline:
  F6/F3/F4 evidence → F7 LLM-based Explainable Reporting

Future Runtime Extension:
  F5 OCPP Context-aware Targeted Validation
```

본 백서에서 핵심 연구·구현 경로는 **F1, F2-A, F2-B, F2-C, F6**이다. F3/F4/F7은 필수 후보 생성 경로를 대체하지 않으며, Candidate HVVD의 설명성, 검토 우선순위, 보고서 groundedness를 높이는 보강 기능이다. 특히 F3는 Reference HVVD Repository를 즉시 요구하지 않고, 초기에는 취약 유형별 Reference Pattern Repository를 사용한다.

---

# 8. F1. OCPP-centric Knowledge Layer

## 8.1 역할

F1은 ChargeGuard-HVVD의 기준 지식 계층이다. 단순한 OCPP schema 저장소가 아니라, OCPP action/field의 보안 의미와 expected check를 구조화한다.

```
F1의 역할:
- OCPP action/field의 보안 의미 정의
- payload field trust level 정의
- expected validation / authorization / state check 정의
- dangerous sink domain 연결
- root cause taxonomy 제공
- CWE 및 impact mapping 제공
- HVVD generation rule 제공
```

## 8.2 구성 요소

```
OCPP Action Security Profile:
  action_name, protocol_version, security_relevance, expected_state, sensitive_fields

Payload Field Trust Profile:
  field_name, semantic_type, trust_level, validation_requirement, sink_domain

Expected Check Profile:
  check_id, check_type, applicable_action, applicable_field, evidence_pattern

Dangerous Sink Domain Profile:
  sink_domain, sink_api, language, related_cwe, severity

Root Cause Taxonomy:
  root_cause_id, condition, missing_check_mapping, CWE mapping

Impact Mapping:
  charging_service_impact, device_impact, user_impact, operator_impact

HVVD Generation Rule:
  condition, required_evidence, output_field_mapping, limitation_rule
```

## 8.3 예시: UpdateFirmware.location

```
Action:
  UpdateFirmware

Field:
  location

Semantic type:
  firmware_download_url

Expected checks:
  - URL_SCHEME_VALIDATION
  - HOST_ALLOWLIST
  - FIRMWARE_SIGNATURE_VERIFICATION
  - INSTALL_BLOCK_ON_VERIFY_FAIL
  - SAFE_DOWNLOAD_API_NO_SHELL

Dangerous sink domains:
  - shell_command_execution
  - unsafe_url_fetch
  - firmware_installation

Related CWE:
  - CWE-78
  - CWE-494
  - CWE-345
  - CWE-347

Potential impact:
  - malicious firmware download
  - device takeover
  - charging service disruption
```

## 8.4 F1의 경계

F1은 취약점을 탐지하지 않는다. F1은 F2-A, F2-B, F2-C, F6가 일관된 기준으로 판단할 수 있도록 knowledge schema와 rule을 제공한다.

---

# 9. F2-A. OCPP-aware Static Analysis

## 9.1 목적

F2-A는 OCPP 도메인 지식을 활용하여 소스코드에서 OCPP action/field와 내부 코드 흐름을 연결하는 정적 분석 계층이다.

```
F2-A의 핵심 질문:
- 어떤 OCPP action이 어떤 handler로 매핑되는가?
- 어떤 payload field가 어떤 변수/객체 field로 binding되는가?
- 해당 source가 어떤 sink로 흐르는가?
- expected check가 실제 코드에서 관찰되는가?
- 어떤 check가 누락되었거나 약한가?
```

## 9.2 처리 흐름

```
OCPP Handler / Command Path Mapping
  ↓
Payload Field / Command Input Binding
  ↓
Field Semantic Binding
  ↓
Source-Flow-Sink / Source-Decision Extraction
  ↓
Dangerous Sink / Security-sensitive Decision Mapping
  ↓
Observed Check Detection
    ├─ Rule-based Check Pattern Detection
    └─ Optional LLM-assisted Check Semantics Classification
  ↓
Expected Check Matching
  ↓
Missing / Weak / Unverified Check Candidate Generation
  ↓
OCPP-native Evidence Package 생성
  ↓
OCPP-native Candidate HVVD Fragment 생성
```

## 9.3 주요 산출물

```
ocpp_source_map.json:
  - OCPP action, handler, request object, payload field access 후보

handler_map.json:
  - OCPP action과 inbound handler 또는 outbound command path 간 매핑 evidence

field_binding_map.json:
  - OCPP payload field 또는 command input과 코드 변수/DTO property/getter 간 binding evidence
  
ocpp_flow_candidates.jsonl:
  - OCPP action/field 기반 source-flow-sink 후보

observed_check_analysis.jsonl:
  - rule-based observed check detection 결과
  - optional LLM-assisted check semantics classification 결과
  - weak/partial check 판정 결과

expected_check_matching_results.jsonl:
  - F1 expected check와 observed check candidate 간 matching 결과

missing_check_candidates.jsonl:
  - missing / weak / partial / unverified check candidate

ocpp_native_candidate_fragments.jsonl:
  - F6로 전달 가능한 OCPP-native candidate HVVD fragment

ocpp_evidence_packages.jsonl:
  - file/function/line/evidence_id 기반 추적 가능한 상세 evidence package
```

## 9.4 F2-A의 경계

F2-A는 정적 분석 evidence를 생성한다. F2-A만으로 취약점 확정, runtime exploitability, OCPP exposure 최종 판단을 수행하지 않는다.

F2-A에서 LLM을 사용하는 경우에도 그 역할은 observed check semantics classification으로 제한된다. 즉, LLM은 코드 evidence가 F1 Expected Check Profile의 어떤 expected check에 대응하는지, 또는 weak/partial check인지 판정하는 Validation Checker로만 사용된다.

F2-A의 LLM은 command injection, memory overflow, unsafe firmware download 등 취약 유형 자체를 분류하는 Type-specific Vulnerability Detector가 아니다. 그 역할은 F2-B가 담당한다.

---

# 10. F2-B. Type-specific LLM Candidate Classification

## 10.1 역할

F2-B는 F2-0 Common Code Fact Layer에서 생성된 source-flow-sink evidence, sink evidence, check evidence, function context를 입력으로 받아 취약 유형별 후보 분류를 수행하는 source-code-side classification 계층이다.

F2-B는 F2-A의 하위 단계가 아니며, F2-A가 생성한 OCPP-native 후보를 재분류하는 계층도 아니다. F2-A와 F2-B는 F2-0을 공유하는 독립 분석 계층이다.

F2-B의 LLM은 command injection, memory safety, unsafe external resource 등 취약 유형별 candidate classification을 수행한다. 이는 F2-A의 LLM-assisted Validation Checker와 구분된다.

F2-B는 별도 LLM 모델을 학습하는 구조가 아니다. 일반 LLM 엔진을 공통 추론 백엔드로 활용하되, Type-specific Detector Package를 통해 LLM_REQUEST를 구성하고, LLM의 판단 범위를 제한한다.

```
F2-B 핵심 원칙:
LLM Detector ≠ vulnerability confirmer
LLM Detector = evidence-bounded candidate classifier
```

## 10.2 Type-specific Detector Package의 의미

```
Type-specific Detector Package
=
General-purpose LLM Engine에 전달할 LLM_REQUEST를 구성하기 위한
취약 유형별 제어 패키지
```

Detector Package는 다음을 포함한다.

```
- evidence filter
- detector_type
- allowed_label_space
- allowed_cwe_set
- detector_specific_rules
- evidence_usage_policy
- forbidden_claims
- required_output_schema
- post-processing rule
- Candidate HVVD mapping rule
```

즉, Detector Package는 별도 LLM 모델이 아니라 LLM_REQUEST의 내용을 채우기 위한 취약 유형별 설정 묶음이다.

## 10.3 처리 흐름

```
Static Evidence
  ↓
Detector Routing
  ↓
Type-specific Detector Package Selection
  ↓
LLM_REQUEST 구성
  ├─ Common Prompt
  └─ LLM_CALL_INPUT
      ├─ Detector Control Input
      └─ Analysis Target Evidence Input
  ↓
General-purpose LLM Engine 호출
  ↓
TYPE_SPECIFIC_DETECTOR_OUTPUT
  ↓
Post-Processor 검증
  ↓
GENERIC_CODE_CANDIDATE_HVVD fragment
```

## 10.4 MVP Detector 범위

초기 C 기반 충전기 controlled validation에서는 다음 Detector를 둔다.

```
C Charger MVP Detectors:
- Command Injection Detector Package
- Memory Safety Detector Package
- Firmware / OTA Weakness Detector Package
```

Java 기반 CSMS 확장에서는 Detector 구성을 다음처럼 재정의한다.

```
Java CSMS Extension Detectors:
- Backend Injection Detector Package
- Unsafe External Resource Detector Package
- Backend Authorization & State Logic Weakness Detector Package
```

## 10.5 F2-B의 산출물

```
TYPE_SPECIFIC_DETECTOR_OUTPUT:
  - detector_type
  - classification_label
  - source_summary
  - sink_summary
  - flow_summary
  - observed_checks
  - missing_or_weak_checks
  - root_cause_candidate
  - related_cwe
  - evidence_basis
  - confidence
  - limitation

GENERIC_CODE_CANDIDATE_HVVD fragment:
  - F6에서 최종 Candidate HVVD로 통합될 중간 산출물
```

## 10.6 F2-B의 경계

F2-B는 다음을 수행하지 않는다.

```
- 취약점 확정
- runtime exploitability 확인
- OCPP remote exploitability 단정
- EXTERNAL_EXPOSED 또는 OCPP_EXPOSED 최종 판단
- F5 validation 결과 대체
- CONFIRMED_HVVD 상태 전이
```

F2-B의 세부 Detector Package, LLM_REQUEST schema, label space, detector_specific_rules, full example은 별도 문서인 「F2-B Type-specific Detector 개념 설계」에서 정의한다.

---

# 11. F2-C. External Exposure Classification

## 11.1 목적

F2-C는 F2-B가 생성한 `GENERIC_CODE_CANDIDATE_HVVD`가 외부 입력면을 통해 도달 가능한지 분류하는 단계이다. F2-B는 command injection, memory safety, firmware/OTA weakness 등 일반 보안 관점의 취약 후보를 생성하지만, 해당 후보가 실제 외부 입력 경로와 연결되는지는 별도로 판단해야 한다.

따라서 F2-C는 취약 유형 분류 단계가 아니라, generic code vulnerability candidate의 external exposure를 분류하는 단계이다.

```
위험 코드 후보 존재
≠ 외부 입력면에서 도달 가능
≠ OCPP 원격 도달 가능
≠ runtime exploit 가능
≠ confirmed vulnerability
```

초기 구현에서는 OCPP action handler 또는 OCPP payload field에서 후보 function/sink까지 도달 가능한지를 우선 판정한다. 이후 REST API, Admin UI, CLI, OTA channel, MQTT, diagnostic interface 등 충전 인프라 소프트웨어의 다른 외부 입력면으로 확장할 수 있다.

즉, F2-C는 다음 질문에 답한다.

```
F2-B가 생성한 generic 취약 후보는
어떤 외부 입력면을 통해 도달 가능한가?
```

---

## 11.2 분류 결과

F2-C의 분류 결과는 `exposure_class`와 `exposure_surface`를 분리하여 표현한다. 이를 통해 OCPP 중심 MVP를 유지하면서도 REST API, Admin UI, CLI, OTA channel 등 다른 입력면으로 확장할 수 있다.

### 11.2.1 exposure_class

```
EXTERNAL_EXPOSED:
  후보 function/sink가 외부 입력면에서 도달 가능한 근거가 존재함

INTERNAL_ONLY:
  후보는 존재하지만 외부 입력면에서 도달 가능한 근거가 없으며,
  내부 관리 함수, 로컬 유틸리티, 테스트 코드, 배치 작업 등에 한정됨

UNKNOWN_EXPOSURE:
  dynamic dispatch, callback, reflection, unresolved framework boundary,
  function pointer, indirect call 등으로 외부 도달성을 판단할 수 없음
```

### 11.2.2 exposure_surface

```
OCPP:
  OCPP action handler, OCPP payload field, 또는 outbound OCPP command path에서
  candidate function/sink까지 call/data-flow 근거가 존재함

REST_API:
  REST endpoint, HTTP controller, API route 등에서 candidate function/sink까지
  도달 가능한 근거가 존재함

ADMIN_UI:
  관리자 웹 UI 또는 관리 콘솔 입력에서 candidate function/sink까지
  도달 가능한 근거가 존재함

CLI:
  로컬 또는 원격 관리 CLI 입력에서 candidate function/sink까지
  도달 가능한 근거가 존재함

OTA_CHANNEL:
  OTA update, firmware update, package download/install 경로에서
  candidate function/sink까지 도달 가능한 근거가 존재함

MQTT:
  MQTT topic/message handler에서 candidate function/sink까지
  도달 가능한 근거가 존재함

LOCAL_CONFIG:
  설정 파일, 환경 변수, 로컬 configuration loader에서
  candidate function/sink까지 도달 가능한 근거가 존재함

UNKNOWN:
  입력면 유형을 특정할 수 없음
```

초기 MVP에서는 다음 세 가지를 우선 사용한다.

```
EXTERNAL_EXPOSED + OCPP
INTERNAL_ONLY
UNKNOWN_EXPOSURE
```

---

## 11.3 F2-C의 효과

F2-C는 LLM 또는 정적 분석 결과가 generic 취약 후보를 외부에서 악용 가능한 취약점으로 과잉 단정하는 문제를 줄인다.

```
F2-B:
  Command Injection candidate 가능성 분류

F2-C:
  해당 candidate가 OCPP, REST API, Admin UI, CLI, OTA channel 등
  외부 입력면에서 도달 가능한지 분류
```

예를 들어 F2-B가 다음 후보를 생성했다고 하자.

```
config_value
→ sprintf(cmd, ...)
→ system(cmd)
```

이 후보는 command injection 관점에서는 위험할 수 있다. 그러나 F2-C는 이 입력이 어디에서 유래했는지를 별도로 판단한다.

```
Case 1:
  OCPP ChangeConfiguration.value
  → config_value
  → system(cmd)

  exposure_class: EXTERNAL_EXPOSED
  exposure_surface: OCPP

Case 2:
  local maintenance CLI argument
  → config_value
  → system(cmd)

  exposure_class: EXTERNAL_EXPOSED
  exposure_surface: CLI

Case 3:
  internal constant
  → config_value
  → system(cmd)

  exposure_class: INTERNAL_ONLY

Case 4:
  unresolved callback
  → config_value
  → system(cmd)

  exposure_class: UNKNOWN_EXPOSURE
```

이를 통해 F2-C는 다음을 보장한다.

```
- F2-B의 취약 유형 분류 결과와 외부 노출성 판단을 분리한다.
- generic code candidate를 곧바로 OCPP remote exploit 가능 후보로 단정하지 않는다.
- OCPP 중심 MVP를 유지하면서도 REST API, Admin UI, CLI, OTA channel 등으로 확장 가능하게 한다.
- F6 Evidence-aware HVVD Generation 단계에서 exposure evidence와 limitation을 명확히 기록할 수 있게 한다.
```

---

## 11.4 F2-A와 F2-C의 관계

F2-A는 OCPP action/field에서 출발하는 OCPP-native 후보를 생성하는 계층이다. 따라서 F2-A 후보는 기본적으로 OCPP 문맥을 전제로 한다.

반면 F2-C는 F2-A 후보를 다시 OCPP 노출성 판정하는 단계가 아니다. F2-C의 주 대상은 F2-B에서 생성된 generic code vulnerability candidate이다.

```
F2-A:
  OCPP action/field 기반 OCPP-native candidate 생성

F2-B:
  일반 보안 관점의 generic code vulnerability candidate 생성

F2-C:
  F2-B generic candidate의 external exposure surface 분류
```

다만 F2-C가 OCPP 노출성을 판단할 때는 F2-0 Common Code Fact Layer 또는 F2-A에서 생성된 OCPP handler map, field binding, call graph, data-flow evidence를 참조할 수 있다.

즉, F2-C의 관계는 다음과 같이 정의한다.

```
classification target:
  F2-B generic code vulnerability candidate

reference evidence:
  F2-0 Common Code Fact Layer
  OCPP handler map
  field binding
  call graph
  data-flow evidence
  external entrypoint map
```

---

## 11.5 출력 예시

```json
{
  "candidate_id": "GEN-CAND-0001",
  "source_candidate_id": "F2B-CMD-0001",
  "exposure_class": "EXTERNAL_EXPOSED",
  "exposure_surfaces": [
    {
      "surface": "OCPP",
      "entry_type": "OCPP_ACTION_HANDLER",
      "action": "UpdateFirmware",
      "field": "location",
      "handler": "handle_update_firmware",
      "evidence": [
        "UpdateFirmware.location is bound to firmware_url",
        "handle_update_firmware() calls download_firmware(firmware_url)",
        "download_firmware() reaches system(cmd)"
      ],
      "confidence": 0.84
    }
  ],
  "limitations": [
    "static analysis cannot confirm runtime exploitability",
    "external exposure does not imply confirmed vulnerability"
  ]
}
```

---

# 12. F6. Evidence-aware HVVD Generation

## 12.1 HVVD의 정의

HVVD는 자유형 취약점 보고서가 아니라, source-code evidence, OCPP context, detector output, exposure classification, root cause, missing check, limitation을 구조화하여 보존하는 근거 추적형 취약 후보 서술자이다.

```
HVVD
=
Hybrid Vulnerability Variant Descriptor
```

## 12.2 F6의 입력

```
F1:
  OCPP action/field security semantics, expected checks, root cause taxonomy

F2-A:
  OCPP-aware source-flow-sink evidence
  OCPP field semantic binding
  rule-based observed check evidence
  optional LLM-assisted check semantics classification result
  expected check matching result
  missing / weak / unverified check candidates
  
  F6는 F2-A의 LLM-assisted check semantics 결과를 HVVD evidence로 사용할 수 있으나, 이를 취약점 확정 근거로 단독 사용하지 않는다. LLM-assisted 결과는 observed check/missing check 판단의 보조 evidence이며, runtime exploitability 또는 confirmed vulnerability 판단을 대체하지 않는다.
  

F2-B:
  type-specific classification_label, root_cause_candidate, related_cwe, evidence_basis

F2-C:
  external exposure class, exposure surface, and reachability evidence

Optional F3/F4:
  similarity enrichment, risk evidence
```

## 12.3 HVVD 기본 구조

```json
{
  "hvvd_id": "HVVD-CAND-00042",
  "hvvd_type": "EXTERNAL_EXPOSED_GENERIC_CANDIDATE_HVVD",
  "assessment_status": "STATIC_SUSPECT_HVVD",
  "ocpp_context": {
    "action": "UpdateFirmware",
    "field": "location"
  },
  "code_evidence": {
    "source": "firmware_url",
    "sink": "system(cmd)",
    "flow": "firmware_url -> sprintf(cmd) -> system(cmd)"
  },
  "detector_result": {
    "detector_type": "COMMAND_INJECTION",
    "classification_label": "COMMAND_INJECTION_LIKELY",
    "related_cwe": ["CWE-78"]
  },
  "missing_checks": [
    "SHELL_FREE_EXECUTION",
    "COMMAND_ARG_ALLOWLIST",
    "SHELL_METACHARACTER_ESCAPE"
  ],
  "exposure": {
    "exposure_class": "EXTERNAL_EXPOSED",
     "exposure_surfaces": [
      {
         "surface": "OCPP",
          "action": "UpdateFirmware",
          "field": "location"
      }
     ]
  },
  "limitation": [
    "Runtime exploitability is not confirmed.",
    "This HVVD is based on static source-code evidence."
  ]
}
```

## 12.4 HVVD 유형

```
OCPP_NATIVE_CANDIDATE_HVVD:
  OCPP action/field 의미와 expected check 누락을 중심으로 생성된 후보

GENERIC_CODE_CANDIDATE_HVVD:
  일반 코드 취약 후보이지만 external exposure가 아직 분류되지 않았거나 내부 전용 후보

EXTERNAL_EXPOSED_GENERIC_CANDIDATE_HVVD:
  일반 코드 취약 후보가 하나 이상의 외부 입력면에서 도달 가능한 것으로 분류된 후보

OCPP_EXPOSED_GENERIC_CANDIDATE_HVVD:
  EXTERNAL_EXPOSED_GENERIC_CANDIDATE_HVVD 중 exposure_surface가 OCPP인 후보
```

## 12.5 Assessment Status

```
STATIC_SUSPECT_HVVD:
  정적 분석 및 후보 분류 결과 기반 suspect 상태

REVIEW_READY_HVVD:
  보강 근거와 위험도 산출이 완료되어 검토 가능한 상태

USER_EXCLUDED_HVVD:
  사용자 또는 분석자가 검증 제외한 상태

CONFIRMED_HVVD:
  runtime/protocol behavior evidence로 위험 동작이 확인된 상태

DISMISSED_HVVD:
  검증 결과 기각된 상태

UNREACHED_RISK_HVVD:
  runtime validation에서 대상 flow/sink에 도달하지 못한 상태

GUARDED_FLOW_HVVD:
  방어 근거가 관찰되었으나 완전 안전 확정은 아닌 상태
```

본 백서의 핵심 범위는 `STATIC_SUSPECT_HVVD`와 `REVIEW_READY_HVVD` 생성까지이다. `CONFIRMED_HVVD`는 F5 또는 별도 runtime validation evidence가 있을 때만 전이된다.

---

# 13. F3. Evidence-aware Similarity Enrichment

## 13.1 역할과 위치

F3는 핵심 후보 생성 파이프라인의 필수 단계가 아니라 선택적 보강 계층이다. F3는 Candidate HVVD를 확정하는 단계가 아니라, F2/F6에서 생성된 Candidate HVVD를 기존 취약 지식 또는 reference pattern과 비교하여 root cause, missing check, related CWE, impact, remediation 근거를 보강한다.

```
F2/F6 Candidate HVVD
  ↓
F3 Evidence-aware Similarity Enrichment
  ↓
F4 Risk Scoring / F7 Reporting / Analyst Review
```

F3가 추가되면 ChargeGuard-HVVD는 단순히 “위험 후보를 탐지하고 리포팅하는 시스템”을 넘어, 후보를 기존 취약 지식과 구조적으로 연결하는 evidence-aware vulnerability reasoning system으로 확장된다.

## 13.2 Reference HVVD 구축 부담과 축소 전략

F3를 처음부터 대규모 Reference HVVD Repository 기반으로 설계하면 구축 부담이 크다. 공개 CVE 설명만으로는 source, sink, flow shape, missing check, patch semantics, OCPP context를 충분히 확보하기 어렵기 때문이다. 따라서 초기 F3는 Reference HVVD가 아니라 취약 유형별 canonical Reference Pattern Repository 기반으로 시작한다.

```
초기 구현:
  Reference Pattern Repository
  - Command Injection Pattern
  - Memory Safety Pattern
  - Firmware / OTA Weakness Pattern
  - Backend Injection Pattern
  - Unsafe External Resource Pattern
  - OCPP Authorization / State Logic Pattern

장기 확장:
  Reference HVVD Repository
  - 검증된 Candidate HVVD
  - 실제 분석 사례
  - CVE/advisory/patch 기반 정규화 사례
  - OCPP domain-specific weakness case
```

즉, F3의 초기 목표는 “대규모 CVE/HVVD 검색 엔진”이 아니라, Candidate HVVD의 설명 근거를 보강하는 reference pattern matching 계층이다.

## 13.3 Reference Pattern 기본 구조

Reference Pattern은 다음 필드를 갖는 경량 기준 객체로 정의한다.

```json
{
  "pattern_id": "PATTERN-CMD-001",
  "vulnerability_class": "command_injection",
  "sink_domain": "shell_command_execution",
  "flow_shape": "external_input_to_command_string_to_shell_sink",
  "required_evidence": [
    "external_input_source",
    "command_string_construction",
    "shell_execution_sink"
  ],
  "weak_or_missing_checks": [
    "SHELL_FREE_EXECUTION",
    "COMMAND_ARG_ALLOWLIST",
    "SHELL_METACHARACTER_ESCAPE"
  ],
  "related_cwe": ["CWE-78", "CWE-88"],
  "root_cause_family": "command_boundary_missing",
  "impact_pattern": ["arbitrary_command_execution"],
  "remediation_pattern": [
    "use_shell_free_execution",
    "apply_strict_argument_allowlist",
    "avoid_string_interpolated_commands"
  ],
  "limitation": "Pattern similarity does not confirm runtime exploitability."
}
```

## 13.4 Similarity 기준

F3의 유사도는 단순 embedding similarity가 아니라 evidence 구조를 반영한 다축 유사도이다.

```
Similarity axes:
- source type similarity
- sink domain similarity
- flow shape similarity
- missing check similarity
- root cause family similarity
- related CWE similarity
- OCPP action/field context similarity
- remediation pattern similarity
```

F3 출력은 단일 score만 제공하지 않고, 왜 유사한지 `similarity_basis`를 함께 제공해야 한다.

```json
{
  "candidate_id": "HVVD-CAND-00042",
  "matched_pattern_id": "PATTERN-CMD-001",
  "similarity_score": 0.87,
  "similarity_basis": [
    "same_sink_domain: shell_command_execution",
    "same_flow_shape: external_input_to_command_string_to_shell_sink",
    "same_missing_check: SHELL_FREE_EXECUTION",
    "same_root_cause_family: command_boundary_missing"
  ],
  "interpretation": "The candidate shares a command injection pattern with missing command boundary enforcement.",
  "limitation": "Similarity does not confirm runtime exploitability."
}
```

## 13.5 F3의 경계

```
Similarity high
≠ vulnerability confirmed
≠ runtime exploitability confirmed
≠ same CVE reproduced
≠ OCPP remote exploitability confirmed
```

F3는 설명 보강과 F4/F6/F7 품질 향상을 위한 optional enrichment로 유지한다. F3 결과는 F4의 위험도 산출, F6의 HVVD 보강, F7의 설명형 리포팅에 활용될 수 있으나, 취약점 확정 또는 runtime exploitability 판단의 근거로 사용하지 않는다.

## 13.6 F3 평가 지표

F3를 논문 평가에 포함하는 경우 다음 지표를 사용한다.

```
- Top-1 Pattern Match Accuracy
- Top-3 Pattern Match Accuracy
- Root Cause Family Match Rate
- Missing Check Match Rate
- CWE Match Rate
- Similarity Rationale Quality
- Overmatch Rate
```

특히 `Overmatch Rate`는 관련 없는 reference pattern을 높은 유사도로 잘못 연결하는 비율로, F3의 신뢰성 평가에서 중요하다.

---

# 14. F4. KB/Rule-based Risk Scoring

F4는 Candidate HVVD의 위험도를 rule 기반으로 산출하는 선택적 계층이다. F4는 ML 기반 risk prediction이 아니라 F1 knowledge, F2 evidence, F2-C exposure status, missing check, sink severity를 반영한 rule-based scoring이다.

```
Risk factors:
- OCPP action risk
- payload field trust level
- sink severity
- missing check severity
- exposure status
- detector confidence
- optional similarity evidence
```

F4는 취약점 확정이 아니라 검토 우선순위와 reporting priority를 제공한다.

---

# 15. F7. LLM-based Explainable Reporting

F7은 HVVD를 사용자 역할별 설명형 리포트로 변환한다. F7의 입력은 원시 코드가 아니라 F6에서 생성된 evidence-aware HVVD이다.

```
Developer Report:
  수정 위치, missing check, remediation guide 중심

Security Analyst Report:
  source-sink flow, root cause, CWE, exposure status 중심

Evaluator Report:
  evidence traceability, limitation, assessment status 중심

Manager Summary:
  영향, 위험도, 대응 우선순위 중심
```

F7도 취약점을 새로 판단하지 않는다. F7은 HVVD에 있는 evidence와 limitation을 유지한 채 설명을 생성한다.

---

# 16. 구현 전략

## 16.1 단계적 구현 전략

ChargeGuard-HVVD의 구현은 한 번에 모든 언어와 모든 대상 시스템을 처리하는 방식이 아니라, controlled validation과 real-world extension을 분리한다.

```
Phase 1. C 기반 충전기 controlled validation
  - synthetic charger variant set 구축
  - Command Injection, Memory Safety, Firmware / OTA Weakness Detector 검증
  - evidence package, detector output, HVVD schema 안정화

Phase 2. Java 기반 CSMS real-world extension
  - inbound OCPP action handler mapping, outbound command path mapping
  - DTO / command input field binding
  - service/repository/command dispatch path 추적

Phase 3. 논문/제품 수준 평가
  - baseline 비교
  - ablation study
  - real-world case study
  - HVVD usefulness 평가
```

## 16.2 C 기반 충전기 controlled validation

C 기반 synthetic charger dataset은 핵심 메커니즘 검증용이다.

```
대상 모듈:
- firmware_update.c
- diagnostic_cmd.c
- configuration_parser.c
- meter_value_parser.c
- local_cli.c
- ocpp_handler_stub.c

취약 유형:
- external input → command string → system/popen
- payload field → fixed buffer → strcpy/sprintf/memcpy
- firmware_url → download → install_firmware without signature verification
```

이 단계의 목적은 실제 제품 취약점 발견이 아니라 `Static Evidence → Type-specific LLM Classification → Candidate HVVD`의 작동성을 검증하는 것이다.

## 16.3 Java 기반 CSMS 확장

SCI급 재현성과 데이터셋 확보를 위해 Java 기반 CSMS를 주요 확장 대상으로 둔다.

Java CSMS 분석 흐름은 메시지 방향에 따라 inbound path와 outbound path로 구분한다.

```
Inbound OCPP path:
  Charge Point
    → OCPP WebSocket / JSON-RPC endpoint
    → Action Dispatcher
    → Inbound Action Handler
    → Request DTO / Payload Field Binding
    → Service Layer
    → Repository / Authorization / State / Validation / File / URL Sink

Outbound OCPP path:
  Admin API / Backend Operation / Scheduler / Policy Engine
    → Command Controller or Service
    → Command Request DTO / Command Input Binding
    → Authorization / Ownership / State Check
    → OCPP Command Builder
    → Command Dispatch Service
    → Charge Point
```

Java CSMS에서의 주요 Detector는 다음이다.

```
Backend Injection Detector:
  SQL/JPQL/native query injection, process injection, expression injection 후보

Unsafe External Resource Detector:
  SSRF, unsafe URL fetch, path traversal, unsafe file read/write 후보

Backend Authorization & State Logic Weakness Detector:
  station ownership, tenant boundary, idTag authorization, transaction state, connector state check 누락 후보
```

---

# 17. 데이터셋 및 평가 전략

## 17.1 데이터셋 전략

```
Dataset A. C-based Charger Synthetic Variant Set
  - controlled validation용
  - vulnerable / guarded / negative / partial / unknown case 포함

Dataset B. Java-based CSMS Open-source Code Set
  - real-world applicability 평가용
  - OCPP handler mapping, service/repository call-chain 분석

Dataset C. Java CSMS Synthetic Variant Set
  - CSMS 취약 유형별 ground truth 확보용
  - Backend Injection, Unsafe Resource, Authorization/State Logic case 포함
```

## 17.2 Baseline

```
B1. Static Analyzer only
B2. Rule-only Detector
B3. Raw-code General LLM
B4. Evidence-only General LLM without Type-specific Package
B5. Type-specific LLM Candidate Classification
B6. Type-specific LLM + Post-Processor
B7. Full Pipeline: F1 + F2-A + F2-B + F2-C + F6
```

## 17.3 평가 지표

```
F2-A 평가:
- Handler / Command Path Mapping Accuracy
- Field / Command Input Binding Accuracy
- Field Semantic Binding Accuracy
- Source-Sink / Source-Decision Flow Precision / Recall
- Observed Check Detection Accuracy
- LLM-assisted Check Semantics Classification Accuracy
- Expected Check Matching Accuracy
- Missing / Weak / Partial Check Classification Accuracy
- Static Evidence Traceability

F2-B 평가:
- Classification Label Accuracy
- Evidence Consistency Rate
- Label Validity Rate
- CWE Match Rate
- Forbidden Claim Rate
- Guarded Case Accuracy
- Partial Flow Handling Accuracy

F2-C 평가:
- External Exposure Classification Accuracy
- Exposure Surface Identification Accuracy
- External Exposure Overclaim Rate( MVP에서는 OCPP Overclaim Rate를 하위 지표로 측정)
- Exposure Evidence Completeness
- Entry-to-Sink Reachability Coverage
- Unknown Exposure Handling Accuracy

F6 평가:
- HVVD Completeness Rate
- HVVD Evidence Traceability
- Root Cause Mapping Accuracy
- Missing Check Mapping Accuracy
- Human Review Usefulness

```

SCI급 확장을 위해서는 Evidence Consistency Rate, External Exposure Overclaim Rate, Guarded Case Accuracy, Exposure Evidence Completeness, HVVD Traceability를 핵심 지표로 제시한다.

```
External Exposure Classification Accuracy
  - F2-B generic 후보를 EXTERNAL_EXPOSED / INTERNAL_ONLY / UNKNOWN_EXPOSURE로 정확히 분류했는지 평가

Exposure Surface Identification Accuracy
  - 외부 노출면을 OCPP / REST_API / ADMIN_UI / CLI / OTA_CHANNEL / MQTT / LOCAL_CONFIG 등으로 정확히 식별했는지 평가

External Exposure Overclaim Rate
  - INTERNAL_ONLY 또는 UNKNOWN_EXPOSURE 후보를 EXTERNAL_EXPOSED로 과잉 판정한 비율

Exposure Evidence Completeness
  - external entrypoint, handler, source binding, call/data-flow, sink evidence가 충분히 포함되었는지 평가

Entry-to-Sink Reachability Coverage
  - 외부 entrypoint에서 candidate sink까지의 call/data-flow 경로를 얼마나 완전하게 포착했는지 평가

Unknown Exposure Handling Accuracy
  - dynamic dispatch, callback, reflection, function pointer, unresolved
```

## 17.4 Ablation Study

```
A1. without OCPP Knowledge Layer
A2. without Type-specific Detector Package
A3. without allowed_label_space
A4. without forbidden_claims
A5. without Post-Processor
A6. without F2-C Exposure Separation
A7. without missing check evidence
A8. without LLM-assisted Validation Checker
```

Ablation의 목적은 ChargeGuard-HVVD의 각 구성요소가 실제로 output controllability, evidence consistency, overclaim suppression, HVVD completeness에 기여하는지 확인하는 것이다.

---

# 18. 대표 분석 시나리오

---

## 18.1 C 기반 충전기: UpdateFirmware.location Command Injection 후보

```
Input:
  OCPP UpdateFirmware.location 또는 firmware_url parameter

Code flow:
  firmware_url
  → sprintf(cmd, "wget %s -O /tmp/fw.bin", firmware_url)
  → system(cmd)

F2-A:
  OCPP UpdateFirmware.location에서 firmware_url이 바인딩되는 경우,
  UpdateFirmware.location의 firmware_download_url 의미와 expected check 누락 후보를 식별한다.

  OCPP-native evidence:
    - action: UpdateFirmware
    - field: location
    - field_semantic: firmware_download_url
    - expected checks:
      - URL scheme validation
      - host allowlist
      - safe download API without shell
      - signature verification

F2-B:
  classification_label: COMMAND_INJECTION_LIKELY

  Evidence:
    - external or unresolved input is used as firmware_url
    - firmware_url is embedded into a command string
    - command string reaches system(cmd)

F2-C:
  exposure_class: EXTERNAL_EXPOSED 또는 UNKNOWN_EXPOSURE

  Case 1. OCPP UpdateFirmware.location에서 firmware_url까지의 binding 근거가 존재하는 경우:
    exposure_class: EXTERNAL_EXPOSED
    exposure_surface: OCPP
    exposure_entrypoint:
      - action: UpdateFirmware
      - field: location
      - handler: UpdateFirmware handler

  Case 2. firmware_url parameter의 외부 입력 출처를 정적으로 확인할 수 없는 경우:
    exposure_class: UNKNOWN_EXPOSURE
    exposure_surface: UNKNOWN

F6:
  Case 1:
    EXTERNAL_EXPOSED_GENERIC_CANDIDATE_HVVD
    - vulnerability_class: COMMAND_INJECTION
    - exposure_surface: OCPP
    - linked_ocpp_action: UpdateFirmware
    - linked_ocpp_field: location
    - evidence_refs: source-flow-sink evidence, OCPP binding evidence, missing check evidence

  Case 2:
    GENERIC_CODE_CANDIDATE_HVVD
    - vulnerability_class: COMMAND_INJECTION
    - exposure_class: UNKNOWN_EXPOSURE
    - limitation: external input origin is not statically confirmed

Limitation:
  external exposure does not imply confirmed runtime exploitability
  system(cmd) reachability does not imply successful command execution under runtime constraints
```

## 18.2 Java CSMS: RemoteStartTransaction Authorization / State Check Missing 후보

```
Input:
  RemoteStartTransaction-related command input
  - idTag
  - connectorId
  - chargePointId
  - operatorId 또는 tenantId

Code flow:
  Admin API / Backend Operation
    → RemoteStartCommandController.remoteStart(...)
    → remoteStartCommandService.start(...)
    → commandService.sendRemoteStartCommand(...)

F2-A:
  RemoteStartTransaction이 CSMS_TO_CHARGE_POINT 방향의 outbound remote command action임을 식별한다.
  command input field가 remote command dispatch까지 전달되는지 추적하고,
  idTag authorization, station ownership, connector availability, station online state,
  transaction state check가 관찰되는지 비교한다.

F2-B:
  Backend Authorization & State Logic Weakness 후보로 분류 가능

F2-C:
  이 후보는 F2-A 주도 OCPP-native candidate이므로 F2-C가 다시 OCPP_REACHABLE로 판정하지 않는다.
  단, 동일 코드 흐름이 F2-B generic candidate로도 생성된 경우에는 external exposure evidence로 OCPP command path를 참조할 수 있다.

F6:
  OCPP_NATIVE_CANDIDATE_HVVD
  - action: RemoteStartTransaction
  - message_direction: CSMS_TO_CHARGE_POINT
  - sink_domain: REMOTE_COMMAND_DISPATCH
  - missing_check_candidates:
    - OPERATOR_PERMISSION_CHECK
    - STATION_OWNERSHIP_CHECK
    - IDTAG_AUTHORIZATION_CHECK
    - CONNECTOR_AVAILABILITY_CHECK
    - STATION_ONLINE_STATE_CHECK
    - TRANSACTION_STATE_CHECK

Limitation:
  정적 evidence만으로 runtime exploitability 또는 실제 원격 충전 시작 성공 여부를 확정하지 않는다.
```

## 18.3 Java CSMS: UpdateFirmware.location Unsafe URL 후보

```
Input:
  UpdateFirmware.location

Potential sink:
  URL.openConnection()
  HttpClient.send()
  RestTemplate.exchange()
  firmware URL forwarding

Expected checks:
  - URL scheme validation
  - host allowlist
  - internal network block
  - firmware policy check
  - firmware integrity check
  - safe download API usage
  - station ownership

F2-A:
  UpdateFirmware.location의 firmware_download_url 의미와 expected check를 기준으로
  URL scheme validation, host allowlist, firmware policy check, firmware integrity check,
  safe download API 사용 여부를 분석한다.

F2-B:
  UNSAFE_EXTERNAL_RESOURCE_POSSIBLE

F2-C:
  F2-B가 생성한 UNSAFE_EXTERNAL_RESOURCE_POSSIBLE generic 후보에 대해
  OCPP UpdateFirmware.location에서 URL sink까지의 도달 근거가 확인되는 경우:

  exposure_class: EXTERNAL_EXPOSED
  exposure_surface: OCPP
  exposure_entrypoint:
  - action: UpdateFirmware
  - field: location
  - handler 또는 command path: UpdateFirmware dispatch path

Limitation:
  external exposure does not imply confirmed SSRF or exploitable unsafe URL behavior
  runtime network reachability and firmware policy bypass require additional validation

F6:
  evidence-aware HVVD with unsafe URL / firmware download limitation
```

# 19. 연구적 가치

ChargeGuard-HVVD의 연구적 가치는 LLM으로 취약점을 직접 확정하는 데 있지 않다. **핵심은 일반 LLM을 정적 분석 evidence와 Detector Package로 제어하여, 도메인 의미를 포함한 취약 후보를 구조화하는 것이다.**

```
핵심 연구 가치:
- OCPP action/field의 보안 의미를 정적 분석 evidence와 결합
- Raw-code LLM의 hallucination과 overclaim을 줄이는 evidence-bounded 구조
- 취약 후보 분류와 external exposure 판단을 분리
- HVVD를 통해 machine-readable하면서 human-reviewable한 결과 생성
- C 기반 controlled validation과 Java CSMS real-world extension이 가능한 확장 구조
```

F3를 포함하면 연구 가치는 다음 방향으로 강화된다.

```
F3 포함 시 강화 가치:
- Candidate HVVD와 기존 취약 지식의 구조적 연결
- Reference Pattern 기반 root cause / missing check / impact / remediation 보강
- F4 risk scoring의 근거 품질 향상
- F7 reporting의 groundedness 향상
- ablation study를 통한 보강 효과 검증 가능
```

따라서 백서 기준 최종 포지션은 다음과 같다.

```
F1 + F2-A + F2-B + F2-C + F6:
  핵심 evidence-aware HVVD 생성 경로

F3 + F4 + F7:
  논문성·설명성·검토 우선순위를 높이는 보강 경로
```

SCI급 연구로 확장하려면 다음 보강이 필요하다.

```
- F1 Knowledge Layer 구축 절차와 schema 객관화
- F2-A 정적 분석 알고리즘 구체화
- F2-B Detector Package의 output controllability 실험
- F2-C exposure separation 효과 검증
- F3 Reference Pattern matching 성능 및 overmatch 평가
- F6 HVVD traceability와 completeness 평가
- synthetic dataset + real-world Java CSMS case study
- baseline comparison + ablation study
```

---

# 20. 한계 및 향후 확장

## 20.1 현재 범위의 한계

```
- 정적 분석 evidence 품질에 의존
- LLM 출력 비결정성 존재
- Detector Package 설계 편향 가능
- F2/F6 결과는 runtime exploitability를 확인하지 않음
- Reference HVVD Repository 구축에는 장기 축적이 필요
- Java CSMS framework 분석에는 별도 정적 분석 전략이 필요
```

## 20.2 향후 확장

```
F5 Protocol Behavior Validation:
  OCPP state-aware scenario generation, targeted validation, runtime evidence 수집

Java CSMS 확장:
  Inbound OCPP handler mapping,
  outbound command path mapping,
  DTO/command input binding,
  service/repository 분석,
  Backend Authorization & State Logic Weakness Detector 확장

Reference Pattern Repository 확장:
  초기 canonical pattern에서 검증된 Reference HVVD repository로 발전

CI/CD 연계:
  pull request 단계의 OCPP-aware security candidate review

Runtime telemetry 연계:
  HVVD lifecycle 상태와 운영 evidence 연결
```

---

# 21. 결론

ChargeGuard-HVVD는 OCPP action/field의 보안 의미를 정적 분석 evidence와 결합하고, 일반 LLM을 취약 유형별 Detector Package로 제어하여, external exposure 판단과 분리된 근거 추적형 Candidate HVVD를 생성하는 EV 충전 인프라 소스코드 취약 후보 분석 프레임워크이다.

본 백서는 전체 프레임워크의 기준선을 정의한다. F2-B의 세부 Detector Package 설계는 별도 문서에서 확장하며, ChargeGuard 백서는 전체 기능 간 책임 경계와 일관성을 유지하는 역할을 한다.

최종 정의는 다음과 같다.

```
ChargeGuard-HVVD는
OCPP action/field의 보안 의미를 정적 분석 evidence와 결합하고,
일반 LLM을 취약 유형별 Detector Package로 제어하여,
external exposure 판단과 분리된 근거 추적형 Candidate HVVD를 생성하는
EV 충전 인프라 소스코드 취약 후보 분석 프레임워크이다.
```

핵심 메시지는 다음과 같다.

```
ChargeGuard-HVVD의 가치는 LLM의 취약점 확정 능력이 아니라,
LLM을 evidence-bounded하게 제어하여
정적 분석 결과를 신뢰 가능한 Candidate HVVD로 구조화하는 데 있다.
```