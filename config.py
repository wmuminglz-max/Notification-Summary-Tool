"""配置文件"""
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    # Flask 配置
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB 最大文件大小
    UPLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'uploads')
    
    # 小米 MiMo API 配置
    MIMO_API_KEY = os.getenv('MIMO_API_KEY', '')
    MIMO_BASE_URL = os.getenv('MIMO_BASE_URL', 'https://api.xiaomimimo.com/v1')
    MIMO_MODEL = os.getenv('MIMO_MODEL', 'mimo-v2.5-pro')
    
    # 允许的文件扩展名
    ALLOWED_EXTENSIONS = {'pdf', 'docx', 'doc', 'txt'}
