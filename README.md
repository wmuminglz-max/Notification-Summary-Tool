# 通知摘要工具

一个基于 Flask 和小米 MiMo 大模型的通知摘要工具，可以把通知、公告、文档内容整理成清晰的摘要和待办事项。

## 功能特点

- 支持上传 PDF、Word（docx/doc）和 TXT 文件
- 支持直接粘贴通知文本
- 使用小米 MiMo 大模型生成摘要和待办事项
- 支持围绕摘要结果继续多轮提问
- 支持复制和下载整理结果

## 技术栈

- 后端：Flask
- 前端：原生 HTML、CSS、JavaScript
- 大模型接口：小米 MiMo（OpenAI 兼容接口）
- 文件处理：pypdf、PyMuPDF、python-docx、pytesseract、Pillow、OpenCV

## 快速开始

### 1. 克隆项目

```bash
git clone <https://github.com/wmuminglz-max/Notification-Summary-Tool.get>
cd notification-summarizer
```

如果你是在本地目录中使用，也可以直接进入项目目录。

### 2. 创建虚拟环境

```bash
python -m venv .venv
```

Windows PowerShell：

```powershell
.\.venv\Scripts\Activate.ps1
```

macOS/Linux：

```bash
source .venv/bin/activate
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

编辑 `.env`，填入你的 MiMo API Key：

```env
MIMO_API_KEY=your-api-key-here
MIMO_BASE_URL=https://api.xiaomimimo.com/v1
MIMO_MODEL=mimo-v2.5-pro
SECRET_KEY=your-secret-key-here
```

MiMo API Key 可在小米 MiMo 平台获取。

### 5. 启动应用

```bash
python app.py
```

默认访问地址：

```text
http://localhost:1314
```

## 使用方式

1. 打开浏览器访问本地应用地址。
2. 在设置中填写 MiMo API Key，或提前在 `.env` 中配置。
3. 上传通知文件，或直接粘贴通知文本。
4. 点击生成摘要。
5. 查看整理后的摘要、待办事项，并继续提问或导出结果。

## 支持的模型

- `mimo-v2.5-pro`：默认模型，适合复杂通知摘要和待办事项整理。
- `mimo-v2.5`：通用模型，适合日常通知摘要整理。

## 目录结构

```text
notification-summarizer/
├── app.py
├── config.py
├── requirements.txt
├── .env.example
├── .gitignore
├── LICENSE
├── README.md
├── templates/
│   └── index.html
├── static/
│   ├── css/
│   │   └── style.css
│   └── js/
│       └── main.js
├── utils/
│   ├── mimo_client.py
│   ├── pdf_reader.py
│   └── word_reader.py
└── uploads/
    └── .gitkeep
```

## 注意事项
- 生产环境请设置强随机 `SECRET_KEY`。
- 生产环境请关闭 Flask debug 模式，并使用 Gunicorn、uWSGI 等 WSGI 服务部署。
- 如需公网使用，建议为配置接口增加鉴权，避免 API Key 被未授权修改。

## License

本项目使用 MIT License，详见 [LICENSE](LICENSE)。
