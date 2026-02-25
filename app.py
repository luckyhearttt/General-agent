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

# ✏️【修改】只隐藏footer和deploy按钮，保留侧边栏开关
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
    SURVEY_1_LINK = st.secrets["links"]["survey_1"]
    SURVEY_2_LINK = st.secrets["links"]["survey_2"]
    MOODLE_LINK = st.secrets["links"]["moodle"]
except:
    st.error("⚠️ Secrets not configured. Please contact your instructor.")
    st.stop()

WELCOME_MESSAGE = "Hi! I'm your AI assistant. You can ask me about anything, or let me help you brainstorm and refine your plan. Let's get started!"

# ==========================================
# 2. 数据库逻辑 (不动)
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
                st.toast(f"⚠️ Failed to save record, but your conversation is not affected. Details: {e}")

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
                    role_map = {"Student": "user", "AI": "assistant"}
                    role = role_map.get(row[2], "assistant")
                    user_history.append({"role": role, "content": row[3]})
        return user_history
    except Exception as e:
        st.error(f"⚠️ Unable to load history. Error: {e}")
        return []

# ==========================================
# 3. AI 核心逻辑 (不动)
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
                
        return full_content if full_content else "AI is thinking but didn't return a response..."
        
    except Exception as e:
        return f"Connection error: {str(e)}"

# ==========================================
# 4. 知识库内容 (不动)
# ==========================================

def render_knowledge_base():
    st.markdown("## 📖 Accountable Talk & Dialogic Teaching Strategies")
    st.markdown("Use this as a reference while designing your lesson plan.")
    st.divider()

    st.markdown("### 1. APT: Four Goals & Eight Talk Moves")

    with st.expander("🎯 Goal 1: Help individual students share, expand, and clarify their thinking (Elaborating)", expanded=False):
        st.markdown("""
**Move 1 — "Say More"**  
Ask students to elaborate on a brief, vague, or unclear statement.

> *"Can you say more about that?"*  
> *"What do you mean by that?"*  
> *"Can you give an example?"*

---

**Move 2 — "Revoice"**  
The teacher restates a student's reasoning and gives them a chance to confirm or correct.

> *"So let me see if I understand — you're saying … Is that right?"*  
> *"In other words, you're suggesting …?"*
""")

    with st.expander("🎯 Goal 2: Help students deepen their reasoning (Reasoning)", expanded=False):
        st.markdown("""
**Move 3 — "Press for Reasoning"**  
Ask students to explain the thinking behind their answer.

> *"Why do you think that?"*  
> *"What's your evidence?"*  
> *"How did you arrive at that answer?"*

---

**Move 4 — "Challenge"**  
Offer a counter-example or alternative perspective to test and deepen reasoning.

> *"Is that always the case?"*  
> *"What if the denominator were 0?"*  
> *"Can you think of a case where that wouldn't work?"*  
> *"What would someone who disagrees say?"*
""")

    with st.expander("🎯 Goal 3: Help students listen carefully to one another (Listening)", expanded=False):
        st.markdown("""
**Move 5 — "Restate"**  
Prompt students to repeat or paraphrase what someone else said.

> *"Who can repeat what Javon just said, in your own words?"*  
> *"What did your partner say?"*
""")

    with st.expander("🎯 Goal 4: Help students think with others (Thinking with Others)", expanded=False):
        st.markdown("""
**Move 6 — "Agree / Disagree"**  
Ask students to take a position on someone else's idea and explain why.

> *"Do you agree or disagree? Why?"*  
> *"What do you think about what she just said?"*  
> *"Thumbs up if you agree, thumbs down if you disagree."*

---

**Move 7 — "Add On"**  
Invite students to build on or extend a classmate's idea.

> *"Who can add on to what Jamal said?"*  
> *"Can anyone take that idea a step further?"*

---

**Move 8 — "Explain Other"**  
Ask a student to explain another student's reasoning.

> *"Who can explain what Aisha meant?"*  
> *"Why do you think he said that?"*  
> *"Can you explain her reasoning in your own words?"*
""")

    st.divider()

    st.markdown("### 2. Accountable Talk: Three Dimensions of Accountability")
    st.info("""
**Accountable Talk** is a core practice framework developed by the Institute for Learning at the University of Pittsburgh. It requires classroom talk to be accountable in three dimensions:
""")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.markdown("""
**🤝 To the Community**
- Listen carefully, not just wait to speak
- Paraphrase & build on each other's ideas
- Challenge ideas, not people
""")
    with col2:
        st.markdown("""
**📚 To Accurate Knowledge**
- Be specific and accurate
- Expect & answer challenging questions
- Use verifiable sources
""")
    with col3:
        st.markdown("""
**🧠 To Rigorous Thinking**
- Push for quality of claims & arguments
- Evidence must be sufficient, credible, relevant
- Use data, examples, analogies
""")

    st.divider()

    st.markdown("### 3. Talk Moves as Tools, Not Scripts: Five Principles")

    principles = [
        ("🔧 Tools are designed to solve problems",
         "A tool only makes sense in light of a specific problem or purpose, and in relation to other tools in the toolkit."),
        ("🎯 Understanding a tool requires knowing its purpose",
         "No tool — not even a hammer — is transparent in its use. Learning to use a tool means learning the materials it acts upon."),
        ("📈 Some tools are easier to pick up than others",
         "For example, *Wait Time* is one of the most researched talk moves, yet it is notoriously difficult to master."),
        ("🔗 Tools must be used in strategic sequence",
         "This takes practice, attention to the materials, and understanding of the larger purpose."),
        ("🪪 Tools belong to an identity",
         "Asking teachers to adopt new tools is, in a sense, asking them to take on a new identity — one that embodies particular values and beliefs.")
    ]

    for i, (title, desc) in enumerate(principles, 1):
        st.markdown(f"**{i}. {title}**")
        st.markdown(f"   {desc}")
        if i < len(principles):
            st.markdown("")

# ==========================================
# 4b. 任务步骤页面 (新增)
# ==========================================

# ✏️【新增】任务步骤页面，包含问卷链接和Moodle提交
def render_task_page():
    st.markdown("## 📝 Your Task: Step by Step")
    st.markdown("Follow these three steps to complete today's activity.")
    st.divider()

    # --- STEP 1 ---
    with st.expander("**Step 1: Pre-Survey** (Complete this first!)", expanded=True):
        st.markdown("""
Before starting the task, please complete a short survey about your AI usage and dialogic teaching knowledge.

⏱️ Estimated time: **5-7 minutes**
""")
        
        st.markdown(f"""
<a href="{SURVEY_1_LINK}" target="_blank">
    <button style="
        width: 100%;
        background-color: #4CAF50;
        color: white;
        border: none;
        padding: 12px;
        border-radius: 5px;
        cursor: pointer;
        font-weight: bold;
        font-size: 16px;
    ">
    📋 Open Pre-Survey
    </button>
</a>
""", unsafe_allow_html=True)

    st.markdown("")

    # --- STEP 2 ---
    with st.expander("**Step 2: Design Task with AI** (Main activity — 40 min)", expanded=True):
        st.markdown("""
Design a **5–10 minute lesson plan** for a classroom activity you may teach in the future. Please use **dialogic teaching** in your design.

You may design and include the following:

1. 📋 **Lesson plan** — What will you teach? What learning objectives would you like to achieve?
2. 📝 **Conduct plan** — How do you plan to conduct the lesson to achieve these objectives?
3. 💬 **A simulated teacher-student dialogue** — Show what your dialogic teaching might look like

---

💡 Consider real classroom complexity — students may be silent, give partial answers, or surprise you.

💡 Use AI however you like — brainstorm, get feedback, generate content, discuss ideas, etc.

⏱️ **Time: 40 minutes.**

---

When you're done, click the button below to submit your work on the Moodle Discussion Forum.
""")
        
        st.markdown(f"""
<a href="{MOODLE_LINK}" target="_blank">
    <button style="
        width: 100%;
        background-color: #ff4b4b;
        color: white;
        border: none;
        padding: 12px;
        border-radius: 5px;
        cursor: pointer;
        font-weight: bold;
        font-size: 16px;
    ">
    📤 Submit to Moodle Discussion Forum
    </button>
</a>
""", unsafe_allow_html=True)

    st.markdown("")

    # --- STEP 3 ---
    with st.expander("**Step 3: Post-Survey & Reflection** (After finishing the task)", expanded=True):
        st.markdown("""
After completing your design task, please take a few minutes to reflect on your AI experience and fill in a short survey.

⏱️ Estimated time: **5-7 minutes**
""")
        
        st.markdown(f"""
<a href="{SURVEY_2_LINK}" target="_blank">
    <button style="
        width: 100%;
        background-color: #2196F3;
        color: white;
        border: none;
        padding: 12px;
        border-radius: 5px;
        cursor: pointer;
        font-weight: bold;
        font-size: 16px;
    ">
    📝 Open Post-Survey
    </button>
</a>
""", unsafe_allow_html=True)

# ==========================================
# 5. 界面逻辑
# ==========================================

if "db_conn" not in st.session_state:
    st.session_state.db_conn = get_google_sheet()

# ✏️【新增】初始化页面状态
if "current_page" not in st.session_state:
    st.session_state.current_page = "chat"

# ✏️【新增】初始化处理状态（防止连续提交）
if "is_processing" not in st.session_state:
    st.session_state.is_processing = False

# --- 登录页 ---
if 'user_name' not in st.session_state:
    st.markdown("<br><br>", unsafe_allow_html=True)
    st.markdown("<h1 style='text-align: center;'>🎓 Connect to Your AI Assistant</h1>", unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1,2,1])
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

    # ✏️【修改】侧边栏导航按钮
    st.markdown("**📌 Navigation**")
    
    if st.button("💬 AI Chat", use_container_width=True, 
                 type="primary" if st.session_state.current_page == "chat" else "secondary"):
        st.session_state.current_page = "chat"
        st.rerun()
    
    if st.button("📝 Task Steps & Links", use_container_width=True,
                 type="primary" if st.session_state.current_page == "task" else "secondary"):
        st.session_state.current_page = "task"
        st.rerun()
    
    if st.button("📖 Dialogic Teaching Reference", use_container_width=True,
                 type="primary" if st.session_state.current_page == "reference" else "secondary"):
        st.session_state.current_page = "reference"
        st.rerun()

    st.divider()

    # ✏️【保留】Tips
    st.warning("""
**💡 Tips**
1. **General AI** — This AI is not a dialogic teaching expert. Give it context when asking.
2. **Keep your name** — Use the same link & name throughout, or history will be lost.
3. **Be patient** — If no response, wait a moment. Don't refresh repeatedly.
""")

    st.divider()
    if st.button("Log Out"):
        st.session_state.clear()
        st.rerun()

# --- 主内容区：根据侧边栏选择渲染 ---

if st.session_state.current_page == "chat":
    # ✏️【修改】聊天页面标题
    st.markdown("## 💬 AI Chat")
    st.caption("Ask me anything — I'm here to help you with your teaching design.")
    st.divider()
    
    # 显示历史消息
    for msg in st.session_state.messages:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])

    # 处理输入
    # ✏️【修改】添加处理状态保护
    if prompt := st.chat_input("Type your message here...", disabled=st.session_state.is_processing):
        
        # 设置处理中状态
        st.session_state.is_processing = True
        
        # 1. 显示用户输入
        st.session_state.messages.append({"role": "user", "content": prompt})
        with st.chat_message("user"):
            st.markdown(prompt)
        save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "Student", prompt)

        # 2. 生成 AI 回复
        with st.chat_message("assistant"):
            with st.spinner("🧠 AI is thinking..."):
                response = chat_with_coze(prompt, st.session_state.user_name)
                st.markdown(response)
        
        # 3. 保存 AI 回复
        st.session_state.messages.append({"role": "assistant", "content": response})
        save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "AI", response)
        
        # 4. 重置处理状态
        st.session_state.is_processing = False
        st.rerun()

elif st.session_state.current_page == "task":
    render_task_page()

elif st.session_state.current_page == "reference":
    render_knowledge_base()











