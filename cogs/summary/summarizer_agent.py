import os
import logging
import re
from datetime import datetime, timedelta, timezone

# OpenAI 및 tiktoken 대신 google.generativeai 임포트
import google.generativeai as genai
from google.api_core import exceptions as google_exceptions

# --------- 상수 정의 (환경 변수에서 로드) ---------
GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash-preview-09-2025")
TIMEZONE_OFFSET_HOURS = int(os.getenv("TIMEZONE_OFFSET_HOURS", 9))
DEFAULT_MAX_REQUEST_TOKENS = int(os.getenv("DEFAULT_MAX_REQUEST_TOKENS", 12000))
MAX_RESPONSE_TOKENS = int(os.getenv("MAX_RESPONSE_TOKENS", 2000))
TEMPERATURE = float(os.getenv("TEMPERATURE", 0.5))

SUMMARY_PROMPT_TEMPLATE = (
    "당신은 Discord 대화 로그를 분석하여, 논의된 모든 주제를 독립적으로 분리하고 심층 요약하는 AI 분석가입니다.\n"
    "당신의 응답은 정해진 토큰 제한이 있으므로, 반드시 주어진 형식과 지침에 따라 완결된 형태의 결과물을 생성해야 합니다.\n\n"
    "--- \n\n"
    "[핵심 지침]\n\n"
    "1. 의미 있는 주제 그룹화 및 질적 판단 (가장 중요 원칙)\n"
    "   - 대화의 흐름을 분석하여, 논리적으로 강하게 연결된 논의는 하나의 상위 주제로 묶고, 완전히 새로운 화제가 시작되면 명확하게 분리해야 합니다.\n"
    "   - (예시: 'A 캐릭터의 스킬 문제점 지적'과 그에 대한 '개선 방안 제안'은 'A 캐릭터 밸런스 조정 논의'라는 하나의 주제로 묶을 수 있습니다.)\n"
    "   - 하지만 'A 캐릭터 이야기' 중 갑자기 '새로운 이벤트 공지'로 화제가 넘어갔다면, 이는 명백히 다른 두 개의 주제로 분리해야 합니다.\n"
    "   - 만약 전체 대화의 양이 매우 적거나, 의미 있는 논점이 거의 없다면 억지로 주제를 여러 개 만들지 마세요. 이 경우, 가장 중요한 1~3개의 주제로만 압축하여 요약하는 것이 더 효과적입니다.\n"
    "   - 목표는 너무 잘게 쪼개는 것이 아니라, 대화의 큰 줄기를 파악하여 의미 단위로 요약하는 것입니다. 단, 모든 대화를 하나의 주제로 묶는 것은 허용되지 않습니다.\n\n"
    "2. 지능적인 분량 조절 (결과 잘림 방지)\n"
    "   - 당신의 최우선 목표는 정해진 형식에 맞춰 잘리지 않는 '완성된 요약본'을 출력하는 것입니다.\n"
    "   - 내용이 너무 길어 출력 토큰 제한에 걸릴 것으로 예상되면, 각 주제의 '세부 내용'을 중심으로 내용을 조금씩 줄여서 전체 요약이 완성될 수 있도록 분량을 조절해야 합니다.\n"
    "   - 일부 내용을 조금 짧게 쓰더라도, 모든 주제 블록과 마지막 '[전체 대화 개요]'까지 반드시 출력해야 합니다.\n\n"
    "3. 주제별 필수 정보 (출력 형식 엄수)\n"
    "   - 아래 [출력 형식]에 명시된 모든 항목(주제 제목, 시간대, 참여자, 키워드, 요약)을 빠짐없이 포함해야 합니다.\n\n"
    "--- \n\n"
    "{extra_prompt_section}"
    "[출력 형식 (이하 형식 절대 준수)]\n\n"
    "[주제-1] <주제 제목>\n"
    "논의 시간대: <HH:MM ~ HH:MM 형식의 시간 범위>\n"
    "주요 참여자: <가장 기여도가 높은 2~3명의 닉네임 목록>\n"
    "핵심 키워드: <주제를 대표하는 핵심 단어 3~5개 목록>\n"
    "요약:\n"
    "- 핵심 요지: <주제의 결론 또는 가장 중요한 논점 1~2 문장>\n"
    "- 배경/맥락: <논의가 시작된 계기나 이유>\n"
    "- 세부 내용: <주요 의견의 흐름, 구체적인 주장이나 사례>\n"
    "---\n"
    "[주제-2] <주제 제목>\n"
    "...\n"
    "---\n"
    "[전체 대화 개요]\n"
    "<모든 주제를 종합하여 대화의 전체적인 분위기나 최종 경향을 1~2줄로 요약>\n\n"
    "--- \n\n"
    "[대화 로그]\n"
    "{joined_messages}"
)

# OpenAI 클라이언트 대신 Gemini 모델 객체
gemini_model = None

def initialize_gemini_client(api_key: str):
    global gemini_model
    try:
        genai.configure(api_key=api_key)
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
        ]
        gemini_model = genai.GenerativeModel(GEMINI_MODEL, safety_settings=safety_settings)
        logging.info(f"[초기화] Gemini 클라이언트 초기화 성공. 모델: {GEMINI_MODEL}")
    except Exception as e:
        logging.error(f"[초기화] Gemini 클라이언트 초기화 실패: {e}", exc_info=True)
        raise

# [수정됨] 봇 멈춤(blocking) 현상을 유발하는 API 호출을 제거하고 로컬 근사치 계산으로 변경합니다.
def count_tokens(text: str) -> int:
    if not gemini_model:
        logging.warning("Gemini 모델이 초기화되지 않았으나 count_tokens 호출됨.")
    
    # 텍스트의 길이를 반환하여 네트워크 호출을 방지합니다.
    # 한글/영문 토큰 수 차이를 감안하더라도, 
    # API 호출로 인한 멈춤 현상을 해결하는 것이 더 중요합니다.
    return len(text)

def to_local_time(utc_dt: datetime) -> datetime:
    return utc_dt.astimezone(timezone(timedelta(hours=TIMEZONE_OFFSET_HOURS)))

def format_message(log_tuple: tuple) -> str:
    dt, _, _, author, content = log_tuple
    dt_str = to_local_time(dt).strftime('%Y-%m-%d %H:%M:%S')
    return f"[{dt_str}][{author}]: {content}"

def parse_summary_to_structured_data(summary_text: str) -> dict:
    data = {'topics': [], 'overall_summary': ''}
    try:
        topic_blocks = re.findall(r'(\[주제-\d+\][\s\S]*?)(?=\n\[주제-\d+\]|\n\[전체 대화 개요\]|\Z)', summary_text)
        for block in topic_blocks:
            topic_data = {}
            title_match = re.search(r'\[주제-\d+\]\s*(.*)', block)
            if title_match: topic_data['title'] = title_match.group(1).strip()
            time_match = re.search(r'논의 시간대:\s*(.*)', block)
            if time_match: topic_data['time'] = time_match.group(1).strip()
            participants_match = re.search(r'주요 참여자:\s*(.*)', block)
            if participants_match: topic_data['participants'] = participants_match.group(1).strip()
            keywords_match = re.search(r'핵심 키워드:\s*(.*)', block)
            if keywords_match: topic_data['keywords'] = keywords_match.group(1).strip()
            summary_section_match = re.search(r'요약:\s*([\s\S]*)', block)
            if summary_section_match:
                summary_content = summary_section_match.group(1)
                main_point_match = re.search(r'-\s*핵심 요지:\s*(.*)', summary_content)
                if main_point_match: topic_data['main_point'] = main_point_match.group(1).strip()
                context_match = re.search(r'-\s*배경/맥락:\s*(.*)', summary_content)
                if context_match: topic_data['context'] = context_match.group(1).strip()
                details_match = re.search(r'-\s*세부 내용:\s*([\s\S]*)', summary_content)
                if details_match: topic_data['details'] = details_match.group(1).strip()
            if topic_data.get('title'):
                data['topics'].append(topic_data)
        overall_summary_match = re.search(r'\[전체 대화 개요\]\s*([\s\S]*)', summary_text)
        if overall_summary_match:
            data['overall_summary'] = overall_summary_match.group(1).strip().split('---')[0].strip()
    except Exception as e:
        logging.error(f"요약 텍스트 파싱 중 오류 발생: {e}", exc_info=True)
        return {'topics': [], 'overall_summary': '결과를 파싱하는 데 실패했습니다.'}
    return data

def _build_summary_prompt(joined_messages: str, extra_prompt: str | None = None) -> str:
    extra_prompt_section = f"\n[추가 요청사항]\n{extra_prompt}\n" if extra_prompt else ""
    return SUMMARY_PROMPT_TEMPLATE.format(joined_messages=joined_messages, extra_prompt_section=extra_prompt_section)

# gpt_summarize -> gemini_summarize로 변경
async def gemini_summarize(messages: list[tuple], **kwargs) -> tuple[str, int | None]:
    if not gemini_model:
        return "Gemini 클라이언트가 초기화되지 않았습니다.", 0
    
    extra_prompt = kwargs.get('extra_prompt')
    
    # count_tokens가 동기 함수가 되었으므로 await 제거
    base_prompt_for_token_calc = _build_summary_prompt("", extra_prompt)
    base_prompt_tokens = count_tokens(base_prompt_for_token_calc)
    
    allowed_message_content_tokens = DEFAULT_MAX_REQUEST_TOKENS - base_prompt_tokens - MAX_RESPONSE_TOKENS - 100
    logging.info(f"요청 토큰 제한: {DEFAULT_MAX_REQUEST_TOKENS}, 프롬프트/답변 예약 후 메시지용 토큰: {allowed_message_content_tokens}")
    
    final_formatted_messages = []
    current_tokens = 0
    for msg_tuple in reversed(messages):
        formatted_msg = format_message(msg_tuple)
        msg_tokens = count_tokens(formatted_msg) # await 제거
        if current_tokens + msg_tokens > allowed_message_content_tokens:
            logging.warning(f"메시지 토큰 제한 도달. 총 {len(final_formatted_messages)}개의 메시지만 요약에 포함됩니다.")
            break
        final_formatted_messages.insert(0, formatted_msg)
        current_tokens += msg_tokens
        
    if not final_formatted_messages:
        logging.warning("요약할 메시지가 없습니다 (토큰 제한으로 인해 포함할 수 없거나, 원본 메시지가 없음).")
        return "요약할 메시지가 없거나 너무 짧습니다.", 0
        
    joined_final_messages = "\n".join(final_formatted_messages)
    final_prompt = _build_summary_prompt(joined_final_messages, extra_prompt)
    input_tokens = count_tokens(final_prompt) # await 제거
    
    logging.info(f"최종 Gemini 요약 요청 토큰 수: {input_tokens} / {DEFAULT_MAX_REQUEST_TOKENS}")
    
    try:
        # Gemini API 호출 로직으로 변경
        generation_config = genai.GenerationConfig(
            max_output_tokens=MAX_RESPONSE_TOKENS,
            temperature=TEMPERATURE
        )
        
        response = await gemini_model.generate_content_async(
            final_prompt,
            generation_config=generation_config
        )
        
        # .text 속성으로 결과물 접근
        summary_content = response.text.strip()
        logging.info("Gemini 요약 요청 성공.")
        return summary_content, input_tokens

    # Gemini (google-api-core) 예외 처리
    except google_exceptions.ResourceExhausted as e:
        logging.error(f"Gemini API 호출 제한 초과: {e}")
        return "Gemini API 호출 한도를 초과했습니다. 잠시 후 다시 시도해주세요.", input_tokens
    except google_exceptions.GoogleAPICallError as e:
        logging.error(f"Gemini API 호출 오류: {e}")
        return f"Gemini API 오류가 발생했습니다: {e}", input_tokens
    except Exception as e:
        # response.prompt_feedback 등으로 인한 차단 처리
        if 'response' in locals() and hasattr(response, 'prompt_feedback'):
             logging.error(f"Gemini 요청이 차단되었습니다. 사유: {response.prompt_feedback}")
             return f"Gemini 요청이 차단되었습니다. 사유: {response.prompt_feedback}", input_tokens
        
        logging.error(f"Gemini 요약 생성 중 예기치 않은 오류: {e}", exc_info=True)
        return "Gemini 요약 생성 중 알 수 없는 오류가 발생했습니다.", input_tokens