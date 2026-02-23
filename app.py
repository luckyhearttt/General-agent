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

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

try:
    COZE_API_TOKEN = st.secrets["coze"]["api_token"]
    BOT_ID = st.secrets["coze"]["bot_id"]
    SHEET_NAME = st.secrets["google"]["sheet_name"]
    CLASS_PASSWORD = "888" 
except:
    st.error("⚠️ 密钥未配置，请检查 Streamlit Secrets")
    st.stop()

WELCOME_MESSAGE = "我是你的专属 AI 导师。你可以问我关于教学策略的问题，或者让我帮你评估你的教案构思。让我们开始吧！"

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
        st.error(f"⚠️ 无法连接数据库，请联系老师。错误详情: {e}")
        return None

# ✏️【修改点1】写入加重试机制，防止20人并发时偶尔超限丢数据
def save_to_sheet(sheet, user_name, role, content):
    if not sheet:
        return
    time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    for attempt in range(3):  # 最多重试3次
        try:
            time.sleep(random.uniform(0.3, 0.8))  # 随机延迟，错开并发
            sheet.append_row([time_now, user_name, role, content])
            return  # 成功就退出
        except Exception as e:
            if attempt < 2:
                time.sleep(2)  # 失败后等2秒再试
            else:
                st.toast(f"⚠️ 记录保存失败，但不影响对话。详情: {e}")

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
    except Exception as e:
        st.error(f"⚠️ 无法读取历史记录。错误详情: {e}")
        return []

# ==========================================
# 3. AI 核心逻辑
# ==========================================

def chat_with_coze(query, user_name):
    url = "https://api.coze.cn/v3/chat"
    headers = {"Authorization": f"Bearer {COZE_API_TOKEN}", "Content-Type": "application/json"}
    safe_user_id = f"stu_{user_name}".replace(" ", "_")
    
    # ✏️【修改点2】上下文从6条(3轮)扩大到14条(7轮)
    context_messages = []
    if "messages" in st.session_state:
        recent = st.session_state.messages[-14:]  # 7轮 = 14条消息
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
    
    full_content = ""
    
    try:
        response = requests.post(url, headers=headers, json=data, stream=True)
        
        current_event = None
        
        for line in response.iter_lines():
            if not line: continue
            decoded_line = line.decode('utf-8')
            
            if decoded_line.startswith("event:"):
                current_event = decoded_line[6:].strip()
                continue
            
            if decoded_line.startswith("data:"):
                json_str = decoded_line[5:].strip()
                if json_str == "[DONE]": continue
                
                if current_event == "conversation.message.delta":
                    try:
                        chunk = json.loads(json_str)
                        if chunk.get('type') == 'answer':
                            full_content += chunk.get('content', '')
                    except:
                        pass
                
                current_event = None
                
        return full_content if full_content else "AI 似乎在思考，但没有回应..."
        
    except Exception as e:
        return f"连接错误: {str(e)}"

# ==========================================
# 4. 界面逻辑
# ==========================================

if "db_conn" not in st.session_state:
    st.session_state.db_conn = get_google_sheet()

# --- 登录页 ---
if 'user_name' not in st.session_state:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🎓 连接你的AI助手</h1>", unsafe_allow_html=True)
    
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

with st.sidebar:
    st.markdown(f"**👤 学员: {st.session_state.user_name}**")
    st.divider()
    
    # 🤖 使用提示板块
    st.warning("""
    **🤖 AI 说明**
    1. **这是通用 AI**: 它不是专门的对话式教学专家，提问时请**把背景说清楚**。
    2. **不要换号**: 全程请使用**同一个链接**和**同一个名字**，否则历史记录会丢失。
    3. **耐心等待**: 如果没有回复，请稍等片刻，不要频繁刷新页面。
    
    """)
    
    st.divider()

    # 📝 任务说明板块
    st.info("""
    **📝 课堂任务**
    请为你未来可能教授的一个科目，完成以下任务：

    设计一个约5分钟的课堂教学片段，其中需要运用至少2种对话式教学策略（例如APT策略）。你的最终提交需要包含：

    教案概要（你打算教什么、怎么教）
    一段模拟的师生对话（展示你设计的对话式教学可能的样子）
    简要说明你选择这些策略的理由

    ---
    💡  **小提示**：在设计师生对话时，请考虑真实课堂的复杂性——学生可能会沉默、回答不完整、或者给出意料之外的答案。
    💡  **小提示**：你可以用各种方式和AI互动——比如让它帮你查资料、给你反馈、和你一起讨论想法、帮你生成内容等等。怎么用完全由你决定。

    ⏱️ 时间：40分钟。完成后点击跳转至Moodle提交。
    """)
    
    # 🔗 Moodle 跳转按钮
    st.markdown("""
    <a href="https://moodle.hku.hk/" target="_blank">
        <button style="
            width: 100%;
            background-color: #ff4b4b;
            color: white;
            border: none;
            padding: 10px;
            border-radius: 5px;
            cursor: pointer;
            font-weight: bold;
        ">
        📤 完成后点击跳转至 Moodle 的 Discussion Forum 提交
        </button>
    </a>
    """, unsafe_allow_html=True)

    st.divider()
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
    
    # 1. 显示用户输入
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "学生", prompt)

    # 2. 生成 AI 回复
    with st.chat_message("assistant"):
        with st.spinner("🧠 AI 正在分析你的回答..."):
            response = chat_with_coze(prompt, st.session_state.user_name)
            st.markdown(response)
    
    # 3. 保存 AI 回复
    st.session_state.messages.append({"role": "assistant", "content": response})
    save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "AI", response)







