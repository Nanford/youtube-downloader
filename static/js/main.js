// YouTube 下载器前端逻辑
class YouTubeDownloader {
    constructor() {
        this.socket = null;
        this.isDownloading = false;
        this.autoScroll = true;
        
        this.initElements();
        this.initSocketConnection();
        this.bindEvents();
        this.updateURLCount();
    }
    
    // 初始化 DOM 元素引用
    initElements() {
        this.elements = {
            // 输入相关
            urlInput: document.getElementById('url-input'),
            urlCount: document.getElementById('url-count'),
            downloadBtn: document.getElementById('download-btn'),
            clearBtn: document.getElementById('clear-btn'),
            
            // 进度相关
            progressSection: document.querySelector('.progress-section'),
            progressText: document.getElementById('progress-text'),
            progressFill: document.getElementById('progress-fill'),
            progressPercentage: document.getElementById('progress-percentage'),
            downloadStatus: document.getElementById('download-status'),
            
            // 日志相关
            logContainer: document.getElementById('log-container'),
            clearLogBtn: document.getElementById('clear-log-btn'),
            autoScrollBtn: document.getElementById('auto-scroll-btn'),
            
            // 状态相关
            connectionStatus: document.getElementById('connection-status'),
            connectionText: document.getElementById('connection-text'),
            serverStatus: document.getElementById('server-status'),
            downloadDir: document.getElementById('download-dir')
        };
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
            console.log('Socket 连接确认:', data.message);
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
    
    // 开始下载
    async startDownload() {
        if (this.isDownloading) {
            return;
        }
        
        const urls = this.extractURLs(this.elements.urlInput.value);
        
        if (urls.length === 0) {
            this.addLogEntry('⚠️ 请输入有效的 YouTube 链接', 'warning');
            return;
        }
        
        // 设置下载状态
        this.setDownloadingState(true);
        this.showProgressSection();
        
        try {
            const response = await fetch('/api/download', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    urls: urls
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
            
        } catch (error) {
            this.addLogEntry(`❌ 网络错误: ${error.message}`, 'error');
            this.setDownloadingState(false);
        }
    }
    
    // 设置下载状态
    setDownloadingState(downloading) {
        this.isDownloading = downloading;
        
        if (downloading) {
            this.elements.downloadBtn.textContent = '下载中...';
            this.elements.downloadBtn.classList.add('loading', 'disabled');
            this.elements.downloadBtn.disabled = true;
        } else {
            this.elements.downloadBtn.innerHTML = '<i class="fas fa-download"></i> 开始下载';
            this.elements.downloadBtn.classList.remove('loading', 'disabled');
            this.elements.downloadBtn.disabled = false;
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
        
        // 如果下载完成，重置状态
        if (status === 'completed') {
            setTimeout(() => {
                this.setDownloadingState(false);
            }, 2000);
        }
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
            const response = await fetch('/api/status');
            const status = await response.json();
            
            // 更新下载目录显示
            this.elements.downloadDir.textContent = status.download_dir;
            
            // 如果正在下载，更新UI状态
            if (status.is_downloading) {
                this.setDownloadingState(true);
                this.showProgressSection();
                this.updateProgress(status.progress);
            }
            
        } catch (error) {
            console.error('获取状态失败:', error);
        }
    }
}

// 工具函数：节流
function throttle(func, wait) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

// 工具函数：防抖
function debounce(func, wait, immediate) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            timeout = null;
            if (!immediate) func(...args);
        };
        const callNow = immediate && !timeout;
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
        if (callNow) func(...args);
    };
}

// DOM 加载完成后初始化应用
document.addEventListener('DOMContentLoaded', () => {
    console.log('🚀 YouTube 下载器初始化中...');
    
    // 创建应用实例
    window.downloader = new YouTubeDownloader();
    
    // 获取初始状态
    window.downloader.getStatus();
    
    // 添加全局错误处理
    window.addEventListener('error', (e) => {
        console.error('全局错误:', e.error);
        if (window.downloader) {
            window.downloader.addLogEntry(`❌ 应用错误: ${e.error.message}`, 'error');
        }
    });
    
    console.log('✅ YouTube 下载器初始化完成');
});