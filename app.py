import streamlit as st
import requests
import json
import gspread
from oauth2client.service_account import ServiceAccountCredentials
from datetime import datetime

# ==========================================
# 1. 配置区域
# ==========================================

# 从 Streamlit Secrets 获取敏感信息 (稍后会在网页后台填)
# 这样代码里就不包含任何密码，非常安全
try:
    COZE_API_TOKEN = st.secrets["coze"]["api_token"]
    BOT_ID = st.secrets["coze"]["bot_id"]
    SHEET_NAME = st.secrets["google"]["sheet_name"]
    # 班级密码 (可选，这里先设为通用密码)
    CLASS_PASSWORD = "888" 
except:
    # 这是一个防呆设计，防止本地运行时报错太难看
    st.error("⚠️ 尚未配置 Secrets！请在 Streamlit Cloud 后台配置。")
    st.stop()

# ==========================================
# 2. 数据库功能：Google Sheets
# ==========================================

def get_google_sheet():
    """连接到 Google 表格"""
    scope = ['https://spreadsheets.google.com/feeds',
             'https://www.googleapis.com/auth/drive']
    
    try:
        # 从 Secrets 里读取 JSON 内容
        # 注意：我们需要把 toml 里的字典转换回 json 对象
        json_creds = dict(st.secrets["gcp_service_account"])
        
        creds = ServiceAccountCredentials.from_json_keyfile_dict(json_creds, scope)
        client = gspread.authorize(creds)
        
        # 打开指定的表格
        sheet = client.open(SHEET_NAME).sheet1
        return sheet
    except Exception as e:
        st.error(f"无法连接数据库，请联系老师。错误详情: {e}")
        return None

def save_to_sheet(sheet, user_name, role, content):
    """保存一条对话记录"""
    if sheet:
        time_now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        try:
            # 追加一行：[时间, 学生姓名, 角色, 内容]
            sheet.append_row([time_now, user_name, role, content])
        except Exception as e:
            # 如果网络抖动保存失败，不影响学生继续对话，只在后台打印
            print(f"Save failed: {e}")

def load_history_from_sheet(sheet, user_name):
    """加载历史记录 (断点续传)"""
    if not sheet:
        return []
        
    try:
        # 获取所有记录 (注意：如果数据量上万条，这里需要优化，目前几百条没问题)
        all_records = sheet.get_all_values() 
        # get_all_values 返回的是列表的列表，第一行通常是表头
        
        user_history = []
        # 跳过表头 (假设第一行是标题)
        for row in all_records[1:]:
            # 假设结构是: [时间, 姓名, 角色, 内容]
            # row[1] 是姓名，row[2] 是角色，row[3] 是内容
            if len(row) >= 4 and row[1] == user_name:
                role_map = {"学生": "user", "AI": "assistant", "AI导师": "assistant"}
                role = role_map.get(row[2], "assistant")
                user_history.append({"role": role, "content": row[3]})
        return user_history
    except Exception as e:
        st.warning(f"历史记录加载失败: {e}")
        return []

# ==========================================
# 3. AI 核心：Coze API (流式)
# ==========================================

def chat_with_coze(query, user_name):
    url = "https://api.coze.cn/v3/chat"
    headers = {
        "Authorization": f"Bearer {COZE_API_TOKEN}",
        "Content-Type": "application/json"
    }
    
    # 使用 safe_user_id 确保 Coze 后台也能区分用户
    data = {
        "bot_id": BOT_ID,
        "user_id": f"stu_{user_name}",
        "stream": True,
        "auto_save_history": True,
        "additional_messages": [
            {"role": "user", "content": query, "content_type": "text"}
        ]
    }
    
    try:
        response = requests.post(url, headers=headers, json=data, stream=True)
        if response.status_code != 200:
            return f"🚫 网络连接失败: {response.status_code}"
            
        full_content = ""
        for line in response.iter_lines():
            if not line: continue
            decoded_line = line.decode('utf-8')
            if decoded_line.startswith("data:"):
                json_str = decoded_line[5:]
                try:
                    if json_str.strip() == "[DONE]": continue
                    chunk = json.loads(json_str)
                    if chunk.get('event') == 'conversation.message.delta' or chunk.get('type') == 'answer':
                        content = chunk.get('content', '')
                        full_content += content
                except: continue

        if not full_content:
            return "🤔 AI 思考中..."
        return full_content

    except Exception as e:
        return f"💥 出错: {str(e)}"

# ==========================================
# 4. 网页主逻辑
# ==========================================

st.set_page_config(page_title="AI 教学助手", page_icon="🎓", layout="wide")

# 连接数据库 (只连接一次)
if "db_conn" not in st.session_state:
    st.session_state.db_conn = get_google_sheet()

# --- 登录页 ---
if 'user_name' not in st.session_state:
    st.markdown("<h1 style='text-align: center;'>🎓 登录你的课堂</h1>", unsafe_allow_html=True)
    col1, col2, col3 = st.columns([1,2,1])
    with col2:
        name_input = st.text_input("👤 你的姓名 (拼音或英文)：", placeholder="例如：ZhangSan")
        pwd_input = st.text_input("🔑 班级暗号：", type="password")
        
        if st.button("🚀 开始学习", use_container_width=True):
            if name_input and pwd_input == CLASS_PASSWORD:
                st.session_state.user_name = name_input
                # 🌟 登陆成功瞬间，去数据库拉取历史记录
                with st.spinner("正在同步你的学习进度..."):
                    history = load_history_from_sheet(st.session_state.db_conn, name_input)
                    st.session_state.messages = history
                st.rerun()
            elif pwd_input != CLASS_PASSWORD:
                st.error("暗号错误！")
            else:
                st.error("请输入姓名。")
    st.stop()

# --- 聊天页 ---
with st.sidebar:
    st.write(f"当前学生: **{st.session_state.user_name}**")
    if st.button("🚪 退出 (清除缓存)"):
        for key in list(st.session_state.keys()):
            del st.session_state[key]
        st.rerun()

st.title("🤖 教学对话练习")

# 显示历史
if "messages" not in st.session_state:
    st.session_state.messages = []

for msg in st.session_state.messages:
    with st.chat_message(msg["role"]):
        st.markdown(msg["content"])

# 处理输入
if prompt := st.chat_input("请输入回答..."):
    # 1. 用户
    st.session_state.messages.append({"role": "user", "content": prompt})
    with st.chat_message("user"):
        st.markdown(prompt)
    # ☁️ 存数据库
    save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "学生", prompt)

    # 2. AI
    with st.chat_message("assistant"):
        response = chat_with_coze(prompt, st.session_state.user_name)
        st.markdown(response)
            
    # 3. AI 记录
    st.session_state.messages.append({"role": "assistant", "content": response})
    # ☁️ 存数据库
    save_to_sheet(st.session_state.db_conn, st.session_state.user_name, "AI", response)




