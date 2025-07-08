#!/bin/bash
# YouTube 下载器 - yt.leenf.online 自动部署脚本
# 从 GitHub 仓库部署

set -e

# 配置
DOMAIN="yt.leenf.online"
APP_DIR="/opt/youtube-downloader"
GITHUB_REPO="https://github.com/YOUR_USERNAME/youtube-downloader.git"  # 请替换为您的仓库地址
EMAIL="admin@leenf.online"  # 请替换为您的邮箱

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
PURPLE='\033[0;35m'
NC='\033[0m'

log_info() { echo -e "${GREEN}[INFO]${NC} $1"; }
log_warn() { echo -e "${YELLOW}[WARN]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }
log_step() { echo -e "${BLUE}[STEP]${NC} $1"; }
log_success() { echo -e "${PURPLE}[SUCCESS]${NC} $1"; }

# 检查是否为 root
check_root() {
    if [[ $EUID -eq 0 ]]; then
        log_error "请不要以 root 用户运行此脚本"
        exit 1
    fi
}

# 检查域名解析
check_domain_dns() {
    log_step "检查域名 DNS 解析..."
    
    CURRENT_IP=$(curl -s http://checkip.amazonaws.com/ || curl -s http://ipv4.icanhazip.com/)
    DOMAIN_IP=$(dig +short $DOMAIN @8.8.8.8 | head -n1)
    
    log_info "服务器 IP: $CURRENT_IP"
    log_info "域名解析 IP: $DOMAIN_IP"
    
    if [[ "$CURRENT_IP" != "$DOMAIN_IP" ]]; then
        log_warn "域名解析可能不正确"
        read -p "是否继续部署？(y/N): " continue_deploy
        if [[ $continue_deploy != "y" ]]; then
            exit 1
        fi
    else
        log_success "域名解析正确"
    fi
}

# 安装系统依赖
install_dependencies() {
    log_step "安装系统依赖..."
    
    # 更新包列表
    sudo apt update
    
    # 安装基础依赖
    sudo apt install -y git curl wget docker.io docker-compose
    
    # 添加用户到 docker 组
    sudo usermod -aG docker $USER
    
    # 检查 Docker 版本
    docker --version
    docker-compose --version
    
    log_success "系统依赖安装完成"
}

# 从 GitHub 克隆代码
clone_repository() {
    log_step "从 GitHub 克隆代码..."
    
    # 如果目录已存在，先备份
    if [[ -d "$APP_DIR" ]]; then
        sudo mv "$APP_DIR" "${APP_DIR}_backup_$(date +%Y%m%d_%H%M%S)"
        log_info "已备份现有目录"
    fi
    
    # 创建目录并设置权限
    sudo mkdir -p "$APP_DIR"
    sudo chown $USER:$USER "$APP_DIR"
    
    # 克隆仓库
    git clone "$GITHUB_REPO" "$APP_DIR"
    cd "$APP_DIR"
    
    log_success "代码克隆完成"
}

# 配置环境
setup_environment() {
    log_step "配置环境..."
    
    cd "$APP_DIR"
    
    # 生成随机密钥
    SECRET_KEY=$(openssl rand -hex 32)
    
    # 创建 .env 文件
    cat > .env << EOF
# 生产环境配置
SECRET_KEY=$SECRET_KEY
FLASK_DEBUG=False
DOMAIN=$DOMAIN
HOST=0.0.0.0
PORT=8000

# SSL 配置
CERTBOT_EMAIL=$EMAIL

# 下载配置
MAX_CONCURRENT_DOWNLOADS=3
DOWNLOAD_TIMEOUT=1800
MAX_CONTENT_LENGTH=20971520

# 安全配置
ENABLE_USER_SESSIONS=True
EOF
    
    # 创建必要目录
    mkdir -p {downloads,uploads,logs,ssl/certbot/conf,ssl/certbot/www}
    
    log_success "环境配置完成"
}

# 配置防火墙
setup_firewall() {
    log_step "配置防火墙..."
    
    if command -v ufw &> /dev/null; then
        sudo ufw allow 22/tcp
        sudo ufw allow 80/tcp
        sudo ufw allow 443/tcp
        sudo ufw --force enable
        log_success "UFW 防火墙配置完成"
    else
        log_warn "未检测到 UFW，请手动配置防火墙"
    fi
}

# 启动应用
start_application() {
    log_step "启动应用..."
    
    cd "$APP_DIR"
    
    # 构建并启动服务
    docker-compose up -d --build
    
    # 等待服务启动
    sleep 30
    
    # 检查服务状态
    docker-compose ps
    
    log_success "应用启动完成"
}

# 获取 SSL 证书
setup_ssl() {
    log_step "配置 SSL 证书..."
    
    cd "$APP_DIR"
    
    # 获取 SSL 证书
    docker-compose run --rm certbot certonly \
        --webroot \
        --webroot-path=/var/www/certbot \
        --email "$EMAIL" \
        --agree-tos \
        --no-eff-email \
        -d "$DOMAIN"
    
    if [[ $? -eq 0 ]]; then
        log_success "SSL 证书获取成功"
        
        # 重启 Nginx 以启用 SSL
        docker-compose restart nginx
    else
        log_warn "SSL 证书获取失败，将以 HTTP 模式运行"
    fi
}

# 设置自动更新
setup_auto_update() {
    log_step "设置自动更新..."
    
    cd "$APP_DIR"
    
    # 创建更新脚本
    cat > update.sh << 'EOF'
#!/bin/bash
# 自动更新脚本

cd /opt/youtube-downloader

echo "$(date): 开始更新..." >> logs/update.log

# 停止服务
docker-compose down

# 备份当前数据
tar -czf "backup_$(date +%Y%m%d_%H%M%S).tar.gz" downloads uploads logs

# 更新代码
git pull origin main

# 重新构建并启动
docker-compose build --no-cache
docker-compose up -d

# 清理旧镜像
docker image prune -f

echo "$(date): 更新完成" >> logs/update.log
EOF
    
    chmod +x update.sh
    
    # 设置自动更新 cron 任务（可选）
    read -p "是否设置每周自动更新？(y/N): " setup_cron
    if [[ $setup_cron == "y" ]]; then
        (crontab -l 2>/dev/null; echo "0 2 * * 0 cd $APP_DIR && ./update.sh") | crontab -
        log_success "自动更新已设置（每周日凌晨2点）"
    fi
}

# 设置监控
setup_monitoring() {
    log_step "设置监控..."
    
    cd "$APP_DIR"
    
    # 创建健康检查脚本
    cat > health_check.sh << 'EOF'
#!/bin/bash
# 健康检查脚本

LOG_FILE="logs/health_check.log"

# 检查应用健康状态
if ! curl -f -s "https://yt.leenf.online/api/status" > /dev/null; then
    echo "$(date): 应用健康检查失败，重启服务" >> $LOG_FILE
    docker-compose restart youtube-downloader
fi

# 检查 Nginx
if ! curl -f -s "https://yt.leenf.online/health" > /dev/null; then
    echo "$(date): Nginx 健康检查失败，重启服务" >> $LOG_FILE
    docker-compose restart nginx
fi

# 清理旧文件
find downloads/ -name "*.mp4" -mtime +7 -delete 2>/dev/null
find uploads/ -name "*.txt" -mtime +3 -delete 2>/dev/null

# 日志轮转
find logs/ -name "*.log" -size +100M -exec gzip {} \; 2>/dev/null
EOF
    
    chmod +x health_check.sh
    
    # 设置健康检查 cron
    (crontab -l 2>/dev/null; echo "*/10 * * * * cd $APP_DIR && ./health_check.sh") | crontab -
    
    log_success "监控设置完成"
}

# 显示部署信息
show_deployment_info() {
    clear
    echo "🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉"
    echo "🎊 YouTube 下载器部署成功！"
    echo "🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉"
    echo
    echo "🌐 网站地址: https://$DOMAIN"
    echo "📁 应用目录: $APP_DIR"
    echo "📊 GitHub 仓库: $GITHUB_REPO"
    echo
    echo "🔧 管理命令:"
    echo "   cd $APP_DIR"
    echo "   docker-compose ps              # 查看服务状态"
    echo "   docker-compose logs -f         # 查看日志"
    echo "   docker-compose restart         # 重启服务"
    echo "   ./update.sh                    # 更新应用"
    echo
    echo "📝 重要文件:"
    echo "   $APP_DIR/.env                  # 环境配置"
    echo "   $APP_DIR/logs/                 # 应用日志"
    echo "   $APP_DIR/downloads/            # 下载文件"
    echo
    echo "🚀 下一步:"
    echo "   1. 访问 https://$DOMAIN"
    echo "   2. 上传您的 cookies.txt 文件"
    echo "   3. 开始下载 YouTube 视频"
    echo
    echo "📞 如需帮助:"
    echo "   查看日志: docker-compose logs"
    echo "   重新部署: git pull && docker-compose up -d --build"
    echo
    echo "🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉🎉"
}

# 主函数
main() {
    log_info "开始自动部署 yt.leenf.online YouTube 下载器..."
    
    check_root
    check_domain_dns
    install_dependencies
    clone_repository
    setup_environment
    setup_firewall
    start_application
    setup_ssl
    setup_auto_update
    setup_monitoring
    
    show_deployment_info
}

# 运行主函数
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi