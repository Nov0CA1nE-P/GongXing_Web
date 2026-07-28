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

`COURSEWARE_MAX_UPLOAD_MB` 是单个课件文件的应用层大小上限，默认 50 MB，允许范围为 1～500 MB；无效值会导致后端拒绝启动。后端会按分块统计真实文件大小，不能只依赖浏览器提供的 `Content-Length`。

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

## 课件文件存储

项目不会把整个 `data/` 或上传目录作为静态目录公开。课件只能通过以下专用接口访问：

```text
GET /data/uploads/{filename}
```

接口只接受安全的单一文件名和 PDF、PPT、PPTX 扩展名；解析后的文件必须位于 `data/uploads/`，符号链接会被拒绝。PDF 使用浏览器内联响应，PPT/PPTX 作为附件下载，响应均包含 `X-Content-Type-Options: nosniff`。因此 `/data/site.db`、临时文件和其他内部数据不会通过 HTTP 提供。

上传时会同时检查扩展名、声明的 MIME 和文件内容：

- PDF 检查 `%PDF-` 文件头。
- PPT 使用 `olefile` 检查 OLE 容器和 `PowerPoint Document` 数据流。
- PPTX 检查 ZIP、必要的 OOXML 文件和类型声明；ZIP 最多 2048 个条目，声明的总解压大小不超过 250 MiB，`[Content_Types].xml` 不超过 1 MiB，`ppt/presentation.xml` 不超过 8 MiB。校验不会完整解压 PPTX。

磁盘文件名由服务端随机生成，标题、日期和用户文件名不会参与路径。上传和删除使用非公开临时目录及失败回滚。

删除隔离文件分为两种状态：

- `.recover-*.hold`：数据库尚未确认删除、仍可能需要恢复的副本。数据库失败且自动恢复文件失败时会保留该文件，启动清理永远不会删除，需要管理员人工核对数据库后恢复或处理。
- `.delete-*.delete`：数据库已经提交删除、只待清理的文件。即时清理失败时，可在超过 24 小时后由启动清理删除。

启动清理除此之外只处理本模块生成且超过 24 小时的 `.upload-*.part`。它不会删除较新的文件、未知名称、符号链接或恢复保留态文件。

应用层文件限制不能替代部署入口的请求体限制。默认 50 MB 配置在正式部署时还应设置 Nginx：

```nginx
client_max_body_size 51m;
```

如果调整应用上限，应同步调整 Nginx或云平台的等效限制，并为 multipart 请求留出合理开销。

### 历史课件路径

新数据库记录只保存安全文件名。运行时仍可兼容目录后缀明确为 `data/uploads` 的 Windows 或 POSIX 历史绝对路径，但原始数据库路径永远不会直接用于打开、响应或删除文件。无法可靠映射到当前上传目录的记录不会暴露路径，删除时返回 409。

只读审计工具不会修改数据库，也不会输出原始路径：

```bash
python scripts/audit_courseware_paths.py \
  --database <数据库备份或测试数据库> \
  --uploads-dir <对应上传目录>
```

本轮不提供自动迁移。真实路径改写应在完成数据库和上传文件备份后，作为独立维护任务执行。

## 管理员认证与部署限制

管理后台使用服务端内存会话和 `HttpOnly` Cookie。密码只在登录请求体中传输一次，不进入 URL、Cookie、`localStorage` 或 `sessionStorage`。会话不会自动续期；退出按钮、服务端绝对过期、后端重启或服务端主动吊销会使其失效。Cookie 不设置 `Max-Age` 或 `Expires`，因此不能把“关闭浏览器”当作可靠退出方式。

当前认证实现有以下明确限制：

- 只支持一个后端进程和一个实例。生产环境只能运行一个 Uvicorn worker；不要使用 `uvicorn --workers 2`、Gunicorn 多 worker 或多个并行后端实例，否则请求被分配到其他进程时会随机返回 401。
- 需要扩展为多进程或多实例时，必须先把会话迁移到 Redis、数据库或其他共享存储。
- 只支持前端与 API 同站部署。开发环境依靠 Vite 代理，生产环境应由 Nginx 在同一站点反向代理 `/api`；当前的 `credentials: "same-origin"` 不支持独立 API 域名。
- Cookie 使用 `SameSite=Strict`，不设置宽泛的 Domain。当前暂时假设没有不受信任的同站子域，且所有修改状态的接口均使用 POST、PUT 或 DELETE。

这只是当前单域场景的基础保护。公开上线前仍需单独完成精确 CORS 与可信 Origin、Origin/Referer 校验或 CSRF Token 等完整防护，并补充登录限流。当前认证闭环完成不代表后台已经适合直接暴露到公网。
