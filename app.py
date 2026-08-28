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

import asyncio
import base64
import io
import json
import os
import re
import datetime

import streamlit as st
from PIL import Image
from openai import OpenAI

# ============================================================
# 全局配置（想改什么，改这里就行）
# ============================================================
PASSWORD = "8888"                       # 门禁密码，建议改成只有你们家知道的
ALLOWED_START_HOUR = 0                  # 允许使用起始时间（小时）【今晚临时全天开放，明早改回 8】
ALLOWED_END_HOUR = 24                   # 允许使用结束时间（小时）【今晚临时全天开放，明早改回 21】
MAX_SESSION_MINUTES = 45                # 单次连续使用时长（分钟），超时温柔提醒
# 数据目录放在用户主目录：应用源码目录每次重新部署都会被清空，主目录能多撑住一些
DATA_DIR = os.path.join(os.path.expanduser("~"), "xiaomianao_data")
IMAGE_DIR = os.path.join(DATA_DIR, "images")
BEIJING_TZ = datetime.timezone(datetime.timedelta(hours=8))  # 云端服务器是 UTC，必须换算成北京时间
ALBUM_JSON = os.path.join(DATA_DIR, "album.json")
KEY_FILE = os.path.join(DATA_DIR, "api_key.txt")
ASR_KEY_FILE = os.path.join(DATA_DIR, "asr_key.txt")

# 默认 API 配置（OpenAI 兼容格式，智谱 AI 的地址）
DEFAULT_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"
DEFAULT_MODEL = "glm-5.3-flash"         # 聊天 + 看图全能，已实测可用

# 一键激活链接：打开即把正确的 Key 写进应用（Key 已带在链接里，仅你自家 app 用）
ACTIVATION_URL = "https://xiaomianao-fjgd7rxrneeyy8nqnegqv6.streamlit.app/?key=1df0cdefee2d4dd7bf56e95871a8c8ad.JeyyXxr35DlYIKt0"


def _is_valid_zhipu_key(key: str) -> bool:
    """智谱 Key 格式：32 位十六进制 id + 点 + 密钥。
    用来拦住被污染的 Key（比如误把门禁密码 8888 填进了 Key 框，Key 会变成 8888 开头而非法）。"""
    return bool(re.match(r"^[0-9a-fA-F]{32}\.[A-Za-z0-9]+$", key.strip()))


def _load_api_key() -> str:
    """API Key 读取优先级：Streamlit Secrets > 云端运行目录(一次性激活链接写入) > 环境变量。
    注意：代码仓库是公开的，Key 永远不写死在代码里。任何来源只要格式不对都会被忽略。"""
    try:
        v = st.secrets.get("ZHIPU_API_KEY")  # type: ignore[attr-defined]
        if v and _is_valid_zhipu_key(v):
            return v.strip()
    except Exception:
        pass
    try:
        with open(KEY_FILE, "r", encoding="utf-8") as f:
            s = f.read().strip()
            if s and _is_valid_zhipu_key(s):
                return s
    except Exception:
        pass
    e = os.environ.get("ZHIPU_API_KEY", "")
    return e.strip() if _is_valid_zhipu_key(e) else ""


def _save_key(key: str) -> None:
    """把 API Key 存到云端运行目录（只存服务器端，不写进代码仓库）。
    格式非法绝不保存，防止污染。"""
    if not _is_valid_zhipu_key(key):
        return
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key.strip())
    except Exception:
        pass


def _activate_key_from_url() -> None:
    """支持一次性激活链接：?key=xxx 打开后自动保存 Key，然后清掉网址里的参数。
    只对格式合法的 Key 生效，防止把门禁密码之类误当成 Key 存进去。"""
    try:
        val = st.query_params.get("key")
        key = val[0] if isinstance(val, list) else val
        if key and _is_valid_zhipu_key(key):
            _save_key(key)
            st.session_state.api_key = key.strip()
            try:
                st.query_params.clear()
            except Exception:
                pass
    except Exception:
        pass


DEFAULT_API_KEY = _load_api_key()

# 语音识别（ASR）配置：任何 OpenAI 兼容 / 或支持 /audio/transcriptions 的接口都能用
# 硅基流动 SenseVoiceSmall 目前是免费的，注册后送额度：https://cloud.siliconflow.cn
DEFAULT_ASR_BASE_URL = "https://api.siliconflow.cn/v1"
DEFAULT_ASR_MODEL = "FunAudioLLM/SenseVoiceSmall"


def _load_asr_key() -> str:
    """单独读取语音识别 Key（不能复用大模型的 Key 文件）"""
    try:
        v = st.secrets.get("ASR_API_KEY")  # type: ignore[attr-defined]
        if v:
            return v
    except Exception:
        pass
    try:
        with open(ASR_KEY_FILE, "r", encoding="utf-8") as f:
            s = f.read().strip()
            if s:
                return s
    except Exception:
        pass
    return os.environ.get("ASR_API_KEY", "")


DEFAULT_ASR_KEY = _load_asr_key()


def _save_asr_key(key: str) -> None:
    """保存语音识别 Key 到云端运行目录"""
    try:
        os.makedirs(DATA_DIR, exist_ok=True)
        with open(ASR_KEY_FILE, "w", encoding="utf-8") as f:
            f.write(key.strip())
    except Exception:
        pass

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
        "voice": "zh-CN-XiaoxiaoNeural",   # 温柔亲切的女声（豆包那种感觉）
        "pitch": "+0Hz",
        "rate": "+0%",
        "greeting": "嗨，我是豆姐，有什么开心的事想跟我说说吗？",
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
        "voice": "zh-CN-YunyangNeural",    # 沉稳专业的男声
        "pitch": "-5Hz",
        "rate": "+0%",
        "greeting": "你好，我是夏博士，又有什么有趣的问题要问我吗？",
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
        "voice": "zh-CN-XiaoyiNeural",     # 活泼女声，调高音调更可爱
        "pitch": "+18Hz",
        "rate": "+12%",
        "greeting": "嗨嗨！我是柯小瓶，我们今天要去哪里冒险呀！",
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
        "api_key": DEFAULT_API_KEY,
        "base_url": DEFAULT_BASE_URL,
        "model_name": DEFAULT_MODEL,
        "auto_speak": True,
        "asr_base_url": DEFAULT_ASR_BASE_URL,
        "asr_key": DEFAULT_ASR_KEY,
        "asr_model": DEFAULT_ASR_MODEL,
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
    filename = f"{now_beijing().strftime('%Y%m%d_%H%M%S')}.jpg"
    pil_image.convert("RGB").save(os.path.join(IMAGE_DIR, filename), quality=90)
    return filename


def get_client():
    """根据侧边栏配置创建 OpenAI 兼容客户端"""
    api_key = (st.session_state.get("api_key") or "").strip()
    if not api_key:
        raise RuntimeError(
            "还没有配置 API Key。爸爸妈妈可以在左侧「家长设置中心」粘贴 Key 并点「保存 Key」，"
            "或直接打开带 ?key= 的专属激活链接"
        )
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


# ---------------- 语音能力 ----------------
def _clean_for_speech(text: str) -> str:
    """去掉 emoji 和符号，让朗读更自然"""
    text = re.sub(r"[🌸🔬🧚🌳🎉💪❤️✨🌱⭐🌙📸🎭🔑⚙️🛡️🔄🧹🔊🎤]", " ", text)
    text = re.sub(r"[*#`>_\-]{2,}", " ", text)
    return re.sub(r"\s+", " ", text).strip()


@st.cache_data(ttl=3600, show_spinner=False)
def text_to_speech(text: str, role: str) -> bytes:
    """文字转语音：每个角色有自己的声音，返回 mp3 字节"""
    import edge_tts

    info = ROLES.get(role, {})
    async def _generate() -> bytes:
        comm = edge_tts.Communicate(
            _clean_for_speech(text),
            info.get("voice", "zh-CN-XiaoxiaoNeural"),
            pitch=info.get("pitch", "+0Hz"),
            rate=info.get("rate", "+0%"),
        )
        buf = io.BytesIO()
        async for chunk in comm.stream():
            if chunk["type"] == "audio":
                buf.write(chunk["data"])
        return buf.getvalue()

    return asyncio.run(_generate())


def transcribe_audio(audio_bytes: bytes) -> str:
    """语音转文字：调用 OpenAI 兼容的音频识别接口"""
    key = (st.session_state.get("asr_key") or "").strip()
    if not key:
        raise RuntimeError("还没配置语音识别 Key")
    client = OpenAI(
        api_key=key,
        base_url=(st.session_state.get("asr_base_url") or "").strip() or DEFAULT_ASR_BASE_URL,
    )
    resp = client.audio.transcriptions.create(
        model=(st.session_state.get("asr_model") or "").strip() or DEFAULT_ASR_MODEL,
        file=("voice.wav", audio_bytes, "audio/wav"),
    )
    return (getattr(resp, "text", None) or "").strip()


def now_beijing() -> datetime.datetime:
    """北京时间（云端服务器跑的是 UTC，必须强制换算，否则防沉迷时段会差 8 小时）"""
    return datetime.datetime.now(BEIJING_TZ)


def is_within_allowed_time() -> bool:
    """判断当前是否在使用时段内（按北京时间）"""
    hour = now_beijing().hour
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


def _ask_album_story(pil_image, first: bool = True) -> str:
    """让 AI 给相册照片写一段小故事。first=True 写第一稿；first=False 换一个完全不同的写法。"""
    uri = image_to_data_uri(pil_image)
    base = (
        "你是温柔的知心姐姐，为一个 9 岁半小女孩的家庭相册写文案。"
        "根据照片内容，写一段 100 字左右、温馨有趣、充满正能量的日常小故事。"
        "用第二人称'你'来写，就像跟孩子说话一样。"
        "不要出现任何负面描述，如果照片模糊看不清，就围绕'记录美好瞬间'来写。"
    )
    if not first:
        base += "这次换一个完全不同的角度、不同的细节和写法，不要和刚才那篇重复。"
    return call_chat(
        [
            {
                "role": "system",
                "content": base + SAFETY_PROMPT,
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


def show_album_tab():
    """时光相册：AI 先写草稿，孩子可改 / 可重写，满意了再确认发送"""
    st.markdown("### 📸 时光相册")
    st.caption("上传照片，AI 会帮你写下这个瞬间的小故事，你可以改成自己喜欢的样子 ✨")

    # 草稿状态：确认发送前都只是建议，不进相册
    if "draft" not in st.session_state:
        st.session_state.draft = None
    if "album_draft_editor" not in st.session_state:
        st.session_state.album_draft_editor = ""

    uploaded = st.file_uploader(
        "选择一张照片",
        type=["jpg", "jpeg", "png", "webp"],
        label_visibility="collapsed",
    )

    if uploaded is not None:
        pil_image = Image.open(uploaded)
        st.image(pil_image, use_container_width=True)

        if st.session_state.draft is None:
            # 还没写：请 AI 出第一稿
            if st.button("✨ 让 AI 写一段小故事", use_container_width=True):
                with st.spinner("豆姐正在认真看照片，稍等一下下～"):
                    try:
                        reply = _ask_album_story(pil_image, first=True)
                        st.session_state.draft = {
                            "image": save_uploaded_image(pil_image),
                            "time": now_beijing().strftime("%Y-%m-%d %H:%M"),
                        }
                        st.session_state.album_draft_editor = reply
                        st.rerun()
                    except Exception as e:
                        st.error(f"AI 开小差了：{e}\n\n请检查侧边栏的 API 配置是否正确。")
        else:
            # 已有草稿：可改、可重写、可确认
            st.markdown("---")
            st.markdown("🌟 **AI 写的小故事（可以改成你喜欢的样子哦）**")
            st.session_state.album_draft_editor = st.text_area(
                "改一改这个故事，满意了再点确认发送～",
                value=st.session_state.album_draft_editor,
                height=200,
                label_visibility="collapsed",
                key="album_draft_editor",
            )
            c1, c2, c3 = st.columns(3)
            with c1:
                if st.button("🔄 重新写一个", use_container_width=True):
                    with st.spinner("豆姐再想想别的写法…"):
                        try:
                            st.session_state.album_draft_editor = _ask_album_story(pil_image, first=False)
                            st.rerun()
                        except Exception as e:
                            st.error(f"AI 开小差了：{e}")
            with c2:
                if st.button("✅ 确认发送", use_container_width=True, type="primary"):
                    caption = (st.session_state.album_draft_editor or "").strip()
                    if caption:
                        st.session_state.album.insert(0, {
                            "time": st.session_state.draft["time"],
                            "caption": caption,
                            "image": st.session_state.draft["image"],
                        })
                        save_album()
                    st.session_state.draft = None
                    st.session_state.album_draft_editor = ""
                    st.rerun()
            with c3:
                if st.button("🗑️ 不要了", use_container_width=True):
                    try:
                        os.remove(os.path.join(IMAGE_DIR, st.session_state.draft["image"]))
                    except Exception:
                        pass
                    st.session_state.draft = None
                    st.session_state.album_draft_editor = ""
                    st.rerun()

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

    # 没配 Key 先提醒，避免孩子看到一堆报错
    _ak = (st.session_state.get("api_key") or "").strip()
    if not _ak:
        st.warning(
            "⚠️ 还没配置 API Key，豆姐她们现在没法说话。\n\n"
            "爸爸妈妈点左侧「家长设置中心」里的 🔗 一键激活链接，"
            "或粘贴 Key 后点「💾 保存 Key」就好啦。"
        )

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
    col_a, col_b = st.columns(2)
    with col_a:
        if st.button("🔊 听 ta 的声音", use_container_width=True, help="试听这个角色的声音"):
            try:
                st.session_state.preview_audio = text_to_speech(info["greeting"], name)
                st.session_state.preview_role = name
            except Exception as e:
                st.error(f"语音生成失败：{e}")
    with col_b:
        if st.button("🔄 清空当前对话", use_container_width=True):
            st.session_state.chat[name] = []
            st.rerun()

    # 试听播放器（放进 session_state，避免刷新后消失）
    if st.session_state.get("preview_role") == name and st.session_state.get("preview_audio"):
        st.audio(st.session_state.preview_audio, format="audio/mp3", autoplay=True)

    # 历史消息（助手的回复带上朗读播放器，最新的那条自动播放）
    history = st.session_state.chat[name]
    for idx, msg in enumerate(history):
        with st.chat_message("assistant" if msg["role"] == "assistant" else "user"):
            st.markdown(msg["content"])
            if msg["role"] == "assistant" and st.session_state.get("auto_speak", True):
                try:
                    audio = text_to_speech(msg["content"], name)
                    st.audio(audio, format="audio/mp3", autoplay=(idx == len(history) - 1))
                except Exception:
                    pass

    # 语音输入：录一段话自动转成文字发送
    st.markdown("**🎤 说给她听**（说完点停止，自动发送）")
    audio_value = st.audio_input("按住说话", key=f"mic_{name}", label_visibility="collapsed")
    user_input = None
    if audio_value is not None:
        audio_bytes = audio_value.getvalue()
        fingerprint = f"{len(audio_bytes)}_{name}"
        if st.session_state.get("last_audio") != fingerprint:
            st.session_state.last_audio = fingerprint
            if st.session_state.get("asr_key", "").strip():
                with st.spinner("正在听懂你的话…"):
                    try:
                        user_input = transcribe_audio(audio_bytes)
                        if user_input:
                            st.success(f"听到啦：{user_input}")
                        else:
                            st.warning("没听清楚，再说一遍试试～")
                    except Exception as e:
                        st.error(f"语音识别失败：{e}")
            else:
                st.info(
                    "还没配置语音识别 Key 哦～爸爸妈妈在左侧边栏「🎙️ 语音设置」填一下就能用了。"
                    "（也可以用手机输入法键盘上自带的小话筒，直接说话就能打字）"
                )

    if not user_input:
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
                    _ak = (st.session_state.get("api_key") or "").strip()
                    _masked = (_ak[:6] + "…" + _ak[-4:]) if len(_ak) > 10 else ("(空)" if not _ak else _ak)
                    reply = (
                        f"哎呀，我走神了（{e}）。\n\n"
                        f"当前发出的 Key：{_masked}（长度 {len(_ak)}）\n"
                        "如果前缀不是 `1df0cd`，说明 Key 配错了——点左侧「家长设置中心」里的 "
                        "🔗 一键激活链接重设，或清掉重粘正确 Key 再点「💾 保存 Key」。"
                    )
            st.markdown(reply)
        # 音频在历史消息里统一渲染（这样切换角色、刷新都不会让播放器消失）
        st.session_state.chat[name].append({"role": "assistant", "content": reply})


# ============================================================
# 主流程
# ============================================================
init_state()
_activate_key_from_url()   # 支持 ?key=xxx 一次性激活，放在门禁之前
load_album()

# 家长设置已移到门禁之后渲染（见下方“主流程”中的 with st.sidebar 块），
# 这样登录页干净、孩子也碰不到 API Key 框，避免 Key 被误填污染。

# 门禁
if not st.session_state.authenticated:
    show_login()
    st.stop()

# 防沉迷：时段锁定
if not is_within_allowed_time():
    show_sleep_screen()
    st.stop()

# ================= 家长设置（仅在解锁后显示，孩子碰不到 Key 框） =================
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
    key_input = st.text_input(
        "API Key",
        value=st.session_state.get("api_key", ""),
        type="password",
        help="智谱 Key 格式是 32 位字符 + 点 + 一串密钥；填错会被自动拒绝",
    )
    col_save, col_clear = st.columns(2)
    with col_save:
        if st.button("💾 保存 Key", use_container_width=True):
            if _is_valid_zhipu_key(key_input):
                _save_key(key_input)
                st.session_state.api_key = key_input.strip()
                st.success("Key 已保存 ✅")
            else:
                st.error("这个 Key 格式不对，请检查是不是多了空格，或把门禁密码填进来了")
    with col_clear:
        if st.button("🧹 清除 Key", use_container_width=True):
            try:
                os.remove(KEY_FILE)
            except Exception:
                pass
            st.session_state.api_key = ""
            st.rerun()
    # 当前 Key 状态（一眼看出配没配对）+ 一键激活链接
    _ak = (st.session_state.get("api_key") or "").strip()
    if _ak:
        _masked = (_ak[:6] + "…" + _ak[-4:]) if len(_ak) > 10 else _ak
        _ok_prefix = "✅" if _ak.startswith("1df0cd") else "⚠️ 前缀不对"
        st.caption(f"当前已配置 Key：{_masked}（长度 {len(_ak)}）{_ok_prefix}")
    else:
        st.caption("当前未配置 Key ❌")
    st.markdown(f"🔗 [一键激活链接（点一下自动填好正确 Key）]({ACTIVATION_URL})")
    st.session_state.model_name = st.text_input(
        "模型名称",
        value=st.session_state.get("model_name", DEFAULT_MODEL),
        help="智谱: glm-5.3-flash（默认，聊天+看图全能）\n"
             "OpenAI: gpt-4o\n"
             "通义: qwen-vl-plus",
    )
    st.markdown("---")
    st.markdown("## 🎙️ 语音设置")

    st.session_state.auto_speak = st.checkbox(
        "🔊 自动朗读回复",
        value=st.session_state.get("auto_speak", True),
        help="关掉的话，回复就只显示文字，不自动出声",
    )
    st.caption("三个角色各有一种声音：豆姐=温柔姐姐声、夏博士=沉稳男声、柯小瓶=俏皮可爱声")

    with st.expander("语音识别（说话输入）配置"):
        st.session_state.asr_base_url = st.text_input(
            "识别接口地址",
            value=st.session_state.get("asr_base_url", DEFAULT_ASR_BASE_URL),
        )
        st.session_state.asr_key = st.text_input(
            "识别 Key",
            value=st.session_state.get("asr_key", ""),
            type="password",
        )
        st.session_state.asr_model = st.text_input(
            "识别模型",
            value=st.session_state.get("asr_model", DEFAULT_ASR_MODEL),
            help="硅基流动免费：FunAudioLLM/SenseVoiceSmall\nOpenAI：whisper-1",
        )
        if st.button("💾 保存识别 Key", use_container_width=True):
            if st.session_state.asr_key.strip():
                _save_asr_key(st.session_state.asr_key)
                st.success("识别 Key 已保存 ✅")
            else:
                st.warning("识别 Key 是空的")
        st.info(
            "免费 Key 获取：注册 https://cloud.siliconflow.cn → 控制台 → API 密钥 → 复制，"
            "粘贴到上面即可（SenseVoiceSmall 是免费的）。\n\n"
            "不配置也能用：直接用手机输入法键盘上的 🎤 说话，一样能输入。"
        )

    st.markdown("---")
    st.markdown(
        f"🔒 **守护模式**\n\n"
        f"- 可用时段：每天 {ALLOWED_START_HOUR}:00 - {ALLOWED_END_HOUR}:00\n"
        f"- 连续使用提醒：{MAX_SESSION_MINUTES} 分钟\n"
        f"- AI 内容安全指令：已开启 ✅"
    )

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
