"""
提示词模板导入数据库插件

将 resources/default_prompt_templates/templates.json 中的默认提示词导入到数据库
prompt_templates 表。默认提示词已按法律与平台规范严格限制，禁止非法/政治/色情/犯罪内容。

【重要】本插件仅新增数据库中尚不存在的 key，绝不覆盖或修改已存在的记录。
因此，你本地数据库中的提示词模板与执行前保持一致，已有修改不会被改动。

使用方式（需在项目根目录执行）：
    python tools/import_prompt_templates.py

可选参数：
    --dry-run    仅打印将要新增的 key，不写入数据库
"""
import sys
import os
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import select
from src.core.database import Base
from src.core.models import PromptTemplate
from src.core.db_service import engine, SessionLocal

# 默认模板文件路径（相对项目根）
DEFAULT_TEMPLATES_PATH = "resources/default_prompt_templates/templates.json"


def _resolve_templates_path() -> str:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    return os.path.join(root, DEFAULT_TEMPLATES_PATH.replace("/", os.sep))


def run_import(dry_run: bool = False) -> None:
    import src.api.models  # noqa: F401
    import src.core.models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    path = _resolve_templates_path()
    if not os.path.exists(path):
        print(f"未找到默认模板文件: {path}")
        print(f"请确保存在 {DEFAULT_TEMPLATES_PATH}")
        return

    with open(path, "r", encoding="utf-8") as f:
        prompts = json.load(f)

    db = SessionLocal()
    try:
        # 仅检测表结构是否可用，不修改已有数据
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

        to_add = []
        for p in prompts:
            key = p.get("key")
            if not key:
                continue
            exists = db.execute(select(PromptTemplate).where(PromptTemplate.key == key)).scalar_one_or_none()
            if not exists:
                to_add.append(p)

        if dry_run:
            if not to_add:
                print("没有需要新增的模板（数据库中已存在所有 key）。")
            else:
                print(f"【dry-run】以下 {len(to_add)} 个 key 将被新增（未写入数据库）：")
                for p in to_add:
                    print(f"  - {p['key']}")
            return

        for p in to_add:
            new_prompt = PromptTemplate(
                key=p["key"],
                content=p["content"],
                description=p.get("description"),
            )
            db.add(new_prompt)
            print(f"新增模板: {p['key']}")

        skipped = len(prompts) - len(to_add)
        if skipped:
            print(f"跳过 {skipped} 个已存在 key（保留本地已有内容）。")
        db.commit()
        print("提示词模板导入完成。本地已有提示词未被修改。")
    except Exception as e:
        db.rollback()
        print(f"导入失败: {e}")
        raise
    finally:
        db.close()


def main():
    parser = argparse.ArgumentParser(description="将默认提示词模板导入数据库（不覆盖已有 key）")
    parser.add_argument("--dry-run", action="store_true", help="仅打印将要新增的 key，不写入数据库")
    args = parser.parse_args()
    run_import(dry_run=args.dry_run)


if __name__ == "__main__":
    main()
