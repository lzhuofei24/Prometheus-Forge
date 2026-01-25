# 项目结构说明

本文档说明 Novel-Agent 项目的目录结构和文件组织方式。

## 目录分类

### 根目录文件（保留在项目根，便于首次打开与 CI/部署）

**说明与入口**
- `README.md` - 项目主页（中英混排）
- `README-zh.md` - 中文版说明

**环境与依赖**
- `.env` / `.env.example` - 环境变量（不提交 .env）
- `environment.yml` - Conda 环境
- `requirements.txt` - pip 依赖（可选）

**Docker**
- `docker-compose.yml` - Redis 等服务编排
- `docker-compose.override.yml.example` - 本地覆盖示例
- `Dockerfile.api` - API 镜像构建

**启动脚本（Windows，均在根目录执行）**
- `start_all_tabs.bat` - 在 Windows Terminal 多标签页启动 API、前端、全部 Worker（推荐）
- `start_all_workers.bat` - 仅启动全部 Celery Worker
- `start_all.bat` - 启动 API + 前端 + Worker（多窗口）
- `start_workers.bat` - 仅启动 Worker（旧版队列名）
- `restart_all.bat` - 重启相关服务
- `stop_all.bat` - 停止所有相关进程
- `START_HERE.bat` - 传统一键检查与启动（含 Streamlit 指引）

除上述文件外，**工具类/测试类/说明类** 已归位到子目录：
- 删除小说 → `scripts/delete_novel.py`
- 导入 API 测试 → `tests/test_import_api.py`，测试用 txt → `tests/fixtures/test_novel.txt`
- 重构总结 → `docs/REFACTORING_SUMMARY.md`

### 配置文件目录 (`config/`)
- `settings.yaml` - 全局配置（模型、路径等）
- `prompts/` - 提示词模板
  - `extraction.yaml` - 设定提取 Prompt
  - `writing.yaml` - 写作 Prompt

### 数据目录 (`data/`)
- `raw/` - 存放用户上传的 .txt 原著文件
- `chroma_db/` - ChromaDB 持久化存储

### 工作区目录 (`workspace/`)
- 所有生成的内容存储在此目录
- 每个小说项目有独立的子目录

### 源代码目录 (`src/`)
- `main.py` - 程序入口
- `core/` - 基础设施层（配置、LLM、日志）
- `rag/` - RAG 知识库模块
- `workers/` - 核心业务逻辑
- `utils/` - 工具模块（文件管理器）

### 测试目录 (`tests/`)
- `test_*.py` - 各类单元/集成测试（如 `test_api.py`、`test_import_api.py`、`test_controller.py` 等）
- `fixtures/` - 测试用静态数据（如 `test_novel.txt`）
- `conftest.py` - pytest  fixtures 与配置

### 脚本目录 (`scripts/`)
- `create_test_novel.py` - 在数据库中创建测试小说
- `delete_novel.py` - 按标题删除数据库中的小说
- `seed_prompts.py` - 将默认提示词写入数据库
- 其他运维/迁移/生成类脚本（见 `scripts/README.md`）

### 工具目录 (`tools/`)
- `switch_model.py` - 模型切换
- `diagnose_network.py` - 网络诊断
- `import_prompt_templates.py` - 将默认提示词模板导入数据库
- 其他独立小工具

### 文档目录 (`docs/`)
项目文档统一放在此目录：
- `TROUBLESHOOTING.md` - 故障排除指南
- `PROJECT_STRUCTURE.md` - 本文件（项目结构说明）

## 使用说明

### 运行测试
```bash
# 运行所有测试
python tests/test_api.py
python tests/test_api_simple.py
python tests/test_api_with_retry.py
python tests/test_model_switch.py
```

### 使用工具
```bash
# 模型切换工具
python tools/switch_model.py list
python tools/switch_model.py switch <preset>
python tools/switch_model.py current

# 网络诊断工具
python tools/diagnose_network.py
```

### 查看文档
- 主文档：`README.md`（根目录）
- 故障排除：`docs/TROUBLESHOOTING.md`
- 项目结构：`docs/PROJECT_STRUCTURE.md`（本文件）

## 路径引用说明

所有脚本文件中的路径引用都已更新为相对于项目根目录：
- 测试文件：使用 `Path(__file__).parent.parent` 获取项目根目录
- 工具脚本：使用 `Path(__file__).parent.parent` 获取项目根目录
- 配置文件路径：使用 `project_root / "config" / "settings.yaml"` 的形式

## 文件组织原则

1. **测试文件** → `tests/` 目录
2. **工具脚本** → `tools/` 目录
3. **文档文件** → `docs/` 目录
4. **源代码** → `src/` 目录
5. **配置文件** → `config/` 目录（保留在根目录）
6. **数据文件** → `data/` 目录
7. **生成内容** → `workspace/` 目录
