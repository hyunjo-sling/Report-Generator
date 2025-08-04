import streamlit as st
import google.generativeai as genai
import re
from datetime import datetime, timedelta
from streamlit_cookies_manager import EncryptedCookieManager
import streamlit_antd_components as sac # UX 개선용 컴포넌트
from streamlit_copy_to_clipboard import st_copy_to_clipboard # UX 개선용 컴포넌트

# --- 페이지 기본 설정 ---
st.set_page_config(page_title="AI 수행평가 생성기", page_icon="👾", layout="wide")

# --- API 키 설정 ---
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    # <<< 핵심 수정: 현재 사용 가능한 최신 고성능 모델로 수정 >>>
    model = genai.GenerativeModel('gemini-2.5-pro') 
except Exception:
    st.error("🚨 구글 API 키를 설정해주세요! .streamlit/secrets.toml 파일에 키를 추가해야 합니다."); st.stop()

# --- 디자인(CSS) 주입 함수 ---
def apply_custom_css():
    st.markdown("""
        <style>
        @import url('https://cdn.jsdelivr.net/gh/orioncactus/pretendard/dist/web/static/pretendard.css');
        html, body, [class*="st-"], [class*="css-"] { font-family: 'Pretendard', sans-serif; }
        .stButton>button {
            border: 1px solid #4A90E2; border-radius: 8px; color: #4A90E2; background-color: transparent;
            transition: all 0.2s ease-in-out;
        }
        .stButton>button:hover {
            border-color: #ffffff; color: #ffffff; background-color: #4A90E2;
        }
        </style>
    """, unsafe_allow_html=True)

# --- 비용 및 사용량 표시 함수 ---
def display_usage_and_cost(response, task_name="이번 요청"):
    try:
        usage_data = response.usage_metadata
        input_tokens = usage_data.prompt_token_count
        output_tokens = usage_data.candidates_token_count
        total_tokens = usage_data.total_token_count
        # <<< 핵심 수정: Gemini 1.5 Pro의 공식 단가로 수정 >>>
        input_cost = (input_tokens / 1_000_000) * 1.25 
        output_cost = (output_tokens / 1_000_000) * 10.00
        total_cost = input_cost + output_cost
        with st.expander(f"📊 {task_name}에 대한 사용량 및 예상 비용 확인하기"):
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("입력 토큰", f"{input_tokens:,}")
            with c2: st.metric("출력 토큰", f"{output_tokens:,}")
            with c3: st.metric("총 토큰", f"{total_tokens:,}")
            st.markdown("---")
            cc1, cc2, cc3 = st.columns(3)
            with cc1: st.metric("입력 비용(USD)", f"${input_cost:.6f}")
            with cc2: st.metric("출력 비용(USD)", f"${output_cost:.6f}")
            with cc3: st.metric("총 비용(USD)", f"${total_cost:.6f}")
    except: st.warning("사용량 메타데이터를 가져오는 데 실패했습니다.")

def initialize_session_state():
    states = {'stage': 0, 'topic_list': [], 'user_inputs': {}, 'processed_files': [], 'recommend_toggle': False, 'topic_option': "주제 직접 입력", 'generated_text': ""}
    for key, value in states.items():
        if key not in st.session_state: st.session_state[key] = value

def check_password():
    # (비밀번호 확인 로직은 수정 없음, 생략)
    cookies = EncryptedCookieManager(password=st.secrets.get("COOKIE_ENCRYPTION_KEY", "default_secret"))
    if not cookies.ready(): st.stop()
    if cookies.get("login_status"): return True
    try: correct_password = st.secrets["APP_PASSWORD"]
    except KeyError: st.error("🚨 앱 비밀번호가 설정되지 않았습니다."); return False
    with st.form("password_form"):
        st.title("🔐 접속 인증"); password = st.text_input("비밀번호", type="password")
        if st.form_submit_button("확인"):
            if password == correct_password:
                cookies['login_status'] = 'logged_in'; cookies.save(); st.rerun()
            else: st.error("비밀번호가 일치하지 않습니다.")
    return False

# --- 메인 앱 로직 ---
def main():
    apply_custom_css()
    st.title("👾 AI 수행평가 생성기")
    st.markdown("Gemini 2.5 Pro 사용 중")
    initialize_session_state()

    # <<< UX 개선: 진행 단계 시각화 >>>
    sac.steps(
        items=[
            sac.StepsItem(title='정보 입력', icon='pencil-square'),
            sac.StepsItem(title='주제 선택', icon='check2-square', disabled=(not st.session_state.user_inputs.get('recommend', False))),
            sac.StepsItem(title='결과 확인', icon='card-checklist'),
        ], index=st.session_state.stage, format_func='title', placement='horizontal'
    )
    
    if st.session_state.stage > 0:
        if st.sidebar.button("🔄 새로운 수행평가 생성하기", use_container_width=True):
            st.session_state.clear(); st.rerun()

    st.markdown("<hr>", unsafe_allow_html=True)

    if st.session_state.stage == 0: render_initial_input_stage()
    elif st.session_state.stage == 1: render_topic_recommendation_stage()
    elif st.session_state.stage == 2: render_final_generation_stage()

def render_initial_input_stage():
    with st.form(key="main_form"):
        st.subheader("1. 수행평가 설명 및 요청사항")
        description = st.text_area("수행평가 안내문을 여기에 붙여넣거나, 원하는 결과물(형식, 분량, 강조점 등)을 자세히 설명해주세요.", height=250, help="이 항목은 필수입니다.")
        uploaded_files = st.file_uploader("관련 파일 첨부 (최대 5개, PDF/이미지 권장)", type=['png', 'jpg', 'jpeg', 'pdf'], accept_multiple_files=True)
        st.markdown("---")
        st.subheader("2. 주제 설정 방식")
        recommend_topics = st.toggle("주제 추천 활성화", help="AI에게 탐구 주제를 추천받고 싶을 때 이 옵션을 켜세요.")
        
        final_topic_input = None
        if recommend_topics:
            st.info("AI가 입력된 설명과 파일을 바탕으로 주제 5개를 추천합니다.")
        else:
            topic_option = st.radio("주제 선택", ["주제 직접 입력", "주제 없음(설명에 모두 포함)"], horizontal=True)
            if topic_option == "주제 직접 입력": final_topic_input = st.text_input("탐구할 주제를 입력하세요:")
        
        with st.expander("🔍 추가 정보 입력 (선택 사항)"):
             subject = st.text_input("과목/단원"); level = st.text_input("학생 수준"); achievement = st.text_input("핵심 개념")
        submitted = st.form_submit_button("🚀 생성 시작!")

    if submitted:
        if not description: st.warning("⚠️ '수행평가 설명 및 요청사항'은 필수입니다."); st.stop()
        st.session_state.user_inputs = {
            "description": description, "subject": subject, "level": level, "achievement": achievement,
            "files": uploaded_files, "recommend": recommend_topics, "topic_input": final_topic_input
        }
        st.session_state.stage = 1 if recommend_topics else 2
        st.rerun()

def render_topic_recommendation_stage():
    st.subheader("💡 AI 추천 주제")
    if not st.session_state.topic_list:
        with st.spinner("AI가 창의적인 주제 5개를 만들고 있습니다..."):
            inputs = st.session_state.user_inputs; files_to_use = []
            if inputs['files']:
                for f in inputs['files']: files_to_use.append(genai.upload_file(path=f, mime_type=f.type))
            st.session_state.processed_files = files_to_use
            rec_prompt = f"당신은 학생들의 수행평가를 도와주는 최고의 조언가입니다. 아래 '수행평가 설명'과 첨부 파일들을 깊이 있게 분석하여, 창의적인 탐구 주제 5개를 추천해줘. 각 주제는 번호 목록으로 간결하게 제시해줘.\n\n### 수행평가 설명:\n{inputs['description']}"
            prompt_parts = [rec_prompt]; 
            if files_to_use: prompt_parts.extend(files_to_use)
            try:
                response = model.generate_content(prompt_parts)
                st.session_state.topic_list = re.compile(r"^\s*\d+\.\s*(.*)", re.MULTILINE).findall(response.text)
                st.markdown(response.text); display_usage_and_cost(response, "주제 추천")
            except Exception as e: st.error(f"주제 추천 중 오류: {e}"); st.session_state.clear(); st.rerun()
    
    if st.session_state.topic_list:
        with st.form(key="topic_choice_form"):
            chosen_topic = st.radio("마음에 드는 주제를 하나 선택하세요.", st.session_state.topic_list)
            if st.form_submit_button("✅ 이 주제로 결과물 생성"):
                st.session_state.user_inputs['topic_input'] = chosen_topic
                st.session_state.stage = 2; st.rerun()
    else: st.warning("AI가 추천 주제를 생성하지 못했습니다. 설명을 더 자세히 적어보세요.")

def render_final_generation_stage():
    st.subheader("🎉 최종 결과물")
    if not st.session_state.generated_text:
        with st.spinner("요청사항을 분석하고 최종 결과물을 생성하는 중입니다..."):
            inputs = st.session_state.user_inputs; topic = inputs.get('topic_input')
            files_to_use = st.session_state.get('processed_files', [])
            if not files_to_use and inputs['files']:
                for f in inputs['files']: files_to_use.append(genai.upload_file(path=f, mime_type=f.type))
            
            prompt = f"""... (프롬프트 내용 생략) ...""" # 이전과 동일한 최종 프롬프트
            prompt_parts = [prompt]; 
            if files_to_use: prompt_parts.extend(files_to_use)
            try:
                final_response = model.generate_content(prompt_parts)
                st.session_state.generated_text = final_response.text
                display_usage_and_cost(final_response, "최종 결과물 생성")
            except Exception as e: st.error(f"결과물 생성 중 오류: {e}")

    if st.session_state.generated_text:
        edited_text = st.text_area("결과물 (수정 가능)", value=st.session_state.generated_text, height=600)
        
        # <<< UX 개선: 복사 및 다운로드 버튼 >>>
        col1, col2 = st.columns([0.2, 0.8])
        with col1:
            st_copy_to_clipboard(edited_text, "클립보드로 복사", "✅ 복사 완료!", button_props={"use_container_width": True})
        with col2:
            st.download_button(label="마크다운(.md) 파일로 다운로드", data=edited_text, file_name=f"ai_report.md", mime="text/markdown", use_container_width=True)

if __name__ == "__main__":
    if check_password(): main()
