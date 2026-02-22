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
    page_title="AI 助手", 
    page_icon="🎓", 
    layout="centered"
)

# 隐藏多余菜单
hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

# 获取 Secrets
try:
    COZE_API_TOKEN = st.secrets["coze"]["api_token"]
    BOT_ID = st.secrets["coze"]["bot_id"]
    SHEET_NAME = st.secrets["google"]["sheet_name"]
    CLASS_PASSWORD = "888" 
except:
    st.error("⚠️ 密钥未配置，请检查 Streamlit Secrets")
    st.stop()

# 开场白
WELCOME_MESSAGE = "我是你的专属 AI 导师。你可以问我关于教学策略的问题，或者让我帮你评估你的教案构思。让我们开始吧！"

# ==========================================
# 2. 数据库逻辑 (回归你提供的稳定版逻辑)
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
        print(f"DB Connection Error: {e}")
        return None

def save_to_sheet(sheet, user_name, role, content):
    if sheet:
        # 简单延时防并发
        time.sleep(random.uniform(0.1, 0.3))
        time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            sheet.append_row([time_now, user_name, role, content])
        except Exception as e:
            print(f"Save Error: {e}")

def load_history_from_sheet(sheet, user_name):
    if not sheet: return []
    try:
        all_records = sheet.get_all_values()
        user_history = []
        target_name = user_name.strip().lower()
        for row in all_records[1:]:
            if len(row) >= 4:
                current_name = str(row[1]).strip().lower() if row[1] else ""
                if current_name == target_name:
                    role_map = {"学生": "user", "AI": "assistant", "AI导师": "assistant"}
                    role = role_map.get(row[2], "assistant")
                    user_history.append({"role": role, "content": row[3]})
        return user_history
    except:
        return []

# ==========================================
# 3. AI 核心逻辑 (改为生成器，供 write_stream 使用)
# ==========================================

def chat_with_coze_stream(query, user_name):
    """
    这是一个生成器函数，专门用于流式输出
    """
    url = "https://api.coze.cn/v3/chat"
    headers = {"Authorization": f"Bearer {COZE_API_TOKEN}", "Content-Type": "application/json"}
    safe_user_id = f"stu_{user_name}".replace(" ", "_")
    
    data = {
        "bot_id": BOT_ID, "user_id": safe_user_id, "stream": True,
        "auto_save_history": True,
        "additional_messages": [{"role": "user", "content": query, "content_type": "text"}]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, stream=True)
        
        for line in response.iter_lines():
            if not line: continue
            decoded_line = line.decode('utf-8')
            if decoded_line.startswith("data:"):
                json_str = decoded_line[5:]
                try:
                    if json_str.strip() == "[DONE]": continue
                    chunk = json.loads(json_str)
                    
                    # 🌟 只提取增量内容，避免重复
                    if chunk.get('event') == 'conversation.message.delta':
                        content = chunk.get('content', '')
                        if content:
                            yield content
                except: continue
    except Exception as e:
        yield f"Error: {str(e)}"

# ==========================================
# 4. 界面逻辑 (极简版)
# ==========================================

if "db_conn" not in st.session_state:
    st.session_state.db_conn = get_google_sheet()

# --- 登录页 ---
if 'user_name' not in st.session_state:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🎓 登录你的课堂</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        st.info("👋 欢迎！请输入你的姓名和班级暗号开始练习。")
        name_input = st.text_input("你的姓名 (拼音或英文):", key="login_name")
        pwd_input = st.text_input("班级暗号:", type="password")
        
        if st.button("🚀 开始学习", use_container_width=True):
            if name_input and pwd_input == CLASS_PASSWORD:
                clean_name = name_input.strip()
                st.session_state.user_name = clean_name
                
                with st.spinner("正在连接 AI 导师..."):
                    history = load_history_from_sheet(st.session_state.db_conn, clean_name)
                    st.session_state.messages = history
                    if not history:
                        st.session_state.messages.append({"role": "assistant", "content": WELCOME_MESSAGE})
                st.rerun()
            elif pwd_input != CLASS_PASSWORD:
                st.error("🚫 暗号错误")
            else:
                st.error("⚠️ 请输入姓名")
    st.stop()

# --- 主界面 ---

# 侧边栏
with st.sidebar:
    st.markdown(f"**👤 学员: {st.session_state.user_name}**")
    st.divider()
    st.markdown("### 📝 你的任务")
    st.markdown("""
    **设计一个 5-10 分钟的课堂教学片段。**
    
    1. **要求：** 运用至少 2 种对话式教学策略。
    2. **工具：** 自由使用 AI 辅助。
    3. **提交：** 完成后请提交至 Moodle。
    """)
    st.warning("⚠️ **提示：** AI 可能会犯错，请保持独立思考。")
    if st.button("退出登录"):
        st.session_state.clear()
        st.rerun()

st.title("🎓 教学对话练习")

# 显示历史消息
for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 处理输入
if prompt := st.chat_input("在此输入你的问题..."):
    
    # 1. 立即显示并保存用户输入
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "学生", prompt)

    # 2. 生成 AI 回复 (使用官方 write_stream，完美解决重复问题)
    with st.chat_message("assistant"):
        # write_stream 会自动处理生成器，打完字后返回完整的字符串
        full_response = st.write_stream(chat_with_coze_stream(prompt, st.session_state.user_name))
    
    # 3. 保存 AI 回复
    st.session_state.messages.append({"role": "assistant", "content": full_response})
    save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "AI", full_response)
