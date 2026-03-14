#!/bin/bash

echo "=========================================="
echo "  Playwright 系统依赖安装脚本"
echo "=========================================="
echo ""

# 检查是否在 frontend 目录
if [ ! -f "package.json" ]; then
    echo "❌ 请在 frontend 目录下运行此脚本"
    echo "   cd frontend && ../scripts/install-playwright-deps.sh"
    exit 1
fi

echo "📦 开始安装 Playwright Chromium 所需的系统依赖..."
echo ""

# 检测系统类型
if [ -f /etc/debian_version ]; then
    echo "检测到 Debian/Ubuntu 系统"
    echo ""
    
    # 安装依赖
    sudo apt-get update && sudo apt-get install -y \
        libasound2 \
        libatk-bridge2.0-0 \
        libatk1.0-0 \
        libatspi2.0-0 \
        libcups2 \
        libdbus-1-3 \
        libdrm2 \
        libgbm1 \
        libgtk-3-0 \
        libnspr4 \
        libnss3 \
        libwayland-client0 \
        libxcomposite1 \
        libxdamage1 \
        libxfixes3 \
        libxkbcommon0 \
        libxrandr2 \
        xdg-utils
    
elif [ -f /etc/redhat-release ]; then
    echo "检测到 RedHat/CentOS/Fedora 系统"
    echo ""
    
    sudo yum install -y \
        alsa-lib \
        atk \
        cups-libs \
        gtk3 \
        ipa-gothic-fonts \
        libXcomposite \
        libXcursor \
        libXdamage \
        libXext \
        libXi \
        libXrandr \
        libXScrnSaver \
        libXtst \
        pango \
        xorg-x11-fonts-100dpi \
        xorg-x11-fonts-75dpi \
        xorg-x11-fonts-cyrillic \
        xorg-x11-fonts-misc \
        xorg-x11-fonts-Type1 \
        xorg-x11-utils
else
    echo "⚠️  未检测到支持的系统，尝试使用 Playwright 自动安装..."
    npx playwright install-deps chromium
fi

echo ""
echo "✅ 系统依赖安装完成！"
echo ""
echo "=========================================="
echo "  接下来可以运行："
echo "=========================================="
echo ""
echo "1. UI 模式测试（推荐）："
echo "   npm run test:e2e:ui"
echo ""
echo "2. 命令行测试："
echo "   npm run test:e2e:chromium"
echo ""
echo "3. 查看测试报告："
echo "   npm run test:e2e:report"
echo ""
echo "=========================================="
