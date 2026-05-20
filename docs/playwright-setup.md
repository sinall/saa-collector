# Playwright 快速启动指南

> 当前测试规范见 `../openspec/specs/collector-testing/spec.md`，完整测试用法见 `testing.md`。

## 安装系统依赖

在运行测试之前，需要先安装 Playwright 所需的系统依赖库。

### 方法1：使用 Playwright 自动安装（推荐）

```bash
cd frontend
npx playwright install-deps chromium
```

这会自动安装 Chromium 浏览器所需的所有系统依赖（需要 sudo 权限）。

### 方法2：手动安装依赖

如果自动安装失败，可以手动安装依赖：

#### Ubuntu/Debian
```bash
sudo apt-get update
sudo apt-get install -y \
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
```

#### CentOS/RHEL/Fedora
```bash
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
```

## 运行测试

### 1. UI 模式（推荐）
```bash
cd frontend
npm run test:e2e:ui
```

### 2. 命令行模式
```bash
cd frontend
npm run test:e2e:chromium
```

### 3. 调试模式
```bash
cd frontend
npm run test:e2e:debug
```

## 验证安装

安装完成后，可以运行以下命令验证：

```bash
cd frontend
npx playwright --version
```

应该显示 Playwright 的版本号。

## 常见问题

### Q: 提示缺少 libasound.so.2
**A:** 这是因为缺少音频库依赖，运行：
```bash
cd frontend
npx playwright install-deps chromium
```

### Q: 浏览器无法启动
**A:** 确保已安装所有系统依赖，或尝试重新安装浏览器：
```bash
cd frontend
npx playwright install chromium
```

### Q: 需要更新文档
**A:** 完整文档请查看 `docs/testing.md`

## 下一步

1. 安装系统依赖
2. 运行测试验证：`npm run test:e2e:ui`
3. 查看 `docs/testing.md` 了解更多用法
