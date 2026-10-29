# 通知摘要工具

一个基于 Flask 和小米 MiMo 大模型的通知摘要工具，可以把通知、公告、文档内容整理成清晰的摘要和待办事项。

## 功能特点

- 支持上传 PDF、Word（docx；旧版 doc 请先转换为 docx）和 TXT 文件
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

前置条件：安装 Git 和 Python（建议使用 Python 3.11）。先运行 `python --version` 确认；若系统仅提供 `python3`，下文的 `python` 请替换为 `python3`。

### 1. 克隆项目

```bash
git clone https://github.com/wmuminglz-max/Notification-Summary-Tool.git
cd Notification-Summary-Tool
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
python -m pip install -r requirements.txt
```

扫描版 PDF 的 OCR 还需要系统安装 Tesseract；`pip` 安装的 `pytesseract` 只是 Python 接口。中文识别需安装简体中文语言包 `chi_sim`，建议同时安装英文包 `eng`。例如 Ubuntu/Debian：

```bash
sudo apt-get update
sudo apt-get install tesseract-ocr tesseract-ocr-chi-sim tesseract-ocr-eng
```

macOS 可用 Homebrew 安装 `tesseract` 和 `tesseract-lang`；Windows 安装 Tesseract 及所需语言包，并将其安装目录加入 PATH。安装后重新打开终端，重新激活虚拟环境，用 `tesseract --version` 和 `tesseract --list-langs` 确认可执行文件及语言包可用。直接粘贴文本、TXT、DOCX 和带文本层的 PDF 无需 OCR。

### 4. 配置环境变量

复制 `.env.example` 为 `.env`：

```bash
cp .env.example .env
```

Windows PowerShell：

```powershell
Copy-Item .env.example .env
```

编辑项目根目录的 `.env`，填入你的 MiMo API Key 和生成的随机 `SECRET_KEY`。以下占位文本必须替换，不是真实密钥：

```env
MIMO_API_KEY=your-api-key-here
MIMO_BASE_URL=https://api.xiaomimimo.com/v1
MIMO_MODEL=mimo-v2.5-pro
SECRET_KEY=your-secret-key-here
```

MiMo API Key 可在小米 MiMo 平台获取。`MIMO_BASE_URL` 和 `MIMO_MODEL` 的示例值与 `config.py` 默认值一致，模型可用性以你的 API 账号为准。

生成 `SECRET_KEY`（将输出粘贴到 `.env` 对应项）：

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

程序会自动加载 `.env`；已经存在的同名系统环境变量优先。修改 `.env` 后需重启应用。`.gitignore` 会忽略真实环境文件，请勿提交或分享密钥。

### 5. 启动应用

```bash
python app.py
```

在项目根目录、虚拟环境已激活的终端中运行。看到 Flask 启动信息后保持终端开启，浏览器访问：

```text
http://localhost:1314
```

首次可确认首页能够打开，并在设置中确认 API Key 已配置；生成摘要需要有效的 MiMo API Key 和网络连接。按 `Ctrl+C` 停止服务。

`python app.py` 启动的是启用 debug、监听 `0.0.0.0:1314` 的开发服务器，仅用于受信任的本地开发环境，不要直接暴露到公网。

## 使用方式

1. 打开浏览器访问本地应用地址。
2. 在设置中填写 MiMo API Key，或提前在 `.env` 中配置。网页设置仅保存在当前服务进程内，重启后需重新填写；要持久配置请使用 `.env`。
3. 上传通知文件，或直接粘贴通知文本。
4. 点击生成摘要。
5. 查看整理后的摘要、待办事项，并继续提问或导出结果。

旧版二进制 `.doc` 虽可在上传界面选择，但当前读取器使用 `python-docx`，请先另存为 `.docx` 再上传。单次上传请求大小上限为 16MB。

## 模型配置

- `mimo-v2.5-pro`：默认模型，适合复杂通知摘要和待办事项整理。
- `mimo-v2.5`：界面提供的另一个选项，是否可用取决于 MiMo 服务和账号权限。

## 目录结构

```text
Notification-Summary-Tool/
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
│   ├── __init__.py
│   ├── mimo_client.py
│   ├── pdf_reader.py
│   └── word_reader.py
└── uploads/  # 启动时自动创建，不在仓库中
```

## 注意事项
- 生产环境请设置强随机 `SECRET_KEY`。
- 生产环境请关闭 Flask debug 模式，并使用 Gunicorn、uWSGI 等 WSGI 服务部署。
- 如需公网使用，建议为配置接口增加鉴权，避免 API Key 被未授权修改。

## License

本项目使用 MIT License，详见 [LICENSE](LICENSE)。
