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
    layout="wide"
)

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
WELCOME_MESSAGE = "我是你的专属 AI 导师，让我们开始对话吧。"

# ==========================================
# 2. 数据库与并发处理
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
        print(f"DB Error: {e}")
        return None

def save_to_sheet(sheet, user_name, role, content):
    """
    写入数据，包含防并发限制的机制
    """
    if sheet:
        # 1. 随机延迟 0.1~0.5秒，错开30人的并发请求
        time.sleep(random.uniform(0.1, 0.5))
        
        time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            sheet.append_row([time_now, user_name, role, content])
        except Exception as e:
            # 2. 如果因为频率限制报错，静默失败，不影响学生使用
            print(f"Write Failed (Rate Limit likely): {e}")

def load_history_from_sheet(sheet, user_name):
    if not sheet: return []
    try:
        all_records = sheet.get_all_values()
        user_history = []
        target_name = user_name.strip().lower()
        
        for row in all_records[1:]:
            if len(row) >= 4:
                # 简单清洗数据
                current_name = str(row[1]).strip().lower() if row[1] else ""
                if current_name == target_name:
                    role_map = {"学生": "user", "AI": "assistant", "AI导师": "assistant"}
                    role = role_map.get(row[2], "assistant")
                    user_history.append({"role": role, "content": row[3]})
        return user_history
    except Exception as e:
        print(f"Read History Error: {e}")
        return []

# ==========================================
# 3. AI 核心逻辑
# ==========================================

def chat_with_coze(query, user_name):
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
                    if chunk.get('event') == 'conversation.message.delta' or chunk.get('type') == 'answer':
                        yield chunk.get('content', '')
                except: continue
    except Exception as e:
        yield f"Error: {str(e)}"

# ==========================================
# 4. 界面逻辑
# ==========================================

if "db_conn" not in st.session_state:
    st.session_state.db_conn = get_google_sheet()

# --- 登录页 ---
if 'user_name' not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>🎓 AI 助手</h1>", unsafe_allow_html=True)
    st.markdown("---")
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        name_input = st.text_input("请输入你的真实姓名:", key="login_name")
        pwd_input = st.text_input("班级暗号:", type="password")
        if st.button("🚀 进入课堂", use_container_width=True):
            if name_input and pwd_input == CLASS_PASSWORD:
                clean_name = name_input.strip() # 即使你不改，我还是建议保留这个去空格
                st.session_state.user_name = clean_name
                with st.spinner("正在准备你的专属导师..."):
                    history = load_history_from_sheet(st.session_state.db_conn, clean_name)
                    st.session_state.messages = history
                    # 💡 如果是第一次来，添加开场白
                    if not history:
                        st.session_state.messages.append({"role": "assistant", "content": WELCOME_MESSAGE})
                st.rerun()
            elif pwd_input != CLASS_PASSWORD:
                st.error("暗号错误")
            else:
                st.error("请输入姓名")
    st.stop()

# --- 主界面 ---

# 1. 侧边栏：任务书与提示
with st.sidebar:
    st.info(f"👤 当前学生: **{st.session_state.user_name}**")
    
    st.markdown("### 📝 你的任务")
    st.markdown("""
    为你未来可能教的一个科目，**设计一个 5-10 分钟的课堂教学片段**。
    
    **要求：**
    * 运用至少 2 种对话式教学策略。
    * 你可以自由使用 AI 来辅助（如查询策略、评估教案、模拟场景）。
    * **时间限制：** 25 分钟。
    
    完成后，请将你的设计提交到 Moodle。
    """)
    
    st.markdown("---")
    st.warning("""
    **⚠️ 关于此 AI**
    * 这是一个 General AI，未经过特殊训练。
    * **不要全信：** 它可能会犯错，请结合你的判断力使用。
    * 把它当作你的“合作搭档”而不是“标准答案”。
    """)
    
    if st.button("🚪 退出登录"):
        st.session_state.clear()
        st.rerun()

# 2. 顶部标题
st.title("🎓 教学辅助工作台")

# 3. 双栏布局：左边聊天，右边写教案
# 使用 Tabs 可以有效利用空间，手机端也友好
tab1, tab2 = st.tabs(["💬 AI 对话助手", "📝 教案草稿箱"])

# --- Tab 1: 聊天区 ---
with tab1:
    # 显示历史
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            
    # 输入框
    if prompt := st.chat_input("在这里输入你的问题..."):
        # 用户消息
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "学生", prompt)

        # AI 回复
        with st.chat_message("assistant"):
            container = st.empty()
            full_res = ""
            for chunk in chat_with_coze(prompt, st.session_state.user_name):
                full_res += chunk
                container.markdown(full_res + "▌")
            container.markdown(full_res)
            
        # 记录 AI 消息
        st.session_state.messages.append({"role": "assistant", "content": full_res})
        save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "AI", full_res)

# --- Tab 2: 写作区 ---
with tab2:
    st.caption("你可以在这里边和 AI 讨论，边起草你的教案。完成后请**全选复制**，提交到 Moodle。")
    
    # 初始化草稿内容
    if "draft_text" not in st.session_state:
        st.session_state.draft_text = ""
        
    # 文本区域
    text_area = st.text_area(
        "在此处撰写教案：", 
        value=st.session_state.draft_text,
        height=500, # 足够高，像一张A4纸
        placeholder="例如：\n课题：光合作用\n教学目标：...\n对话策略1：..."
    )
    
    # 实时更新 session state，防止切换 tab 丢失内容
    st.session_state.draft_text = text_area
