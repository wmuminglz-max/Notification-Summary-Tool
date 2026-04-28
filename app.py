"""通知摘要工具 - Flask 主应用"""
import os
from flask import Flask, render_template, request, jsonify
from werkzeug.utils import secure_filename
from werkzeug.exceptions import BadRequest, RequestEntityTooLarge
from config import Config
from utils.mimo_client import MiMoClient
from utils.pdf_reader import read_pdf
from utils.word_reader import read_word


def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

    def allowed_file(filename: str) -> bool:
        return bool(filename) and '.' in filename and filename.rsplit('.', 1)[1].lower() in app.config['ALLOWED_EXTENSIONS']

    def get_mimo_client():
        api_key = app.config['MIMO_API_KEY']
        if not api_key:
            raise ValueError("请设置 MIMO_API_KEY 环境变量或在配置中填写 API Key")
        return MiMoClient(
            api_key=api_key,
            base_url=app.config['MIMO_BASE_URL'],
            model=app.config['MIMO_MODEL']
        )

    def read_single_uploaded_file(file_storage) -> dict:
        if not file_storage or not getattr(file_storage, 'filename', ''):
            raise ValueError('文件不能为空')

        original_name = file_storage.filename or ''
        if not allowed_file(original_name):
            raise ValueError(f'不支持的文件类型，请上传 {", ".join(sorted(app.config["ALLOWED_EXTENSIONS"]))} 格式的文件')

        try:
            file_content = file_storage.read() or b''
        except Exception as e:
            raise Exception(f"读取上传文件内容失败: {e}")

        if not file_content:
            raise Exception(f"上传文件为空: {original_name}")

        safe_name = secure_filename(original_name) or original_name
        ext = original_name.rsplit('.', 1)[1].lower()

        if ext == 'pdf':
            text = read_pdf(file_content)
        elif ext in ['docx', 'doc']:
            text = read_word(file_content)
        elif ext == 'txt':
            text = file_content.decode('utf-8', errors='ignore')
        else:
            raise ValueError(f"暂不支持的文件扩展名: {ext}")

        return {
            'filename': safe_name,
            'original_filename': original_name,
            'content': str(text or '').strip()
        }

    def extract_uploaded_contents() -> list:
        """支持多文件上传，返回 [{'filename':..., 'content':...}, ...]。"""
        try:
            files = request.files
        except Exception as e:
            raise Exception(f"上传表单解析失败: {e}")

        uploaded_files = []
        try:
            uploaded_files.extend([f for f in files.getlist('files') if getattr(f, 'filename', '')])
        except Exception:
            pass

        try:
            single_file = files.get('file')
            if single_file and getattr(single_file, 'filename', ''):
                uploaded_files.append(single_file)
        except Exception as e:
            raise Exception(f"读取上传文件字段失败: {e}")

        if not uploaded_files:
            return []

        extracted = []
        for file_storage in uploaded_files:
            item = read_single_uploaded_file(file_storage)
            if item['content']:
                extracted.append(item)

        return extracted

    def normalize_context_text(value) -> str:
        return str(value or '').strip()

    def normalize_user_role(value) -> str:
        role = normalize_context_text(value)
        return role or '普通学生'


    def sanitize_chat_history(history) -> list:
        """仅保留用户消息，避免模型把自己先前的回答当作事实继续放大。"""
        cleaned = []
        for item in history or []:
            if not isinstance(item, dict):
                continue
            role = str(item.get('role', '')).strip()
            content = normalize_context_text(item.get('content', ''))
            if role == 'user' and content:
                cleaned.append({'role': 'user', 'content': content[:2000]})
        return cleaned[-12:]

    def build_combined_source_text(file_items: list, text_input: str = '') -> str:
        parts = []
        for index, item in enumerate(file_items, start=1):
            content = normalize_context_text(item.get('content'))
            if not content:
                continue
            filename = item.get('original_filename') or item.get('filename') or f'通知{index}'
            parts.append(f"【通知{index}｜{filename}】\n{content}")

        text_input = normalize_context_text(text_input)
        if text_input:
            label = '补充通知内容' if parts else '通知内容'
            parts.append(f"【{label}】\n{text_input}")

        return '\n\n'.join(parts).strip()

    def calculate_source_count(file_items: list, text_input: str = '') -> int:
        count = len([item for item in file_items if normalize_context_text(item.get('content'))])
        if normalize_context_text(text_input):
            count += 1
        return count

    def has_fake_multi_notice(result: str, source_count: int) -> bool:
        text = normalize_context_text(result)
        if source_count <= 1:
            bad_signals = ['通知2', '通知二', '第二份通知', '两份通知', '另一份通知', '第2份通知']
            return any(signal in text for signal in bad_signals)
        return False

    @app.errorhandler(RequestEntityTooLarge)
    def handle_file_too_large(_e):
        return jsonify({
            'success': False,
            'error': '上传文件过大，当前限制为 16MB'
        }), 413

    @app.errorhandler(BadRequest)
    def handle_bad_request(e):
        return jsonify({
            'success': False,
            'error': f'请求格式错误: {e.description or str(e)}'
        }), 400

    @app.route('/')
    def index():
        return render_template('index.html')

    @app.route('/api/summarize', methods=['POST'])
    def summarize():
        stage = '开始处理'
        try:
            stage = '解析上传请求'
            if request.method != 'POST':
                raise Exception('请求方法错误')

            stage = '读取上传文件'
            file_items = extract_uploaded_contents()

            stage = '读取文本输入'
            try:
                text_input = request.form.get('text', '')
                user_role = normalize_user_role(request.form.get('user_role', '普通学生'))
            except Exception as e:
                raise Exception(f"读取文本输入失败: {e}")

            stage = '校验提取结果'
            content = build_combined_source_text(file_items, text_input)
            source_count = calculate_source_count(file_items, text_input)
            if not content:
                return jsonify({
                    'success': False,
                    'error': '未能从文件中提取到可用文本。若为扫描版 PDF，请检查图片清晰度；若为 TXT，请确认编码格式。'
                }), 400

            stage = '调用 MiMo API 生成摘要'
            client = get_mimo_client()
            result = client.summarize_notifications(content, user_role=user_role, source_count=source_count)

            stage = '校验摘要结果一致性'
            if has_fake_multi_notice(result, source_count):
                result = client.summarize_notifications(
                    content,
                    user_role=user_role,
                    source_count=source_count,
                    force_single_source=True
                )

            if has_fake_multi_notice(result, source_count):
                raise ValueError('检测到摘要结果与真实来源数不一致：当前只有 1 份来源内容，但结果中出现了额外通知。请重试或检查原文内容。')

            return jsonify({
                'success': True,
                'result': result,
                'source_content': content,
                'file_count': len(file_items),
                'source_count': source_count,
                'file_names': [item.get('original_filename') or item.get('filename') for item in file_items],
                'user_role': user_role
            })

        except ValueError as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'处理失败（{stage}）: {str(e)}'
            }), 500

    @app.route('/api/todo', methods=['POST'])
    def todo():
        try:
            data = request.get_json(silent=True) or {}
            content = normalize_context_text(data.get('source_content'))
            summary = normalize_context_text(data.get('summary'))
            user_role = normalize_user_role(data.get('user_role'))
            history = data.get('history') or []
            user_role = normalize_user_role(data.get('user_role'))

            if not content and not summary and not history:
                return jsonify({
                    'success': False,
                    'error': '请先生成摘要，或先输入通知内容再整理待办'
                }), 400

            client = get_mimo_client()
            base_content = content or summary
            result = client.organize_todos(content=base_content, summary=summary, history=history, user_role=user_role)

            return jsonify({
                'success': True,
                'result': result
            })

        except ValueError as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'待办整理失败: {str(e)}'
            }), 500

    @app.route('/api/chat', methods=['POST'])
    def chat():
        try:
            data = request.get_json(silent=True) or {}
            message = normalize_context_text(data.get('message', ''))
            history = sanitize_chat_history(data.get('history', []))
            source_content = normalize_context_text(data.get('source_content'))
            summary = normalize_context_text(data.get('summary'))
            user_role = normalize_user_role(data.get('user_role'))

            if not message:
                return jsonify({
                    'success': False,
                    'error': '请输入消息'
                }), 400

            context_parts = [
                '你是一个只允许基于当前通知原文回答问题的通知处理助手。',
                '回答时只能使用通知原文、当前摘要中与原文一致的内容，以及用户刚刚提出的问题。',
                '不要把你之前的回答当成事实来源；历史对话仅用于理解用户追问方向。',
                '如果通知里没有相关信息，必须明确说“通知中没有提到这一点”或“无法从当前通知确认”，不要补充臆测。',
                '如果当前内容包含多份通知，要先分清对应哪一份通知，再回答。',
                f'当前用户身份是：{user_role}。请只保留该身份直接需要关心或执行的信息。',
                '若问题涉及责任归属，而通知没有明确写是谁负责，必须回答“待确认具体责任人”。',
                '回答尽量简洁、明确、可执行。'
            ]
            if source_content:
                context_parts.append(f"\n【当前通知原文】\n{source_content[:18000]}")
            if summary:
                context_parts.append(f"\n【当前摘要】\n{summary[:8000]}")

            client = get_mimo_client()
            response = client.chat(
                message=message,
                history=history,
                system_prompt='\n'.join(context_parts),
                user_role=user_role
            )

            return jsonify({
                'success': True,
                'response': response
            })

        except ValueError as e:
            return jsonify({
                'success': False,
                'error': str(e)
            }), 400
        except Exception as e:
            return jsonify({
                'success': False,
                'error': f'对话失败: {str(e)}'
            }), 500

    @app.route('/api/config', methods=['GET', 'POST'])
    def config_api():
        if request.method == 'GET':
            return jsonify({
                'has_api_key': bool(app.config['MIMO_API_KEY']),
                'model': app.config['MIMO_MODEL']
            })

        data = request.get_json(silent=True) or {}
        api_key = data.get('api_key', '')
        model = data.get('model', 'mimo-v2.5-pro')

        if api_key:
            app.config['MIMO_API_KEY'] = api_key
            app.config['MIMO_MODEL'] = model

        return jsonify({'success': True})

    return app


if __name__ == '__main__':
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=1314)
