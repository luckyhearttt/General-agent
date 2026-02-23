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
    page_title="AI 教学助手", 
    page_icon="🎓", 
    layout="wide"  # 🌟 改为宽屏模式，利用空间显示左右分栏
)

hide_st_style = """
            <style>
            #MainMenu {visibility: hidden;}
            footer {visibility: hidden;}
            header {visibility: hidden;}
            
            /* 调整 tab 字体大小 */
            button[data-baseweb="tab"] {
                font-size: 18px !important;
                font-weight: bold !important;
            }
            </style>
            """
st.markdown(hide_st_style, unsafe_allow_html=True)

try:
    COZE_API_TOKEN = st.secrets["coze"]["api_token"]
    BOT_ID = st.secrets["coze"]["bot_id"]
    SHEET_NAME = st.secrets["google"]["sheet_name"]
    # 允许从 secrets 读取暗号，实现分组暗号不同
    CLASS_PASSWORD = st.secrets.get("class_password", "888") 
except:
    st.error("⚠️ 密钥未配置，请检查 Streamlit Secrets")
    st.stop()

WELCOME_MESSAGE = "我是你的专属 AI 导师。你可以问我关于教学策略的问题，或者让我帮你评估你的教案构思。让我们开始吧！"

# ==========================================
# 2. 数据库逻辑 (保持稳健版)
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
    if not sheet: return
    time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    for attempt in range(3):
        try:
            time.sleep(random.uniform(0.3, 0.8))
            sheet.append_row([time_now, user_name, role, content])
            return
        except Exception as e:
            if attempt < 2: time.sleep(2)
            else: st.toast(f"⚠️ 记录保存失败: {e}")

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
# 3. AI 核心逻辑 (保持 7 轮记忆)
# ==========================================

def chat_with_coze(query, user_name):
    url = "https://api.coze.cn/v3/chat"
    headers = {"Authorization": f"Bearer {COZE_API_TOKEN}", "Content-Type": "application/json"}
    safe_user_id = f"stu_{user_name}".replace(" ", "_")
    
    context_messages = []
    if "messages" in st.session_state:
        recent = st.session_state.messages[-14:] 
        for msg in recent:
            context_messages.append({
                "role": msg["role"],
                "content": msg["content"],
                "content_type": "text"
            })
    
    context_messages.append({"role": "user", "content": query, "content_type": "text"})
    
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
                    except: pass
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
        name_input = st.text_input("你的姓名 (拼音或英文):", key="login_name", placeholder="例如: ZhangSan01")
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
            elif pwd_input != CLASS_PASSWORD: st.error("🚫 暗号错误")
            else: st.error("⚠️ 请输入姓名")
    st.stop()

# --- 主界面 ---

# 🌟 侧边栏优化：任务在前，提示在后
with st.sidebar:
    st.markdown(f"**👤 学员: {st.session_state.user_name}**")
    st.divider()
    
    # 1. 任务说明 (Green for Action)
    st.success("""
    **📝 课堂任务 (Task)**
    
    请为你未来可能教授的一个科目，设计一个约 **5分钟** 的课堂教学片段。
    
    **要求：**
    1. 运用至少 **2种** 对话式教学策略 (例如 APT 策略)。
    2. **最终提交需包含：**
       - 教案概要 (教什么、怎么教)
       - 模拟师生对话 (展示策略运用)
       - 策略选择理由
       
    ⏱️ **时间：** 40分钟
    """)

    # Moodle 按钮
    st.markdown("""
    <a href="https://moodle.hku.hk/" target="_blank" style="text-decoration:none;">
        <button style="width:100%;background-color:#ff4b4b;color:white;border:none;padding:10px;border-radius:5px;font-weight:bold;cursor:pointer;">
        📤 点击跳转至 Moodle 提交
        </button>
    </a>
    """, unsafe_allow_html=True)

    st.divider()

    # 2. AI 提示 (Blue for Info)
    st.info("""
    **🤖 使用提示 (Tips)**
    
    1. **背景清晰**: AI 不是神，提问时请把你的教学背景、年级、科目告诉它。
    2. **保持账号**: 全程使用同一个名字登录，否则记录会丢。
    3. **利用 AI**: 让它帮你查资料、润色对话、反驳你的观点。
    """)
    
    if st.button("🚪 退出登录"):
        st.session_state.clear()
        st.rerun()

st.title("🎓 对话式教学工作台")

# 🌟 核心布局：Tabs 分栏
tab_chat, tab_knowledge = st.tabs(["💬 AI 对话助手", "📖 对话式教学知识库"])

# --- Tab 1: 聊天界面 ---
with tab_chat:
    # 聊天历史显示
    msg_container = st.container()
    with msg_container:
        for msg in st.session_state.messages:
            with st.chat_message(msg["role"]):
                st.markdown(msg["content"])
    
    # 空白占位，防止输入框遮挡最后一条消息
    st.markdown("<br><br><br>", unsafe_allow_html=True)

# --- Tab 2: 知识库界面 ---
with tab_knowledge:
    st.markdown("### 📚 知识库 / Knowledge Base")
    st.caption("这里整理了 APT 和 Accountable Talk 的核心概念，供设计教案时参考。")
    
    with st.expander("📌 1. APT 四大目标与八种对话策略 (Talk Moves)", expanded=True):
        st.markdown("""
        **目标一：帮助个别学生分享、扩展和澄清自己的想法 (Elaborating)**
        > *让学生把话说清楚、说具体。*
        - **策略1「多说 Say More」**：要求学生通过多说来扩展自己的观点。
          - *"你可以再多说一点吗？" / "Can you say more about that?"*
        - **策略2「重述确认 Revoice」**：教师重述学生的观点并求证。
          - *"你是说……对吗？" / "So you are saying... is that right?"*

        **目标二：帮助学生加深推理 (Reasoning)**
        > *让学生不仅给出答案，还要给出理由。*
        - **策略3「追问推理 Press for Reasoning」**：要求学生解释推理过程。
          - *"你为什么这么认为？" / "Why do you think that?"*
        - **策略4「挑战 Challenge」**：提出反例或不同观点。
          - *"如果分母为0会发生什么？" / "What if..."*

        **目标三：帮助学生认真倾听彼此 (Listening)**
        > *建立倾听的课堂文化。*
        - **策略5「重新阐述 Restate」**：引导学生重复他人的观点。
          - *"谁能重复一下他刚才说的话？" / "Who can rephrase what he just said?"*

        **目标四：引导学生与他人共同思考 (Thinking with Others)**
        > *让思维产生碰撞和连接。*
        - **策略6「同意/不同意 Agree/Disagree」**：对他人的观点做出判断。
          - *"你同意他的观点吗？为什么？" / "Do you agree or disagree? Why?"*
        - **策略7「补充 Add On」**：对同学的想法进行延伸。
          - *"谁可以补充他的想法？" / "Who can add on to this idea?"*
        - **策略8「引导解释他人 Explain Other」**：解释另一位同学的观点。
          - *"你认为他为什么会这么说？" / "Why do you think she said that?"*
        """)

    with st.expander("🛡️ 2. Accountable Talk 三大负责任维度"):
        st.markdown("""
        **1. 对学习社群负责 (Accountability to the Learning Community)**
        *   认真倾听彼此。
        *   挑战观点，而不是挑战个人。
        
        **2. 对准确知识负责 (Accountability to Accurate Knowledge)**
        *   发言要具体、准确，而非随口一说。
        *   信息来源要可验证。
        
        **3. 对严谨思维负责 (Accountability to Rigorous Thinking)**
        *   关注论据的质量。
        *   使用数据、类比、假设情景来支撑观点。
        """)

    with st.expander("🔧 3. Talk Moves 使用原则 (Tools not Scripts)"):
        st.markdown("""
        1.  **工具为解决问题而设计** (Tools are designed to solve problems)
        2.  **使用工具需要了解其用途** (Understanding a tool requires knowing its purpose)
        3.  **有些工具比其他工具更容易上手** (Some tools are easier to pick up than others) - *例如“等待时间”看起来简单，其实很难。*
        4.  **工具需要按策略性顺序使用** (Tools must be used in strategic sequence)
        5.  **工具与身份认同相关** (Tools belong to a tool kit associated with an identity)
        """)

# --- 输入框 (注意：st.chat_input 始终固定在底部) ---
if prompt := st.chat_input("在此输入你的想法或问题..."):
    # 逻辑：无论在哪个 Tab 输入，都视为在 Chat Tab 的操作
    
    # 1. 记录用户输入
    st.session_state.messages.append({"role": "user", "content": prompt})
    save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "学生", prompt)

    # 2. 强制刷新界面，确保如果在 Tab 2 输入，也能看到消息更新
    # (Streamlit 机制：输入后会自动 rerun，所以这部分自动处理了)

    # 3. 在 Tab 1 显示新消息 (实际上 rerun 后会重绘整个页面)
    with tab_chat:
         with st.chat_message("user"):
            st.markdown(prompt)
            
         with st.chat_message("assistant"):
            with st.spinner("🧠 AI 正在分析你的回答..."):
                response = chat_with_coze(prompt, st.session_state.user_name)
                st.markdown(response)

    # 4. 保存记录
    st.session_state.messages.append({"role": "assistant", "content": response})
    save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "AI", response)








