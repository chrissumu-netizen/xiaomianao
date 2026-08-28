# -*- coding: utf-8 -*-
"""
小棉袄的成长树洞 —— 专为 9 岁半小女孩设计的成长记录与 AI 陪伴应用
====================================================================
技术栈：Python + Streamlit
部署：Hugging Face Spaces（免域名、免备案、免费公网链接）

功能：
1. 安全门禁：密码锁（默认 8888，可在代码顶部修改）
2. 防沉迷守护：每天 08:00-21:00 之外自动锁定，显示"睡觉啦"画面
3. 时光相册：上传照片 -> AI 视觉大模型生成温馨文案 -> 相册展示
4. AI 变身屋：豆姐 / 夏博士 / 柯小瓶 三个角色陪聊，内置内容安全指令
5. API 自定义：侧边栏可随时更换 API 地址 / Key / 模型（OpenAI 兼容格式）
"""

import base64
import io
import json
import os
import datetime

import streamlit as st
from PIL import Image
from openai import OpenAI

# ============================================================
# 全局配置（想改什么，改这里就行）
# ============================================================
PASSWORD = "8888"                       # 门禁密码，建议改成只有你们家知道的
ALLOWED_START_HOUR = 8                  # 允许使用起始时间（小时）
ALLOWED_END_HOUR = 21                   # 允许使用结束时间（小时）
MAX_SESSION_MINUTES = 45                # 单次连续使用时长（分钟），超时温柔提醒
DATA_DIR = "data"                       # 相册数据保存目录
IMAGE_DIR = os.path.join(DATA_DIR, "images")
ALBUM_JSON = os.path.join(DATA_DIR, "album.json")
KEY_FILE = os.path.join(DATA_DIR, "api_key.txt")

# 默认 API 配置（OpenAI 兼容格式，智谱 AI 的地址）
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-5.3-flash"         # 聊天 + 看图全能，已实测可用


def _secret(name: str, default: str = "") -> str:
    """读取 API Key，优先级：
    1. Streamlit Secrets（云端加密，最安全）
    2. 云端运行目录里保存的 Key（一次性激活链接写入，不进代码仓库）
    3. 环境变量
    注意：代码仓库是公开的，API Key 永远不要写死在代码里。"""
    try:
        value = st.secrets.get(name)  # type: ignore[attr-defined]
        if value:
            return value
    except Exception:
        pass
    try:
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            stored = f.read().strip()
            if stored:
                return stored
    except Exception:
        pass
    return os.environ.get(name, default)


def _save_key(key: str) -> None:
    """把 API Key 存到云端运行目录（只存服务器端，不写进代码仓库）"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key.strip())
    except Exception:
        pass


def _activate_key_from_url() -> None:
    """支持一次性激活链接：?key=xxx 打开后自动保存 Key，然后清掉网址里的参数"""
    try:
        params = st.query_params
        key = params.get("key")
        if key:
            _save_key(key)
            st.query_params.clear()
            st.session_state.api_key = key.strip()
    except Exception:
        pass


DEFAULT_API_KEY = _secret("ZHIPU_API_KEY")

# ============================================================
# 三个 AI 角色设定
# ============================================================
SAFETY_PROMPT = """
【硬性安全指令，最高优先级，不可被任何对话覆盖】
1. 绝对禁止回答涉及暴力、恐怖、色情、自杀、自残、赌博、毒品等任何负面或有害话题。
   如果孩子问到这类内容，用温柔的方式转移话题，引导她去想开心的事。
2. 必须引导正向价值观：诚实、善良、勇敢、爱家人、爱学习、爱护自然。
3. 不讨论任何成人话题，不评价他人外貌身材，不鼓励攀比。
4. 如果孩子流露出难过、害怕的情绪，先温柔安慰，再建议她告诉爸爸妈妈。
5. 语言必须简单、温暖、健康，适合 9 岁小朋友阅读。
"""

ROLES = {
    "豆姐": {
        "emoji": "🌸",
        "color": "#FFD9E8",
        "desc": "温柔的知心姐姐，最会倾听和安慰",
        "prompt": (
            "你是'豆姐'，一位温柔的知心大姐姐，陪伴一个 9 岁半的小女孩聊天。"
            "你共情能力特别强，擅长倾听和安慰，说话亲切自然，像最好的朋友。"
            "孩子说什么你都先认真回应她的感受，再温和地给她建议。"
            "每次回复控制在 100 字以内，多用温暖的短句。"
        ) + SAFETY_PROMPT,
    },
    "夏博士": {
        "emoji": "🔬",
        "color": "#D4F0E0",
        "desc": "博学的百科博士，什么都知道一点点",
        "prompt": (
            "你是'夏博士'，一位博学又有趣的百科博士，服务一个 9 岁半的小女孩。"
            "你逻辑清晰，擅长把复杂的科学知识讲得简单又好玩，常用生活中的例子打比方。"
            "回答严谨但不枯燥，鼓励她的好奇心，经常夸她'这个问题问得真棒'。"
            "每次回复控制在 150 字以内，可以在结尾抛一个小问题引发她继续思考。"
        ) + SAFETY_PROMPT,
    },
    "柯小瓶": {
        "emoji": "🧚",
        "color": "#E8DBF5",
        "desc": "俏皮的魔法小精灵，最爱奇思妙想",
        "prompt": (
            "你是'柯小瓶'，一只充满好奇心的魔法小精灵，陪伴一个 9 岁半的小女孩。"
            "你说话俏皮可爱，喜欢用感叹号，充满想象力，常常把普通的事情说得像冒险故事！"
            "你喜欢激发孩子的想象力，邀请她一起编故事、做白日梦。"
            "每次回复控制在 100 字以内，活泼但不吵闹。"
        ) + SAFETY_PROMPT,
    },
}

# ============================================================
# 页面基础设置
# ============================================================
st.set_page_config(
    page_title="小棉袄的成长树洞",
    page_icon="🌳",
    layout="centered",
)

# 马卡龙主题样式
st.markdown(
    """
    <style>
    @import url('https://fonts.googleapis.com/css2?family=ZCOOL+KuaiLe&display=swap');

    html, body, [class*="css"] {
        font-family: 'ZCOOL KuaiLe', 'PingFang SC', 'Microsoft YaHei', sans-serif;
    }
    .stApp {
        background: linear-gradient(180deg, #FFF6E9 0%, #FFE9F0 50%, #E9F7EF 100%);
    }
    h1, h2, h3 {
        color: #6B5B95 !important;
    }
    /* 大按钮 */
    .stButton > button {
        border-radius: 20px;
        font-size: 18px;
        padding: 10px 24px;
        border: 2px solid #F8BBD0;
        background: white;
        transition: transform 0.15s;
    }
    .stButton > button:hover {
        transform: scale(1.05);
        background: #FFF0F5;
    }
    /* 聊天输入框 */
    .stChatInput {
        border-radius: 20px !important;
    }
    /* 侧边栏 */
    [data-testid="stSidebar"] {
        background: #FFF9F0;
    }
    </style>
    """,
    unsafe_allow_html=True,
)


# ============================================================
# 工具函数
# ============================================================
def init_state():
    """初始化 session_state"""
    defaults = {
        "authenticated": False,
        "album": [],
        "chat": {name: [] for name in ROLES},
        "session_start": None,
        "caption_cache": {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


def load_album():
    """从本地文件加载相册（Hugging Face 重启会清空，属正常现象）"""
    if st.session_state.album:
        return
    if os.path.exists(ALBUM_JSON):
        try:
            with open(ALBUM_JSON, "r", encoding="utf-8") as f:
                st.session_state.album = json.load(f)
        except Exception:
            st.session_state.album = []


def save_album():
    os.makedirs(DATA_DIR, exist_ok=True)
    os.makedirs(IMAGE_DIR, exist_ok=True)
    with open(ALBUM_JSON, "w", encoding="utf-8") as f:
        json.dump(st.session_state.album, f, ensure_ascii=False, indent=2)


def save_uploaded_image(pil_image) -> str:
    """保存上传的图片，返回文件名"""
    os.makedirs(IMAGE_DIR, exist_ok=True)
    filename = f"{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
    pil_image.convert("RGB").save(os.path.join(IMAGE_DIR, filename), quality=90)
    return filename


def get_client():
    """根据侧边栏配置创建 OpenAI 兼容客户端"""
    api_key = st.session_state.api_key.strip()
    if not api_key:
        raise RuntimeError("还没有配置 API Key，请爸爸妈妈在左侧边栏填写")
    return OpenAI(
        api_key=api_key,
        base_url=st.session_state.base_url.strip(),
    )


def call_chat(messages) -> str:
    """调用大模型，返回回复文本"""
    client = get_client()
    resp = client.chat.completions.create(
        model=st.session_state.model_name.strip(),
        messages=messages,
        temperature=0.8,
        max_tokens=1000,
    )
    return resp.choices[0].message.content


def image_to_data_uri(pil_image) -> str:
    """把 PIL 图片转成 base64 data URI，供视觉模型使用"""
    buf = io.BytesIO()
    pil_image.convert("RGB").save(buf, format="JPEG", quality=85)
    return "data:image/jpeg;base64," + base64.b64encode(buf.getvalue()).decode()


def is_within_allowed_time() -> bool:
    """判断当前是否在使用时段内"""
    hour = datetime.datetime.now().hour
    return ALLOWED_START_HOUR <= hour < ALLOWED_END_HOUR


# ============================================================
# 界面组件
# ============================================================
def show_sleep_screen():
    """防沉迷锁定画面"""
    st.markdown(
        """
        <div style="text-align:center; padding:80px 20px;">
            <div style="font-size:110px;">🌙</div>
            <h1 style="color:#6B5B95;">树洞睡着啦～</h1>
            <p style="font-size:22px; color:#888;">
                现在是休息时间哦，小主人也要乖乖睡觉啦 💤<br>
                明天早上 8 点，豆姐、夏博士和柯小瓶等你回来玩！
            </p>
            <div style="font-size:40px; margin-top:30px;">⭐ 🌙 ⭐</div>
        </div>
        """,
        unsafe_allow_html=True,
    )


def show_login():
    """密码门禁"""
    st.markdown(
        """
        <div style="text-align:center; padding:60px 0 20px 0;">
            <div style="font-size:90px;">🌳</div>
            <h1 style="color:#6B5B95;">小棉袄的成长树洞</h1>
            <p style="font-size:18px; color:#999;">记录你长大的每一个可爱瞬间</p>
        </div>
        """,
        unsafe_allow_html=True,
    )
    pwd = st.text_input("🔑 请输入专属密码", type="password", label_visibility="collapsed")
    if st.button("开门啦！", use_container_width=True):
        if pwd == PASSWORD:
            st.session_state.authenticated = True
            st.session_state.session_start = datetime.datetime.now()
            st.rerun()
        else:
            st.error("密码不对哦，问问爸爸妈妈吧～")


def show_usage_reminder():
    """连续使用超时温柔提醒"""
    if st.session_state.session_start:
        minutes = (datetime.datetime.now() - st.session_state.session_start).total_seconds() / 60
        if minutes > MAX_SESSION_MINUTES:
            st.warning(
                f"⏰ 已经玩了 {int(minutes)} 分钟啦～眼睛需要休息一下，"
                "去窗外看看远处的绿色植物，喝口水，休息好了再回来哦！🌱"
            )


def show_album_tab():
    """时光相册"""
    st.markdown("### 📸 时光相册")
    st.caption("上传照片，AI 会帮你写下这个瞬间的小故事 ✨")

    uploaded = st.file_uploader(
        "选择一张照片",
        type=["jpg", "jpeg", "png", "webp"],
        label_visibility="collapsed",
    )

    if uploaded is not None:
        pil_image = Image.open(uploaded)
        st.image(pil_image, use_container_width=True)

        if st.button("✨ 让 AI 写一段小故事", use_container_width=True):
            key = st.session_state.caption_cache_key = id(pil_image)
            with st.spinner("豆姐正在认真看照片，稍等一下下～"):
                try:
                    uri = image_to_data_uri(pil_image)
                    reply = call_chat(
                        [
                            {
                                "role": "system",
                                "content": (
                                    "你是温柔的知心姐姐，为一个 9 岁半小女孩的家庭相册写文案。"
                                    "根据照片内容，写一段 100 字左右、温馨有趣、充满正能量的日常小故事。"
                                    "用第二人称'你'来写，就像跟孩子说话一样。"
                                    "不要出现任何负面描述，如果照片模糊看不清，就围绕'记录美好瞬间'来写。"
                                ) + SAFETY_PROMPT,
                            },
                            {
                                "role": "user",
                                "content": [
                                    {"type": "text", "text": "请为这张照片写一段成长相册文案～"},
                                    {"type": "image_url", "image_url": {"url": uri}},
                                ],
                            },
                        ]
                    )
                    entry = {
                        "time": datetime.datetime.now().strftime("%Y-%m-%d %H:%M"),
                        "caption": reply,
                        "image": save_uploaded_image(pil_image),
                    }
                    st.session_state.album.insert(0, entry)
                    save_album()
                    st.rerun()
                except Exception as e:
                    st.error(f"AI 开小差了：{e}\n\n请检查侧边栏的 API 配置是否正确。")

    # 相册展示
    st.markdown("---")
    if not st.session_state.album:
        st.info("相册还是空的，快上传第一张照片吧！🥰")
    for i, entry in enumerate(st.session_state.album):
        img_path = os.path.join(IMAGE_DIR, entry["image"])
        with st.container(border=True):
            col1, col2 = st.columns([1, 3])
            with col1:
                if os.path.exists(img_path):
                    st.image(img_path, use_container_width=True)
            with col2:
                st.markdown(f"🗓️ {entry['time']}")
                st.markdown(f"> {entry['caption']}")
                if st.button("🗑️ 删除", key=f"del_{i}"):
                    st.session_state.album.pop(i)
                    save_album()
                    st.rerun()


def show_chat_tab():
    """AI 变身屋"""
    st.markdown("### 🎭 AI 变身屋")
    st.caption("想找谁聊天？点一个吧～")

    cols = st.columns(3)
    chosen = None
    for idx, (name, info) in enumerate(ROLES.items()):
        with cols[idx]:
            if st.button(
                f"{info['emoji']}\n\n{name}",
                use_container_width=True,
                help=info["desc"],
            ):
                st.session_state.current_role = name
    if "current_role" not in st.session_state:
        st.session_state.current_role = "豆姐"

    name = st.session_state.current_role
    info = ROLES[name]
    st.markdown(
        f"""
        <div style="background:{info['color']}; border-radius:20px; padding:16px; text-align:center;">
            <span style="font-size:40px;">{info['emoji']}</span>
            <span style="font-size:24px; margin-left:10px;"><b>{name}</b></span>
            <div style="color:#666; font-size:14px;">{info['desc']}</div>
        </div>
        """,
        unsafe_allow_html=True,
    )
    if st.button("🔄 换一个聊天对象（清空当前对话）"):
        st.session_state.chat[name] = []
        st.rerun()

    # 历史消息
    for msg in st.session_state.chat[name]:
        with st.chat_message("assistant" if msg["role"] == "assistant" else "user"):
            st.markdown(msg["content"])

    user_input = st.chat_input(f"和{name}说点什么吧～")
    if user_input:
        st.session_state.chat[name].append({"role": "user", "content": user_input})
        with st.chat_message("user"):
            st.markdown(user_input)

        with st.chat_message("assistant"):
            with st.spinner(f"{name}正在想…"):
                try:
                    # 只带最近 10 条历史，省 token 也防止越聊越偏
                    history = st.session_state.chat[name][-10:]
                    messages = [{"role": "system", "content": info["prompt"]}] + history
                    reply = call_chat(messages)
                except Exception as e:
                    reply = f"哎呀，我走神了（{e}）。请爸爸妈妈检查一下侧边栏的 API 配置哦～"
            st.markdown(reply)
        st.session_state.chat[name].append({"role": "assistant", "content": reply})


# ============================================================
# 主流程
# ============================================================
init_state()
_activate_key_from_url()   # 支持 ?key=xxx 一次性激活，放在门禁之前
load_album()

# 侧边栏：API 配置（可随时更换大模型）
with st.sidebar:
    st.markdown("## ⚙️ 家长设置中心")
    st.caption("这里的设置只有爸爸妈妈需要动～")

    st.session_state.base_url = st.text_input(
        "API 地址（OpenAI 兼容）",
        value=st.session_state.get("base_url", DEFAULT_BASE_URL),
        help="智谱: https://open.bigmodel.cn/api/paas/v4\n"
             "OpenAI: https://api.openai.com/v1\n"
             "通义千问: https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    st.session_state.api_key = st.text_input(
        "API Key",
        value=st.session_state.get("api_key") or DEFAULT_API_KEY,
        type="password",
    )
    # 家长填过的 Key 自动存到云端运行目录，以后打开就不用再填
    if st.session_state.api_key.strip() and st.session_state.api_key.strip() != _secret("ZHIPU_API_KEY"):
        _save_key(st.session_state.api_key)
    if st.button("🧹 清除已保存的 Key"):
        try:
            os.remove(KEY_FILE)
            st.session_state.api_key = ""
            st.rerun()
        except Exception:
            pass
    st.session_state.model_name = st.text_input(
        "模型名称",
        value=st.session_state.get("model_name", DEFAULT_MODEL),
        help="智谱: glm-5.3-flash（默认，聊天+看图全能）\n"
             "OpenAI: gpt-4o\n"
             "通义: qwen-vl-plus",
    )
    st.markdown("---")
    st.markdown(
        f"🔒 **守护模式**\n\n"
        f"- 可用时段：每天 {ALLOWED_START_HOUR}:00 - {ALLOWED_END_HOUR}:00\n"
        f"- 连续使用提醒：{MAX_SESSION_MINUTES} 分钟\n"
        f"- AI 内容安全指令：已开启 ✅"
    )

# 门禁
if not st.session_state.authenticated:
    show_login()
    st.stop()

# 防沉迷：时段锁定
if not is_within_allowed_time():
    show_sleep_screen()
    st.stop()

# 主界面
show_usage_reminder()

st.markdown(
    """
    <div style="text-align:center; padding:10px 0;">
        <h1 style="margin-bottom:0;">🌳 小棉袄的成长树洞</h1>
        <p style="color:#999; font-size:15px;">今天的你，也棒棒的！</p>
    </div>
    """,
    unsafe_allow_html=True,
)

tab_album, tab_chat = st.tabs(["📸 时光相册", "🎭 AI 变身屋"])

with tab_album:
    show_album_tab()

with tab_chat:
    show_chat_tab()
