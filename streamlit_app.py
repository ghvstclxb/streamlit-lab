import base64
from pathlib import Path
import streamlit as st
from openai import OpenAI
from app_helpers import file_fingerprint, text_deltas

st.set_page_config(page_title='Streamlit AI Lab', page_icon='📚')
TEXT_MODEL = 'gpt-6-luna'
IMAGE_MODEL = 'gpt-image-2.6-flare'

with st.sidebar:
    st.title('AI 실습')
    api_key = st.text_input('OpenAI API Key', type='password', key='api_key')
    st.caption('키는 현재 세션에서만 사용됩니다.')
    if api_key:
        st.session_state.openai_client = OpenAI(api_key=api_key)
    else:
        st.session_state.pop('openai_client', None)

def client():
    if 'openai_client' not in st.session_state:
        st.info('사이드바에 OpenAI API 키를 입력하세요.')
        st.stop()
    return st.session_state.openai_client

@st.cache_data(show_spinner=False, ttl=3600, max_entries=50)
def answer_question(_client, key_scope, prompt):
    return _client.responses.create(model=TEXT_MODEL, input=prompt).output_text

def home():
    st.title('텍스트와 이미지 생성')
    question = st.text_area('질문을 입력하세요')
    if st.button('답변 생성') and question.strip():
        c = client()
        try:
            import hashlib
            key_scope = hashlib.sha256(st.session_state.api_key.encode()).hexdigest()
            with st.spinner('답변을 생성하고 있습니다...'):
                st.write(answer_question(c, key_scope, question))
        except Exception as e:
            st.error(f'답변 생성 실패: {e}')
    prompt = st.text_area('이미지 설명')
    if st.button('이미지 생성') and prompt.strip():
        c = client()
        try:
            with st.spinner('이미지를 생성하고 있습니다...'):
                result = c.images.generate(model=IMAGE_MODEL, prompt=prompt)
                st.session_state.generated_image = base64.b64decode(result.data[0].b64_json)
        except Exception as e:
            st.error(f'이미지 생성 실패: {e}')
    if st.session_state.get('generated_image'):
        st.image(st.session_state.generated_image)

def chat_page(title, state_key, instructions=None, tools=None):
    st.title(title)
    if state_key not in st.session_state:
        st.session_state[state_key] = []
    def clear():
        st.session_state[state_key] = []
    st.button('Clear', on_click=clear, key='clear_'+state_key)
    for msg in st.session_state[state_key]:
        with st.chat_message(msg['role']): st.markdown(msg['content'])
    if question := st.chat_input('질문을 입력하세요', key='input_'+state_key):
        c = client()
        history = st.session_state[state_key]
        history.append({'role':'user','content':question})
        with st.chat_message('user'): st.markdown(question)
        try:
            kwargs = {'model':TEXT_MODEL, 'input':history, 'stream':True}
            if instructions: kwargs['instructions'] = instructions
            if tools: kwargs['tools'] = tools
            with st.chat_message('assistant'):
                response = st.write_stream(text_deltas(c.responses.create(**kwargs)))
            history.append({'role':'assistant','content':response})
        except Exception as e:
            history.pop()
            st.error(f'응답을 가져오지 못했습니다: {e}')

def chat(): chat_page('Chat', 'chat_messages')

def library():
    rules = Path(__file__).with_name('library_rules.txt').read_text(encoding='utf-8')
    st.caption('출처: 국립부경대학교 도서관 규정')
    st.link_button('도서관 규정 원문', 'https://libweb.pknu.ac.kr/guide/intro/regulation/')
    chat_page('국립부경대학교 도서관 챗봇', 'library_messages', '다음 도서관 규정에 근거해서만 답하고, 근거 조항을 밝히세요. 내용에 없으면 모른다고 답하세요.\n\n'+rules)

def pdf_chat():
    st.title('ChatPDF')
    uploaded = st.file_uploader('PDF 파일 한 개를 선택하세요', type=['pdf'], key=f"pdf_upload_{st.session_state.get('pdf_generation', 0)}")
    if not uploaded:
        st.info('PDF를 업로드하면 문서에 관해 질문할 수 있습니다.')
        return
    c = client()
    fingerprint = file_fingerprint(uploaded.name, uploaded.getvalue())
    state = st.session_state.get('pdf_store')
    if state and state['fingerprint'] != fingerprint:
        st.warning('다른 파일을 사용하려면 Leave를 눌러 기존 문서를 종료하세요.')
    elif not state:
        try:
            with st.spinner('PDF를 검색할 수 있도록 준비 중입니다...'):
                store = c.vector_stores.create(name='Streamlit ChatPDF')
                try:
                    f = c.files.create(file=(uploaded.name, uploaded.getvalue(), 'application/pdf'), purpose='assistants')
                    batch = c.vector_stores.file_batches.create_and_poll(vector_store_id=store.id, file_ids=[f.id])
                    if batch.status != 'completed' or batch.file_counts.failed:
                        raise RuntimeError('PDF 색인에 실패했습니다.')
                except Exception:
                    c.vector_stores.delete(store.id)
                    raise
                state = {'fingerprint':fingerprint, 'store_id':store.id, 'file_id':f.id}
                st.session_state.pdf_store = state
        except Exception as e:
            st.error(f'PDF 준비 실패: {e}')
            return
    if state and st.button('Leave'):
        try:
            c.vector_stores.delete(state['store_id'])
            c.files.delete(state['file_id'])
        except Exception as e:
            st.error(f'원격 파일 정리 실패: {e}')
            return
        st.session_state.pop('pdf_store', None)
        st.session_state.pop('pdf_messages', None)
        st.session_state['pdf_generation'] = st.session_state.get('pdf_generation', 0) + 1
        st.rerun()
    if state and state['fingerprint'] == fingerprint:
        chat_page('PDF 질문과 답변', 'pdf_messages', '업로드한 문서를 검색하여 근거를 바탕으로 답하고, 찾지 못한 내용은 모른다고 답하세요.', [{'type':'file_search','vector_store_ids':[state['store_id']]}])

pages = [st.Page(home, title='Home', icon='🏠'), st.Page(chat, title='Chat', icon='💬'), st.Page(library, title='도서관 챗봇', icon='📚'), st.Page(pdf_chat, title='ChatPDF', icon='📄')]
st.navigation(pages).run()

