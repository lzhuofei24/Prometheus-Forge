#!/usr/bin/env python
"""
项目清理脚本 - 删除 Streamlit 架构残留文件

⚠️ 警告：此脚本会删除文件，请先查看待删除清单，确认后再执行。
"""

import os
import shutil
from pathlib import Path
from typing import List, Tuple

PROJECT_ROOT = Path(__file__).parent.parent


def find_files_to_delete() -> Tuple[List[Path], List[Path], List[str]]:
    """
    分析项目，找出需要删除的文件和目录
    
    Returns:
        (directories_to_delete, files_to_delete, dependencies_to_remove)
    """
    dirs_to_delete = []
    files_to_delete = []
    deps_to_remove = []
    
    # 1. 删除整个 Streamlit GUI 目录
    gui_dir = PROJECT_ROOT / "src" / "gui"
    if gui_dir.exists():
        dirs_to_delete.append(gui_dir)
    
    # 2. 检查 main.py 中的 gui 命令引用
    main_py = PROJECT_ROOT / "src" / "main.py"
    if main_py.exists():
        content = main_py.read_text(encoding='utf-8')
        if 'from src.gui' in content or 'gui_main' in content:
            files_to_delete.append(('modify', main_py, '移除 gui 命令'))
    
    # 3. 检查 tasks.py 是否仍在使用
    # 注意：tasks.py 包含旧版 Celery 任务，但新架构使用 tasks_new.py
    # 检查是否有非 gui 目录的代码在使用它
    tasks_py = PROJECT_ROOT / "src" / "workers" / "tasks.py"
    if tasks_py.exists():
        # 搜索除了 gui 目录外的引用
        import subprocess
        try:
            result = subprocess.run(
                ['grep', '-r', 'from src.workers.tasks import', 'src'],
                cwd=PROJECT_ROOT,
                capture_output=True,
                text=True,
                shell=True
            )
            # 过滤掉 gui 目录的引用
            non_gui_refs = [line for line in result.stdout.split('\n') 
                          if line and 'src/gui' not in line]
            if non_gui_refs:
                files_to_delete.append(('check', tasks_py, f'仍被 {len(non_gui_refs)} 处引用（非 gui），需手动检查'))
            else:
                files_to_delete.append(('archive', tasks_py, '仅被 gui 使用，可归档或删除'))
        except:
            files_to_delete.append(('check', tasks_py, '无法检查引用，需手动确认'))
    
    # 4. 临时文件和缓存
    temp_patterns = [
        '**/__pycache__',
        '**/.DS_Store',
        '**/*.pyc',
        '**/*.pyo',
        '**/.pytest_cache',
    ]
    
    for pattern in temp_patterns:
        for path in PROJECT_ROOT.glob(pattern):
            if path.is_dir():
                dirs_to_delete.append(path)
            else:
                files_to_delete.append(('delete', path, '临时文件'))
    
    # 5. 日志文件（保留 logs 目录结构）
    for log_file in PROJECT_ROOT.glob('*.log'):
        if log_file.is_file():
            files_to_delete.append(('delete', log_file, '日志文件'))
    
    # 6. 检查 environment.yml 中的 streamlit 依赖
    env_yml = PROJECT_ROOT / "environment.yml"
    if env_yml.exists():
        content = env_yml.read_text(encoding='utf-8')
        if 'streamlit' in content.lower():
            deps_to_remove.append('streamlit')
            files_to_delete.append(('modify', env_yml, '移除 streamlit 依赖'))
    
    # 7. 检查 tools/check_system.py 中的 streamlit 使用
    check_system = PROJECT_ROOT / "tools" / "check_system.py"
    if check_system.exists():
        content = check_system.read_text(encoding='utf-8')
        if 'streamlit' in content.lower():
            files_to_delete.append(('modify', check_system, '移除 streamlit 引用'))
    
    return dirs_to_delete, files_to_delete, deps_to_remove


def print_deletion_plan(dirs: List[Path], files: List[Tuple], deps: List[str]):
    """打印删除计划"""
    print("=" * 80)
    print("📋 待删除清单")
    print("=" * 80)
    
    print("\n🗂️  目录（将完全删除）:")
    for i, dir_path in enumerate(dirs, 1):
        rel_path = dir_path.relative_to(PROJECT_ROOT)
        print(f"  {i}. {rel_path}")
    
    print("\n📄 文件:")
    modify_count = 0
    delete_count = 0
    check_count = 0
    
    for i, (action, file_path, reason) in enumerate(files, 1):
        if isinstance(file_path, Path):
            rel_path = file_path.relative_to(PROJECT_ROOT)
        else:
            rel_path = file_path
        
        if action == 'modify':
            action_icon = "✏️ "
            modify_count += 1
        elif action == 'delete':
            action_icon = "🗑️ "
            delete_count += 1
        elif action == 'check':
            action_icon = "⚠️ "
            check_count += 1
        elif action == 'archive':
            action_icon = "📦"
            check_count += 1
        else:
            action_icon = "❓"
        
        print(f"  {i}. {action_icon} {rel_path}")
        print(f"      └─ {reason}")
    
    print("\n📦 依赖（将从 environment.yml 移除）:")
    for i, dep in enumerate(deps, 1):
        print(f"  {i}. {dep}")
    
    print("\n" + "=" * 80)
    print(f"📊 统计:")
    print(f"  - 目录: {len(dirs)} 个")
    print(f"  - 文件删除: {delete_count} 个")
    print(f"  - 文件修改: {modify_count} 个")
    print(f"  - 需检查: {check_count} 个")
    print(f"  - 依赖移除: {len(deps)} 个")
    print("=" * 80)


def execute_cleanup(dirs: List[Path], files: List[Tuple], deps: List[str], dry_run: bool = True):
    """执行清理操作"""
    if dry_run:
        print("\n🔍 这是预览模式，不会实际删除文件")
        print("要执行删除，请运行: python scripts/cleanup.py --execute\n")
        return
    
    print("\n🚀 开始执行清理...\n")
    
    # 删除目录
    for dir_path in dirs:
        if dir_path.exists():
            print(f"删除目录: {dir_path.relative_to(PROJECT_ROOT)}")
            shutil.rmtree(dir_path)
    
    # 处理文件
    for action, file_path, reason in files:
        if not isinstance(file_path, Path):
            continue
            
        if action == 'delete' and file_path.exists():
            print(f"删除文件: {file_path.relative_to(PROJECT_ROOT)}")
            file_path.unlink()
        elif action == 'modify' and file_path.exists():
            print(f"修改文件: {file_path.relative_to(PROJECT_ROOT)}")
            if 'gui' in str(file_path):
                # 移除 main.py 中的 gui 命令
                content = file_path.read_text(encoding='utf-8')
                lines = content.split('\n')
                new_lines = []
                skip_next = False
                for i, line in enumerate(lines):
                    if 'gui_parser' in line or 'from src.gui' in line:
                        skip_next = True
                        continue
                    if skip_next and ('elif args.command == "gui"' in line or 'gui_main' in line):
                        skip_next = False
                        continue
                    if skip_next and line.strip() == '':
                        skip_next = False
                        continue
                    skip_next = False
                    new_lines.append(line)
                file_path.write_text('\n'.join(new_lines), encoding='utf-8')
            elif 'environment.yml' in str(file_path):
                # 移除 streamlit 依赖
                content = file_path.read_text(encoding='utf-8')
                lines = content.split('\n')
                new_lines = []
                for line in lines:
                    if 'streamlit' in line.lower() and not line.strip().startswith('#'):
                        continue
                    new_lines.append(line)
                file_path.write_text('\n'.join(new_lines), encoding='utf-8')
    
    print("\n✅ 清理完成！")


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description='清理项目中的 Streamlit 残留文件')
    parser.add_argument(
        '--execute',
        action='store_true',
        help='实际执行删除操作（默认是预览模式）'
    )
    
    args = parser.parse_args()
    
    print("🔍 正在分析项目结构...\n")
    dirs, files, deps = find_files_to_delete()
    
    print_deletion_plan(dirs, files, deps)
    
    execute_cleanup(dirs, files, deps, dry_run=not args.execute)
    
    if not args.execute:
        print("\n💡 提示：要执行实际删除，请运行:")
        print("   python scripts/cleanup.py --execute")


if __name__ == "__main__":
    main()
