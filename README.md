# 🎬 YouTube 下载器

一个现代化的 Web 版 YouTube 视频下载器，基于 Flask + Socket.IO + yt-dlp 构建，支持多用户会话隔离。

## ✨ 功能特性

- 🌐 **现代化 Web 界面** - 响应式设计，支持移动端
- 🚀 **实时下载进度** - WebSocket 实时通信
- 📝 **实时日志输出** - 详细的下载过程信息
- 📁 **批量下载支持** - 一次性下载多个视频
- 👥 **多用户支持** - 会话隔离，数据安全
- 🔒 **HTTPS 支持** - SSL 证书自动管理
- 🍪 **Cookies 上传** - 支持用户上传认证文件
- 📱 **移动端适配** - 完美支持手机和平板

## 🚀 快速部署

### 方法一：一键自动部署（推荐）

```bash
# 下载并运行部署脚本
wget https://raw.githubusercontent.com/YOUR_USERNAME/youtube-downloader/main/deploy.sh
chmod +x deploy.sh
./deploy.sh
```

### 方法二：手动部署

```bash
# 1. 克隆仓库
git clone https://github.com/YOUR_USERNAME/youtube-downloader.git
cd youtube-downloader

# 2. 配置环境
cp .env.example .env
# 编辑 .env 文件，设置必要的配置

# 3. 启动服务
docker-compose up -d --build
```

## 📋 部署要求

### 系统要求
- **操作系统**: Ubuntu 20.04+ / CentOS 8+
- **内存**: 最低 2GB RAM
- **存储**: 最低 20GB 可用空间
- **网络**: 开放 80, 443 端口

### 软件要求
- Docker 20.10+
- Docker Compose 1.29+
- Git

## 🔧 配置说明

### 环境变量

复制 `.env.example` 为 `.env` 并配置以下变量：

```bash
# 基础配置
SECRET_KEY=your_secret_key_here
DOMAIN=yt.leenf.online
CERTBOT_EMAIL=admin@leenf.online

# 下载配置
MAX_CONCURRENT_DOWNLOADS=3
DOWNLOAD_TIMEOUT=1800
```

### 域名配置

确保您的域名已正确解析到服务器 IP：

```bash
# 检查 DNS 解析
nslookup yt.leenf.online
```

## 📂 项目结构

```
youtube-downloader/
├── app.py                 # Flask 主应用
├── requirements.txt       # Python 依赖
├── Dockerfile            # Docker 镜像配置
├── docker-compose.yml    # 容器编排
├── nginx.conf            # Nginx 配置
├── deploy.sh             # 自动部署脚本
├── templates/            # HTML 模板
│   └── index.html
├── static/               # 静态资源
│   ├── css/
│   └── js/
└── docs/                 # 文档
```

## 🎯 使用方法

1. **访问网站**：https://yt.leenf.online
2. **上传 Cookies**：
   - 使用浏览器扩展 "Get cookies.txt LOCALLY" 导出 cookies.txt
   - 上传到网站
3. **输入链接**：粘贴 YouTube 视频链接
4. **开始下载**：点击下载按钮
5. **下载文件**：完成后可直接下载视频文件

## 🍪 获取 Cookies

### 推荐方法：浏览器扩展

1. 安装 Chrome 扩展：[Get cookies.txt LOCALLY](https://chrome.google.com/webstore/detail/get-cookiestxt-locally/cclelndahbckbenkjhflpdbgdldlbecc)
2. 访问 [YouTube](https://www.youtube.com) 并登录
3. 点击扩展图标 → Export → 保存为 cookies.txt
4. 上传到下载器

### 重要提示

- 必须在完全登录状态下获取
- 文件格式必须是 Netscape 格式
- Cookies 有效期通常为 1-3 个月
- 请勿分享给其他人

## 🛠️ 管理维护

### 常用命令

```bash
cd /opt/youtube-downloader

# 查看服务状态
docker-compose ps

# 查看日志
docker-compose logs -f

# 重启服务
docker-compose restart

# 更新应用
./update.sh
```

### 证书管理

```bash
# 手动续期 SSL 证书
docker-compose run --rm certbot renew

# 强制续期
docker-compose run --rm certbot renew --force-renewal
```

### 数据备份

```bash
# 备份用户数据
tar -czf backup_$(date +%Y%m%d).tar.gz downloads uploads logs

# 清理旧文件
find downloads/ -mtime +7 -type f -delete
```

## 🚨 故障排除

### 常见问题

#### 1. 无法访问网站
```bash
# 检查服务状态
docker-compose ps

# 检查防火墙
sudo ufw status

# 检查 DNS 解析
nslookup yt.leenf.online
```

#### 2. SSL 证书问题
```bash
# 检查证书状态
docker-compose logs certbot

# 手动获取证书
docker-compose run --rm certbot certonly --manual -d yt.leenf.online
```

#### 3. 下载失败
```bash
# 检查应用日志
docker-compose logs youtube-downloader

# 验证 cookies 文件
cat uploads/cookies_*.txt
```

## 📊 性能优化

### 硬件建议

- **小型部署**: 2 CPU, 4GB RAM, 50GB 存储
- **中型部署**: 4 CPU, 8GB RAM, 200GB 存储
- **大型部署**: 8+ CPU, 16GB+ RAM, 1TB+ 存储

### 软件优化

- 定期清理下载文件
- 监控磁盘空间使用
- 配置日志轮转
- 使用 CDN 加速静态资源

## 🔒 安全注意事项

- 定期更新系统和依赖
- 使用强密码和 SSH 密钥
- 配置防火墙限制访问
- 定期备份重要数据
- 监控异常访问

## 📄 许可证

本项目基于 MIT 许可证开源。

## 🤝 贡献

欢迎提交 Issue 和 Pull Request！

### 开发环境设置

```bash
# 克隆仓库
git clone https://github.com/YOUR_USERNAME/youtube-downloader.git
cd youtube-downloader

# 创建虚拟环境
python -m venv venv
source venv/bin/activate  # Linux/Mac
# venv\Scripts\activate   # Windows

# 安装依赖
pip install -r requirements.txt

# 启动开发服务器
python app.py
```

## 📞 支持

- **GitHub Issues**: [提交问题](https://github.com/YOUR_USERNAME/youtube-downloader/issues)
- **文档**: [查看文档](https://github.com/YOUR_USERNAME/youtube-downloader/tree/main/docs)
- **更新日志**: [查看更新](https://github.com/YOUR_USERNAME/youtube-downloader/releases)

---

⭐ 如果这个项目对您有帮助，请给个 Star！