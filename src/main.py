"""
程序入口模块

Novel-Agent 的主程序入口，提供命令行界面。
"""

import argparse
from pathlib import Path
from dotenv import load_dotenv
from src.core.config import Settings
from src.core.llm import LLMClient
from src.core.logger import setup_logger
from src.utils.file_manager import ProjectManager
from src.rag.indexer import VectorIndexer
from src.rag.retriever import VectorRetriever
from src.workers.crawler import Crawler
from src.workers.author import Author

# 加载环境变量
load_dotenv()

# 初始化日志
logger = setup_logger()


def init_components(config: Settings):
    """
    初始化所有组件
    
    Args:
        config: 配置对象
        
    Returns:
        包含所有组件的字典
    """
    # 初始化 LLM 客户端
    llm_client = LLMClient(
        provider=config.model.provider,
        model=config.model.name,
        temperature=config.model.temperature,
        max_tokens=config.model.max_tokens
    )
    
    # 初始化文件管理器
    file_manager = ProjectManager(Path(config.paths.workspace))
    
    # 初始化向量索引器
    indexer = VectorIndexer(
        persist_directory=Path(config.paths.chroma_db),
        collection_name="novel_chunks"
    )
    
    # 初始化向量检索器
    retriever = VectorRetriever(indexer.collection)
    
    # 初始化 Crawler
    crawler = Crawler(
        llm_client=llm_client,
        indexer=indexer,
        file_manager=file_manager
    )
    
    # 初始化 Author
    author = Author(
        llm_client=llm_client,
        retriever=retriever,
        file_manager=file_manager
    )
    
    return {
        "llm_client": llm_client,
        "file_manager": file_manager,
        "indexer": indexer,
        "retriever": retriever,
        "crawler": crawler,
        "author": author
    }


def cmd_extract(args, components):
    """提取设定命令"""
    logger.info(f"开始处理小说：{args.novel_name}")
    logger.info(f"原始文件：{args.raw_file}")
    
    raw_file_path = Path(args.raw_file)
    if not raw_file_path.exists():
        logger.error(f"文件不存在：{raw_file_path}")
        return
    
    try:
        components["crawler"].process_novel(
            novel_name=args.novel_name,
            raw_file_path=raw_file_path
        )
        logger.info(f"✅ 小说《{args.novel_name}》处理完成！")
        logger.info(f"设定文件已保存到：workspace/{args.novel_name}/global/")
    except Exception as e:
        logger.error(f"❌ 处理失败：{e}", exc_info=True)


def cmd_write(args, components):
    """生成章节命令"""
    logger.info(f"开始生成章节：{args.novel_name} 第{args.chapter_num}章")
    
    try:
        # 获取前文上下文（如果有）
        previous_context = None
        if args.use_context:
            existing_chapters = components["file_manager"].list_chapters(args.novel_name)
            previous_chapters = [ch for ch in existing_chapters if ch < args.chapter_num]
            if previous_chapters:
                previous_context = []
                for ch_num in previous_chapters[-3:]:  # 只使用最近3章
                    ch_path = components["file_manager"].get_chapter_path(args.novel_name, ch_num)
                    outline_path = ch_path / "outline.md"
                    if outline_path.exists():
                        outline = components["file_manager"].load_content(outline_path)
                        previous_context.append({
                            "chapter_num": ch_num,
                            "outline": outline[:200]  # 只取前200字符
                        })
        
        result = components["author"].write_chapter(
            novel_name=args.novel_name,
            chapter_num=args.chapter_num,
            auto_outline=args.auto_outline,
            previous_context=previous_context
        )
        
        logger.info(f"✅ 第{args.chapter_num}章生成完成！")
        logger.info(f"大纲：{len(result['outline'])} 字符")
        logger.info(f"正文：{len(result['content'])} 字符")
    except Exception as e:
        logger.error(f"❌ 生成失败：{e}", exc_info=True)


def cmd_list(args, components):
    """列出章节命令"""
    novel_name = args.novel_name
    chapters = components["file_manager"].list_chapters(novel_name)
    
    if not chapters:
        logger.info(f"小说《{novel_name}》还没有章节。")
        return
    
    logger.info(f"小说《{novel_name}》共有 {len(chapters)} 章：")
    for ch_num in chapters:
        ch_path = components["file_manager"].get_chapter_path(novel_name, ch_num)
        meta_path = ch_path / "meta.json"
        if meta_path.exists():
            meta = components["file_manager"].load_content(meta_path)
            status = meta.get("status", "unknown")
            word_count = meta.get("word_count", 0)
            logger.info(f"  第{ch_num}章 - 状态：{status}，字数：{word_count}")
        else:
            logger.info(f"  第{ch_num}章")


def main():
    """
    主函数
    
    程序入口点，初始化各个组件并启动应用。
    """
    parser = argparse.ArgumentParser(
        description="Novel-Agent: 基于逆向工程的小说创作系统",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  # 提取小说设定
  python -m src.main extract --novel "我的小说" --raw-file data/raw/novel.txt
  
  # 生成第1章
  python -m src.main write --novel "我的小说" --chapter 1
  
  # 列出所有章节
  python -m src.main list --novel "我的小说"
        """
    )
    
    # 全局参数
    parser.add_argument(
        "--config",
        type=Path,
        default=Path("config/settings.yaml"),
        help="配置文件路径（默认：config/settings.yaml）"
    )
    
    # 子命令
    subparsers = parser.add_subparsers(dest="command", help="可用命令")
    
    # extract 命令：提取设定
    extract_parser = subparsers.add_parser("extract", help="从原始文本提取小说设定")
    extract_parser.add_argument("--novel", dest="novel_name", required=True, help="小说名称")
    extract_parser.add_argument("--raw-file", dest="raw_file", required=True, help="原始文本文件路径")
    
    # write 命令：生成章节
    write_parser = subparsers.add_parser("write", help="生成小说章节")
    write_parser.add_argument("--novel", dest="novel_name", required=True, help="小说名称")
    write_parser.add_argument("--chapter", dest="chapter_num", type=int, required=True, help="章节编号")
    write_parser.add_argument(
        "--no-auto-outline",
        dest="auto_outline",
        action="store_false",
        default=True,
        help="不自动生成大纲（使用已有大纲）"
    )
    write_parser.add_argument(
        "--use-context",
        dest="use_context",
        action="store_true",
        default=False,
        help="使用前文上下文生成大纲"
    )
    
    # list 命令：列出章节
    list_parser = subparsers.add_parser("list", help="列出小说的所有章节")
    list_parser.add_argument("--novel", dest="novel_name", required=True, help="小说名称")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        return
    
    # 加载配置
    logger.info("加载配置文件...")
    config = Settings.load_from_yaml(args.config)
    logger.info(f"使用模型：{config.model.name} ({config.model.provider})")
    
    # 初始化组件
    logger.info("初始化组件...")
    components = init_components(config)
    
    # 执行命令
    if args.command == "extract":
        cmd_extract(args, components)
    elif args.command == "write":
        cmd_write(args, components)
    elif args.command == "list":
        cmd_list(args, components)
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
