"""
测试项目TODO列表中的各个功能
根据测试文本，逐步测试每个功能并打印进度
"""

import sys
from pathlib import Path
from dotenv import load_dotenv
import platform

try:
    import pytest
except ImportError:
    pytest = None

sys.path.insert(0, str(Path(__file__).parent.parent))

from src.core.config import Settings
from src.core.llm import LLMClient
from src.core.logger import setup_logger
from src.utils.file_manager import ProjectManager
from src.rag.indexer import VectorIndexer
from src.rag.retriever import VectorRetriever
from src.workers.crawler import Crawler
from src.workers.author import Author

load_dotenv()
logger = setup_logger()

NOVEL_NAME = "测试小说"
TEST_FILE = Path("data/raw/test_novel.txt")


if pytest:
    @pytest.fixture(scope="module")
    def config():
        config_path = Path("config/settings.yaml")
        if not config_path.exists():
            pytest.skip(f"配置文件不存在: {config_path}")
        return Settings.load_from_yaml(config_path)


    @pytest.fixture(scope="module")
    def llm_client(config):
        return LLMClient(
            provider=config.model.provider,
            model=config.model.name,
            temperature=config.model.temperature,
            max_tokens=config.model.max_tokens
        )


    @pytest.fixture(scope="module")
    def file_manager(config):
        manager = ProjectManager(Path(config.paths.workspace))
        manager.init_novel(NOVEL_NAME)
        return manager


    @pytest.fixture(scope="module")
    def indexer(config):
        return VectorIndexer(
            persist_directory=Path(config.paths.chroma_db),
            collection_name="novel_chunks"
        )


    @pytest.fixture(scope="module")
    def retriever(indexer):
        return VectorRetriever(indexer.collection)


    @pytest.fixture(scope="module")
    def crawler(llm_client, indexer, file_manager):
        return Crawler(
            llm_client=llm_client,
            indexer=indexer,
            file_manager=file_manager
        )


    @pytest.fixture(scope="module")
    def author(llm_client, retriever, file_manager):
        return Author(
            llm_client=llm_client,
            retriever=retriever,
            file_manager=file_manager
        )


    @pytest.fixture(scope="module")
    def text(crawler):
        if not TEST_FILE.exists():
            pytest.skip(f"测试文件不存在: {TEST_FILE}")
        return crawler.load_raw_text(TEST_FILE)


    @pytest.fixture(scope="module")
    def outline(author):
        return author.generate_outline(
            novel_name=NOVEL_NAME,
            chapter_num=1
        )


def print_progress(step: int, total: int, message: str):
    """打印进度"""
    progress = f"[{step}/{total}]"
    print(f"\n{'='*60}")
    print(f"{progress} {message}")
    print(f"{'='*60}")


def test_1_load_raw_text(crawler: Crawler, text):
    """测试1: Crawler.load_raw_text() - 文本加载逻辑"""
    print_progress(1, 7, "测试文本加载功能")
    
    print(f"✅ 文本加载成功")
    print(f"   - 文件路径: {TEST_FILE}")
    print(f"   - 文本长度: {len(text)} 字符")
    print(f"   - 前100字符: {text[:100]}...")
    assert text is not None and len(text) > 0


def test_2_extract_settings(crawler: Crawler, text):
    """测试2: Crawler.extract_settings() - 设定提取逻辑"""
    print_progress(2, 7, "测试设定提取功能")
    
    settings = crawler.extract_settings(text, NOVEL_NAME)
    print(f"✅ 设定提取成功")
    
    bios = settings.get("bios", [])
    world = settings.get("world", "")
    relations = settings.get("relations", {})
    
    print(f"   - 人物数量: {len(bios)}")
    for i, bio in enumerate(bios[:3], 1):
        name = bio.get("name", "未知")
        print(f"     人物{i}: {name}")
    
    print(f"   - 世界观长度: {len(world)} 字符")
    print(f"   - 关系数量: {len(relations)}")
    
    global_dir = crawler.file_manager.get_global_settings_path(NOVEL_NAME)
    print(f"   - 设定文件已保存到: {global_dir}")
    assert settings is not None


def test_3_index_text(indexer: VectorIndexer, text):
    """测试3: VectorIndexer.index_text() - 文本索引逻辑"""
    print_progress(3, 7, "测试文本索引功能")
    
    metadata = {
        "novel_name": NOVEL_NAME,
        "source": "raw_text",
        "file_path": str(TEST_FILE)
    }
    
    count_before = indexer.collection.count()
    print(f"   - 索引前文档数: {count_before}")
    
    indexer.index_text(text, metadata=metadata)
    
    count_after = indexer.collection.count()
    print(f"✅ 文本索引成功")
    print(f"   - 索引后文档数: {count_after}")
    print(f"   - 新增文档数: {count_after - count_before}")
    assert count_after > count_before


def test_4_retrieve(retriever: VectorRetriever, indexer):
    """测试4: VectorRetriever.retrieve() - 检索逻辑"""
    print_progress(4, 7, "测试检索功能")
    
    import time
    import gc
    
    time.sleep(2.0)
    gc.collect()
    
    query = "林风 剑客"
    results = retriever.retrieve(query, top_k=3)
    
    print(f"✅ 检索成功")
    print(f"   - 查询文本: {query}")
    print(f"   - 返回结果数: {len(results)}")
    
    for i, result in enumerate(results, 1):
        text = result.get("text", "")
        distance = result.get("distance", 0.0)
        print(f"   - 结果{i}: 相似度距离={distance:.4f}, 文本长度={len(text)}")
        if text:
            print(f"     文本预览: {text[:80]}...")
    
    assert results is not None


def test_5_generate_outline(author: Author, outline):
    """测试5: Author.generate_outline() - 大纲生成逻辑"""
    print_progress(5, 7, "测试大纲生成功能")
    
    print(f"✅ 大纲生成成功")
    print(f"   - 章节编号: 1")
    print(f"   - 大纲长度: {len(outline)} 字符")
    print(f"   - 大纲预览:")
    print(f"     {outline[:200]}...")
    
    chapter_path = author.file_manager.get_chapter_path(NOVEL_NAME, 1)
    outline_path = chapter_path / "outline.md"
    print(f"   - 大纲已保存到: {outline_path}")
    assert outline is not None and len(outline) > 0


def test_6_generate_content(author: Author, outline):
    """测试6: Author.generate_content() - 正文生成逻辑"""
    print_progress(6, 7, "测试正文生成功能")
    
    chapter_num = 1
    content = author.generate_content(
        novel_name=NOVEL_NAME,
        chapter_num=chapter_num,
        outline=outline
    )
    
    print(f"✅ 正文生成成功")
    print(f"   - 章节编号: {chapter_num}")
    print(f"   - 正文长度: {len(content)} 字符")
    print(f"   - 正文预览:")
    print(f"     {content[:200]}...")
    
    chapter_path = author.file_manager.get_chapter_path(NOVEL_NAME, chapter_num)
    content_path = chapter_path / "content.md"
    print(f"   - 正文已保存到: {content_path}")
    assert content is not None and len(content) > 0


def test_7_write_chapter(author: Author):
    """测试7: Author.write_chapter() - 完整章节生成（包含main功能测试）"""
    print_progress(7, 7, "测试完整章节生成功能")
    
    chapter_num = 2
    result = author.write_chapter(
        novel_name=NOVEL_NAME,
        chapter_num=chapter_num,
        auto_outline=True
    )
    
    print(f"✅ 完整章节生成成功")
    print(f"   - 章节编号: {chapter_num}")
    print(f"   - 大纲长度: {len(result['outline'])} 字符")
    print(f"   - 正文长度: {len(result['content'])} 字符")
    
    chapter_path = author.file_manager.get_chapter_path(NOVEL_NAME, chapter_num)
    print(f"   - 章节文件已保存到: {chapter_path}")
    assert result is not None and 'outline' in result and 'content' in result


def main():
    """主测试函数"""
    print("\n" + "="*60)
    print("开始测试项目TODO列表中的各个功能")
    print("="*60)
    
    config_path = Path("config/settings.yaml")
    if not config_path.exists():
        print(f"❌ 配置文件不存在: {config_path}")
        return
    
    print(f"\n加载配置文件: {config_path}")
    config = Settings.load_from_yaml(config_path)
    print(f"使用模型: {config.model.name} ({config.model.provider})")
    
    print("\n初始化组件...")
    llm_client = LLMClient(
        provider=config.model.provider,
        model=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens
    )
    
    file_manager = ProjectManager(Path(config.paths.workspace))
    file_manager.init_novel(NOVEL_NAME)
    
    indexer = VectorIndexer(
        persist_directory=Path(config.paths.chroma_db),
        collection_name="novel_chunks"
    )
    
    retriever = VectorRetriever(indexer.collection)
    
    crawler = Crawler(
        llm_client=llm_client,
        indexer=indexer,
        file_manager=file_manager
    )
    
    author = Author(
        llm_client=llm_client,
        retriever=retriever,
        file_manager=file_manager
    )
    
    print("✅ 组件初始化完成\n")
    
    if not TEST_FILE.exists():
        print(f"❌ 测试文件不存在: {TEST_FILE}")
        return
    
    text = crawler.load_raw_text(TEST_FILE)
    try:
        test_1_load_raw_text(crawler, text)
    except AssertionError as e:
        print(f"\n❌ 测试终止：文本加载失败 - {e}")
        return
    
    try:
        test_2_extract_settings(crawler, text)
    except AssertionError as e:
        print(f"\n❌ 测试终止：设定提取失败 - {e}")
        return
    
    try:
        test_3_index_text(indexer, text)
    except AssertionError as e:
        print(f"\n❌ 测试终止：文本索引失败 - {e}")
        return
    
    if platform.system() != "Windows":
        try:
            test_4_retrieve(retriever, indexer)
        except AssertionError as e:
            print(f"\n❌ 测试终止：检索失败 - {e}")
            return
    else:
        print_progress(4, 7, "测试检索功能")
        print("⏭️  跳过（Windows 上 ChromaDB 存在访问违规问题）")
    
    outline = author.generate_outline(
        novel_name=NOVEL_NAME,
        chapter_num=1
    )
    try:
        test_5_generate_outline(author, outline)
    except AssertionError as e:
        print(f"\n❌ 测试终止：大纲生成失败 - {e}")
        return
    
    try:
        test_6_generate_content(author, outline)
    except AssertionError as e:
        print(f"\n❌ 测试终止：正文生成失败 - {e}")
        return
    
    try:
        test_7_write_chapter(author)
    except AssertionError as e:
        print(f"\n❌ 测试终止：完整章节生成失败 - {e}")
        return
    
    print("\n" + "="*60)
    print("✅ 所有功能测试完成！")
    print("="*60)
    print(f"\n测试结果总结:")
    print(f"  - 小说名称: {NOVEL_NAME}")
    print(f"  - 测试文件: {TEST_FILE}")
    print(f"  - 已生成章节: {file_manager.list_chapters(NOVEL_NAME)}")
    print(f"  - 工作区路径: {file_manager.workspace_root / NOVEL_NAME}")


if __name__ == "__main__":
    main()
