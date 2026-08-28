---
title: 小棉袄的成长树洞
emoji: 🌳
colorFrom: pink
colorTo: purple
sdk: docker
app_port: 7860
pinned: false
short_description: 为九岁半小女孩定制的成长记录与AI陪伴空间
---

# 🌳 小棉袄的成长树洞

为 9 岁半小主人定制的成长记录 + AI 陪伴应用。
免域名、免备案，部署在 Hugging Face Spaces 上，手机浏览器打开就能用。

> 部署方式：Docker SDK + Streamlit（Hugging Face 自 2025-04-30 起已弃用内置 Streamlit SDK）。

## 功能

| 功能 | 说明 |
|------|------|
| 🔒 安全门禁 | 密码登录（默认 `8888`，在 `app.py` 顶部 `PASSWORD` 处修改） |
| 🌙 防沉迷 | 每天 `8:00-21:00` 之外自动锁定为"睡觉啦"画面；连续使用 45 分钟提醒休息 |
| 📸 时光相册 | 上传照片 → AI 视觉模型自动写 100 字温馨小故事 → 相册保存展示 |
| 🎭 AI 变身屋 | 三个角色：豆姐（知心姐姐🌸）/ 夏博士（百科博士🔬）/ 柯小瓶（魔法小精灵🧚） |
| ⚙️ API 自定义 | 侧边栏可随时更换 API 地址 / Key / 模型（OpenAI 兼容格式即可） |
| 🛡️ 内容安全 | 每个角色的 System Prompt 都内置硬性安全指令，屏蔽一切负面话题 |

## 已部署（线上可用）

| 项目 | 内容 |
|------|------|
| 访问地址 | **https://xiaomianao-fjgd7rxrneeyy8nqnegqv6.streamlit.app/** |
| 托管平台 | Streamlit Community Cloud（免费，免域名免备案） |
| 代码仓库 | https://github.com/chrissumu-netizen/xiaomianao |
| 模型 | 智谱 AI `glm-5.3-flash`（聊天 + 看图全能，已实测） |

代码推到 GitHub 后，Streamlit Cloud 会在约 1 分钟自动重新部署。

## API Key 的安全存法（重要）

代码仓库是**公开**的，所以 API Key 没有写进任何代码文件。实际生效方式有两条：

1. **一次性激活链接**（当前正在用）：用 `?key=你的Key` 打开应用一次，
   Key 会写入云端运行目录，之后正常网址就能用，网址里的参数会自动清掉。
   Key 只存在于服务器端，不进代码仓库、不进浏览器历史。
2. **Streamlit Secrets**（更规范）：应用菜单 ⋯ → Settings → Secrets 里填
   `ZHIPU_API_KEY = "你的Key"`，优先级最高。

想换模型改左侧边栏「家长设置中心」：

| 供应商 | API 地址 | 模型名 | 说明 |
|--------|---------|--------|------|
| 智谱 AI（默认） | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.3-flash` | 聊天+看图全能 |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` | 付费，效果最好 |
| 阿里通义 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-plus` | 国内直连，有免费额度 |

> 注意：时光相册需要**支持图片的模型**，纯文字模型会报错。
> 应用若长时间无人访问会休眠，下次打开冷启动约 30 秒。

## 重要提醒

- **相册数据是临时的**：云端重启后会清空照片和文案（免费托管的通病）。
  重要内容建议截图保存；想要真正的长期保存，可以后续接入云存储。
- **API Key 若失效**：重新用一次性激活链接打开一次即可。
- **改密码**：`app.py` 第 29 行 `PASSWORD = "8888"`
- **改时段**：`ALLOWED_START_HOUR`（默认 8）/ `ALLOWED_END_HOUR`（默认 21）
- **改角色名字**：搜索 `ROLES` 字典，把"豆姐"等名字替换即可

## 本地运行（可选）

```bash
pip install -r requirements.txt
streamlit run app.py
```
