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

## API 配置（已预填，开箱即用）

API Key 已预填在 `app.py` 里（智谱 AI `glm-5.3-flash`，聊天+看图全能，已实测）。
想换模型时在左侧边栏「家长设置中心」改：

| 供应商 | API 地址 | 模型名 | 说明 |
|--------|---------|--------|------|
| 智谱 AI（默认） | `https://open.bigmodel.cn/api/paas/v4` | `glm-5.3-flash` | 聊天+看图全能 |
| OpenAI | `https://api.openai.com/v1` | `gpt-4o` | 付费，效果最好 |
| 阿里通义 | `https://dashscope.aliyuncs.com/compatible-mode/v1` | `qwen-vl-plus` | 国内直连，有免费额度 |

> 注意：时光相册需要**支持图片的模型**，纯文字模型会报错。
> ⚠️ 因为 Key 写在代码里，Space 必须设为 **Private**。

## 部署到 Hugging Face Spaces（5 分钟搞定）

1. 注册/登录 https://huggingface.co （免费）
2. 右上角头像 → **New Space**
3. 填写：
   - Space name：随便起，比如 `xiaomianao`
   - License：选 `mit` 或不选
   - **SDK：选 Streamlit** ⚠️ 关键步骤
   - Visibility：建议选 **Private**（只有家人能访问）
4. 创建后，把 `app.py` 和 `requirements.txt` 两个文件上传（页面里有 "Add file → Upload files" 按钮）
5. 等 1-2 分钟自动构建完成，页面顶部就是你的专属网址：
   `https://你的用户名-你的spacename.hf.space`
6. 手机浏览器打开这个网址即可使用 ✅

## 重要提醒

- **相册数据是临时的**：Hugging Face 免费版重启应用后会清空上传的照片和文案。
  想长期保存有两个办法：
  1. 把重要照片+文案截图保存到手机（最简单）
  2. 后续可以升级为持久化存储（需要我来改代码，接入云存储）
- **API Key 安全**：侧边栏的 Key 只存在浏览器本次会话里，刷新后要重新填。
  如果嫌麻烦，可以把 Key 写死进 `app.py`（改 `DEFAULT_BASE_URL` 那一段，加一行
  `os.environ["ZHIPU_API_KEY"] = "你的key"` 之类），但 Private Space 才建议这么做。
- **改密码**：`app.py` 第 26 行 `PASSWORD = "8888"`
- **改时段**：`ALLOWED_START_HOUR` / `ALLOWED_END_HOUR`
- **改角色名字**：搜索 `ROLES` 字典，把"豆姐"等名字替换即可

## 本地运行（可选）

```bash
pip install -r requirements.txt
streamlit run app.py
```
