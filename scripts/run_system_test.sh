#!/usr/bin/env bash
# 全链路 E2E 系统测试（Mock AI，无需真实 API / Redis / Worker）
# 需在项目环境中运行（conda activate novel-agent 或项目 venv），且安装 celery、fakeredis。
# 从项目根运行，仅加载 e2e/conftest；缺 celery 时整批 E2E 会 SKIP。
set -e
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
export PYTHONPATH="$ROOT"
python -m pytest tests/e2e -v -s --rootdir="$ROOT" "$@"
