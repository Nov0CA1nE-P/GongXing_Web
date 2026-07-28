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

必须显式设置 `APP_ENV`。需要 AI 问答能力时再填写 API Key。相对数据库路径以项目根目录为基准，默认数据库位于 `data/site.db`。

管理员密码没有默认值。`production` 环境要求密码至少 12 个字符，且不能使用 `admin123` 或示例占位符；否则后端会明确拒绝启动。`development` 环境未配置安全密码时，公开页面仍可启动，但管理员登录会返回 503。

`ADMIN_SESSION_TTL_SECONDS` 是管理员会话的绝对有效期，默认 7200 秒，允许范围为 300～28800 秒；无效值会导致后端拒绝启动。

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

## 管理员认证与部署限制

管理后台使用服务端内存会话和 `HttpOnly` Cookie。密码只在登录请求体中传输一次，不进入 URL、Cookie、`localStorage` 或 `sessionStorage`。会话不会自动续期；退出按钮、服务端绝对过期、后端重启或服务端主动吊销会使其失效。Cookie 不设置 `Max-Age` 或 `Expires`，因此不能把“关闭浏览器”当作可靠退出方式。

当前认证实现有以下明确限制：

- 只支持一个后端进程和一个实例。生产环境只能运行一个 Uvicorn worker；不要使用 `uvicorn --workers 2`、Gunicorn 多 worker 或多个并行后端实例，否则请求被分配到其他进程时会随机返回 401。
- 需要扩展为多进程或多实例时，必须先把会话迁移到 Redis、数据库或其他共享存储。
- 只支持前端与 API 同站部署。开发环境依靠 Vite 代理，生产环境应由 Nginx 在同一站点反向代理 `/api`；当前的 `credentials: "same-origin"` 不支持独立 API 域名。
- Cookie 使用 `SameSite=Strict`，不设置宽泛的 Domain。当前暂时假设没有不受信任的同站子域，且所有修改状态的接口均使用 POST、PUT 或 DELETE。

这只是当前单域场景的基础保护。公开上线前仍需单独完成精确 CORS 与可信 Origin、Origin/Referer 校验或 CSRF Token 等完整防护，并补充登录限流。当前认证闭环完成不代表后台已经适合直接暴露到公网。
