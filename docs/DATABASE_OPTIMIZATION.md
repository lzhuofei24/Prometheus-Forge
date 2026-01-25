# 数据库结构分析与优化建议

## 当前数据库结构

### 表结构

#### 1. `novels` 表
- `id` (String(36), PK)
- `title` (String(255), indexed)
- `genre` (String(100))
- `summary` (Text)
- `created_at`, `updated_at`

#### 2. `chapters` 表
- `id` (String(36), PK)
- `novel_id` (String(36), FK, indexed)
- `index` (Integer)
- `title` (String(255))
- `status` (Enum, indexed)
- `created_at`, `updated_at`
- 索引: `(novel_id, index)`

#### 3. `chapter_drafts` 表
- `id` (String(36), PK)
- `chapter_id` (String(36), FK, indexed)
- `version` (Integer)
- `content` (Text) - 可能很大
- `summary` (Text) - 可能很大
- `critique_data` (JSON)
- `is_active` (Boolean, indexed)
- `created_at`
- 索引: `(chapter_id, is_active)`, `(chapter_id, version)`

## 发现的问题

### 1. 性能问题

**问题1: 查询 active_draft 效率低**
```python
# 当前实现
chapter = get_chapter_by_novel_and_index(...)
db.refresh(chapter, ["drafts"])  # 加载所有 drafts
active_draft = next((d for d in chapter.drafts if d.is_active), None)
```
- 需要加载所有 drafts 到内存
- 在 Python 中过滤，而不是在数据库层面

**问题2: 频繁的版本号查询**
```python
# 每次保存都要查询最新版本
result = db.execute(
    select(ChapterDraft)
    .where(ChapterDraft.chapter_id == chapter.id)
    .order_by(ChapterDraft.version.desc())
    .limit(1)
)
```
- 可以优化为在 Chapter 表中缓存 latest_version

**问题3: 多次数据库往返**
- `get_chapter_content` 先查询 Chapter，再 refresh drafts
- 可以合并为一次查询

### 2. 数据设计问题

**问题1: content 和 summary 混在一起**
- 大纲和正文存储在同一张表的不同字段
- 但它们的生命周期不同（大纲先创建，正文后创建）
- 导致很多 draft 记录中 content 为空

**问题2: 版本管理不够清晰**
- 每次保存都创建新版本，即使内容没变
- 没有区分"内容变更"和"元数据变更"

**问题3: 缺少常用字段的缓存**
- Chapter 表中没有 `latest_draft_id` 或 `active_draft_id`
- 每次都要查询 drafts 表

### 3. 索引优化

**缺失的复合索引:**
- `(chapter_id, is_active, version)` - 最常用的查询模式
- `(novel_id, index, status)` - 按状态查询章节

## 优化方案

### 方案1: 添加缓存字段（推荐，简单有效）

在 `Chapter` 表中添加：
```python
active_draft_id = Column(String(36), ForeignKey("chapter_drafts.id"), nullable=True, index=True)
latest_version = Column(Integer, default=0, nullable=False)
```

**优点:**
- 最小改动，向后兼容
- 显著提升查询性能
- 不需要修改现有代码逻辑

**缺点:**
- 需要维护缓存字段的一致性

### 方案2: 分离 Outline 和 Content（推荐，结构更清晰）

创建新表 `chapter_outlines`:
```python
class ChapterOutline(Base):
    __tablename__ = "chapter_outlines"
    
    id = Column(String(36), primary_key=True)
    chapter_id = Column(String(36), ForeignKey("chapters.id"), nullable=False, index=True)
    outline = Column(Text, nullable=False)
    version = Column(Integer, default=1)
    is_active = Column(Boolean, default=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
```

`ChapterDraft` 只存储 content:
```python
class ChapterDraft(Base):
    # 移除 summary 字段
    content = Column(Text, nullable=False)  # 改为 NOT NULL
    # 其他字段保持不变
```

**优点:**
- 结构更清晰，符合业务逻辑
- 减少数据冗余
- 查询更高效

**缺点:**
- 需要数据迁移
- 需要修改相关代码

### 方案3: 优化索引和查询（必须）

添加复合索引:
```python
__table_args__ = (
    Index("idx_draft_chapter_active_version", "chapter_id", "is_active", "version"),
    Index("idx_chapter_novel_status", "novel_id", "index", "status"),
)
```

优化查询方法:
```python
@staticmethod
def get_active_draft(chapter_id: str) -> Optional[ChapterDraft]:
    with SessionLocal() as db:
        return db.execute(
            select(ChapterDraft)
            .where(and_(
                ChapterDraft.chapter_id == chapter_id,
                ChapterDraft.is_active == True
            ))
            .limit(1)
        ).scalar_one_or_none()
```

### 方案4: 添加内容摘要字段（可选）

在 `Chapter` 表中添加:
```python
content_preview = Column(String(500), nullable=True)  # 前500字预览
word_count = Column(Integer, default=0)  # 字数统计
```

**优点:**
- 列表查询时不需要加载完整内容
- 可以快速显示章节预览

## 推荐实施顺序

1. **立即实施**: 方案3（优化索引和查询）
2. **短期实施**: 方案1（添加缓存字段）
3. **中期考虑**: 方案2（分离 Outline 和 Content）
4. **长期优化**: 方案4（添加摘要字段）

## 性能提升预期

- 查询 active_draft: **10-50x** 提升（通过直接查询 + 索引）
- 列表章节: **2-5x** 提升（通过缓存字段）
- 保存操作: **1.5-2x** 提升（减少版本号查询）
