"""
将 resources/default_prompts.json 中的默认提示词导入到数据库 prompt_templates 表。
默认不覆盖已存在的 key，以保留本地已修改的版本。合规性声明：默认内容为通用创作逻辑，
严格遵守法律法规，不包含任何非法、政治或色情内容。
"""
import sys
import os
import json

# 确保能导入 src 模块
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from src.core.database import Base
from src.core.models import PromptTemplate
from src.core.db_service import engine, SessionLocal


def seed_prompts():
    # 注册所有使用 Base 的模型，并确保 prompt_templates 表存在且结构正确
    import src.api.models  # noqa: F401
    import src.core.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    db = SessionLocal()
    file_path = os.path.join(os.path.dirname(__file__), "..", "resources", "default_prompts.json")

    try:
        if not os.path.exists(file_path):
            print(f"未找到默认提示词文件: {file_path}")
            return

        with open(file_path, "r", encoding="utf-8") as f:
            prompts = json.load(f)

        print(f"检测到 {len(prompts)} 个默认模板...")

        # 若表已存在但为旧版/异结构（缺少 key 等列），先删除再重建
        try:
            db.execute(select(PromptTemplate).limit(1)).scalar_one_or_none()
        except Exception as e:
            if "no such column" in str(e) or "no such table" in str(e).lower():
                db.close()
                PromptTemplate.__table__.drop(engine, checkfirst=True)
                Base.metadata.create_all(bind=engine)
                db = SessionLocal()
            else:
                raise

        for p in prompts:
            exists = db.execute(select(PromptTemplate).where(PromptTemplate.key == p["key"])).scalar_one_or_none()
            if not exists:
                print(f"新增模板: {p['key']}")
                new_prompt = PromptTemplate(
                    key=p["key"],
                    content=p["content"],
                    description=p.get("description"),
                )
                db.add(new_prompt)
            else:
                print(f"跳过已存在模板: {p['key']} (保留本地修改)")

        db.commit()
        print("提示词数据库同步完成。")

    except Exception as e:
        print(f"导入失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    seed_prompts()
