import streamlit as st
import requests
import json
import gspread
import time
import random
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ==========================================
# 1. 基础配置
# ==========================================

st.set_page_config(
    page_title="AI Teaching Assistant",
    page_icon="🎓",
    layout="centered",
    initial_sidebar_state="expanded"
)

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            .stDeployButton {display: none;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

try:
    COZE_API_TOKEN = st.secrets["coze"]["api_token"]
    BOT_ID = st.secrets["coze"]["bot_id"]
    SHEET_NAME = st.secrets["google"]["sheet_name"]
    CLASS_PASSWORD = st.secrets["auth"]["class_password"]
    # ✏️【新增】四个跳转链接
    TASK_GUIDE_LINK = st.secrets["links"]["task_guide"]
    SURVEY_1_LINK = st.secrets["links"]["survey_1"]
    MOODLE_LINK = st.secrets["links"]["moodle"]
    REFLECTIVE_SURVEY_LINK = st.secrets["links"]["reflective_survey"]
except:
    st.error("⚠️ Secrets not configured. Please contact your instructor.")
    st.stop()

WELCOME_MESSAGE = "Hi! I'm your AI assistant for today's task. You can ask me about dialogic teaching, APT talk moves, or anything related to the classroom transcript analysis. Let's get started!"

# ==========================================
# 2. 数据库逻辑
# ==========================================

@st.cache_resource
def get_google_sheet():
    scope = ['https://spreadsheets.google.com/feeds', 'https://www.googleapis.com/auth/drive']
    try:
        if "json_content" in st.secrets["gcp_service_account"]:
            json_creds = json.loads(st.secrets["gcp_service_account"]["json_content"])
        else:
            json_creds = dict(st.secrets["gcp_service_account"])
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json_creds, scope)
        client = gspread.authorize(creds)
        return client.open(SHEET_NAME).sheet1
    except Exception as e:
        st.error(f"⚠️ Unable to connect to database. Please contact your instructor. Error: {e}")
        return None

def save_to_sheet(sheet, user_name, role, content):
    if not sheet:
        return
    time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for attempt in range(3):
        try:
            time.sleep(random.uniform(0.3, 0.8))
            sheet.append_row([time_now, user_name, role, content])
            return
        except Exception as e:
            if attempt < 2:
                time.sleep(2)
            else:
                st.toast(f"⚠️ Failed to save record. Details: {e}")

def load_history_from_sheet(sheet, user_name):
    if not sheet:
        return []
    try:
        all_records = sheet.get_all_values()
        user_history = []
        target_name = user_name.strip().lower()
        for row in all_records[1:]:
            if len(row) >= 4:
                current_name = str(row[1]).strip().lower() if row[1] else ""
                if current_name == target_name:
                    role_map = {"Student": "user", "AI": "assistant"}
                    role = role_map.get(row[2], "assistant")
                    user_history.append({"role": role, "content": row[3]})
        return user_history
    except Exception as e:
        st.error(f"⚠️ Unable to load history. Error: {e}")
        return []

# ==========================================
# 3. AI 核心逻辑 — ✏️【重写】流式响应
# ==========================================

def chat_with_coze_stream(query, user_name):
    """
    流式调用 Coze API，返回一个生成器（generator），
    每次 yield 当前累积的文本内容，供 st.write_stream 使用。
    """
    url = "https://api.coze.cn/v3/chat"
    headers = {
        "Authorization": f"Bearer {COZE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    safe_user_id = f"stu_{user_name}".replace(" ", "_")

    # 构建上下文消息
    context_messages = []
    if "messages" in st.session_state:
        recent = st.session_state.messages[-14:]
        for msg in recent:
            context_messages.append({
                "role": msg["role"],
                "content": msg["content"],
                "content_type": "text"
            })

    context_messages.append({
        "role": "user",
        "content": query,
        "content_type": "text"
    })

    data = {
        "bot_id": BOT_ID,
        "user_id": safe_user_id,
        "stream": True,
        "auto_save_history": True,
        "additional_messages": context_messages
    }

    try:
        response = requests.post(url, headers=headers, json=data, stream=True)
        current_event = None

        for line in response.iter_lines():
            if not line:
                continue
            decoded_line = line.decode('utf-8')

            if decoded_line.startswith("event:"):
                current_event = decoded_line[6:].strip()
                continue

            if decoded_line.startswith("data:"):
                json_str = decoded_line[5:].strip()
                if json_str == "[DONE]":
                    continue

                if current_event == "conversation.message.delta":
                    try:
                        chunk = json.loads(json_str)
                        if chunk.get('type') == 'answer':
                            content_piece = chunk.get('content', '')
                            if content_piece:
                                yield content_piece
                    except:
                        pass

                current_event = None

    except Exception as e:
        yield f"Connection error: {str(e)}"

# ==========================================
# 4. 界面逻辑
# ==========================================

if "db_conn" not in st.session_state:
    st.session_state.db_conn = get_google_sheet()

if "is_processing" not in st.session_state:
    st.session_state.is_processing = False

# --- 登录页 ---
if 'user_name' not in st.session_state:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🎓 AI Teaching Assistant</h1>", unsafe_allow_html=True)

    col1, col2, col3 = st.columns([1, 2, 1])
    with col2:
        st.info("👋 Welcome! Enter your name and class code to begin.")
        name_input = st.text_input("Your Name:", key="login_name")
        pwd_input = st.text_input("Class Code:", type="password")

        if st.button("🚀 Start", use_container_width=True):
            if name_input and pwd_input == CLASS_PASSWORD:
                clean_name = name_input.strip()
                st.session_state.user_name = clean_name
                with st.spinner("Connecting to AI assistant..."):
                    history = load_history_from_sheet(st.session_state.db_conn, clean_name)
                    st.session_state.messages = history
                    if not history:
                        st.session_state.messages.append({"role": "assistant", "content": WELCOME_MESSAGE})
                st.rerun()
            elif pwd_input != CLASS_PASSWORD:
                st.error("🚫 Incorrect class code.")
            else:
                st.error("⚠️ Please enter your name.")
    st.stop()

# --- 侧边栏 ---
with st.sidebar:
    st.markdown(f"**👤 Student: {st.session_state.user_name}**")
    st.divider()

    # ✏️【新增】四个跳转按钮
    st.markdown("**📌 Quick Links**")

    st.link_button("📖 Task Guide & Transcript", TASK_GUIDE_LINK, use_container_width=True)
    st.link_button("📋 Submit Part 1 (Survey)", SURVEY_1_LINK, use_container_width=True)
    st.link_button("📤 Submit Part 2 (Moodle)", MOODLE_LINK, use_container_width=True)
    st.link_button("📝 Reflective Survey", REFLECTIVE_SURVEY_LINK, use_container_width=True)

    st.divider()

    st.warning("""
**💡 Tips**
1. **Be patient** — If no response, wait a moment. Don't refresh.
2. **Keep your name** — Use the same name throughout, or history will be lost.
3. **AI may not always be correct** — Think critically about its responses.
""")

    st.divider()
    if st.button("Log Out"):
        st.session_state.clear()
        st.rerun()

# --- 主聊天区 ---

st.markdown("## 💬 AI Chat")
st.caption("Ask me anything about the classroom transcript and dialogic teaching strategies.")
st.divider()

# 显示历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# ✏️【重写】处理输入 — 流式输出
if prompt := st.chat_input("Type your message here...", disabled=st.session_state.is_processing):

    st.session_state.is_processing = True

    # 1. 显示用户输入
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "Student", prompt)

    # 2. 流式生成 AI 回复
    with st.chat_message("assistant"):
        response_text = st.write_stream(chat_with_coze_stream(prompt, st.session_state.user_name))

    # 3. 保存完整回复
    st.session_state.messages.append({"role": "assistant", "content": response_text})
    save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "AI", response_text)

    # 4. 重置状态
    st.session_state.is_processing = False
    st.rerun()













