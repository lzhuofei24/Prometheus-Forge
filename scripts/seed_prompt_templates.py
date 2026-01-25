#!/usr/bin/env python
"""将「系统预期」的提示词模板从 config/prompts/*.yaml 或内置默认写入数据库。
- 不存在的 key：INSERT。
- 已存在但 content 为空：用 YAML/默认文案 UPDATE 补全。

用法（在项目根目录执行）:
  python scripts/seed_prompt_templates.py

数据库默认: data/novel_content_db/prometheus_forge.db
可通过环境变量 DATABASE_URL 指定（支持 sqlite:/// 或 sqlite+aiosqlite:/// 形式，会转为本地路径）。
"""

import os
import sqlite3
import sys
from pathlib import Path

project_root = Path(__file__).resolve().parent.parent
default_db = project_root / "data" / "novel_content_db" / "prometheus_forge.db"
prompts_dir = project_root / "config" / "prompts"

# 与 src.api.routers.prompts 一致
EXPECTED_KEYS = [
    "fiction_system",
    "writing",
    "critique",
    "critique_handler",
    "extraction",
    "plot_check",
    "style_check",
    "character_check",
    "censor",
    "architect",
    "writer_builder",
    "knowledge_extraction",
    "knowledge_summary",
    "media_prompt_engineering",
]

# 描述格式：xx模板，用于 xx agent。其它使用位置：……
DESCRIPTIONS = {
    "fiction_system": "创作合规系统模板，用于各 Agent 共用。其它使用位置：Architect、Writer、Critic、Builder、Planner、Editor、PlotChecker、StyleChecker、CharacterChecker、ImportWorkflow、tasks 等",
    "writing": "正文写作模板，用于 Author。其它使用位置：无",
    "critique": "审稿模板，用于 ChiefEditor、review_chapter_task。其它使用位置：workflow/graph 中的 critic 节点",
    "critique_handler": "Worker 审稿模板，用于 CriticHandler，输出 score/critique/suggestions/passed/details。占位符：reference_context, outline, draft_content, chapter_num。其它使用位置：无",
    "extraction": "设定抽取模板，用于 ImportWorkflow、Crawler。其它使用位置：无",
    "plot_check": "剧情检查模板，用于 PlotChecker。其它使用位置：无",
    "style_check": "文风检查模板，用于 StyleChecker。其它使用位置：无",
    "character_check": "人设检查模板，用于 CharacterChecker。其它使用位置：无",
    "censor": "内容合规审查模板（LLM 审查），用于 CensorHandler。占位符：user 中 {content}。其它使用位置：无",
    "architect": "大纲规划模板，用于 ArchitectHandler、Planner、Novelist、tasks。占位符：reference_context, chapter_num, feedback_section（可为空）。其它使用位置：无",
    "writer_builder": "场景正文撰写模板，用于 WriterHandler。占位符：reference_context, chapter_num, scene_id, scene_summary, key_characters, expected_words, previous_text, feedback_section。其它使用位置：无",
    "knowledge_extraction": "知识库实体抽取模板，用于 KnowledgeHandler。占位符：chapter_content。其它使用位置：无",
    "knowledge_summary": "知识库章节摘要模板，用于 KnowledgeHandler。占位符：content。其它使用位置：无",
    "media_prompt_engineering": "插画 Prompt 工程模板，用于 MediaHandler。占位符：chinese_text。其它使用位置：无",
}

FICTION_SYSTEM_DEFAULT = """你是一位专业的文学编辑和小说创作助手。

【合规要求，必须遵守】
1. 所有产出必须符合中华人民共和国法律法规及内容安全与出版规范，禁止任何非法、政治敏感、色情、暴力恐怖、违法犯罪或违背公序良俗的内容。
2. 内容健康向上，适合全年龄或合规分级受众；不涉及真实政党、敏感历史事件或违法犯罪细节。
3. 在合规前提下进行客观分析与文学润色，严格遵循用户指令（如 JSON 格式），并**使用简体中文**回复。
"""


def _db_path() -> Path:
    url = os.getenv("DATABASE_URL", "").strip()
    if url.startswith("sqlite+aiosqlite:///"):
        p = url.replace("sqlite+aiosqlite:///", "", 1)
        return Path(p) if os.path.isabs(p) else (project_root / p)
    if url.startswith("sqlite:///"):
        p = url.replace("sqlite:///", "", 1)
        return Path(p) if os.path.isabs(p) else (project_root / p)
    return default_db


def main() -> None:
    db_path = _db_path()
    if not db_path.exists():
        print(f"数据库文件不存在: {db_path}")
        print("请先启动 API 或执行初始化以创建数据库。")
        sys.exit(1)

    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()

    # 确保表存在（若项目已 init_db 则一定存在）
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS prompt_templates (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            key VARCHAR(50) UNIQUE NOT NULL,
            content TEXT NOT NULL,
            description VARCHAR(200),
            is_active BOOLEAN DEFAULT 1,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            updated_at DATETIME
        )
        """
    )
    conn.commit()

    inserted = 0
    updated = 0
    desc_synced = 0
    skipped = 0

    for key in EXPECTED_KEYS:
        if key == "fiction_system":
            content = FICTION_SYSTEM_DEFAULT
        else:
            yaml_path = prompts_dir / f"{key}.yaml"
            if not yaml_path.exists():
                print(f"  跳过（找不到文件）: {key} -> {yaml_path}")
                skipped += 1
                continue
            content = yaml_path.read_text(encoding="utf-8")

        desc = DESCRIPTIONS.get(key, "")

        cur.execute("SELECT id, content FROM prompt_templates WHERE key = ?", (key,))
        row = cur.fetchone()
        if row is None:
            cur.execute(
                """
                INSERT INTO prompt_templates (key, content, description, is_active)
                VALUES (?, ?, ?, 1)
                """,
                (key, content, desc or None),
            )
            conn.commit()
            print(f"  已写入: {key}")
            inserted += 1
        else:
            existing = (row["content"] or "").strip()
            if not existing:
                cur.execute(
                    "UPDATE prompt_templates SET content = ?, description = ? WHERE key = ?",
                    (content, desc or None, key),
                )
                conn.commit()
                print(f"  已补全（原内容为空）: {key}")
                updated += 1
            else:
                # 已有内容时仍同步 description，保证与 DESCRIPTIONS 一致
                cur.execute(
                    "UPDATE prompt_templates SET description = ?, updated_at = CURRENT_TIMESTAMP WHERE key = ?",
                    (desc or None, key),
                )
                conn.commit()
                print(f"  已同步描述: {key}")
                desc_synced += 1

    conn.close()
    print()
    print("=" * 50)
    print(f"完毕。新增 {inserted} 条，补全空内容 {updated} 条，同步描述 {desc_synced} 条，跳过 {skipped} 条。")
    print("=" * 50)


if __name__ == "__main__":
    main()
