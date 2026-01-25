# Prometheus Forge 前端

React 19 + TypeScript + Vite + Tailwind，写作/阅读/工作流监控/资源监控单页应用。

## 本地开发

```bash
# 在项目根目录
cd web
npm install
npm run dev
```

默认：<http://localhost:5173>。API 需单独启动（见仓库根目录 README 与 `start_all_tabs.bat`）。

## 构建

```bash
npm run build
```

产出在 `dist/`，可由任意静态服务或后端挂载。
