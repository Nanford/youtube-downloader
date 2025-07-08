#!/usr/bin/env python3
"""
YouTube 下载器 - 修复版
适用于 yt.leenf.online
"""

import os
import sys
import subprocess
import threading
import json
import time
import datetime
import uuid
import logging
import re
from pathlib import Path
from flask import Flask, render_template, request, jsonify, send_from_directory
from flask_socketio import SocketIO, emit, join_room, leave_room
from werkzeug.utils import secure_filename
from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置类
class Config:
    SECRET_KEY = os.getenv('SECRET_KEY', os.urandom(24).hex())
    DEBUG = os.getenv('FLASK_DEBUG', 'False').lower() == 'true'
    DOMAIN = os.getenv('DOMAIN', 'yt.leenf.online')
    HOST = os.getenv('HOST', '0.0.0.0')
    PORT = int(os.getenv('PORT', 8091))
    
    # 目录配置
    BASE_DIR = Path(__file__).parent
    DOWNLOAD_DIR = Path(os.getenv('DOWNLOAD_DIR', BASE_DIR / 'downloads'))
    UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', BASE_DIR / 'uploads'))
    LOG_DIR = Path(os.getenv('LOG_DIR', BASE_DIR / 'logs'))
    
    # 文件配置 - 🔧 加强安全限制
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 1 * 1024 * 1024))  # 1MB
    MAX_COOKIES_FILE_SIZE = int(os.getenv('MAX_COOKIES_FILE_SIZE', 100 * 1024))  # 100KB
    MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', 2))  # 降低并发数
    DOWNLOAD_TIMEOUT = int(os.getenv('DOWNLOAD_TIMEOUT', 1800))
    
    def __init__(self):
        # 创建必要目录
        for directory in [self.DOWNLOAD_DIR, self.UPLOAD_DIR, self.LOG_DIR]:
            directory.mkdir(parents=True, exist_ok=True)

config = Config()

# 创建 Flask 应用
app = Flask(__name__)
app.config.from_object(config)
socketio = SocketIO(app, cors_allowed_origins="*", async_mode='threading')

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]',
    handlers=[
        logging.FileHandler(config.LOG_DIR / 'app.log'),
        logging.StreamHandler()
    ]
)

if not config.DEBUG:
    file_handler = logging.FileHandler(config.LOG_DIR / 'app.log')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)

# 🔧 安全函数
def sanitize_log_message(message):
    """清理日志消息，防止注入"""
    if not isinstance(message, str):
        message = str(message)
    # 移除潜在危险字符
    message = re.sub(r'[<>"\'\\\x00-\x1f\x7f-\x9f]', '', message)
    # 限制长度
    if len(message) > 500:
        message = message[:497] + "..."
    return message

def validate_session_id(session_id):
    """验证会话ID格式"""
    if not session_id:
        return False
    # 允许UUID格式或32位十六进制字符串
    pattern = r'^[a-f0-9]{8}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{4}-[a-f0-9]{12}$|^[a-f0-9]{32}$'
    return bool(re.match(pattern, session_id))

def validate_url(url):
    """验证URL是否为有效的YouTube链接"""
    if not url or len(url) > 500:
        return False
    youtube_patterns = [
        r'https?://(?:www\.)?youtube\.com/watch\?v=[\w-]+',
        r'https?://(?:www\.)?youtube\.com/shorts/[\w-]+',
        r'https?://youtu\.be/[\w-]+',
        r'https?://(?:www\.)?youtube\.com/playlist\?list=[\w-]+',
        r'https?://(?:www\.)?youtube\.com/channel/[\w-]+',
        r'https?://(?:www\.)?youtube\.com/@[\w-]+',
    ]
    return any(re.match(pattern, url) for pattern in youtube_patterns)

# 用户会话类
class UserSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.created_at = datetime.datetime.now()
        self.last_activity = datetime.datetime.now()
        self.download_manager = None
        
    def update_activity(self):
        """更新最后活动时间"""
        self.last_activity = datetime.datetime.now()
        
    def get_cookies_path(self):
        return config.UPLOAD_DIR / f"cookies_{self.session_id}.txt"
    
    def get_download_dir(self):
        download_dir = config.DOWNLOAD_DIR / f"session_{self.session_id}"
        download_dir.mkdir(exist_ok=True)
        return download_dir

# 全局会话存储
user_sessions = {}

def get_or_create_session():
    """获取或创建用户会话"""
    session_id = request.headers.get('X-Session-ID')
    
    # 验证现有会话ID
    if session_id and validate_session_id(session_id) and session_id in user_sessions:
        user_sessions[session_id].update_activity()
        return user_sessions[session_id], session_id
    
    # 创建新会话
    session_id = str(uuid.uuid4())
    user_sessions[session_id] = UserSession(session_id)
    return user_sessions[session_id], session_id

# Cookies 管理器
class CookiesManager:
    def __init__(self, session_id):
        self.session_id = session_id
        self.cookies_file = config.UPLOAD_DIR / f"cookies_{session_id}.txt"
    
    def check_cookies_exist(self):
        return self.cookies_file.exists()
    
    def get_cookies_age_days(self):
        if not self.check_cookies_exist():
            return None
        mtime = self.cookies_file.stat().st_mtime
        age_seconds = time.time() - mtime
        return int(age_seconds / 86400)
    
    def validate_cookies_file(self, content):
        """🔧 增强的 cookies 文件验证"""
        try:
            # 检查内容长度
            if len(content) > config.MAX_COOKIES_FILE_SIZE:
                return False, "Cookies 文件过大"
            
            if len(content.strip()) < 50:
                return False, "Cookies 文件内容过少"
            
            # 检查是否包含危险内容
            dangerous_patterns = [
                r'<script[^>]*>',
                r'javascript:',
                r'data:',
                r'vbscript:',
                r'onload=',
                r'onerror=',
            ]
            
            content_lower = content.lower()
            for pattern in dangerous_patterns:
                if re.search(pattern, content_lower):
                    return False, "文件内容包含潜在危险代码"
            
            lines = content.strip().split('\n')
            valid_lines = [line for line in lines if line.strip() and not line.startswith('#')]
            
            if len(valid_lines) < 5:
                return False, "Cookies 文件内容过少"
            
            # 检查关键 cookies - 更宽松的检查
            youtube_indicators = ['youtube', 'google', 'VISITOR_INFO', 'YSC', 'CONSENT', 'PREF', 'SID']
            found_indicators = sum(1 for indicator in youtube_indicators if indicator in content)
            
            if found_indicators < 2:
                return False, "缺少关键 YouTube cookies"
            
            # 验证cookies格式（Netscape格式）
            valid_cookie_lines = 0
            for line in valid_lines[:10]:  # 只检查前10行
                parts = line.split('\t')
                if len(parts) >= 6:  # Netscape格式至少6个字段
                    valid_cookie_lines += 1
            
            if valid_cookie_lines < 3:
                return False, "Cookies 文件格式不正确（应为 Netscape 格式）"
            
            return True, "Cookies 文件格式正确"
            
        except Exception as e:
            app.logger.error(f"Cookies validation error: {str(e)}")
            return False, f"验证失败: 文件格式错误"
    
    def save_cookies(self, content):
        """🔧 安全的 cookies 保存"""
        is_valid, message = self.validate_cookies_file(content)
        if not is_valid:
            return False, message
        
        try:
            # 创建备份（如果已存在）
            if self.cookies_file.exists():
                backup_file = self.cookies_file.with_suffix('.bak')
                self.cookies_file.rename(backup_file)
            
            # 安全写入
            with open(self.cookies_file, 'w', encoding='utf-8', newline='\n') as f:
                f.write(content)
            
            # 设置文件权限（只有所有者可读写）
            self.cookies_file.chmod(0o600)
            
            app.logger.info(f"Cookies saved for session {self.session_id[:8]}")
            return True, "Cookies 保存成功"
            
        except Exception as e:
            app.logger.error(f"Failed to save cookies: {str(e)}")
            return False, f"保存失败: {str(e)}"
    
    def should_update_cookies(self):
        if not self.check_cookies_exist():
            return True, "❌ 未上传 cookies 文件"
        
        age = self.get_cookies_age_days()
        if age and age > 30:
            return True, f"⏰ Cookies 已使用 {age} 天，建议更新"
        
        return False, f"✅ Cookies 状态良好（{age or 0} 天前上传）"

# 下载管理器
class DownloadManager:
    def __init__(self, session_id):
        self.session_id = session_id
        self.room = f"session_{session_id}"
        self.is_downloading = False
        self.current_progress = {"current": 0, "total": 0, "status": "idle"}
        self.cookies_manager = CookiesManager(session_id)
        self.download_count = 0  # 下载计数
        self.start_time = None
    
    def log_message(self, message):
        safe_message = sanitize_log_message(message)
        app.logger.info(f"[{self.session_id[:8]}] {safe_message}")
        socketio.emit('log_message', {'message': safe_message}, room=self.room)
    
    def update_progress(self, current, total, status="downloading"):
        self.current_progress = {
            "current": current,
            "total": total,
            "status": status,
            "percentage": int((current / total) * 100) if total > 0 else 0
        }
        socketio.emit('progress_update', self.current_progress, room=self.room)
    
    def check_ffmpeg(self):
        """检查 FFmpeg 是否可用"""
        try:
            result = subprocess.run(['ffmpeg', '-version'], 
                                  capture_output=True, text=True, timeout=5)
            return result.returncode == 0
        except:
            return False
    
    def get_download_options(self):
        """🔧 获取安全的下载选项"""
        has_ffmpeg = self.check_ffmpeg()
        
        base_opts = [
            "-o", "%(title).100s.%(ext)s",  # 限制文件名长度
            "--embed-metadata",
            "--no-warnings",
            "--user-agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "--referer", "https://www.youtube.com/",
            "--extractor-retries", "2",  # 减少重试次数
            "--fragment-retries", "2",
            "--retry-sleep", "exp=1:3",  # 减少重试间隔
            "--socket-timeout", "30",
            "--max-filesize", "500M",  # 🔧 添加文件大小限制
            "--max-duration", "3600",  # 🔧 添加时长限制（1小时）
            "--no-playlist",  # 🔧 禁止下载播放列表
        ]
        
        if has_ffmpeg:
            base_opts.extend(["-f", "bv*[height<=720]+ba/b[height<=720]"])  # 🔧 限制分辨率
            self.log_message("🎬 使用 FFmpeg 高画质模式（720p限制）")
        else:
            base_opts.extend(["-f", "best[height<=720]/best"])  # 🔧 限制分辨率
            self.log_message("📱 使用兼容模式（720p限制）")
        
        # 添加 cookies
        if self.cookies_manager.check_cookies_exist():
            base_opts.extend(["--cookies", str(self.cookies_manager.cookies_file)])
            age = self.cookies_manager.get_cookies_age_days()
            self.log_message(f"🍪 使用 cookies 文件（{age}天前上传）")
        
        return base_opts
    
    def validate_urls(self, urls):
        """🔧 验证URL列表"""
        if len(urls) > 5:  # 限制批量下载数量
            return False, "单次最多下载5个视频"
        
        valid_urls = []
        for url in urls:
            if not validate_url(url):
                return False, f"无效的URL: {url[:50]}..."
            valid_urls.append(url)
        
        return True, valid_urls
    
    def download_video(self, url, download_dir):
        """🔧 安全的视频下载"""
        self.log_message(f"🎬 开始下载: {url[:50]}...")
        
        cmd = [sys.executable, "-m", "yt_dlp"] + self.get_download_options()
        cmd.extend(["-P", str(download_dir), url])
        
        try:
            process = subprocess.Popen(
                cmd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                universal_newlines=True
            )
            
            # 设置超时
            timeout = 600  # 10分钟超时
            start_time = time.time()
            
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                    
                # 检查超时
                if time.time() - start_time > timeout:
                    process.terminate()
                    self.log_message("⏰ 下载超时，已终止")
                    return False
                    
                if output:
                    clean_output = output.strip()
                    if clean_output and not clean_output.startswith('['):
                        # 只显示重要信息
                        if any(keyword in clean_output.lower() for keyword in 
                               ['downloading', 'finished', 'error', 'warning']):
                            self.log_message(f"📥 {clean_output[:100]}...")
            
            if process.returncode == 0:
                self.log_message(f"✅ 下载完成: {url[:30]}...")
                return True
            else:
                error = process.stderr.read().strip()
                if "Sign in to confirm" in error:
                    self.log_message("🤖 检测到反机器人保护，请更新 cookies")
                elif "Private video" in error:
                    self.log_message("🔒 私有视频，无法下载")
                elif "Video unavailable" in error:
                    self.log_message("📹 视频不可用")
                else:
                    self.log_message(f"❌ 下载失败: {error[:100]}...")
                return False
                
        except Exception as e:
            self.log_message(f"❌ 下载异常: {str(e)[:100]}...")
            return False
    
    def batch_download(self, urls):
        """🔧 安全的批量下载"""
        if self.is_downloading:
            self.log_message("⚠️ 正在下载中，请等待完成...")
            return
        
        # 验证URLs
        is_valid, result = self.validate_urls(urls)
        if not is_valid:
            self.log_message(f"❌ URL验证失败: {result}")
            return
        
        urls = result
        self.is_downloading = True
        self.start_time = time.time()
        session = user_sessions[self.session_id]
        download_dir = session.get_download_dir()
        
        self.log_message(f"🚀 开始批量下载，共 {len(urls)} 个视频")
        self.update_progress(0, len(urls), "starting")
        
        success_count = 0
        for i, url in enumerate(urls, 1):
            self.update_progress(i-1, len(urls), "downloading")
            self.log_message(f"📋 [{i}/{len(urls)}] 处理: {url[:50]}...")
            
            if self.download_video(url, download_dir):
                success_count += 1
                self.download_count += 1
            
            # 添加延迟，避免被反爬虫
            time.sleep(2)
        
        elapsed_time = int(time.time() - self.start_time)
        self.update_progress(len(urls), len(urls), "completed")
        self.log_message(f"🎉 批量下载完成！成功: {success_count}/{len(urls)} 用时: {elapsed_time}秒")
        self.is_downloading = False

# Flask 路由
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_cookies', methods=['POST'])
def upload_cookies():
    """🔧 修复后的上传 cookies 文件"""
    try:
        session, session_id = get_or_create_session()
        
        # 检查请求
        if 'cookies_file' not in request.files:
            app.logger.warning(f"No file in upload request from {request.remote_addr}")
            return jsonify({"error": "没有文件上传"}), 400
        
        file = request.files['cookies_file']
        if file.filename == '':
            return jsonify({"error": "没有选择文件"}), 400
        
        # 安全文件名
        filename = secure_filename(file.filename)
        if not filename.lower().endswith('.txt'):
            return jsonify({"error": "只支持 .txt 文件"}), 400
        
        # 检查文件大小
        file.seek(0, 2)  # 移动到文件末尾
        file_size = file.tell()
        file.seek(0)  # 重置文件指针
        
        if file_size > config.MAX_COOKIES_FILE_SIZE:
            return jsonify({"error": f"文件过大，最大支持 {config.MAX_COOKIES_FILE_SIZE//1024}KB"}), 400
        
        if file_size == 0:
            return jsonify({"error": "文件为空"}), 400
        
        try:
            content = file.read().decode('utf-8')
        except UnicodeDecodeError:
            return jsonify({"error": "文件编码错误，请使用UTF-8编码"}), 400
        
        # 验证和保存
        cookies_manager = CookiesManager(session_id)
        success, message = cookies_manager.save_cookies(content)
        
        if success:
            app.logger.info(f"Cookies uploaded successfully for session {session_id[:8]} from {request.remote_addr}")
            # 🔧 确保返回正确的格式
            return jsonify({
                "message": message,
                "session_id": session_id,
                "success": True  # 🔧 添加success字段以兼容前端
            })
        else:
            app.logger.warning(f"Cookies upload failed for session {session_id[:8]}: {message}")
            return jsonify({"error": message}), 400
            
    except Exception as e:
        app.logger.error(f"Cookies upload error: {str(e)}")
        return jsonify({"error": "服务器内部错误"}), 500

@app.route('/api/download', methods=['POST'])
def api_download():
    """🔧 改进的下载 API"""
    try:
        session, session_id = get_or_create_session()
        
        if not session.download_manager:
            session.download_manager = DownloadManager(session_id)
        
        data = request.get_json()
        if not data:
            return jsonify({"error": "无效的请求数据"}), 400
            
        urls = data.get('urls', [])
        
        if not urls:
            return jsonify({"error": "没有提供有效的 URL"}), 400
        
        # 🔧 增强URL验证
        valid_urls = []
        for url in urls:
            url = url.strip()
            if validate_url(url):
                valid_urls.append(url)
        
        if not valid_urls:
            return jsonify({"error": "没有找到有效的 YouTube URL"}), 400
        
        if len(valid_urls) > 5:  # 🔧 限制数量
            return jsonify({"error": "单次最多下载5个视频"}), 400
        
        # 🔧 检查下载频率
        if session.download_manager.download_count > 20:  # 每日限制
            return jsonify({"error": "今日下载次数已达上限"}), 429
        
        threading.Thread(
            target=session.download_manager.batch_download,
            args=(valid_urls,),
            daemon=True
        ).start()
        
        app.logger.info(f"Download started for session {session_id[:8]}: {len(valid_urls)} URLs")
        return jsonify({
            "message": f"开始下载 {len(valid_urls)} 个视频",
            "session_id": session_id
        })
        
    except Exception as e:
        app.logger.error(f"Download API error: {str(e)}")
        return jsonify({"error": "服务器内部错误"}), 500

@app.route('/api/status')
def api_status():
    """🔧 改进的状态 API"""
    try:
        session, session_id = get_or_create_session()
        
        if not session.download_manager:
            session.download_manager = DownloadManager(session_id)
        
        should_update, message = session.download_manager.cookies_manager.should_update_cookies()
        
        return jsonify({
            "session_id": session_id,
            "is_downloading": session.download_manager.is_downloading,
            "progress": session.download_manager.current_progress,
            "cookies": {
                "exists": session.download_manager.cookies_manager.check_cookies_exist(),
                "should_update": should_update,
                "status_message": message
            },
            "ffmpeg_available": session.download_manager.check_ffmpeg(),
            "download_count": session.download_manager.download_count
        })
        
    except Exception as e:
        app.logger.error(f"Status API error: {str(e)}")
        return jsonify({"error": "服务器内部错误"}), 500

@app.route('/downloads/<session_id>')
def download_files(session_id):
    """🔧 安全的文件列表"""
    try:
        # 验证会话ID
        if not validate_session_id(session_id) or session_id not in user_sessions:
            return jsonify({"error": "会话不存在"}), 404
        
        session = user_sessions[session_id]
        download_dir = session.get_download_dir()
        
        files = []
        try:
            for file_path in download_dir.iterdir():
                if file_path.is_file() and file_path.stat().st_size > 0:
                    # 🔧 安全的文件名处理
                    safe_name = secure_filename(file_path.name)
                    files.append({
                        "name": safe_name,
                        "size": file_path.stat().st_size,
                        "url": f"/download_file/{session_id}/{safe_name}",
                        "modified": file_path.stat().st_mtime
                    })
            
            # 按修改时间排序
            files.sort(key=lambda x: x['modified'], reverse=True)
            
        except PermissionError:
            app.logger.error(f"Permission denied accessing download dir for session {session_id}")
            return jsonify({"error": "访问权限不足"}), 403
        
        return jsonify({"files": files})
        
    except Exception as e:
        app.logger.error(f"Download files error: {str(e)}")
        return jsonify({"error": "服务器内部错误"}), 500

@app.route('/download_file/<session_id>/<filename>')
def download_file(session_id, filename):
    """🔧 安全的文件下载"""
    try:
        # 验证会话ID
        if not validate_session_id(session_id) or session_id not in user_sessions:
            return jsonify({"error": "会话不存在"}), 404
        
        # 🔧 安全文件名处理
        safe_filename = secure_filename(filename)
        if not safe_filename or safe_filename != filename:
            return jsonify({"error": "无效的文件名"}), 400
        
        session = user_sessions[session_id]
        download_dir = session.get_download_dir()
        file_path = download_dir / safe_filename
        
        # 🔧 检查文件是否存在且在正确目录中
        if not file_path.exists() or not str(file_path).startswith(str(download_dir)):
            return jsonify({"error": "文件不存在"}), 404
        
        return send_from_directory(download_dir, safe_filename, as_attachment=True)
        
    except Exception as e:
        app.logger.error(f"Download file error: {str(e)}")
        return jsonify({"error": "服务器内部错误"}), 500

@socketio.on('connect')
def handle_connect():
    try:
        session, session_id = get_or_create_session()
        join_room(f"session_{session_id}")
        emit('connected', {'session_id': session_id})
        app.logger.info(f"Client connected: session {session_id[:8]}")
    except Exception as e:
        app.logger.error(f"Socket connect error: {str(e)}")

@socketio.on('disconnect')
def handle_disconnect():
    try:
        session, session_id = get_or_create_session()
        leave_room(f"session_{session_id}")
        app.logger.info(f"Client disconnected: session {session_id[:8]}")
    except Exception as e:
        app.logger.error(f"Socket disconnect error: {str(e)}")

# 🔧 清理任务
def cleanup_old_sessions():
    """清理旧会话和文件"""
    try:
        cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=24)
        to_remove = []
        
        for sid, session in user_sessions.items():
            if session.last_activity < cutoff_time:
                to_remove.append(sid)
                
                # 清理文件
                try:
                    cookies_file = session.get_cookies_path()
                    if cookies_file.exists():
                        cookies_file.unlink()
                    
                    download_dir = session.get_download_dir()
                    if download_dir.exists():
                        # 删除旧文件
                        for file_path in download_dir.iterdir():
                            if file_path.is_file():
                                file_age = time.time() - file_path.stat().st_mtime
                                if file_age > 86400:  # 1天
                                    file_path.unlink()
                        
                        # 如果目录为空则删除
                        if not list(download_dir.iterdir()):
                            download_dir.rmdir()
                            
                except Exception as e:
                    app.logger.error(f"Error cleaning session {sid}: {str(e)}")
        
        for session_id in to_remove:
            del user_sessions[session_id]
        
        if to_remove:
            app.logger.info(f"清理了 {len(to_remove)} 个过期会话")
            
    except Exception as e:
        app.logger.error(f"Cleanup error: {str(e)}")

def start_cleanup_task():
    def cleanup_loop():
        while True:
            time.sleep(3600)  # 每小时清理
            cleanup_old_sessions()
    
    threading.Thread(target=cleanup_loop, daemon=True).start()

# 🔧 错误处理
@app.errorhandler(413)
def request_entity_too_large(error):
    return jsonify({"error": "上传文件过大"}), 413

@app.errorhandler(500)
def internal_error(error):
    app.logger.error(f"Internal error: {str(error)}")
    return jsonify({"error": "服务器内部错误"}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "页面不存在"}), 404

if __name__ == '__main__':
    start_cleanup_task()
    app.logger.info(f"🚀 启动 YouTube 下载器 - {config.DOMAIN}")
    socketio.run(app, debug=config.DEBUG, host=config.HOST, port=config.PORT)