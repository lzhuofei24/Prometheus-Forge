#!/usr/bin/env python
"""测试导入小说 API 接口。

在项目根目录执行:
  python tests/test_import_api.py
  python -m pytest tests/test_import_api.py -v -s
"""

import requests
import sys
from pathlib import Path

# 保证从项目根可导入
_project_root = Path(__file__).resolve().parent.parent
if str(_project_root) not in sys.path:
    sys.path.insert(0, str(_project_root))

API_BASE = "http://localhost:8000"

FIXTURES_DIR = Path(__file__).resolve().parent / "fixtures"
TEST_NOVEL_PATH = FIXTURES_DIR / "test_novel.txt"


def create_test_novel_file():
    """在 tests/fixtures/ 下创建测试用 txt 小说文件"""
    test_content = """第一章 初入虚拟世界

李明是一名普通的大学生，平时喜欢玩游戏。某天，他收到了一封神秘的邮件，邀请他参加一个全新的虚拟现实游戏测试。

"虚拟世界历险记"——这个名字听起来就很吸引人。李明毫不犹豫地点击了"接受"按钮。

眼前一黑，再次睁开眼时，他发现自己站在一个陌生的森林中。阳光透过树叶洒下斑驳的光影，鸟鸣声在耳边回响。

"欢迎来到虚拟世界。"一个机械的声音在他脑海中响起。

第二章 第一个任务

系统提示音继续响起："你的第一个任务是找到村庄，并完成新手引导任务。"

李明环顾四周，发现了一条小径。他沿着小径前行，不久后看到了一个古朴的村庄。

村庄里人来人往，NPC们看起来栩栩如生。一个老村长向他走来："年轻人，欢迎来到新手村。我是村长，有什么需要帮助的吗？"

李明按照提示完成了新手任务，获得了第一件装备——一把木剑。

第三章 遭遇怪物

离开新手村后，李明进入了森林深处。突然，一只野狼从树后跳了出来！

"警告：发现敌对生物！"系统提示音响起。

李明握紧木剑，准备战斗。这是他第一次在虚拟世界中战斗，心情既紧张又兴奋。

经过一番激战，李明成功击败了野狼，获得了经验和金币奖励。

"看来这个游戏还挺有趣的。"李明自言自语道。
"""
    FIXTURES_DIR.mkdir(parents=True, exist_ok=True)
    TEST_NOVEL_PATH.write_text(test_content, encoding="utf-8")
    print(f"✅ 创建测试文件: {TEST_NOVEL_PATH}")
    return TEST_NOVEL_PATH


def check_api_health():
    """检查 API 服务器是否运行"""
    try:
        response = requests.get(f"{API_BASE}/health", timeout=2)
        if response.status_code == 200:
            return True
    except Exception:
        pass
    return False


def test_import_novel(file_path: Path, title: str):
    """测试导入小说 API"""
    if not check_api_health():
        print(f"❌ API 服务器未运行: {API_BASE}")
        print("   请先启动后端服务:")
        print("   uvicorn src.api.main:app --reload --port 8000")
        return False

    url = f"{API_BASE}/novels/import"

    print(f"\n📤 开始导入小说: {title}")
    print(f"   文件: {file_path}")
    print(f"   API: {url}")

    try:
        with open(file_path, "rb") as f:
            files = {"file": (file_path.name, f, "text/plain")}
            data = {"title": title, "genre": "科幻"}

            response = requests.post(url, files=files, data=data, timeout=30)

            print(f"\n📥 响应状态码: {response.status_code}")

            if response.status_code == 200:
                result = response.json()
                print("✅ 导入成功！")
                print(f"   小说ID: {result['novel_id']}")
                print(f"   小说标题: {result['novel_title']}")
                print(f"   章节数量: {result['chapters_count']}")
                print("\n   章节列表:")
                for ch in result["chapters"]:
                    print(f"     - 第{ch['index']}章: {ch.get('title', '无标题')} ({ch['word_count']} 字)")
                return True
            else:
                print(f"❌ 导入失败: {response.text}")
                try:
                    print(f"   错误详情: {response.json()}")
                except Exception:
                    pass
                return False

    except requests.exceptions.ConnectionError:
        print(f"❌ 无法连接到 API 服务器: {API_BASE}")
        print("   请确保后端服务正在运行: uvicorn src.api.main:app --reload --port 8000")
        return False
    except Exception as e:
        print(f"❌ 发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False


def main():
    print("=" * 60)
    print("测试导入小说 API 接口")
    print("=" * 60)

    test_file = create_test_novel_file()
    success = test_import_novel(test_file, "虚拟世界历险记")

    if success:
        print("\n" + "=" * 60)
        print("✅ 测试完成！")
        print("=" * 60)
    else:
        print("\n" + "=" * 60)
        print("❌ 测试失败")
        print("=" * 60)
        sys.exit(1)


if __name__ == "__main__":
    main()
