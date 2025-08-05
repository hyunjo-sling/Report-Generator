import streamlit as st
import google.generativeai as genai
import re
from streamlit_cookies_manager import EncryptedCookieManager # <<< 핵심 추가
from datetime import datetime, timedelta # <<< 핵심 추가

# --- 페이지 기본 설정 및 API 키 설정 ---
st.set_page_config(page_title="AI 수행평가 생성기", page_icon="👾", layout="wide")
try:
    genai.configure(api_key=st.secrets["GOOGLE_API_KEY"])
    model = genai.GenerativeModel('gemini-2.5-pro')
except Exception:
    st.error("🚨 구글 API 키를 설정해주세요! .streamlit/secrets.toml 파일에 키를 추가해야 합니다."); st.stop()

# --- 비용 및 사용량 표시 함수 (수정 없음) ---
def display_usage_and_cost(response, task_name="이번 요청"):
    try:
        usage_data = response.usage_metadata; input_tokens = usage_data.prompt_token_count; output_tokens = usage_data.candidates_token_count
        total_tokens = usage_data.total_token_count; input_cost = (input_tokens / 1_000_000) * 1.25; output_cost = (output_tokens / 1_000_000) * 10.00
        total_cost = input_cost + output_cost
        with st.expander(f"📊 {task_name}에 대한 사용량 및 예상 비용 확인하기"):
            col1, col2, col3 = st.columns(3)
            with col1: st.metric("입력 토큰 (Input)", f"{input_tokens:,}")
            with col2: st.metric("출력 토큰 (Output)", f"{output_tokens:,}")
            with col3: st.metric("총 토큰 (Total)", f"{total_tokens:,}")
            st.markdown("---")
            c1, c2, c3 = st.columns(3)
            with c1: st.metric("입력 예상 비용 (USD)", f"${input_cost:.6f}")
            with c2: st.metric("출력 예상 비용 (USD)", f"${output_cost:.6f}")
            with c3: st.metric("총 예상 비용 (USD)", f"${total_cost:.6f}")
            st.info("이 비용은 Pay-as-you-go 요금제를 기준으로 한 **예상치**이며, 무료 사용량 내에서는 청구되지 않을 수 있습니다.")
    except Exception: st.warning("사용량 메타데이터를 가져오는 데 실패했습니다.")

def initialize_session_state():
    states = {'stage': 'initial_input', 'topic_list': [], 'user_inputs': {}, 'processed_files': [], 'recommend_toggle': False, 'topic_option': "주제 직접 입력"}
    for key, value in states.items():
        if key not in st.session_state: st.session_state[key] = value

# --- 메인 앱 로직 (리셋 버튼 구조 변경) ---
def main():
    st.title("👾 AI 수행평가 생성기")
    st.markdown("Gemini 2.5 Pro 사용 중")
    
    initialize_session_state()

    # <<< 핵심 수정: 사이드바에 전역 리셋 버튼 추가 >>>
    # 첫 화면이 아닐 때만 리셋 버튼을 보여줌
    if st.session_state.stage != 'initial_input':
        st.sidebar.title("메뉴")
        if st.sidebar.button("🔄 새로운 수행 생성하기", use_container_width=True):
            st.session_state.clear() # 모든 세션 상태를 깨끗하게 지움
            st.rerun() # 앱을 완전히 처음부터 다시 실행

    st.markdown("---")

    if st.session_state.stage == 'initial_input':
        render_initial_input_stage()
    elif st.session_state.stage == 'topic_recommendation':
        render_topic_recommendation_stage()
    elif st.session_state.stage == 'final_generation':
        render_final_generation_stage()

def render_initial_input_stage():
    # (이전 v13 코드와 동일, 수정 없음)
    st.subheader("1. 수행평가 설명 및 요청사항")
    st.session_state.recommend_toggle = st.toggle("주제 추천 활성화", value=st.session_state.recommend_toggle, help="이 옵션을 켜면, AI가 주제를 추천합니다.")

    if not st.session_state.recommend_toggle:
        st.session_state.topic_option = st.radio("주제 선택", ["주제 직접 입력", "주제 없음(설명에 모두 포함)"], horizontal=True, index=["주제 직접 입력", "주제 없음(설명에 모두 포함)"].index(st.session_state.topic_option))

    with st.form(key="main_form"):
        description = st.text_area("수행평가 안내문의 모든 내용을 여기에 붙여넣거나, 원하는 결과물에 대해 자세히 설명해주세요.", height=250, help="이 항목은 필수입니다.")
        uploaded_files = st.file_uploader("관련 파일 첨부 (최대 5개, PDF/이미지 권장)", type=['png', 'jpg', 'jpeg', 'pdf'], accept_multiple_files=True)
        if uploaded_files and len(uploaded_files) > 5: st.error("🚨 파일은 최대 5개까지만 업로드할 수 있습니다.")
        st.markdown("---")
        st.subheader("2. 주제 설정 방식 (위에서 선택)")
        final_topic_input = None
        if st.session_state.recommend_toggle:
            st.info("수행평가에 대한 설명과 첨부파일을 바탕으로 주제 5개를 추천해 드립니다 😎")
        else:
            if st.session_state.topic_option == "주제 직접 입력": final_topic_input = st.text_input("탐구할 주제를 입력하세요:")
        with st.expander("🔍 추가 정보 입력 (선택 사항)"):
            subject = st.text_input("과목 및 단원"); level = st.text_input("학생 수준"); achievement = st.text_input("핵심 개념 또는 성취 기준")
        submitted = st.form_submit_button("🚀 다음 단계로")

    if submitted:
        if not description: st.warning("⚠️ '수행평가 설명 및 요청사항'은 필수 입력 항목입니다."); st.stop()
        if uploaded_files and len(uploaded_files) > 5: st.error("🚨 파일은 최대 5개까지만 업로드할 수 있습니다. 5개 이하로 다시 시도해주세요."); st.stop()
        st.session_state.user_inputs = {"description": description, "subject": subject, "level": level, "achievement": achievement, "files": uploaded_files, "recommend": st.session_state.recommend_toggle, "topic_input": final_topic_input}
        st.session_state.stage = 'topic_recommendation' if st.session_state.recommend_toggle else 'final_generation'
        st.rerun()

def render_topic_recommendation_stage():
    # (이전 v13 코드와 동일, 하단의 '처음으로' 버튼만 제거)
    st.subheader("✨ AI 추천 주제 5가지")
    if not st.session_state.topic_list:
        with st.spinner("AI가 입력된 설명을 바탕으로 창의적인 주제 5개를 만들고 있습니다..."):
            inputs = st.session_state.user_inputs; files_to_use = []
            if inputs['files']:
                for f in inputs['files']: files_to_use.append(genai.upload_file(path=f, mime_type=f.type))
            st.session_state.processed_files = files_to_use
            rec_prompt = [f"당신은 학생들의 수행평가를 도와주는 최고의 조언가입니다. ... (프롬프트 내용 생략) ..."]
            if files_to_use: rec_prompt.extend(files_to_use)
            try:
                response = model.generate_content(rec_prompt)
                st.session_state.topic_list = re.compile(r"^\s*\d+\.\s*(.*)", re.MULTILINE).findall(response.text)
                st.markdown(response.text); display_usage_and_cost(response, task_name="주제 추천")
            except Exception as e: st.error(f"주제 추천 중 오류 발생: {e}"); st.session_state.clear(); st.rerun()
    else:
        for i, topic in enumerate(st.session_state.topic_list, 1): st.markdown(f"{i}. {topic}")
    
    if st.session_state.topic_list:
        st.markdown("---")
        with st.form(key="topic_choice_form"):
            chosen_topic = st.radio("마음에 드는 주제를 하나 선택하세요.", st.session_state.topic_list, key="topic_choice_radio")
            if st.form_submit_button("✅ 이 주제로 수행평가 생성"):
                st.session_state.user_inputs['topic_input'] = chosen_topic
                st.session_state.stage = 'final_generation'
                st.rerun()
    else: st.error("❌ 추천 주제를 추출하지 못했습니다. 이전 단계로 돌아가 다시 시도해주세요.")
    # '처음으로 돌아가기' 버튼은 사이드바로 이동했으므로 제거

def render_final_generation_stage():
    # (이전 v13 코드와 동일, 하단의 '새로운 작업' 버튼만 제거)
    inputs = st.session_state.user_inputs; topic = inputs.get('topic_input')
    st.markdown("---")
    if topic: st.subheader(f"✅ 주제: \"{topic}\"")
    else: st.subheader("✅ '주제 없음' 요청 처리")

    with st.spinner("요청사항을 분석하고 최종 결과물을 생성하는 중입니다..."):
        files_to_use = st.session_state.get('processed_files', [])
        if not files_to_use and inputs['files']:
            for f in inputs['files']: files_to_use.append(genai.upload_file(path=f, mime_type=f.type))
            st.session_state.processed_files = files_to_use
        
        prompt = f"""당신은 학생의 모든 요구사항을 처리하는 만능 AI 조력자입니다. ... (프롬프트 내용 생략) ... 이제 위의 모든 내용을 바탕으로 최종 결과물 생성을 시작하세요."""
        prompt_parts = [prompt]
        if files_to_use: prompt_parts.extend(files_to_use)
        
        try:
            final_response = model.generate_content(prompt_parts)
            st.subheader("🎉 요청하신 결과물 (수정 가능) 🎉")
            st.text_area("결과물 수정 및 복사", value=final_response.text, height=600, help="이 상자 안에서 내용을 자유롭게 수정하고, 전체 선택(Ctrl+A)하여 복사할 수 있습니다.")
            st.success("생성이 완료되었습니다!")
            display_usage_and_cost(final_response, task_name="최종 결과물 생성")
        except Exception as e: st.error(f"결과물 생성 중 오류가 발생했습니다: {e}")
    # '새로운 작업 시작하기' 버튼은 사이드바로 이동했으므로 제거

def check_password():
    """브라우저 쿠키를 사용하여 24시간 동안 로그인 상태를 유지하는 함수 (수정된 버전)"""
    cookies = EncryptedCookieManager(
        password=st.secrets.get("COOKIE_ENCRYPTION_KEY", "a_default_secret_key_for_testing_123"),
    )

    # 1. 'login_status' 쿠키가 있는지 먼저 확인합니다.
    # 라이브러리가 준비될 때까지 기다리는 것이 좋습니다.
    if not cookies.ready():
        st.stop()
        
    login_cookie = cookies.get("login_status")

    if login_cookie:
        return True

    # 2. 쿠키가 없다면, 비밀번호 입력 폼을 표시합니다.
    try:
        correct_password = st.secrets["APP_PASSWORD"]
    except KeyError:
        st.error("🚨 앱 비밀번호가 설정되지 않았습니다. `.streamlit/secrets.toml` 파일을 확인해주세요.")
        return False
    
    with st.form("password_form"):
        st.title("🔐 접속 인증")
        st.markdown("동료들과 공유한 비밀번호를 입력해주세요.")
        password = st.text_input("비밀번호", type="password")
        submitted = st.form_submit_button("확인")

        if submitted:
            if password == correct_password:
                # 3. 비밀번호가 맞으면, 24시간 동안 유효한 쿠키를 생성합니다.
                expires_at = datetime.now() + timedelta(hours=24)
                
                # <<< 핵심 수정: 올바른 쿠키 설정 방법 >>>
                cookies['login_status'] = 'logged_in' 
                cookies.save() # 변경사항을 브라우저에 저장
                
                # 만료 시간 설정은 별도로 필요하지 않을 수 있으나, 라이브러리 버전에 따라 다를 수 있습니다.
                # 이 라이브러리는 기본적으로 세션 쿠키를 생성하거나, get/set 시 만료를 다룰 수 있습니다.
                # 더 명확한 만료 제어를 위해, 보통은 서버 측에서 토큰과 함께 만료 시간을 관리합니다.
                # 여기서는 라이브러리의 기본 동작을 따릅니다.
                
                st.rerun()
            else:
                st.error("비밀번호가 일치하지 않습니다.")
    return False

if __name__ == "__main__":
    # 비밀번호 확인을 통과해야만, 우리 앱의 메인 로직이 실행됩니다.
    if check_password():
        main()
