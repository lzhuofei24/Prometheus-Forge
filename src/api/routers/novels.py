"""
写作/阅读助手唯一数据源：小说列表、目录、正文、大纲均来自本路由，底层仅读/写数据库，不依赖工作区文件。
"""
import logging
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
from src.core.database import get_db
from src.api.services.novel_service import NovelService
from src.api.services.import_service import ImportService
from src.api.models import ChapterStatus
from pydantic import BaseModel

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/novels", tags=["novels"])


class NovelCreate(BaseModel):
    title: str
    genre: Optional[str] = None
    summary: Optional[str] = None


class NovelResponse(BaseModel):
    id: str
    title: str
    genre: Optional[str] = None
    summary: Optional[str] = None
    created_at: str

    class Config:
        from_attributes = True


class ChapterResponse(BaseModel):
    id: str
    novel_id: str
    index: int
    title: Optional[str] = None
    status: str
    created_at: str

    class Config:
        from_attributes = True


class ChapterContentResponse(BaseModel):
    chapter_id: str
    title: Optional[str]
    status: str
    content: Optional[str] = None
    summary: Optional[str] = None
    critique_data: Optional[dict] = None
    version: int
    created_at: Optional[str] = None


@router.post("", response_model=NovelResponse)
async def create_novel(
    novel: NovelCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新小说"""
    existing = await NovelService.get_novel_by_title(db, novel.title)
    if existing:
        raise HTTPException(status_code=400, detail=f"小说 '{novel.title}' 已存在")
    
    created = await NovelService.create_novel(
        db,
        title=novel.title,
        genre=novel.genre,
        summary=novel.summary
    )
    await db.commit()
    return NovelResponse(
        id=created.id,
        title=created.title,
        genre=created.genre,
        summary=created.summary,
        created_at=created.created_at.isoformat()
    )


@router.get("", response_model=List[NovelResponse])
async def list_novels(
    limit: int = 100,
    offset: int = 0,
    db: AsyncSession = Depends(get_db)
):
    """列出所有小说"""
    novels = await NovelService.list_novels(db, limit=limit, offset=offset)
    return [
        NovelResponse(
            id=n.id,
            title=n.title,
            genre=n.genre,
            summary=n.summary,
            created_at=n.created_at.isoformat()
        )
        for n in novels
    ]


@router.get("/{novel_id}", response_model=NovelResponse)
async def get_novel(
    novel_id: str,
    db: AsyncSession = Depends(get_db)
):
    """获取小说详情"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    return NovelResponse(
        id=novel.id,
        title=novel.title,
        genre=novel.genre,
        summary=novel.summary,
        created_at=novel.created_at.isoformat()
    )


@router.get("/{novel_id}/chapters", response_model=List[ChapterResponse])
async def list_chapters(
    novel_id: str,
    db: AsyncSession = Depends(get_db)
):
    """列出小说的所有章节"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    chapters = await NovelService.list_chapters(db, novel_id)
    return [
        ChapterResponse(
            id=c.id,
            novel_id=c.novel_id,
            index=c.index,
            title=c.title,
            status=c.status.value,
            created_at=c.created_at.isoformat()
        )
        for c in chapters
    ]


@router.get("/{novel_id}/chapters/wordcounts", response_model=dict)
async def get_chapter_wordcounts(
    novel_id: str,
    db: AsyncSession = Depends(get_db),
):
    """批量返回该小说所有章节的正文字数 (index -> 字数)，写作页侧栏用，一次请求。"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    counts = await NovelService.get_chapter_wordcounts(db, novel_id)
    return {str(k): v for k, v in counts.items()}


@router.get("/{novel_id}/chapters/{chapter_index}", response_model=ChapterContentResponse)
async def get_chapter_content(
    novel_id: str,
    chapter_index: int,
    db: AsyncSession = Depends(get_db)
):
    """获取章节内容"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    chapter = await NovelService.get_chapter_by_novel_and_index(
        db, novel_id, chapter_index
    )
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    content = await NovelService.get_chapter_content(db, chapter.id)
    if content is None:
        raise HTTPException(status_code=404, detail="Chapter content not found")
    
    return ChapterContentResponse(**content)


class ChapterCreate(BaseModel):
    novel_id: str
    index: int
    title: Optional[str] = None


class ChapterSave(BaseModel):
    content: Optional[str] = None
    summary: Optional[str] = None
    title: Optional[str] = None


class NovelSettingsUpdate(BaseModel):
    bios: Optional[list] = None
    world: Optional[str] = None
    story_summary: Optional[str] = None


class ImportResponse(BaseModel):
    novel_id: str
    novel_title: str
    chapters_count: int
    chapters: List[dict]


@router.get("/{novel_id}/graph", response_model=dict)
async def get_novel_graph(novel_id: str, db: AsyncSession = Depends(get_db)):
    """GraphRAG：返回该小说的人物/实体关系图谱 (nodes, edges)，供前端 GraphRAGViewer 展示。"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    try:
        from src.rag.graph_store import NetworkXGraphStore
        from src.core.config import GRAPH_STORE_BASE
        store = NetworkXGraphStore(persist_path=str(GRAPH_STORE_BASE), novel_id=novel_id)
        store.load()
        nodes, edges = store.get_all()
        return {"nodes": nodes, "edges": edges}
    except Exception as e:
        logger.warning("get_novel_graph failed: %s", e)
        return {"nodes": [], "edges": []}


@router.get("/{novel_id}/settings", response_model=dict)
async def get_novel_settings(
    novel_id: str,
    db: AsyncSession = Depends(get_db),
):
    """获取小说全局设定（bios, world, story_summary），仅从数据库。"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return await NovelService.get_novel_settings(db, novel_id)


@router.put("/{novel_id}/settings", response_model=dict)
async def update_novel_settings(
    novel_id: str,
    data: NovelSettingsUpdate,
    db: AsyncSession = Depends(get_db),
):
    """更新小说全局设定，只更新传入的字段。"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    return await NovelService.set_novel_settings(
        db, novel_id,
        bios=data.bios,
        world=data.world,
        story_summary=data.story_summary,
    )


@router.post("/import", response_model=ImportResponse)
async def import_novel(
    file: UploadFile = File(...),
    title: str = Form(...),
    genre: Optional[str] = Form(None),
    db: AsyncSession = Depends(get_db)
):
    """导入txt小说文件，自动分章节"""
    if not file.filename.endswith('.txt'):
        raise HTTPException(status_code=400, detail="只支持 .txt 文件")
    
    content = await file.read()
    if len(content) == 0:
        raise HTTPException(status_code=400, detail="文件为空")
    
    if len(content) > 50 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="文件大小不能超过 50MB")
    
    try:
        import_service = ImportService()
        result = await import_service.import_txt_novel(
            db=db,
            file_content=content,
            novel_title=title,
            genre=genre
        )
        return ImportResponse(**result)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"导入失败: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"导入失败: {str(e)}")


@router.post("/chapters", response_model=ChapterResponse)
async def create_chapter(
    chapter: ChapterCreate,
    db: AsyncSession = Depends(get_db)
):
    """创建新章节"""
    novel = await NovelService.get_novel_by_id(db, chapter.novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    existing = await NovelService.get_chapter_by_novel_and_index(db, chapter.novel_id, chapter.index)
    if existing:
        raise HTTPException(status_code=400, detail=f"Chapter with index {chapter.index} already exists")
    
    created = await NovelService.create_chapter(
        db,
        novel_id=chapter.novel_id,
        index=chapter.index,
        title=chapter.title
    )
    await db.commit()
    return ChapterResponse(
        id=created.id,
        novel_id=created.novel_id,
        index=created.index,
        title=created.title,
        status=created.status.value,
        created_at=created.created_at.isoformat()
    )


@router.put("/{novel_id}/chapters/{chapter_index}", response_model=dict)
async def save_chapter(
    novel_id: str,
    chapter_index: int,
    data: ChapterSave,
    db: AsyncSession = Depends(get_db)
):
    """保存章节内容"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    chapter = await NovelService.get_chapter_by_novel_and_index(db, novel_id, chapter_index)
    if not chapter:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    if data.title is not None:
        chapter.title = data.title
        chapter.updated_at = datetime.utcnow()
        await db.flush()

    if data.content is not None or data.summary is not None:
        current = await NovelService.get_chapter_content(db, chapter.id)
        new_content = data.content if data.content is not None else (current.get("content") if current else None)
        new_summary = data.summary if data.summary is not None else (current.get("summary") if current else None)
        await NovelService.save_draft(
            db,
            chapter_id=chapter.id,
            content=new_content,
            summary=new_summary,
        )
        await db.flush()

    await db.commit()
    return {"success": True}


@router.delete("/{novel_id}/chapters/{chapter_index}", response_model=dict)
async def delete_chapter(
    novel_id: str,
    chapter_index: int,
    db: AsyncSession = Depends(get_db)
):
    """删除章节"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    success = await NovelService.delete_chapter(db, novel_id, chapter_index)
    if not success:
        raise HTTPException(status_code=404, detail="Chapter not found")
    
    await db.commit()
    return {"success": True}


@router.delete("/{novel_id}", response_model=dict)
async def delete_novel(
    novel_id: str,
    db: AsyncSession = Depends(get_db)
):
    """删除小说及其所有章节、草稿和相关数据"""
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    success = await NovelService.delete_novel(db, novel_id)
    if not success:
        raise HTTPException(status_code=500, detail="Failed to delete novel")
    
    await db.commit()
    return {"success": True}


@router.get("/{novel_id}/export", response_model=dict)
async def export_novel(
    novel_id: str,
    db: AsyncSession = Depends(get_db)
):
    """导出小说为txt格式"""
    from fastapi.responses import Response
    from urllib.parse import quote
    
    novel = await NovelService.get_novel_by_id(db, novel_id)
    if not novel:
        raise HTTPException(status_code=404, detail="Novel not found")
    
    txt_content = await NovelService.export_novel_to_txt(db, novel_id)
    if txt_content is None:
        raise HTTPException(status_code=500, detail="Failed to export novel")
    
    # 处理文件名编码：使用 RFC 5987 格式支持 UTF-8 文件名
    filename = f"{novel.title}.txt"
    
    # 检查文件名是否包含非 ASCII 字符
    try:
        filename.encode('ascii')
        has_non_ascii = False
    except UnicodeEncodeError:
        has_non_ascii = True
    
    if has_non_ascii:
        # 如果包含非 ASCII 字符，使用 RFC 5987 格式
        # quote() 在 Python 3 中默认使用 UTF-8 编码，返回的字符串只包含 ASCII 字符
        encoded_filename = quote(filename, safe='')
        # 只使用 filename* 参数，不包含原始的 filename 参数（避免 latin-1 编码错误）
        # 确保整个 header 值只包含 ASCII 字符
        content_disposition = "attachment; filename*=UTF-8''" + encoded_filename
    else:
        # 如果只有 ASCII 字符，使用标准的 filename 参数
        content_disposition = f'attachment; filename="{filename}"'
    
    # 返回文件下载响应
    return Response(
        content=txt_content.encode('utf-8'),
        media_type='text/plain; charset=utf-8',
        headers={
            'Content-Disposition': content_disposition
        }
    )
