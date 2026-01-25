# 脚本使用指南

本文档说明 Novel-Agent 项目中所有可执行脚本的用途和使用方法。

## 📁 脚本分布

```
novel-agent/
├── START_HERE.bat          # ⭐ 一键启动脚本（推荐）
├── start_all.bat           # 启动后端服务
├── start_workers.bat       # 单独启动 Workers
├── scripts/                # 辅助脚本目录
│   ├── install_dependencies.bat         # Conda 安装依赖
│   ├── install_dependencies_pip.bat     # pip 安装依赖
│   └── quick_install.bat                # 快速安装
└── tools/                  # 工具脚本目录（Python）
    ├── switch_model.py
    └── diagnose_network.py
```

---

## 🚀 启动脚本（根目录）

### START_HERE.bat ⭐

**推荐使用** - 完整的一键启动脚本。

**功能**：
- ✅ 自动检查 Conda 环境
- ✅ 自动检查 Docker Desktop
- ✅ 启动 Redis
- ✅ 启动 Celery Workers（2个窗口）
- ✅ 提示下一步操作

**用法**：
```bash
# 双击运行，或在终端执行
START_HERE.bat
```

**输出**：
- 打开两个新窗口：
  - `Novel-Agent Worker [Text]` - 文本处理
  - `Novel-Agent Worker [RAG+Media]` - 多模态处理
- 显示启动成功提示

**下一步**：
在新终端运行 Streamlit：
```bash
conda activate novel-agent
streamlit run src/gui/app.py
```

---

### start_all.bat

完整的系统启动脚本（基础版）。

**功能**：
- 检查 Docker Desktop
- 启动 Redis
- 调用 `start_workers.bat` 启动 Workers

**用法**：
```bash
start_all.bat
```

**区别**：
- `START_HERE.bat` 更友好，有美化输出和详细检查
- `start_all.bat` 更简洁，适合命令行用户

---

### start_workers.bat

单独启动 Celery Workers。

**功能**：
- 启动 Text Worker（text_queue，并发1）
- 启动 RAG+Media Worker（rag_queue + media_queue，并发2）

**用法**：
```bash
# 确保 Redis 已启动
docker-compose up -d

# 启动 Workers
start_workers.bat
```

**说明**：
- 打开两个新的 CMD 窗口
- 使用 `--pool=solo`（Windows 必需）
- 日志级别：info

**适用场景**：
- Redis 已经在运行
- 需要重启 Workers
- 调试 Worker 问题

---

## 📦 安装脚本（scripts/）

### install_dependencies.bat

使用 Conda 更新环境。

**用法**：
```bash
scripts\install_dependencies.bat
```

**功能**：
- 执行 `conda env update -f environment.yml`
- 根据 `environment.yml` 更新所有依赖
- 显示安装结果

**适用场景**：
- 首次安装依赖
- 更新依赖版本
- Conda 网络正常

**前置条件**：
- Conda 环境已存在
- 网络连接正常

---

### install_dependencies_pip.bat

使用 pip 安装依赖。

**用法**：
```bash
# 先激活环境
conda activate novel-agent

# 运行脚本
scripts\install_dependencies_pip.bat
```

**功能**：
- 使用 pip 分批安装依赖
- 逐包安装，便于定位问题
- 安装后自动验证

**适用场景**：
- Conda 网络有问题
- 需要使用国内 pip 镜像
- 部分依赖安装失败需要重试

**优势**：
- 可以使用 pip 镜像加速
- 出错时更容易定位问题

---

### quick_install.bat

快速批量安装依赖。

**用法**：
```bash
conda activate novel-agent
scripts\quick_install.bat
```

**功能**：
- 一次性安装所有核心依赖
- 安装后验证关键模块

**适用场景**：
- 快速部署
- 网络稳定时批量安装

---

## 🔧 实用命令脚本

### 创建清理脚本

创建 `scripts\clean.bat` 清理临时文件：

```batch
@echo off
echo 清理临时文件...

REM 清理 Python 缓存
for /d /r . %%d in (__pycache__) do @if exist "%%d" rd /s /q "%%d"
del /s /q *.pyc 2>nul

REM 清理测试输出
del /q test_*.png 2>nul
del /q test_*.mp3 2>nul

echo 清理完成！
pause
```

### 创建备份脚本

创建 `scripts\backup_workspace.bat` 备份工作区：

```batch
@echo off
set BACKUP_DIR=backups\%date:~0,4%%date:~5,2%%date:~8,2%_%time:~0,2%%time:~3,2%
mkdir "%BACKUP_DIR%"

echo 正在备份 workspace...
xcopy /E /I /Y workspace "%BACKUP_DIR%\workspace"

echo 正在备份配置...
copy config\settings.yaml "%BACKUP_DIR%\"

echo 备份完成: %BACKUP_DIR%
pause
```

---

## 📊 脚本对比

| 脚本 | 用途 | 速度 | 网络需求 | 推荐度 |
|------|------|------|----------|--------|
| `START_HERE.bat` | 一键启动 | - | 无 | ⭐⭐⭐⭐⭐ |
| `start_all.bat` | 完整启动 | - | 无 | ⭐⭐⭐⭐ |
| `start_workers.bat` | 启动Workers | - | 无 | ⭐⭐⭐⭐ |
| `install_dependencies.bat` | Conda安装 | 慢 | 高 | ⭐⭐⭐ |
| `install_dependencies_pip.bat` | pip安装 | 中 | 中 | ⭐⭐⭐⭐ |
| `quick_install.bat` | 快速安装 | 快 | 中 | ⭐⭐⭐⭐⭐ |

---

## 🎯 使用流程

### 首次使用

```bash
# Step 1: 创建环境
conda env create -f environment.yml

# Step 2: 激活环境
conda activate novel-agent

# Step 3: 配置 API Key
copy .env.example .env
# 编辑 .env 文件

# Step 4: 一键启动
START_HERE.bat

# Step 5: 启动 GUI（新终端）
streamlit run src/gui/app.py
```

### 日常使用

```bash
# 每次使用只需运行
START_HERE.bat

# 然后在新终端
conda activate novel-agent
streamlit run src/gui/app.py
```

### 更新依赖

```bash
# 拉取最新代码
git pull

# 更新依赖（推荐 pip）
conda activate novel-agent
scripts\quick_install.bat

# 重启系统
START_HERE.bat
```

---

## ⚠️ 常见问题

### Q: 双击 START_HERE.bat 闪退

**原因**：Conda 环境未创建或未激活。

**解决**：
```bash
# 创建环境
conda env create -f environment.yml

# 再次运行
START_HERE.bat
```

---

### Q: Workers 启动失败

**原因**：Redis 未启动或端口被占用。

**解决**：
```bash
# 检查 Redis
docker ps

# 重启 Redis
docker-compose restart

# 检查端口
netstat -an | findstr 6379
```

---

### Q: pip 安装速度慢

**解决**：使用国内镜像

```bash
# 临时使用清华镜像
pip install -i https://pypi.tuna.tsinghua.edu.cn/simple <package>

# 永久配置（可选）
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

---

## 🔗 相关文档

- [快速开始指南](../README.md#-quick-start)
- [系统架构](../docs/ARCHITECTURE.md)
- [故障排查](../docs/TROUBLESHOOTING.md)
- [开发指南](../docs/DEVELOPMENT.md)

---

**最后更新**: 2026-01-24  
**维护者**: Novel-Agent Team
