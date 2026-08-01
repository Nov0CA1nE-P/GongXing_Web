# DigitalOcean 受限测试部署：阶段 A 交付

## 1. 边界

测试站固定为 `test.novocaine.me`，正式环境以后重新设计。当前阶段只准备
仓库，不创建或修改以下内容：

- DigitalOcean Droplet、Backup、Spaces、Firewall、Monitoring 和 Token；
- Namecheap A/AAAA/CNAME 或 Nameserver；
- Let’s Encrypt 证书；
- 服务器账户、目录、密码、Basic Auth、production env；
- 任何收费资源。

阶段 B 开始前必须重新列出资源、地区、月费和销毁方式，并由负责人再次
明确批准。预计清单是 SGP1 的 2 GiB Basic Droplet（$12/月）和
BLR1 Spaces（$5/月），合计约 $17/月。

阶段 B 不启用自动 Droplet Backup：它是整机镜像，无法排除 Basic Auth、
production env 和备份凭据，会违反“Basic Auth 文件不得进入备份”的
强制约束。应用数据由加密 restic/Spaces 备份。若以后需要系统镜像，
必须停止 Nginx、临时移除 Basic Auth 和其他服务器秘密后单独评审。

## 2. 秘密和账户

DigitalOcean 与 Namecheap 必须启用双重验证，两位开发者使用独立账户
或团队权限。恢复码离线保存。

以下内容不得粘贴到 Codex、Git、PR、Issue、日志或 CI：

- 云平台/API Token 和 Namecheap 凭据；
- SSH 私钥；
- Basic Auth 密码及 htpasswd；
- 管理员密码、restic 密码和恢复 Key；
- Spaces Secret Key、DeepSeek Key、production `.env`。

负责人只能在服务器无回显终端、云控制台或受控密码管理器直接填写秘密。
restic 密码至少保留一份与 Droplet、Spaces 账户分离的离线恢复副本，
恢复副本不得进入服务器镜像、对象存储或团队聊天。

## 3. 运行时和依赖

- Node.js 固定为 24.18.0。
- Node.js 24.18.0 官方 Windows x64 包实际自带 npm 11.16.0；阶段 A
  已用这一组合完成 `npm ci`、lint 和 build。CI 会校验 npm 版本，
  阶段 B 安装服务器运行时后仍需再次核对 Linux 包的实际版本。
- 部署 Python 固定为 Linux Python 3.12。
- `backend/requirements.txt` 是顶层依赖输入；
  `backend/requirements.lock` 是按 Linux x86_64/Python 3.12 解析的
  完整哈希锁。
- Python 3.12 CI 是必过项；3.13 只做非阻塞兼容检查。
- Nginx、OpenSSH、Certbot 和系统 Python 补丁继续跟随 Ubuntu 24.04
  安全更新，不能为了固定版本阻止安全修复。

## 4. 无公开窗口的启用顺序

阶段 B 获批后仍必须按以下顺序操作：

1. 完成 SSH、防火墙、非 root 账户和目录权限。
2. 使用交互式 `htpasswd -B` 为每位测试者建立独立账号；禁止使用
   会把密码写入命令历史的 `-b`。
3. 安装 `gongxing-bootstrap.conf`，此时 80 端口只提供 ACME
   challenge，其他请求为 503。
4. 安装并静态检查最终配置、代理头、安全头和完整 Basic Auth。
5. 使用 hosts 或 `curl --resolve` 验证未知 Host 被拒绝。
6. 才在现有 Namecheap Advanced DNS 添加：
   `A / Host=test / Value=<Droplet IPv4> / TTL=Automatic`。
7. 使用 Certbot webroot 模式签发证书，不允许工具临时公开应用。
8. 第一次启用 443 时直接启用带 Basic Auth 的最终配置。
9. 确认 443 认证有效后，80 才切换为 HTTPS 跳转。

`gongxing.htpasswd` 不进入 Git、日志或任何备份；丢失时从密码管理器
中的授权名单重新生成。

## 5. Nginx 契约

- 全站 Basic Auth、noindex、robots 拒绝和未知 Host/SNI 拒绝。
- `client_max_body_size 52m`，应用仍执行精确 50 MiB 文件限制。
- Bootstrap 两个入口、最终 HTTP 未知 Host/跳转和 HTTPS 未知 SNI
  都显式 `access_log off`；HTTPS 应用站点只使用包含 `$uri` 的安全格式，
  不记录查询字符串、认证头、Cookie 或 Basic 用户。
- JS、CSS、JSON、SVG 开启 gzip 并返回 `Vary: Accept-Encoding`。
- 首期启用 nosniff、严格来源 Referrer-Policy、SAMEORIGIN frame 保护和
  谨慎 Permissions-Policy，并仅在 HTTPS 响应加入
  `Strict-Transport-Security: max-age=86400`。测试阶段不使用
  `includeSubDomains` 或 `preload`。
- CSP 不随首次部署强制启用；必须先用真实浏览器验证内联样式、Markdown、
  PDF 预览和全部核心页面，可以先使用 Report-Only。
- `/api` 和 `/data` 明确代理，永远不回退至 React SPA。
- Nginx 清空 `Forwarded` 和客户端 Basic Authorization，覆盖全部
  `X-Forwarded-*` 后再交给只信任 127.0.0.1 的 Uvicorn。

## 6. 文件系统与进程

```text
/opt/gongxing/releases/<git-sha>/   不可变代码和前端构建
/opt/gongxing/current               当前 release 符号链接
/var/lib/gongxing/data/site.db      SQLite
/var/lib/gongxing/data/uploads/     有效上传文件
/etc/gongxing/gongxing.env          应用秘密，0640
/etc/gongxing/backup.env            备份凭据，0600
/etc/gongxing/restic-password       restic 密码，0600
/var/log/nginx/gongxing_*.log       Nginx 安全访问/错误日志，由 logrotate 管理
systemd journal                     FastAPI、备份、恢复和健康观察日志
```

FastAPI 由 `gongxing.service` 以无登录用户运行，绑定
`127.0.0.1:8000` 且固定一个 worker。只有进程退出由 systemd 自动恢复；
HTTP 健康观察只记录和告警，绝不重启服务。

部署脚本有两个互斥模式：

- `--initial-deploy` 只允许在没有 current release、服务停止、releases
  目录为空、数据库不存在、上传目录为空且没有其他持久数据时使用，不要求
  不可能存在的历史快照。成功后服务保持运行并解除维护；失败后删除错误
  current、停止服务并保留维护状态。
- 其他部署一律属于后续升级，必须提供经过验证的
  `--confirmed-backup <snapshot-id>`。它与首次参数同时出现会拒绝，
  并继续保持原服务状态与失败回滚。

首次部署与冒烟通过后必须立即生成并验证第一份备份；从下一次部署开始，
不得再使用首次模式。

部署 cleanup 必须先确定包含最终服务检查在内的最终结果，随后才执行统一
回滚，最后恢复部署前状态。任何后置检查都不能在回滚判断之后把成功改成
失败。最终失败且已经切换 release 时，`current` 不得继续指向失败的新
release；旧 release 即使成功重新启动，命令仍返回失败并保留维护状态。
服务检查通过后还必须同时满足解除维护命令成功和维护文件实际不存在，
否则结果改为失败并在回滚前恢复/保留维护标记。只有服务状态与维护解除
全部成功时才记录部署成功；回滚后不得再次调用解除维护。

## 7. 运维锁和维护状态

部署、备份和恢复共用 `/run/lock/gongxing-ops.lock` 的非阻塞 `flock`。
任一操作运行时，其他操作立即失败。

开始前递归检查 `.recover-*.hold`；发现后停止并人工处理。不得把
`.recover-*.hold`、`.delete-*`、`tmp/` 或隔离恢复目录纳入正常备份。

备份期间创建 `/run/gongxing/maintenance`，Nginx 返回 503 和
`Retry-After: 120`。健康观察发现锁或维护标记时跳过，不重启、不告警。

备份脚本记录原服务状态，通过 trap 恢复：只有原本 running 才重新启动，
原本 stopped 保持 stopped。

## 8. 数据备份与恢复

备份顺序固定为：

1. 获取锁并检查恢复保留态；
2. 建立维护状态，按原状态停止后端；
3. 执行 `wal_checkpoint(TRUNCATE)`；
4. 使用 SQLite Backup API 创建快照；
5. 对快照执行 `PRAGMA integrity_check`；
6. 根据快照数据库筛选数据库关联、非符号链接且具有 PDF 签名的有效文件；
7. 生成数据库/PDF SHA-256 manifest；
8. restic 加密上传；
9. dry-run 保留策略，明确启用后才 prune；
10. trap 恢复原服务状态和 Nginx。

保留每日 7 份、每周 4 份、每月 3 份。恢复演练只恢复到
`/var/lib/gongxing/restore-drill/`，验证 manifest、数据库和 PDF，不自动
覆盖活动数据。

## 9. Spaces 阶段 B 门禁

`configure-spaces.sh` 默认只输出 dry-run。只有同时提供 `--apply` 和
`--stage-b-approved` 才可能修改 bucket。

阶段 B 中使用临时 bucket 管理凭据启用对象版本控制并应用：

- 非当前版本 30 天；
- 不完整 multipart upload 1 天；
- 清理已无历史对象的过期 delete marker。

高权限配置凭据不留在服务器；日常 restic 使用 bucket 范围最小权限。
必须实际演练历史版本和 delete marker 恢复。

DigitalOcean 账单告警是账户总额提醒，不是硬上限。计划设置 18 美元
告警，并逐项核对 Droplet 和 Spaces 账单。测试结束时必须删除
所有当前对象、历史版本、delete marker 和 bucket；若为最后一个 bucket，
还要确认 Spaces 订阅停止。

## 10. CI 与协作

CI 只有 `contents: read`，未声明权限均为 none；Action 固定完整 commit
SHA，checkout 不保留写凭据。CI 不部署、不持有服务器秘密，不使用
`pull_request_target`。

功能分支至少由另一位协作者 review，CI 全绿后才能合并。初期发布由两人
核对 Git SHA、备份 snapshot 和验收结果，再由一人执行人工部署。

## 11. 阶段 A 完成标准

- [x] 前端 build、lint 通过。
- [x] Linux Python 3.12 哈希锁可以完整安装。
- [x] Python 3.12 后端测试通过；3.13 只作为额外结果。
- [x] 部署资产静态/行为测试和所有 shell 语法检查通过。
- [x] Nginx bootstrap 没有应用代理或静态站点入口。
- [x] 最终 443 配置首次启用即包含 Basic Auth。
- [x] 备份、部署、恢复共用 flock 并阻断 recovery hold。
- [x] HTTP 健康检查没有自动重启命令。
- [x] 首次和后续部署门禁、成功/失败状态由隔离行为测试覆盖。
- [x] 每个 Nginx server 块都显式关闭访问日志或使用 `$uri` 安全日志。
- [x] Git 中不存在真实秘密、DB、PDF 或 htpasswd。
- [x] 阶段 B 资源仍未创建，DNS 仍未修改。

目标 Ubuntu 主机上的 `nginx -t`、systemd 启停、GitHub Linux CI、
线上冒烟和恢复演练属于阶段 B 验收，本节的完成状态不代表它们已执行。
