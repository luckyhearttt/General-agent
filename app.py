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
# 2. 数据库逻辑 (完全保留 V2)
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

def save_to_sheet(sheet, user_name, role, content):
    if sheet:
        time.sleep(random.uniform(0.1, 0.3))
        time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            sheet.append_row([time_now, user_name, role, content])
        except Exception as e:
            st.error(f"⚠️ 无法保存记录，请联系老师。错误详情: {e}")

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
# 3. AI 核心逻辑 (修复双重回复 + 增加上下文)
# ==========================================

def chat_with_coze(query, user_name):
    url = "https://api.coze.cn/v3/chat"
    headers = {"Authorization": f"Bearer {COZE_API_TOKEN}", "Content-Type": "application/json"}
    safe_user_id = f"stu_{user_name}".replace(" ", "_")
    
    # 🧠【上下文记忆】把最近3轮对话作为上下文发给 Coze
    context_messages = []
    if "messages" in st.session_state:
        # 取最后6条（3轮 = 3条user + 3条assistant）
        recent = st.session_state.messages[-6:]
        for msg in recent:
            context_messages.append({
                "role": msg["role"],
                "content": msg["content"],
                "content_type": "text"
            })
    
    # 加上本次用户的新输入
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
        
        # 🛡️【修复核心】正确解析 Coze V3 的流式格式
        # Coze V3 流式格式是两行一组:
        #   event:conversation.message.delta
        #   data:{"role":"assistant","type":"answer","content":"xxx",...}
        
        current_event = None
        
        for line in response.iter_lines():
            if not line: continue
            decoded_line = line.decode('utf-8')
            
            # 第一行：读取 event 类型
            if decoded_line.startswith("event:"):
                current_event = decoded_line[6:].strip()
                continue
            
            # 第二行：读取 data 内容
            if decoded_line.startswith("data:"):
                json_str = decoded_line[5:].strip()
                if json_str == "[DONE]": continue
                
                # 🛡️ 只处理 delta 事件（打字过程），跳过 completed（总结包）
                # 这就是双重回复的根源：以前没区分这两个事件
                if current_event == "conversation.message.delta":
                    try:
                        chunk = json.loads(json_str)
                        # 只收 type=answer 的内容（跳过 function_call 等）
                        if chunk.get('type') == 'answer':
                            full_content += chunk.get('content', '')
                    except:
                        pass
                
                # 重置 event，等待下一组
                current_event = None
                
        return full_content if full_content else "AI 似乎在思考，但没有回应..."
        
    except Exception as e:
        return f"连接错误: {str(e)}"

# ==========================================
# 4. 界面逻辑 (完全保留 V2 结构)
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

with st.sidebar:
    st.markdown(f"**👤 学员: {st.session_state.user_name}**")
    st.divider()
    st.info("""
    **📝 你的任务**
    
    设计一个 5-10 分钟的课堂教学片段。
    
    1. **要求：** 运用至少 2 种对话式教学策略。
    2. **工具：** 自由使用 AI 辅助。
    3. **提交：** 完成后请提交至 Moodle。
    """)
    st.warning("**⚠️ 提示：** AI 可能会犯错，请保持独立思考。")
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


