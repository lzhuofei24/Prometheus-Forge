import pytest
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from src.api.services.novel_service import NovelService
from src.api.models import Novel, Chapter, ChapterDraft, ChapterStatus


@pytest.mark.asyncio
async def test_create_novel(db_session: AsyncSession):
    novel = await NovelService.create_novel(
        db_session,
        title="测试小说",
        genre="奇幻",
        summary="这是一个测试小说"
    )
    
    assert novel.id is not None
    assert novel.title == "测试小说"
    assert novel.genre == "奇幻"
    assert novel.summary == "这是一个测试小说"
    assert novel.created_at is not None
    
    await db_session.commit()
    
    retrieved = await NovelService.get_novel_by_id(db_session, novel.id)
    assert retrieved is not None
    assert retrieved.title == "测试小说"


@pytest.mark.asyncio
async def test_get_novel_by_title(db_session: AsyncSession):
    novel = await NovelService.create_novel(
        db_session,
        title="唯一标题",
        genre="科幻"
    )
    await db_session.commit()
    
    found = await NovelService.get_novel_by_title(db_session, "唯一标题")
    assert found is not None
    assert found.id == novel.id
    
    not_found = await NovelService.get_novel_by_title(db_session, "不存在的标题")
    assert not_found is None


@pytest.mark.asyncio
async def test_list_novels(db_session: AsyncSession):
    novel1 = await NovelService.create_novel(db_session, title="小说1")
    novel2 = await NovelService.create_novel(db_session, title="小说2")
    novel3 = await NovelService.create_novel(db_session, title="小说3")
    await db_session.commit()
    
    novels = await NovelService.list_novels(db_session, limit=10)
    assert len(novels) >= 3
    
    titles = [n.title for n in novels]
    assert "小说1" in titles
    assert "小说2" in titles
    assert "小说3" in titles


@pytest.mark.asyncio
async def test_create_chapter(db_session: AsyncSession):
    novel = await NovelService.create_novel(db_session, title="测试小说")
    await db_session.commit()
    
    chapter = await NovelService.create_chapter(
        db_session,
        novel_id=novel.id,
        index=1,
        title="第一章"
    )
    
    assert chapter.id is not None
    assert chapter.novel_id == novel.id
    assert chapter.index == 1
    assert chapter.title == "第一章"
    assert chapter.status == ChapterStatus.PENDING
    
    await db_session.commit()
    
    retrieved = await NovelService.get_chapter_by_id(db_session, chapter.id)
    assert retrieved is not None
    assert retrieved.index == 1


@pytest.mark.asyncio
async def test_get_chapter_by_novel_and_index(db_session: AsyncSession):
    novel = await NovelService.create_novel(db_session, title="测试小说")
    await db_session.commit()
    
    chapter = await NovelService.create_chapter(
        db_session,
        novel_id=novel.id,
        index=5,
        title="第五章"
    )
    await db_session.commit()
    
    found = await NovelService.get_chapter_by_novel_and_index(
        db_session,
        novel.id,
        5
    )
    assert found is not None
    assert found.id == chapter.id
    assert found.index == 5
    
    not_found = await NovelService.get_chapter_by_novel_and_index(
        db_session,
        novel.id,
        999
    )
    assert not_found is None


@pytest.mark.asyncio
async def test_list_chapters(db_session: AsyncSession):
    novel = await NovelService.create_novel(db_session, title="测试小说")
    await db_session.commit()
    
    chapter1 = await NovelService.create_chapter(db_session, novel.id, 1, "第一章")
    chapter2 = await NovelService.create_chapter(db_session, novel.id, 2, "第二章")
    chapter3 = await NovelService.create_chapter(db_session, novel.id, 3, "第三章")
    await db_session.commit()
    
    chapters = await NovelService.list_chapters(db_session, novel.id)
    assert len(chapters) == 3
    
    indices = [c.index for c in chapters]
    assert indices == [1, 2, 3]


@pytest.mark.asyncio
async def test_update_chapter_status(db_session: AsyncSession):
    novel = await NovelService.create_novel(db_session, title="测试小说")
    await db_session.commit()
    
    chapter = await NovelService.create_chapter(db_session, novel.id, 1)
    await db_session.commit()
    
    assert chapter.status == ChapterStatus.PENDING
    
    updated = await NovelService.update_chapter_status(
        db_session,
        chapter.id,
        ChapterStatus.WRITING
    )
    await db_session.commit()
    
    assert updated is not None
    assert updated.status == ChapterStatus.WRITING
    
    retrieved = await NovelService.get_chapter_by_id(db_session, chapter.id)
    assert retrieved.status == ChapterStatus.WRITING


@pytest.mark.asyncio
async def test_save_draft_versioning(db_session: AsyncSession):
    novel = await NovelService.create_novel(db_session, title="测试小说")
    await db_session.commit()
    
    chapter = await NovelService.create_chapter(db_session, novel.id, 1)
    await db_session.commit()
    
    draft1 = await NovelService.save_draft(
        db_session,
        chapter_id=chapter.id,
        content="第一版内容",
        summary="第一版大纲"
    )
    await db_session.commit()
    
    assert draft1.version == 1
    assert draft1.is_active is True
    assert draft1.content == "第一版内容"
    
    draft2 = await NovelService.save_draft(
        db_session,
        chapter_id=chapter.id,
        content="第二版内容",
        summary="第二版大纲"
    )
    await db_session.commit()
    
    assert draft2.version == 2
    assert draft2.is_active is True
    assert draft2.content == "第二版内容"
    
    retrieved_draft1 = await db_session.get(ChapterDraft, draft1.id)
    assert retrieved_draft1.is_active is False
    
    draft3 = await NovelService.save_draft(
        db_session,
        chapter_id=chapter.id,
        content="第三版内容"
    )
    await db_session.commit()
    
    assert draft3.version == 3
    assert draft3.is_active is True
    
    retrieved_draft2 = await db_session.get(ChapterDraft, draft2.id)
    assert retrieved_draft2.is_active is False


@pytest.mark.asyncio
async def test_get_chapter_content(db_session: AsyncSession):
    novel = await NovelService.create_novel(db_session, title="测试小说")
    await db_session.commit()
    
    chapter = await NovelService.create_chapter(db_session, novel.id, 1, "第一章")
    await db_session.commit()
    
    await NovelService.save_draft(
        db_session,
        chapter_id=chapter.id,
        content="这是正文内容",
        summary="这是大纲",
        critique_data={"score": 85, "comments": "很好"}
    )
    await db_session.commit()
    
    content = await NovelService.get_chapter_content(db_session, chapter.id)
    
    assert content is not None
    assert content["chapter_id"] == chapter.id
    assert content["title"] == "第一章"
    assert content["content"] == "这是正文内容"
    assert content["summary"] == "这是大纲"
    assert content["critique_data"]["score"] == 85
    assert content["version"] == 1


@pytest.mark.asyncio
async def test_get_chapter_content_no_draft(db_session: AsyncSession):
    novel = await NovelService.create_novel(db_session, title="测试小说")
    await db_session.commit()
    
    chapter = await NovelService.create_chapter(db_session, novel.id, 1)
    await db_session.commit()
    
    content = await NovelService.get_chapter_content(db_session, chapter.id)
    
    assert content is not None
    assert content["content"] is None
    assert content["summary"] is None
    assert content["version"] == 0


@pytest.mark.asyncio
async def test_get_draft_history(db_session: AsyncSession):
    novel = await NovelService.create_novel(db_session, title="测试小说")
    await db_session.commit()
    
    chapter = await NovelService.create_chapter(db_session, novel.id, 1)
    await db_session.commit()
    
    await NovelService.save_draft(db_session, chapter.id, content="v1")
    await NovelService.save_draft(db_session, chapter.id, content="v2")
    await NovelService.save_draft(db_session, chapter.id, content="v3")
    await db_session.commit()
    
    history = await NovelService.get_draft_history(db_session, chapter.id)
    
    assert len(history) == 3
    assert history[0].version == 3
    assert history[1].version == 2
    assert history[2].version == 1
    assert history[0].content == "v3"
    assert history[1].content == "v2"
    assert history[2].content == "v1"


@pytest.mark.asyncio
async def test_save_draft_with_critique_data(db_session: AsyncSession):
    novel = await NovelService.create_novel(db_session, title="测试小说")
    await db_session.commit()
    
    chapter = await NovelService.create_chapter(db_session, novel.id, 1)
    await db_session.commit()
    
    critique_data = {
        "score": 72,
        "comments": "需要改进",
        "advice": "增加细节描写"
    }
    
    draft = await NovelService.save_draft(
        db_session,
        chapter_id=chapter.id,
        content="内容",
        critique_data=critique_data
    )
    await db_session.commit()
    
    assert draft.critique_data == critique_data
    
    content = await NovelService.get_chapter_content(db_session, chapter.id)
    assert content["critique_data"]["score"] == 72
    assert content["critique_data"]["advice"] == "增加细节描写"
