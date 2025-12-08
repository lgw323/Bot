# -*- coding: utf-8 -*-
import json
import os
import asyncio
import google.generativeai as genai
import sys
import time

sys.path.append("..")
import config
from modules import reporter

INPUT_FILE = config.PROCESSED_DATA_DIR / "clean_data.json"

# --- 1. [1차 분석] 조각 분석 프롬프트 ---
PARTIAL_ANALYSIS_PROMPT = """
당신은 데이터 심리학자이자 정치 사회학 프로파일러입니다.
아래 텍스트는 특정 디스코드 유저의 대화 내용입니다.
이 텍스트에서 드러나는 유저의 **성향적 단서(Cues)**를 찾아 간결하게 메모하세요.

[중점 탐색 항목]
1. **정치/사회적 성향 단서**: 권위/규범 태도, 경제/사회 관점, 정치적 밈 맥락.
2. **문화/게임 소비 패턴**: 선호 장르, 플레이 스타일, 서브컬처 몰입도.
3. **화법 및 성격**: 논리/감정, 공격성, 유머 코드.

[대화 데이터]
{chunk_text}

[출력 형식]
- 핵심 특징만 불조(Bullet point)로 나열.
"""

# --- 2. [2차 분석] 종합 리포트 프롬프트 (수정 없음, 동일) ---
FINAL_SYNTHESIS_PROMPT = """
당신은 엘리트 프로파일러입니다. 아래 내용은 한 유저의 3년 치 대화 데이터를 분석한 '관찰 노트'들입니다.
이 내용을 종합하여, 해당 유저의 정체성을 꿰뚫는 **[심층 프로파일링 보고서]**를 작성하세요.

[관찰 노트 모음]
{summaries}

---

[보고서 작성 가이드라인 (엄수)]

### 1. 🏛️ 사회/정치적 성향 및 가치관 (Political & Social Compass)
*단순한 보수/진보 구분을 넘어, 사회를 바라보는 근본적인 프레임을 분석하세요.*
- **이념적 스펙트럼**: (예: 자유지상주의적 우파, 냉소적 허무주의, 실용주의적 중도 등)
- **예상 지지 사회 시스템**: 이 유저가 이상적이라고 생각하거나, 무의식적으로 지향하는 체제는 무엇입니까?
    - *보기: 기술관료제(Technocracy), 능력주의(Meritocracy), 무정부 자본주의, 사회민주주의, 권위주의적 질서 등*
- **현실 인식 태도**: 사회 이슈나 권위에 대해 어떤 반응(분노, 조롱, 무관심, 분석)을 보입니까?

### 2. 🎮 문화적 DNA 및 게임 취향 (Cultural Archetype)
- **Core Game Genre**: 선호하는 게임들의 공통된 메커니즘은 무엇입니까? (예: 극한의 효율 추구, 서사 몰입, 피지컬 경쟁)
- **서브컬처 수용도**: 소위 '오타쿠 문화'에 대한 심도와 태도.

### 3. 💬 성격 및 커뮤니케이션 매트릭스 (Personality Matrix)
- **화법 분석**: 텍스트 뒤에 숨겨진 감정 상태와 지적 수준.
- **대인 관계**: 집단 내에서 어떤 역할(리더, 추종자, 광대, 관찰자)을 수행합니까?
- **추정 MBTI**: (가장 유력한 유형 1개와 그 논리적 근거)

### 4. 🔑 프로파일링 요약 (Executive Summary)
- 이 사람을 정의하는 **핵심 키워드 3가지** (형용사+명사 조합 권장)
- **한 줄 총평**: 이 유저는 어떤 사람입니까?

---

[작성 톤앤매너]
- **냉철하고 분석적인 전문가의 어조**를 유지하세요.
- 추상적인 표현보다는 **"~라는 발언에서 ~한 성향이 드러남"**과 같이 구체적인 근거를 제시하세요.
- **형식을 절대적으로 준수**하여, 누가 봐도 동일한 포맷의 보고서가 되도록 하세요.
"""

# 중요 변경: 청크 크기를 50만 자로 대폭 상향 (약 15~20만 토큰)
# Gemini 1.5 Flash는 100만 토큰까지 가능하므로 충분함.
# 요청 횟수를 줄이기 위함.
CHUNK_SIZE = 500000 

async def analyze_chunk(model, text_chunk, index, total):
    """데이터 조각 1차 분석"""
    print(f"     🧩 데이터 조각 심층 분석 중... ({index}/{total})")
    try:
        response = await asyncio.to_thread(
            model.generate_content,
            PARTIAL_ANALYSIS_PROMPT.format(chunk_text=text_chunk)
        )
        return response.text
    except Exception as e:
        # 429 에러가 나면 여기서 잡아서 처리 가능 (지금은 로그만)
        print(f"     ⚠️ 조각 {index} 분석 실패: {e}")
        if "429" in str(e):
            print("     ⏳ 쿼터 초과! 60초 대기 후 재시도합니다...")
            await asyncio.sleep(60)
            return await analyze_chunk(model, text_chunk, index, total) # 재귀 재시도
        return ""

async def analyze_user(username, user_data):
    full_text = user_data['full_text']
    msg_count = user_data['msg_count']
    
    print(f"   ▶ [{username}] 프로파일링 시작... (Data: {msg_count:,} msgs)")

    model = genai.GenerativeModel(config.GEMINI_MODEL)
    
    # 1. 텍스트 분할 (Chunking)
    chunks = [full_text[i:i+CHUNK_SIZE] for i in range(0, len(full_text), CHUNK_SIZE)]
    total_chunks = len(chunks)
    
    partial_results = []
    
    # 2. 분석 실행
    # 청크가 1개면 바로 최종 분석으로 넘기면 토큰은 아끼지만,
    # "관찰 노트" -> "종합 보고서"라는 2단계 추론 과정을 거치는 것이 퀄리티가 훨씬 좋으므로 유지합니다.
    # 단, 청크 사이즈를 키웠으므로 요청 횟수는 획기적으로 줄어듭니다.
    
    print(f"     📦 데이터 처리: {total_chunks}회 요청으로 최적화됨.")
    
    for i, chunk in enumerate(chunks):
        result = await analyze_chunk(model, chunk, i+1, total_chunks)
        if result:
            partial_results.append(result)
        
        # 요청 간 쿨타임 (안전하게 5초)
        if i < total_chunks - 1:
            await asyncio.sleep(5)

    # 3. 종합 분석 (Synthesis)
    if not partial_results:
        return "분석 실패: 유효한 데이터가 없거나 모든 요청이 차단되었습니다."

    print(f"     🔄 최종 리포트 작성 중...")
    combined_notes = "\n\n".join(partial_results)
    
    final_prompt = FINAL_SYNTHESIS_PROMPT.format(summaries=combined_notes)
    
    try:
        final_response = await asyncio.to_thread(
            model.generate_content,
            final_prompt
        )
        print(f"     ✅ [{username}] 프로파일링 완료!")
        return final_response.text
    except Exception as e:
        print(f"     ❌ 최종 리포트 생성 실패: {e}")
        if "429" in str(e):
             print("     ⏳ 최종 단계 쿼터 초과! 60초 대기 후 마지막 시도...")
             await asyncio.sleep(60)
             try:
                 final_response = await asyncio.to_thread(model.generate_content, final_prompt)
                 return final_response.text
             except Exception as e2:
                 return f"재시도 실패: {e2}\n\n[중간 분석 데이터]\n{combined_notes}"
        return f"분석 중 오류 발생: {e}\n\n[중간 분석 데이터]\n{combined_notes}"

async def run_analysis(target_user=None):
    if not config.GOOGLE_API_KEY:
        print("❌ 설정 오류: GOOGLE_API_KEY가 없습니다.")
        return

    genai.configure(api_key=config.GOOGLE_API_KEY)

    if not os.path.exists(INPUT_FILE):
        print(f"❌ 데이터 오류: 전처리된 파일이 없습니다 ({INPUT_FILE})")
        return

    with open(INPUT_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)

    targets = {}
    if target_user and target_user != "ALL":
        if target_user in data:
            targets[target_user] = data[target_user]
        else:
            print(f"❌ 사용자 '{target_user}'를 찾을 수 없습니다.")
            return
    else:
        targets = data

    print(f"🧠 AI 프로파일러 가동 (대상: {len(targets)}명)")
    print(f"   - 분석 모델: {config.GEMINI_MODEL}")
    print(f"   - 최적화: 대용량 청크 처리 (요청 수 최소화)")
    
    for i, (user, user_data) in enumerate(targets.items()):
        print(f"\n[{i+1}/{len(targets)}] ========================================")
        
        analysis_result = await analyze_user(user, user_data)
        reporter.save_report(user, analysis_result)
        
        # 유저 간 쿨타임을 대폭 늘림 (연속 요청으로 인한 429 방지)
        if i < len(targets) - 1:
            print("     💤 API 안전 쿨타임 (10초)...")
            await asyncio.sleep(10)

    print("\n✨ 모든 프로파일링 작업이 완료되었습니다.")