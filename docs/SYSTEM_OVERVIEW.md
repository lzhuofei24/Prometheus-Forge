# Prometheus Forge 系统概览

## 系统架构

Prometheus Forge 是一个事件驱动的多智能体小说创作系统，采用微服务架构，支持水平扩展和实时监控。

## 核心组件

### 1. 前端层 (React + TypeScript)

- **技术栈**: React 19.2, TypeScript 5.9, Tailwind CSS, TanStack Query
- **功能**: 
  - 实时工作流监控
  - 智能体状态可视化
  - 工作流追踪时间线
  - 队列状态监控

### 2. API 层 (FastAPI)

- **技术栈**: FastAPI, Pydantic, SQLAlchemy
- **功能**:
  - RESTful API 接口
  - 工作流管理
  - 状态查询
  - 监控数据

### 3. 事件总线 (Dispatcher)

- **职责**: 事件路由和状态管理
- **特点**:
  - 智能体之间完全解耦
  - 通过事件通信
  - 不自动触发任务（由中央控制器管理）

### 4. 智能体系统 (Celery Workers)

#### Architect Agent (架构师)
- **队列**: `architect_pending`
- **职责**: 生成章节大纲
- **输入**: 小说名称、章节号、上下文
- **输出**: 章节大纲

#### Writer Agent (写手)
- **队列**: `writer_pending`
- **职责**: 创作章节正文
- **输入**: 大纲、上下文、反馈（可选）
- **输出**: 章节正文

#### Critic Agent (审稿员)
- **队列**: `critic_pending`
- **职责**: 评估内容质量
- **输入**: 章节正文
- **输出**: 评分（0-100）、建议、是否通过

#### Censor Agent (审查员)
- **队列**: `censor_pending`
- **职责**: 敏感词审查
- **输入**: 章节正文
- **输出**: 是否敏感、原因、检查方式
- **机制**: 
  1. 敏感词列表检查（优先）
  2. LLM 审查（备用）

#### Knowledge Agent (档案员)
- **队列**: `knowledge_pending`
- **职责**: 维护知识库
- **输入**: 章节正文
- **输出**: 提取的实体、更新的摘要
- **功能**:
  - 提取实体（角色、地点、物品）
  - 更新 RAG 向量库
  - 更新滚动摘要

#### Media Agent (媒体)
- **队列**: `media_pending`
- **职责**: 生成章节配图
- **输入**: 章节内容、场景描述
- **输出**: 图片 URL

### 5. 数据层

#### Redis
- **用途**: 
  - 工作流状态存储
  - 审计日志
  - 缓存（章节内容、全局设置、LLM 响应）
- **配置**: db=0 (状态), db=1 (Celery backend)

#### SQLite
- **用途**: 章节数据持久化、提示词模板
- **表结构**:
  - `novels`: 小说信息
  - `chapters`: 章节信息
  - `chapter_drafts`: 章节草稿（支持版本管理）
  - `prompt_templates`: 提示词模板，按 `(key, workflow_type)` 唯一；`workflow_type` 为空表示默认/通用，非空（如 `outline_only`）表示该工作流专用版本

#### ChromaDB
- **用途**: RAG 向量检索
- **功能**: 语义搜索相关上下文

## 工作流程

```
1. 用户启动工作流
   POST /workflow/start
   ↓
2. 系统创建 workflow_id，初始化状态
   ↓
3. 中央控制器调度 Architect Agent
   ↓
4. Architect 生成大纲
   Event: OUTLINE_GENERATED
   ↓
5. 中央控制器调度 Writer Agent
   ↓
6. Writer 创作正文
   Event: CONTENT_WRITTEN
   ↓
7. 中央控制器调度 Critic Agent
   ↓
8. Critic 评估质量
   Event: CRITIQUE_COMPLETED
   ├─ 评分 ≥ 75 → 通过
   └─ 评分 < 75 → 触发 Writer 重写（最多3次）
   ↓
9. 中央控制器调度 Censor Agent
   ↓
10. Censor 审查内容
    Event: CONTENT_CENSORED
    ↓
11. 中央控制器调度 Knowledge Agent
    ↓
12. Knowledge 更新知识库
    Event: KNOWLEDGE_UPDATED
    ↓
13. 工作流完成
```

## 性能优化

### 数据库优化
- JOIN 查询减少往返
- 批量查询多个章节
- 连接池配置（pool_size=10, max_overflow=20）
- 索引优化（active_draft_id, latest_version）

### 缓存策略
- **章节内容缓存**: TTL 1小时
- **全局设置缓存**: TTL 5分钟
- **LLM 响应缓存**: TTL 24小时

### 任务管理
- **任务去重**: 分布式锁防止重复执行
- **超时保护**: 软/硬超时机制
- **任务优先级**: 可配置优先级队列

## 监控和可观测性

### 结构化日志
- 统一 JSON 格式
- 包含 workflow_id, agent, task_id
- 便于追踪和调试

### 实时监控
- 智能体状态
- 队列长度
- 任务执行情况
- 系统资源使用

## 安全特性

### 敏感词审查
- 二级审查机制
- 支持自定义敏感词列表
- LLM 深度审查

### 输入验证
- Pydantic 模型验证
- 防止路径遍历
- API Key 认证（可选）

## 配置管理

### 环境变量 (.env)
- API Keys
- Redis 配置
- 数据库配置

### 配置文件 (config/settings.yaml)
- LLM 模型配置
- 智能体配置
- 路径配置

### 提示词按工作流分版本
- 提示词存储在数据库 `prompt_templates` 表，维度为 `(key, workflow_type)`。
- `workflow_type` 为空表示默认/通用模板；非空（如 `generate_chapter`、`outline_only`）表示该工作流专用版本。
- 运行时：若 state 中有 `workflow_type`，则 `resolve_prompt(key, workflow_type=...)` 优先查该工作流版本，若无再回退到默认。
- 旧库需先执行迁移：`python scripts/migrate_prompt_workflow_type.py`，再启动新代码或执行种子脚本。

### 热重载
- `/admin/reload-config` API
- 无需重启服务

## 部署

### 开发环境
```bash
# 启动后端
uvicorn src.api.main:app --reload

# 启动所有 workers
start_all_workers.bat

# 启动前端
cd web && npm run dev
```

### 生产环境
- 使用 `start_all.bat` 一键启动
- 使用 `stop_all.bat` 一键停止
- 使用 `restart_all.bat` 一键重启

## 测试

运行系统测试：
```bash
python scripts/test_system.py
```

测试包括：
- API 健康检查
- 数据库连接
- Redis 连接
- 各智能体功能测试
