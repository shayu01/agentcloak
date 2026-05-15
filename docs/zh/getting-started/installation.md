# 安装指南

本指南涵盖在所有支持平台上安装 agentcloak 及其依赖。

## 系统要求

- **Python 3.12+**（同时支持 3.13）
- **pip** 或 **uv** 包管理器
- Linux（x64/arm64）、macOS（x64/arm64）或 Windows（x64）

## 基础安装

```bash
pip install agentcloak
```

一条命令安装全部组件：

- `agentcloak` 和 `cloak` CLI 命令
- `agentcloak-mcp` MCP server（23 个工具）
- CloakBrowser 隐身浏览器后端（默认）
- httpcloak TLS 指纹代理（用于 `cloak fetch`）
- 后台 daemon（aiohttp）

CloakBrowser 在首次使用时自动下载补丁版 Chromium 二进制文件（约 200 MB，缓存在 `~/.cloakbrowser/`）。无需手动安装浏览器。

## 可选扩展

| 扩展 | 功能 | 使用场景 |
|------|------|---------|
| `discovery` | [zeroconf](https://github.com/python-zeroconf/python-zeroconf) mDNS | 远程 bridge 自动发现 daemon |

```bash
pip install agentcloak[discovery]
```

## 验证安装

运行内置诊断工具：

```bash
cloak doctor
```

诊断内容包括：

- Python 版本
- CloakBrowser 可用性和二进制文件状态
- Daemon 连通性
- 配置检查

全新安装后的预期输出：

```json
{"ok": true, "data": {"checks": [
  {"name": "python_version", "ok": true, "value": "3.12.x"},
  {"name": "cloakbrowser", "ok": true, "hint": "CloakBrowser available -- default backend"},
  {"name": "default_tier", "value": "auto -> cloak"}
]}}
```

## 系统依赖

### Xvfb（仅限 Linux 服务器）

CloakBrowser 以有头模式运行，因为反爬系统会检测无头浏览器。在没有显示器的 Linux 服务器上，agentcloak 会自动启动 Xvfb（虚拟帧缓冲区）。安装方式：

```bash
# Debian / Ubuntu
sudo apt-get install -y xvfb

# RHEL / Fedora
sudo dnf install -y xorg-x11-server-Xvfb
```

桌面 Linux、macOS 和 Windows 无需额外系统依赖。

### Playwright 系统库

CloakBrowser 底层使用 Playwright。如果遇到共享库缺失错误，安装 Playwright 的系统依赖：

```bash
python -m playwright install-deps chromium
```

## 使用 uv 安装

如果你偏好使用 [uv](https://github.com/astral-sh/uv)：

```bash
uv pip install agentcloak
```

免安装直接运行：

```bash
uvx agentcloak doctor
```

## 开发环境安装

完整的开发环境配置参见 [CONTRIBUTING.md](../../../CONTRIBUTING.md)。

```bash
git clone https://github.com/shayuc137/agentcloak.git
cd agentcloak
pip install -e ".[dev,mcp,stealth]"
```

## 配置

安装后 agentcloak 无需任何配置即可使用。daemon 在首次命令时自动启动。

如需自定义行为，参见[配置参考](../reference/config.md)。

## 后续步骤

- [快速开始教程](./quickstart.md) -- 学习观察-操作循环
- [浏览器后端](../guides/backends.md) -- 根据场景选择合适的后端
- [MCP 配置](../guides/mcp-setup.md) -- 从 MCP 原生客户端连接
