# 阿里云香港公开 V1 部署运行手册

本手册以 `gongxing.novocaine.me` 为正式公开域名，并保留受 Basic Auth 保护的
`test.novocaine.me`。所有 `<SERVER_IP>`、`<PRIVATE_IP>`、
`<ADMIN_HOME_IP>` 和凭据均为运行时占位符，禁止把真实值提交到仓库。

## 0. 强制门禁

- 每个服务器、轻量防火墙、CloudMonitor、DNS、证书或备份存储变更都在执行
  当时取得负责人授权；不自动扩大云资源。
- 保持 `gongxing-admin`、root 远程登录禁用、密码/交互认证禁用、现有 UFW、
  阿里云 cloud-init 23.2.2-8 apt hold 和 hotplug FIFO 0600 drop-in。
- 80/443 仅按已批准的正式/测试 Nginx 入口开放；8000、5173 和数据库端口永不
  对公网开放。
- production `.env`、htpasswd、私钥、管理员密码、DeepSeek Key 和备份凭据
  只由负责人在服务器或密码管理器填写，不进入终端回显、Git、聊天或日志。

## 1. 可信构建与传输

在 Linux x86_64、CPython 3.12、Node 24.18.0 的可信 Linux/WSL 环境执行：

```bash
deploy/scripts/build-release.sh <git-sha> <output-directory>
deploy/scripts/package-release.sh <output-directory> <git-sha> <archive.tar.gz>
```

构建脚本执行前端 build/lint，预下载经过 `requirements.lock` 哈希验证的纯 wheel，
并用离线临时 venv 验证 wheelhouse。打包脚本生成单一归档及同目录的
`.sha256`。通过 SCP 同时上传二者，不上传源码工作区、`.env`、data、数据库、
PDF、私钥或任何秘密。

服务器先在非 release 目录执行：

```bash
sudo deploy/scripts/verify-release-package.sh \
  --archive <archive.tar.gz> \
  --checksum <archive.tar.gz.sha256> \
  --release <git-sha> \
  --output /opt/gongxing/incoming/<git-sha>
```

校验器拒绝摘要/Git SHA 不符、绝对路径、`..`、链接、特殊文件、源码包、缺失
wheel、wheel 哈希异常，以及 data、`.env`、数据库、PDF和秘密文件。输出目录
及清单应为 root 所有且普通用户不可写。

## 2. 运行环境（单独授权后）

安装 Nginx、Python 3.12 venv 能力和必要系统包，不在服务器安装 Node 或构建
前端。2 GiB 机器建议评估并创建 1 GiB swap；只有观测到确切需求才扩大到
2 GiB。FastAPI systemd 单进程仅监听 `127.0.0.1:8000`。

使用统一的 production 环境目录与文件权限安装模板：

```bash
sudo install -d -o root -g gongxing -m 0750 /etc/gongxing
sudo install -o root -g gongxing -m 0640 \
  deploy/env/gongxing.env.example \
  /etc/gongxing/gongxing.env
```

`/etc/gongxing` 必须为 `root:gongxing 0750`，环境文件必须为
`root:gongxing 0640`；父目录和文件均不得是符号链接、不得组写或被其他用户
写入。这样 `gongxing` 服务账户可遍历目录并读取环境文件。随后只在服务器或
密码管理器中填写真实值，禁止把值回显到终端、Git、CI 或聊天：

```dotenv
APP_ENV=production
TRUSTED_ORIGINS=https://gongxing.novocaine.me
CORS_ALLOWED_ORIGINS=
TRUSTED_PROXY_IPS=127.0.0.1
DATABASE_PATH=/var/lib/gongxing/data/site.db
ADMIN_PASSWORD=<GENERATE_ON_SERVER>
DEEPSEEK_API_KEY=
```

`/var/lib/gongxing/data` 保存 SQLite 与上传，`/var/log/gongxing` 保存应用日志；
目录由应用组按最小权限访问。DeepSeek Key 未启用相关能力时可留空。

## 3. 发布事务

把完整性清单传给部署脚本：

```bash
sudo deploy/scripts/deploy-release.sh \
  --confirm-server \
  --artifact /opt/gongxing/incoming/<git-sha> \
  --release <git-sha> \
  --artifact-manifest /opt/gongxing/incoming/<git-sha>.integrity.json \
  --initial-deploy
```

后续发布把 `--initial-deploy` 替换为
`--confirmed-backup <VERIFIED_SNAPSHOT_ID>`。部署、备份、恢复共享
`/run/lock/gongxing-ops.lock`，发现 `.recover-*.hold` 即停止。

公开 V1 在站外备份完成前发布时，只有负责人明确接受新增数据不可恢复风险后，
才可把 `--confirmed-backup` 替换为 `--accept-no-backup-data-loss-risk`。该开关与
快照参数互斥，且每次发布都必须显式传入；省略两者仍会安全失败。完成站外备份
与恢复演练后恢复使用快照 ID，不把风险开关作为常规发布方式。

锁内顺序固定为：复核已验证目录、复制到临时 release、再次复核、离线创建
venv、用 `--no-index --find-links --require-hashes` 安装 wheel、使用临时 venv
执行 `validate-production-config.py`，然后才进入维护、停止旧服务、切换
`current`、启动和健康检查。配置/权限校验失败发生在切换前，不能影响旧服务。
启动后使用同一套有界就绪等待：固定预算 30 秒，最多请求 15 次；每次健康请求
连接超时和总请求超时均为 1 秒，失败后按固定 1 秒间隔重试，并在每次请求前
确认 `gongxing.service` 仍为 active。只接受 `/api/health` 的成功 HTTP 响应；
服务提前退出立即失败，达到期限仍未就绪也失败，脚本不会自动重启服务。

切换后的失败进入统一回滚；只有服务状态和维护文件解除均成功才返回 0。回滚
完成后仅清理本次 `release_id` 对应、位于固定 releases 根目录、且既不是
`current` 目标也不是旧 `previous_target` 的失败 release。历史有效 release、
持久数据和环境配置不参与清理；清理失败仍返回非零并保留维护状态。

## 4. 正式公网入口、DNS 与 HTTPS（单独授权后）

1. 把 `deploy/nginx/conf.d/gongxing-global.conf` 安装为
   `/etc/nginx/conf.d/gongxing-global.conf`，属主 `root:root`、权限 `0644`。保留
   现有测试站配置及 `/etc/nginx/gongxing.htpasswd`，测试站不得取消 Basic Auth。
2. 安装 `gongxing-bootstrap.conf` 作为正式域名临时 HTTP 站点。它只允许
   `/.well-known/acme-challenge/`，其他请求返回 503，不代理应用；未知 Host
   继续由测试站的默认拒绝块处理。
3. 在现有 Namecheap DNS 添加 `gongxing.novocaine.me -> <SERVER_IP>`；不迁移
   Nameserver、不添加 AAAA，也不修改 `test` 记录。验证权威 DNS 与外部解析后
   用 webroot 为正式域名单独签发证书。
4. 安装 `gongxing-public.conf` 到 `/etc/nginx/sites-available/gongxing-public`，
   检查正式站没有 `auth_basic`，测试站仍引用 htpasswd。两个站点均保留 noindex、
   未知 Host/SNI 拒绝、`/api` 与 `/data` 禁止 SPA 回退、52m 上限和安全代理头。
   `nginx -t` 成功后才启用并 reload。
5. FastAPI 仍只监听回环。用伪造 `Forwarded`/`X-Forwarded-*` 验证 Nginx 覆盖
   输入，并验证 Secure Cookie、CSRF、限流与真实客户端 IP 契约。

发布脚本必须保持 `/opt/gongxing` 与 `/opt/gongxing/releases` 为
`root:gongxing 0751`，使 Nginx 的 `www-data` 仅能穿过父目录读取公开静态文件，
但不能列出父目录。不得递归放宽具体 release、backend、`/etc/gongxing` 或
`/var/lib/gongxing/data`，也不得把 `www-data` 加入 `gongxing` 组。

HTTP-01 续期需要长期保留 80 的 ACME challenge 入口，其余 HTTP 可跳转或拒绝。
启用并验证 Certbot timer，然后执行：

```bash
sudo install -o root -g root -m 0755 deploy/scripts/certbot-reload-nginx.sh \
  /etc/letsencrypt/renewal-hooks/deploy/certbot-reload-nginx.sh
sudo python3 deploy/scripts/verify-certbot-hook.py \
  --hook /etc/letsencrypt/renewal-hooks/deploy/certbot-reload-nginx.sh
sudo certbot renew --dry-run --run-deploy-hooks
sudo /etc/letsencrypt/renewal-hooks/deploy/certbot-reload-nginx.sh
```

hook 必须为 root 所有、普通用户不可写；它必须先 `nginx -t`，失败绝不 reload，
成功才 reload。证书私钥权限保持 Certbot 默认安全边界，不进入 Git、发布包或
应用备份。

## 5. 站外备份（公开 V1 上线后补齐）

当前没有 OSS 或其他站外仓库，`gongxing-backup.timer` 不得启用。负责人已接受
公开 V1 在站外备份前上线的临时风险：服务器故障或误删可能导致新增数据无法
恢复。站外备份和恢复演练不阻塞本次发布，但必须作为上线后的独立工作完成；
服务器同盘目录不算站外备份。

批准后配置 `OFFSITE_BACKUP_APPROVED=1` 与远程 restic repository；脚本拒绝
其他批准值、相对/本地路径、`file:`、localhost 和回环地址。备份期间 Nginx
返回 503/Retry-After，脚本 checkpoint SQLite、生成一致快照、完整性检查并只
收集有效 PDF；trap 只恢复备份前原本运行的服务状态。完成一次隔离恢复、
SQLite integrity check 和测试 PDF 校验后才允许真实数据。

## 6. 升级、回滚与排障

升级前确认站外快照 ID、磁盘空间、锁和无 recovery hold。失败时保持维护状态，
检查 `systemctl status gongxing`、`journalctl -u gongxing`、Nginx 安全访问日志和
部署日志；日志不得含查询字符串、密码或 Key。后续部署原服务运行时回滚链接
并尝试恢复旧服务，命令仍返回失败等待人工确认；原服务停止则保持停止。

服务器重启后验证 gongxing/Nginx/Certbot timer 的期望启用状态、UFW、时间同步、
无失败 unit、正式站匿名访问、测试站 Basic Auth、`/api/health` 和静态资源。
公开 V1 上线后仍应尽快完成站外备份；在此之前新增数据按已接受风险运行。

## 7. Git 与服务器专属文件

进入 Git：无秘密的 Nginx/systemd 模板、示例 env、构建/校验/发布/备份脚本、
测试和文档。只留服务器：真实 env、htpasswd、证书私钥、SSH/备份密钥、
SQLite、上传、日志、恢复 hold、发布目录和目标机生成的凭据。

## 8. 动态管理 IP 与监控

家庭公网 IP 变化时，从阿里云控制台先新增新的 `/32` TCP 22 规则，在 UFW
保护会话中同步新增并验证独立 SSH，再删除旧规则。失联时使用阿里云控制台
远程连接恢复，不能临时开放 `0.0.0.0/0`。CloudMonitor 告警只使用确认免费的
既有能力，创建/修改前再次授权；不升级或修改当前有警告的厂商 agent。
