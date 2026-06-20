# 抖音作品解析工具

抖音视频/音频/文案/封面图提取工具

## 功能

- 🎬 解析抖音链接获取视频信息
- 📹 下载无水印视频
- 🎵 提取视频背景音乐
- 🖼️ 下载视频封面图
- 📝 一键复制视频文案

## 本地开发

### 1. 启动后端

```bash
cd backend
pip install -r requirements.txt
uvicorn app:app --host 0.0.0.0 --port 8000
```

### 2. 访问

打开浏览器访问 http://localhost:8000

### 3. 使用

1. 粘贴抖音视频链接（支持短链接和长链接）
2. 点击解析
3. 下载视频、音频、封面图，或复制文案

## 部署到 Railway

### 方式一：GitHub 部署（推荐）

1. 将项目上传到 GitHub 仓库
2. 登录 [Railway](https://railway.app)
3. 点击 "New Project" → "Deploy from GitHub repo"
4. 选择你的仓库
5. Railway 会自动检测并部署

### 方式二：Docker 部署

```bash
docker build -t douyin-extractor .
docker run -p 8000:8000 douyin-extractor
```

## 技术栈

- 后端: Python FastAPI + curl_cffi
- 前端: React + TailwindCSS
- 部署: Railway / Docker

## 注意事项

- 抖音API可能需要有效的Cookie才能解析部分视频
- Cookie 已配置在 `backend/app.py` 中（DEFAULT_COOKIE）
- 如遇Cookie失效，请重新获取并更新

## 项目结构

```
douyin-extractor/
├── backend/
│   ├── app.py              # FastAPI 主应用
│   └── requirements.txt    # Python 依赖
├── frontend/
│   ├── src/
│   │   ├── App.jsx        # React 主组件
│   │   └── index.css     # TailwindCSS 样式
│   ├── dist/             # 构建后的静态文件
│   └── index.html
├── Dockerfile
├── nixpacks.toml
└── railway.json
```
