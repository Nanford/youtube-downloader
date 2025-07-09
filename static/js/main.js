// YouTube 下载器前端逻辑 - 支持画质选择版
class YouTubeDownloader {
    constructor() {
        this.socket = null;
        this.isDownloading = false;
        this.autoScroll = true;
        this.sessionId = null;
        this.qualityOptions = {};
        
        this.initElements();
        this.initSocketConnection();
        this.bindEvents();
        this.updateURLCount();
        this.initFileUpload();
        this.initQualitySelection();
    }
    
    // 初始化 DOM 元素引用
    initElements() {
        this.elements = {
            // 输入相关
            urlInput: document.getElementById('url-input'),
            urlCount: document.getElementById('url-count'),
            downloadBtn: document.getElementById('download-btn'),
            clearBtn: document.getElementById('clear-btn'),
            
            // 画质选择相关
            qualitySelect: document.getElementById('quality-select'),
            selectedQuality: document.getElementById('selected-quality'),
            
            // 进度相关
            progressSection: document.getElementById('progress-section'),
            progressText: document.getElementById('progress-text'),
            progressFill: document.getElementById('progress-fill'),
            progressPercentage: document.getElementById('progress-percentage'),
            downloadStatus: document.getElementById('download-status'),
            ffmpegStatus: document.getElementById('ffmpeg-status'),
            
            // 日志相关
            logContainer: document.getElementById('log-container'),
            clearLogBtn: document.getElementById('clear-log-btn'),
            autoScrollBtn: document.getElementById('auto-scroll-btn'),
            
            // 状态相关
            connectionStatus: document.getElementById('connection-status'),
            connectionText: document.getElementById('connection-text'),
            serverStatus: document.getElementById('server-status'),
            sessionIdDisplay: document.getElementById('session-id'),
            
            // 文件上传相关
            cookiesFile: document.getElementById('cookies-file'),
            uploadArea: document.getElementById('upload-area'),
            cookiesStatus: document.getElementById('cookies-status'),
            uploadModal: document.getElementById('upload-modal'),
            uploadProgressFill: document.getElementById('upload-progress-fill'),
            uploadProgressText: document.getElementById('upload-progress-text'),
            
            // 文件列表相关
            filesSection: document.getElementById('files-section'),
            filesList: document.getElementById('files-list'),
            refreshFilesBtn: document.getElementById('refresh-files-btn')
        };
    }
    
    // 初始化画质选择
    initQualitySelection() {
        // 监听画质选择变化
        if (this.elements.qualitySelect) {
            this.elements.qualitySelect.addEventListener('change', (e) => {
                const selectedQuality = e.target.value;
                this.updateSelectedQuality(selectedQuality);
                this.addLogEntry(`🎯 选择画质: ${this.getQualityName(selectedQuality)}`, 'info');
            });
            
            // 设置初始选中的画质
            this.updateSelectedQuality(this.elements.qualitySelect.value);
        }
    }
    
    // 更新选中的画质显示
    updateSelectedQuality(quality) {
        if (this.elements.selectedQuality) {
            const qualityName = this.getQualityName(quality);
            this.elements.selectedQuality.textContent = qualityName;
        }
    }
    
    // 获取画质名称
    getQualityName(quality) {
        const qualityMap = {
            'best': '最高画质',
            '2160p': '4K (2160p)',
            '1440p': '2K (1440p)',
            '1080p': '全高清 (1080p)',
            '720p': '高清 (720p)',
            '480p': '标清 (480p)',
            '360p': '流畅 (360p)'
        };
        return qualityMap[quality] || quality;
    }
    
    // 获取当前选中的画质
    getSelectedQuality() {
        return this.elements.qualitySelect ? this.elements.qualitySelect.value : '1080p';
    }
    
    // 初始化文件上传相关
    initFileUpload() {
        // 拖放事件
        this.elements.uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            this.elements.uploadArea.classList.add('dragover');
        });
        
        this.elements.uploadArea.addEventListener('dragleave', () => {
            this.elements.uploadArea.classList.remove('dragover');
        });
        
        this.elements.uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            this.elements.uploadArea.classList.remove('dragover');
            
            const files = e.dataTransfer.files;
            if (files.length > 0) {
                this.uploadCookiesFile(files[0]);
            }
        });
        
        // 文件选择事件
        this.elements.cookiesFile.addEventListener('change', (e) => {
            const file = e.target.files[0];
            if (file) {
                this.uploadCookiesFile(file);
            }
        });
    }
    
    // 修复后的上传Cookies文件方法
    uploadCookiesFile(file) {
        if (!file) return;
        
        // 检查文件类型和大小
        if (file.type !== 'text/plain' && !file.name.endsWith('.txt')) {
            this.addLogEntry('❌ 只支持上传 .txt 文件', 'error');
            return;
        }
        
        if (file.size > 100 * 1024) { // 100KB 限制
            this.addLogEntry('❌ 文件过大，最大支持 100KB', 'error');
            return;
        }
        
        if (file.size === 0) {
            this.addLogEntry('❌ 文件为空，请选择有效的 cookies 文件', 'error');
            return;
        }
        
        // 显示上传模态框
        this.elements.uploadModal.style.display = 'block';
        this.elements.uploadProgressFill.style.width = '0%';
        this.elements.uploadProgressText.textContent = '准备上传...';
        
        const formData = new FormData();
        formData.append('cookies_file', file);
        
        // 创建XHR请求以监控进度
        const xhr = new XMLHttpRequest();
        xhr.open('POST', '/upload_cookies', true);
        
        // 添加会话ID头部（如果有）
        if (this.sessionId) {
            xhr.setRequestHeader('X-Session-ID', this.sessionId);
        }
        
        // 添加超时设置
        xhr.timeout = 30000; // 30秒超时
        
        // 上传进度
        xhr.upload.onprogress = (e) => {
            if (e.lengthComputable) {
                const percentComplete = Math.round((e.loaded / e.total) * 100);
                this.elements.uploadProgressFill.style.width = percentComplete + '%';
                this.elements.uploadProgressText.textContent = `上传中 ${percentComplete}%...`;
            }
        };
        
        // 请求完成
        xhr.onload = () => {
            this.elements.uploadModal.style.display = 'none';
            
            if (xhr.status === 200) {
                try {
                    const response = JSON.parse(xhr.responseText);
                    
                    if (response.message && !response.error) {
                        this.elements.cookiesStatus.innerHTML = `
                            <span class="status-text success">✅ 已上传</span>
                        `;
                        this.addLogEntry(`🍪 Cookies 上传成功: ${response.message}`, 'success');
                        
                        // 更新会话ID
                        if (response.session_id) {
                            this.sessionId = response.session_id;
                            this.elements.sessionIdDisplay.textContent = response.session_id.substring(0, 8);
                        }
                        
                        // 刷新状态
                        setTimeout(() => this.getStatus(), 1000);
                    } else {
                        this.elements.cookiesStatus.innerHTML = `
                            <span class="status-text error">❌ 上传失败</span>
                        `;
                        this.addLogEntry(`❌ Cookies 上传失败: ${response.error}`, 'error');
                    }
                } catch (e) {
                    this.elements.cookiesStatus.innerHTML = `
                        <span class="status-text error">❌ 解析错误</span>
                    `;
                    this.addLogEntry('❌ 服务器响应解析错误', 'error');
                    console.error('JSON解析错误:', e, '原始响应:', xhr.responseText);
                }
            } else {
                // 处理HTTP错误状态
                let errorMessage = `HTTP ${xhr.status}`;
                try {
                    const errorResponse = JSON.parse(xhr.responseText);
                    if (errorResponse.error) {
                        errorMessage = errorResponse.error;
                    }
                } catch (e) {
                    // 忽略JSON解析错误，使用默认错误消息
                }
                
                this.elements.cookiesStatus.innerHTML = `
                    <span class="status-text error">❌ 上传失败</span>
                `;
                this.addLogEntry(`❌ 上传失败: ${errorMessage}`, 'error');
            }
            
            // 清空文件输入框，允许重复上传同一文件
            this.elements.cookiesFile.value = '';
        };
        
        // 错误处理
        xhr.onerror = () => {
            this.elements.uploadModal.style.display = 'none';
            this.elements.cookiesStatus.innerHTML = `
                <span class="status-text error">❌ 网络错误</span>
            `;
            this.addLogEntry('❌ 网络错误，请检查连接', 'error');
            this.elements.cookiesFile.value = '';
        };
        
        // 超时处理
        xhr.ontimeout = () => {
            this.elements.uploadModal.style.display = 'none';
            this.elements.cookiesStatus.innerHTML = `
                <span class="status-text error">❌ 上传超时</span>
            `;
            this.addLogEntry('❌ 上传超时，请重试', 'error');
            this.elements.cookiesFile.value = '';
        };
        
        // 发送请求
        xhr.send(formData);
        this.addLogEntry(`📤 正在上传 Cookies 文件: ${file.name} (${(file.size/1024).toFixed(1)}KB)`, 'info');
    }
    
    // 初始化 Socket.IO 连接
    initSocketConnection() {
        this.socket = io();
        
        // 连接成功
        this.socket.on('connect', () => {
            this.updateConnectionStatus(true);
            this.addLogEntry('🌐 已连接到服务器', 'success');
        });
        
        // 连接断开
        this.socket.on('disconnect', () => {
            this.updateConnectionStatus(false);
            this.addLogEntry('❌ 与服务器断开连接', 'error');
        });
        
        // 接收日志消息
        this.socket.on('log_message', (data) => {
            this.addLogEntry(data.message);
        });
        
        // 接收进度更新
        this.socket.on('progress_update', (data) => {
            this.updateProgress(data);
        });
        
        // 连接确认
        this.socket.on('connected', (data) => {
            if (data.session_id) {
                this.sessionId = data.session_id;
                this.elements.sessionIdDisplay.textContent = data.session_id.substring(0, 8);
            }
            console.log('Socket 连接确认:', data);
        });
    }
    
    // 绑定事件监听器
    bindEvents() {
        // URL 输入框变化
        this.elements.urlInput.addEventListener('input', () => {
            this.updateURLCount();
        });
        
        // 下载按钮
        this.elements.downloadBtn.addEventListener('click', () => {
            this.startDownload();
        });
        
        // 清空按钮
        this.elements.clearBtn.addEventListener('click', () => {
            this.clearInput();
        });
        
        // 清空日志按钮
        this.elements.clearLogBtn.addEventListener('click', () => {
            this.clearLog();
        });
        
        // 自动滚动切换
        this.elements.autoScrollBtn.addEventListener('click', () => {
            this.toggleAutoScroll();
        });
        
        // 刷新文件列表按钮
        if (this.elements.refreshFilesBtn) {
            this.elements.refreshFilesBtn.addEventListener('click', () => {
                this.refreshFilesList();
            });
        }
        
        // 键盘快捷键
        document.addEventListener('keydown', (e) => {
            if (e.ctrlKey || e.metaKey) {
                switch(e.key) {
                    case 'Enter':
                        e.preventDefault();
                        if (!this.isDownloading) {
                            this.startDownload();
                        }
                        break;
                    case 'l':
                        e.preventDefault();
                        this.clearLog();
                        break;
                }
            }
        });
    }
    
    // 更新连接状态
    updateConnectionStatus(isConnected) {
        const statusDot = this.elements.connectionStatus;
        const statusText = this.elements.connectionText;
        const serverStatus = this.elements.serverStatus;
        
        if (isConnected) {
            statusDot.classList.remove('offline');
            statusDot.classList.add('online');
            statusText.textContent = '已连接';
            serverStatus.textContent = '运行中';
        } else {
            statusDot.classList.remove('online');
            statusDot.classList.add('offline');
            statusText.textContent = '连接断开';
            serverStatus.textContent = '断开连接';
        }
    }
    
    // 更新 URL 计数
    updateURLCount() {
        const text = this.elements.urlInput.value;
        const urls = this.extractURLs(text);
        this.elements.urlCount.textContent = urls.length;
        
        // 更新下载按钮状态
        if (urls.length > 0 && !this.isDownloading) {
            this.elements.downloadBtn.disabled = false;
            this.elements.downloadBtn.classList.remove('disabled');
        } else {
            this.elements.downloadBtn.disabled = true;
            this.elements.downloadBtn.classList.add('disabled');
        }
    }
    
    // 提取有效的 YouTube URLs
    extractURLs(text) {
        const lines = text.split('\n');
        const urls = [];
        
        lines.forEach(line => {
            const trimmed = line.trim();
            if (trimmed && (trimmed.includes('youtube.com') || trimmed.includes('youtu.be'))) {
                urls.push(trimmed);
            }
        });
        
        return urls;
    }
    
    // 开始下载 - 支持画质选择
    async startDownload() {
        if (this.isDownloading) {
            return;
        }
        
        const urls = this.extractURLs(this.elements.urlInput.value);
        const selectedQuality = this.getSelectedQuality();
        
        if (urls.length === 0) {
            this.addLogEntry('⚠️ 请输入有效的 YouTube 链接', 'warning');
            return;
        }
        
        // 设置下载状态
        this.setDownloadingState(true);
        this.showProgressSection();
        this.updateSelectedQuality(selectedQuality);
        
        try {
            const headers = {
                'Content-Type': 'application/json',
            };
            
            // 添加会话ID头部
            if (this.sessionId) {
                headers['X-Session-ID'] = this.sessionId;
            }
            
            const response = await fetch('/api/download', {
                method: 'POST',
                headers: headers,
                body: JSON.stringify({
                    urls: urls,
                    quality: selectedQuality  // 新增画质参数
                })
            });
            
            if (!response.ok) {
                const error = await response.json();
                this.addLogEntry(`❌ 请求失败: ${error.error}`, 'error');
                this.setDownloadingState(false);
                return;
            }
            
            const result = await response.json();
            this.addLogEntry(`📤 ${result.message}`, 'info');
            
            // 更新会话ID
            if (result.session_id) {
                this.sessionId = result.session_id;
                this.elements.sessionIdDisplay.textContent = result.session_id.substring(0, 8);
            }
            
        } catch (error) {
            this.addLogEntry(`❌ 网络错误: ${error.message}`, 'error');
            this.setDownloadingState(false);
        }
    }
    
    // 设置下载状态
    setDownloadingState(downloading) {
        this.isDownloading = downloading;
        
        if (downloading) {
            this.elements.downloadBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> 下载中...';
            this.elements.downloadBtn.classList.add('loading', 'disabled');
            this.elements.downloadBtn.disabled = true;
        } else {
            this.elements.downloadBtn.innerHTML = '<i class="fas fa-download"></i> 开始下载';
            this.elements.downloadBtn.classList.remove('loading', 'disabled');
            this.updateURLCount(); // 重新检查URL状态
        }
    }
    
    // 显示进度区域
    showProgressSection() {
        this.elements.progressSection.style.display = 'block';
        this.elements.progressSection.scrollIntoView({ behavior: 'smooth' });
    }
    
    // 更新进度
    updateProgress(data) {
        const { current, total, percentage, status } = data;
        
        // 更新进度文本
        this.elements.progressText.textContent = `${current}/${total}`;
        this.elements.progressPercentage.textContent = `${percentage}%`;
        
        // 更新进度条
        this.elements.progressFill.style.width = `${percentage}%`;
        
        // 更新状态
        const statusMap = {
            'idle': '准备中',
            'starting': '启动中',
            'downloading': '下载中',
            'completed': '已完成'
        };
        
        this.elements.downloadStatus.textContent = statusMap[status] || status;
        
        // 如果下载完成，重置状态并刷新文件列表
        if (status === 'completed') {
            setTimeout(() => {
                this.setDownloadingState(false);
                this.refreshFilesList();
            }, 2000);
        }
    }
    
    // 刷新文件列表
    async refreshFilesList() {
        if (!this.sessionId) return;
        
        try {
            const response = await fetch(`/downloads/${this.sessionId}`);
            if (response.ok) {
                const data = await response.json();
                this.updateFilesList(data.files);
            }
        } catch (error) {
            console.error('刷新文件列表失败:', error);
        }
    }
    
    // 更新文件列表显示
    updateFilesList(files) {
        if (!files || files.length === 0) {
            this.elements.filesSection.style.display = 'none';
            return;
        }
        
        this.elements.filesSection.style.display = 'block';
        this.elements.filesList.innerHTML = '';
        
        files.forEach(file => {
            const fileItem = document.createElement('div');
            fileItem.className = 'file-item';
            fileItem.innerHTML = `
                <div class="file-info">
                    <span class="file-name">${file.name}</span>
                    <span class="file-size">${this.formatFileSize(file.size)}</span>
                </div>
                <a href="${file.url}" class="btn btn-small" download>
                    <i class="fas fa-download"></i> 下载
                </a>
            `;
            this.elements.filesList.appendChild(fileItem);
        });
    }
    
    // 格式化文件大小
    formatFileSize(bytes) {
        if (bytes === 0) return '0 B';
        const k = 1024;
        const sizes = ['B', 'KB', 'MB', 'GB'];
        const i = Math.floor(Math.log(bytes) / Math.log(k));
        return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
    }
    
    // 添加日志条目
    addLogEntry(message, type = 'info') {
        // 如果是欢迎消息，先清除
        const welcome = this.elements.logContainer.querySelector('.log-welcome');
        if (welcome) {
            welcome.remove();
        }
        
        const logEntry = document.createElement('div');
        logEntry.className = `log-entry ${type}`;
        
        // 添加时间戳
        const timestamp = new Date().toLocaleTimeString();
        logEntry.innerHTML = `<span class="log-time">[${timestamp}]</span> ${message}`;
        
        this.elements.logContainer.appendChild(logEntry);
        
        // 自动滚动到底部
        if (this.autoScroll) {
            this.scrollLogToBottom();
        }
        
        // 限制日志条目数量（保持性能）
        const maxEntries = 100;
        const entries = this.elements.logContainer.querySelectorAll('.log-entry');
        if (entries.length > maxEntries) {
            entries[0].remove();
        }
    }
    
    // 滚动日志到底部
    scrollLogToBottom() {
        this.elements.logContainer.scrollTop = this.elements.logContainer.scrollHeight;
    }
    
    // 清空输入
    clearInput() {
        this.elements.urlInput.value = '';
        this.updateURLCount();
        this.addLogEntry('🗑️ 已清空输入框', 'info');
    }
    
    // 清空日志
    clearLog() {
        this.elements.logContainer.innerHTML = `
            <div class="log-welcome">
                <i class="fas fa-info-circle"></i>
                日志已清空，准备开始新的下载任务。
                <br><br>
                <strong>提示：</strong>现在可以选择画质进行下载，从360p到4K任你选择！
            </div>
        `;
    }
    
    // 切换自动滚动
    toggleAutoScroll() {
        this.autoScroll = !this.autoScroll;
        
        if (this.autoScroll) {
            this.elements.autoScrollBtn.classList.add('active');
            this.elements.autoScrollBtn.innerHTML = '<i class="fas fa-arrow-down"></i> 自动滚动';
            this.scrollLogToBottom();
        } else {
            this.elements.autoScrollBtn.classList.remove('active');
            this.elements.autoScrollBtn.innerHTML = '<i class="fas fa-pause"></i> 已暂停';
        }
    }
    
    // 获取应用状态
    async getStatus() {
        try {
            const headers = {};
            if (this.sessionId) {
                headers['X-Session-ID'] = this.sessionId;
            }
            
            const response = await fetch('/api/status', { headers });
            const status = await response.json();
            
            // 更新会话ID
            if (status.session_id) {
                this.sessionId = status.session_id;
                this.elements.sessionIdDisplay.textContent = status.session_id.substring(0, 8);
            }
            
            // 保存画质选项
            if (status.quality_options) {
                this.qualityOptions = status.quality_options;
            }
            
            // 更新Cookies状态
            if (status.cookies) {
                if (status.cookies.exists) {
                    this.elements.cookiesStatus.innerHTML = `
                        <span class="status-text ${status.cookies.should_update ? 'warning' : 'success'}">
                            ${status.cookies.status_message}
                        </span>
                    `;
                } else {
                    this.elements.cookiesStatus.innerHTML = `
                        <span class="status-text error">❌ 未上传</span>
                    `;
                }
            }
            
            // 更新FFmpeg状态
            if (this.elements.ffmpegStatus) {
                this.elements.ffmpegStatus.textContent = status.ffmpeg_available ? '✅ 可用' : '❌ 不可用';
            }
            
            // 如果正在下载，更新UI状态
            if (status.is_downloading) {
                this.setDownloadingState(true);
                this.showProgressSection();
                this.updateProgress(status.progress);
            }
            
            // 刷新文件列表
            this.refreshFilesList();
            
        } catch (error) {
            console.error('获取状态失败:', error);
        }
    }
}

// DOM 加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 YouTube 下载器初始化中...');
    
    // 创建应用实例
    window.downloader = new YouTubeDownloader();
    
    // 获取初始状态
    window.downloader.getStatus();
    
    // 定期更新状态（可选）
    setInterval(() => {
        if (!window.downloader.isDownloading) {
            window.downloader.getStatus();
        }
    }, 30000); // 每30秒更新一次
    
    // 添加全局错误处理
    window.addEventListener('error', (e) => {
        console.error('全局错误:', e.error);
        if (window.downloader) {
            window.downloader.addLogEntry(`❌ 应用错误: ${e.error.message}`, 'error');
        }
    });
    
    // 处理页面刷新时的状态恢复
    window.addEventListener('beforeunload', () => {
        // 可以在这里保存一些状态到localStorage
        console.log('页面即将刷新/关闭');
    });
    
    console.log('✅ YouTube 下载器初始化完成');
});

// 显示和隐藏关于模态框
function showAbout() {
    document.getElementById('about-modal').style.display = 'block';
}

function hideAbout() {
    document.getElementById('about-modal').style.display = 'none';
}

// 添加模态框外部点击关闭功能
document.addEventListener('click', (e) => {
    if (e.target.classList.contains('modal')) {
        e.target.style.display = 'none';
    }
});

// 模态框点击关闭
document.addEventListener('DOMContentLoaded', () => {
    // 点击模态框外部关闭
    document.getElementById('about-modal').addEventListener('click', (e) => {
        if (e.target.id === 'about-modal') {
            hideAbout();
        }
    });
});