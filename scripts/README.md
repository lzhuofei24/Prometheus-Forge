# Scripts 脚本目录

本目录包含 Novel-Agent 的辅助脚本，包括安装脚本（.bat）和批处理脚本（.py）。

## 📦 安装脚本

### install_dependencies.bat

使用 Conda 更新环境依赖。

**用法**：
```bash
cd d:\project\novel-agent
scripts\install_dependencies.bat
```

**说明**：
- 执行 `conda env update -f environment.yml`
- 适用于已有 conda 环境的情况
- 如果环境不存在，请先创建环境

**前置条件**：
- Conda 已安装
- 已创建 `novel-agent` 环境

---

### install_dependencies_pip.bat

使用 pip 安装所有依赖。

**用法**：
```bash
# 确保已激活 conda 环境
conda activate novel-agent

# 运行脚本
scripts\install_dependencies_pip.bat
```

**说明**：
- 逐个安装核心依赖包
- 适用于 conda 网络有问题的情况
- 安装完成后会进行验证

**包含的依赖**：
- langchain, langgraph, chromadb
- openai, pydantic, pyyaml
- celery, redis, flower
- sentence-transformers, edge-tts
- requests, pillow

---

### quick_install.bat

快速安装所有依赖（合并版）。

**用法**：
```bash
conda activate novel-agent
scripts\quick_install.bat
```

**说明**：
- 使用 pip 一次性安装所有依赖
- 最快的安装方式
- 安装后自动验证关键模块

---

## 🚀 启动脚本

**注意**：启动脚本位于项目根目录，不在此文件夹中。

### 根目录启动脚本

| 脚本 | 说明 | 用途 |
|------|------|------|
| `start_all.bat` | 完整启动脚本 | 自动启动 Redis + Celery Workers |
| `start_workers.bat` | Worker 启动脚本 | 单独启动 Celery Workers |

**快速启动**：
```bash
# 完整启动（Redis + Workers）
start_all.bat

# 然后在新终端启动 Streamlit
streamlit run src/gui/app.py
```

---

## 🗑️ 已废弃脚本

以下脚本已从项目中移除：

- ~~`setup_hf_mirror.bat`~~ - HuggingFace 镜像配置（已放弃本地生图）

---

## 💡 使用建议

### 首次安装

1. **使用 Conda（推荐）**：
   ```bash
   conda env create -f environment.yml
   conda activate novel-agent
   ```

2. **如果 Conda 网络有问题**：
   ```bash
   conda create -n novel-agent python=3.10
   conda activate novel-agent
   scripts\quick_install.bat
   ```

### 更新依赖

```bash
# 方式 1: 使用 Conda
scripts\install_dependencies.bat

# 方式 2: 使用 pip
conda activate novel-agent
scripts\install_dependencies_pip.bat
```

### 启动系统

```bash
# 方式 1: 一键启动（推荐）
start_all.bat

# 方式 2: 分步启动
docker-compose up -d           # 启动 Redis
start_workers.bat               # 启动 Workers
streamlit run src/gui/app.py   # 启动 GUI
```

---

## 📝 脚本维护

### 添加新脚本

1. 在 `scripts/` 目录创建新的 `.bat` 文件
2. 添加清晰的注释和 echo 输出
3. 更新本 README.md

### 脚本模板

```batch
@echo off
echo ========================================
echo 脚本名称和用途
echo ========================================
echo.

REM 检查前置条件
REM ...

echo 正在执行主要操作...
REM 执行命令

if %errorlevel% neq 0 (
    echo 错误: 操作失败
    pause
    exit /b 1
)

echo.
echo ========================================
echo 执行完成！
echo ========================================
echo.
pause
```

---

## 🐍 Python 批处理脚本

### generate_global_files.py

生成全局设定文件（人物、世界观）。

**用法**：
```bash
python scripts\generate_global_files.py
```

**功能**：
- 从原著文本提取人物设定
- 生成 `bios.json`
- 生成 `world.md`

---

### generate_outlines.py

批量生成章节大纲。

**用法**：
```bash
python scripts\generate_outlines.py
```

**说明**：
- 为指定范围的章节批量生成大纲
- 跳过已存在的章节

---

### process_first_10_chapters.py

处理前 10 章。

**用法**：
```bash
python scripts\process_first_10_chapters.py
```

**功能**：
- 批量生成前 10 章的完整内容
- 包括大纲、正文、审稿、多模态

---

### process_remaining_chapters.py

处理剩余章节。

**用法**：
```bash
python scripts\process_remaining_chapters.py
```

**说明**：
- 处理第 11 章及以后的章节
- 自动跳过已完成的章节

---

### reprocess_failed_chapters.py

重新处理失败的章节。

**用法**：
```bash
python scripts\reprocess_failed_chapters.py
```

**功能**：
- 检测失败或不完整的章节
- 重新生成内容

---

### check_missing_chapters.py

检查缺失的章节。

**用法**：
```bash
python scripts\check_missing_chapters.py
```

**输出**：
- 列出所有缺失的章节编号
- 显示已完成的章节统计

---

### test_monitor_pending.py

在「Architect IN (Pending) = 1」场景下检查监控接口是否正确：对比 Redis 中 `architect_pending` 长度与 `GET /monitor/resources` 返回的 `stats.queues.architect_pending`。

**用法**（需先启动 Backend，如通过 `start_all_tabs.bat`）：
```bash
# 仅核对当前 Redis 与接口返回值是否一致
python scripts\test_monitor_pending.py

# 先往 architect_pending 塞 1 条，再请求接口，验证返回 1
python scripts\test_monitor_pending.py --seed

# 还原：从 architect_pending 弹出一条（配合 --seed 使用）
python scripts\test_monitor_pending.py --cleanup
```

**可选参数**：`--api-base http://127.0.0.1:8000`、`--timeout 10`。

---

### test_controller_heartbeat.py

检查 Controller 是否在线：看 Redis 心跳键 `system:controller:heartbeat` 及 `GET /monitor/resources` 的 `stats.controller.online`。

**用法**：
```bash
python scripts\test_controller_heartbeat.py
python scripts\test_controller_heartbeat.py --write-heartbeat   # 仅写入一次心跳用于调试
```

---

### seed_prompts.py

将 `resources/default_prompts.json` 中的默认提示词写入数据库 `prompt_templates` 表。提示词以 SQL 为准，不再依赖本地 YAML 或 Git。已存在的 `key` 会跳过，保留本地修改。

**用法**：
```bash
python scripts\seed_prompts.py
```

**说明**：
- 首次部署或表结构升级后执行，用于初始化/同步默认模板。
- 若表中已有同 `key` 记录，不会覆盖。

---

### delete_novel.py

按标题删除数据库中的小说（含章节与草稿）。用于清理测试数据或误创建的小说。

**用法**（在项目根目录执行）：
```bash
python scripts/delete_novel.py
python scripts/delete_novel.py --title "我的小说"
```

**说明**：默认删除标题为「虚拟世界历险记」的小说，可用 `--title` 指定其他标题。

---

### generate_chapter_87.py

生成特定章节（示例：第87章）。

**用法**：
```bash
python scripts\generate_chapter_87.py
```

**说明**：
- 单独生成某一章
- 可以复制并修改为其他章节号

---

## 📋 脚本分类总结

### 安装类（.bat）

| 脚本 | 速度 | 网络需求 | 推荐度 |
|------|------|----------|--------|
| `quick_install.bat` | ⚡ 快 | 中 | ⭐⭐⭐⭐⭐ |
| `install_dependencies_pip.bat` | ⚡ 中 | 中 | ⭐⭐⭐⭐ |
| `install_dependencies.bat` | 🐌 慢 | 高 | ⭐⭐⭐ |

### 批处理类（.py）

| 脚本 | 用途 | 使用频率 |
|------|------|----------|
| `generate_global_files.py` | 初始化设定 | 一次性 |
| `generate_outlines.py` | 批量大纲 | 偶尔 |
| `process_first_10_chapters.py` | 批量处理 | 偶尔 |
| `check_missing_chapters.py` | 检查进度 | 经常 |
| `reprocess_failed_chapters.py` | 修复失败 | 偶尔 |

---

## 🔗 相关文档

- [快速开始](../README.md#-quick-start)
- [开发指南](../docs/DEVELOPMENT.md)
- [故障排查](../docs/TROUBLESHOOTING.md)
- [快速参考](../docs/QUICK_REFERENCE.md)
