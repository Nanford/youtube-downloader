#!/usr/bin/env python3
"""
YouTube 下载器 - 生产版
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
    PORT = int(os.getenv('PORT', 8090))
    
    # 目录配置
    BASE_DIR = Path(__file__).parent
    DOWNLOAD_DIR = Path(os.getenv('DOWNLOAD_DIR', BASE_DIR / 'downloads'))
    UPLOAD_DIR = Path(os.getenv('UPLOAD_DIR', BASE_DIR / 'uploads'))
    LOG_DIR = Path(os.getenv('LOG_DIR', BASE_DIR / 'logs'))
    
    # 文件配置
    MAX_CONTENT_LENGTH = int(os.getenv('MAX_CONTENT_LENGTH', 20 * 1024 * 1024))
    MAX_CONCURRENT_DOWNLOADS = int(os.getenv('MAX_CONCURRENT_DOWNLOADS', 3))
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
if not config.DEBUG:
    file_handler = logging.FileHandler(config.LOG_DIR / 'app.log')
    file_handler.setFormatter(logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s [in %(pathname)s:%(lineno)d]'
    ))
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    app.logger.setLevel(logging.INFO)

# 用户会话类
class UserSession:
    def __init__(self, session_id):
        self.session_id = session_id
        self.created_at = datetime.datetime.now()
        self.download_manager = None
        
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
    session_id = request.headers.get('X-Session-ID') or str(uuid.uuid4())
    
    if session_id not in user_sessions:
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
        """验证 cookies 文件"""
        try:
            lines = content.strip().split('\n')
            valid_lines = [line for line in lines if line.strip() and not line.startswith('#')]
            
            if len(valid_lines) < 5:
                return False, "Cookies 文件内容过少"
            
            # 检查关键 cookies
            important_cookies = ['VISITOR_INFO1_LIVE', 'YSC', 'CONSENT']
            found = sum(1 for cookie in important_cookies if cookie in content)
            
            if found < 2:
                return False, "缺少关键 YouTube cookies"
            
            return True, "Cookies 文件格式正确"
        except Exception as e:
            return False, f"验证失败: {str(e)}"
    
    def save_cookies(self, content):
        """保存 cookies 文件"""
        is_valid, message = self.validate_cookies_file(content)
        if not is_valid:
            return False, message
        
        try:
            with open(self.cookies_file, 'w', encoding='utf-8') as f:
                f.write(content)
            return True, "Cookies 保存成功"
        except Exception as e:
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
    
    def log_message(self, message):
        app.logger.info(f"[{self.session_id}] {message}")
        socketio.emit('log_message', {'message': message}, room=self.room)
    
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
        """获取下载选项"""
        has_ffmpeg = self.check_ffmpeg()
        
        base_opts = [
            "-o", "%(title)s.%(ext)s",
            "--embed-metadata",
            "--no-warnings",
            "--user-agent", "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36",
            "--referer", "https://www.youtube.com/",
            "--extractor-retries", "3",
            "--fragment-retries", "3",
            "--retry-sleep", "exp=1:5",
            "--socket-timeout", "30",
        ]
        
        if has_ffmpeg:
            base_opts.extend(["-f", "bv*+ba/b"])
            self.log_message("🎬 使用 FFmpeg 高画质模式")
        else:
            base_opts.extend(["-f", "best[ext=mp4]/best"])
            self.log_message("📱 使用兼容模式")
        
        # 添加 cookies
        if self.cookies_manager.check_cookies_exist():
            base_opts.extend(["--cookies", str(self.cookies_manager.cookies_file)])
            age = self.cookies_manager.get_cookies_age_days()
            self.log_message(f"🍪 使用 cookies 文件（{age}天前上传）")
        
        return base_opts
    
    def download_video(self, url, download_dir):
        """下载单个视频"""
        self.log_message(f"🎬 开始下载: {url}")
        
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
            
            while True:
                output = process.stdout.readline()
                if output == '' and process.poll() is not None:
                    break
                if output:
                    clean_output = output.strip()
                    if clean_output and not clean_output.startswith('['):
                        self.log_message(f"📥 {clean_output}")
            
            if process.returncode == 0:
                self.log_message(f"✅ 下载完成: {url}")
                return True
            else:
                error = process.stderr.read().strip()
                if "Sign in to confirm" in error:
                    self.log_message("🤖 检测到反机器人保护，请更新 cookies")
                else:
                    self.log_message(f"❌ 下载失败: {error[:200]}...")
                return False
                
        except Exception as e:
            self.log_message(f"❌ 下载异常: {str(e)}")
            return False
    
    def batch_download(self, urls):
        """批量下载"""
        if self.is_downloading:
            self.log_message("⚠️ 正在下载中，请等待完成...")
            return
        
        self.is_downloading = True
        session = user_sessions[self.session_id]
        download_dir = session.get_download_dir()
        
        self.log_message(f"🚀 开始批量下载，共 {len(urls)} 个视频")
        self.update_progress(0, len(urls), "starting")
        
        success_count = 0
        for i, url in enumerate(urls, 1):
            self.update_progress(i-1, len(urls), "downloading")
            self.log_message(f"📋 [{i}/{len(urls)}] 处理: {url}")
            
            if self.download_video(url, download_dir):
                success_count += 1
            
            time.sleep(1)
        
        self.update_progress(len(urls), len(urls), "completed")
        self.log_message(f"🎉 批量下载完成！成功: {success_count}/{len(urls)}")
        self.is_downloading = False

# Flask 路由
@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload_cookies', methods=['POST'])
def upload_cookies():
    """上传 cookies 文件"""
    session, session_id = get_or_create_session()
    
    if 'cookies_file' not in request.files:
        return jsonify({"error": "没有文件上传"}), 400
    
    file = request.files['cookies_file']
    if file.filename == '':
        return jsonify({"error": "没有选择文件"}), 400
    
    try:
        content = file.read().decode('utf-8')
        cookies_manager = CookiesManager(session_id)
        success, message = cookies_manager.save_cookies(content)
        
        if success:
            return jsonify({"message": message, "session_id": session_id})
        else:
            return jsonify({"error": message}), 400
    except Exception as e:
        return jsonify({"error": f"文件读取失败: {str(e)}"}), 400

@app.route('/api/download', methods=['POST'])
def api_download():
    """下载 API"""
    session, session_id = get_or_create_session()
    
    if not session.download_manager:
        session.download_manager = DownloadManager(session_id)
    
    data = request.get_json()
    urls = data.get('urls', [])
    
    if not urls:
        return jsonify({"error": "没有提供有效的 URL"}), 400
    
    valid_urls = [url.strip() for url in urls 
                  if url.strip() and ('youtube.com' in url or 'youtu.be' in url)]
    
    if not valid_urls:
        return jsonify({"error": "没有找到有效的 YouTube URL"}), 400
    
    threading.Thread(
        target=session.download_manager.batch_download,
        args=(valid_urls,),
        daemon=True
    ).start()
    
    return jsonify({"message": f"开始下载 {len(valid_urls)} 个视频", "session_id": session_id})

@app.route('/api/status')
def api_status():
    """获取状态"""
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
        "ffmpeg_available": session.download_manager.check_ffmpeg()
    })

@app.route('/downloads/<session_id>')
def download_files(session_id):
    """下载文件列表"""
    if session_id not in user_sessions:
        return jsonify({"error": "会话不存在"}), 404
    
    session = user_sessions[session_id]
    download_dir = session.get_download_dir()
    
    files = []
    for file_path in download_dir.iterdir():
        if file_path.is_file():
            files.append({
                "name": file_path.name,
                "size": file_path.stat().st_size,
                "url": f"/download_file/{session_id}/{file_path.name}"
            })
    
    return jsonify({"files": files})

@app.route('/download_file/<session_id>/<filename>')
def download_file(session_id, filename):
    """下载单个文件"""
    if session_id not in user_sessions:
        return jsonify({"error": "会话不存在"}), 404
    
    session = user_sessions[session_id]
    download_dir = session.get_download_dir()
    
    return send_from_directory(download_dir, filename, as_attachment=True)

@socketio.on('connect')
def handle_connect():
    session, session_id = get_or_create_session()
    join_room(f"session_{session_id}")
    emit('connected', {'session_id': session_id})

@socketio.on('disconnect')
def handle_disconnect():
    session, session_id = get_or_create_session()
    leave_room(f"session_{session_id}")

# 清理任务
def cleanup_old_sessions():
    """清理旧会话"""
    cutoff_time = datetime.datetime.now() - datetime.timedelta(hours=24)
    to_remove = [sid for sid, session in user_sessions.items() 
                 if session.created_at < cutoff_time]
    
    for session_id in to_remove:
        del user_sessions[session_id]
    
    app.logger.info(f"清理了 {len(to_remove)} 个过期会话")

def start_cleanup_task():
    def cleanup_loop():
        while True:
            time.sleep(3600)  # 每小时清理
            cleanup_old_sessions()
    
    threading.Thread(target=cleanup_loop, daemon=True).start()

if __name__ == '__main__':
    start_cleanup_task()
    app.logger.info(f"🚀 启动 YouTube 下载器 - {config.DOMAIN}")
    socketio.run(app, debug=config.DEBUG, host=config.HOST, port=config.PORT)