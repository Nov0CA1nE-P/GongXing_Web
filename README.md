# 躬行启杭交流平台

这是一个包含 React 前端和 FastAPI 后端的全栈项目。

## 项目结构

```text
Summercamp_website\
  frontend\       React、TypeScript、Vite 前端
  backend\        FastAPI 后端和接口
  data\           数据库、课件和上传文件
  scripts\        Windows 与 Unix 启动脚本
  .env.example    环境变量示例
```

在 Codex 桌面端开发时，项目入口应选择：

```text
E:\VibeCoding\projects\Summercamp_website
```

不要只选择 `frontend/`，否则涉及接口、数据库或启动脚本的任务无法获得完整上下文。

## 环境配置

复制 `.env.example` 为 `.env`，再填写本机配置。不要提交或展示 `.env` 的真实内容。

至少应修改示例管理员密码；需要 AI 问答能力时再填写 API Key。相对数据库路径以项目根目录为基准，默认数据库位于 `data/site.db`。

## 启动

Windows 可以运行：

```bat
scripts\start.bat
```

macOS 或 Linux 可以运行：

```bash
bash scripts/start.sh
```

启动脚本会检查环境、安装缺少的项目依赖并分别启动：

- 前端：`http://localhost:5173`
- 后端：`http://localhost:8000`
- 管理页面：`http://localhost:5173/admin`

安装依赖会修改本机环境和依赖目录，交给 Codex 执行前应明确授权。

## 开发检查

前端依赖已经安装时，在 `frontend/` 运行：

```bash
npm run build
npm run lint
```

后端可以先进行 Python 语法检查，再启动服务并访问 `/api/health`。
