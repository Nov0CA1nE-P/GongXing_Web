# 阿里云香港受限测试部署运行手册

本手册用于 `test.novocaine.me`。所有 `<SERVER_IP>`、`<PRIVATE_IP>`、
`<ADMIN_HOME_IP>` 和凭据均为运行时占位符，禁止把真实值提交到仓库。

## 0. 强制门禁

- 每个服务器、轻量防火墙、CloudMonitor、DNS、证书或备份存储变更都在执行
  当时取得负责人授权；不自动扩大云资源。
- 保持 `gongxing-admin`、root 远程登录禁用、密码/交互认证禁用、现有 UFW、
  阿里云 cloud-init 23.2.2-8 apt hold 和 hotplug FIFO 0600 drop-in。
- 80/443 当前关闭；8000、5173 和数据库端口永不对公网开放。
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

创建 `/etc/gongxing/gongxing.env`，属主 `root:gongxing`，权限 `0640` 或更严：

```dotenv
APP_ENV=production
TRUSTED_ORIGINS=https://test.novocaine.me
CORS_ALLOWED_ORIGINS=
TRUSTED_PROXY_IPS=127.0.0.1
DATABASE_PATH=/var/lib/gongxing/data/site.db
ADMIN_PASSWORD=<GENERATE_ON_SERVER>
DEEPSEEK_API_KEY=
```

`/var/lib/gongxing/data` 保存 SQLite 与上传，`/var/log/gongxing` 保存应用日志；
目录由应用组按最小权限访问。DeepSeek Key 在受限测试可留空。

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

锁内顺序固定为：复核已验证目录、复制到临时 release、再次复核、离线创建
venv、用 `--no-index --find-links --require-hashes` 安装 wheel、使用临时 venv
执行 `validate-production-config.py`，然后才进入维护、停止旧服务、切换
`current`、启动和健康检查。配置/权限校验失败发生在切换前，不能影响旧服务。
切换后的失败进入统一回滚；只有服务状态和维护文件解除均成功才返回 0。

## 4. 公网入口、DNS 与 HTTPS（单独授权后）

1. 先生成逐用户 `/etc/nginx/gongxing.htpasswd`，设为 root 所有且不可被普通
   用户写入；安装未知 Host 拒绝和 `gongxing-bootstrap.conf`。bootstrap 的
   80 只允许 `/.well-known/acme-challenge/`，其他请求 404/维护，不代理应用。
2. 经授权在轻量防火墙和 UFW 开放 80/443。此时 443 尚无站点，应用没有
   无认证公开窗口。
3. 在现有 Namecheap DNS 添加 `test.novocaine.me -> <SERVER_IP>`；不迁移
   Nameserver。验证权威 DNS 与外部解析后签发证书。
4. 安装最终 Nginx 配置前检查其中已含全站 Basic Auth、noindex、未知
   Host/SNI 拒绝、`/api` 与 `/data` 禁止 SPA 回退、52m 传输上限和安全代理头。
   `nginx -t` 成功才 reload，第一次启用 443 时认证必须已经生效。
5. FastAPI 仍只监听回环。用伪造 `Forwarded`/`X-Forwarded-*` 验证 Nginx 覆盖
   输入，并验证 Secure Cookie、CSRF、限流与真实客户端 IP 契约。

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

## 5. 站外备份（当前未授权）

当前没有 OSS 或其他站外仓库，`gongxing-backup.timer` 不得启用。真实联系人
数据或课件上传前，负责人需要单独批准远程加密仓库、地域、费用、密钥保管、
保留策略和删除流程。服务器同盘目录不是站外备份。

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
无失败 unit，以及 Basic Auth、`/api/health` 和静态资源。线上只使用测试 PDF、
临时账号和虚构数据冒烟；清理临时数据并确认备份恢复后，才按审批顺序上传
真实课件。

## 7. Git 与服务器专属文件

进入 Git：无秘密的 Nginx/systemd 模板、示例 env、构建/校验/发布/备份脚本、
测试和文档。只留服务器：真实 env、htpasswd、证书私钥、SSH/备份密钥、
SQLite、上传、日志、恢复 hold、发布目录和目标机生成的凭据。

## 8. 动态管理 IP 与监控

家庭公网 IP 变化时，从阿里云控制台先新增新的 `/32` TCP 22 规则，在 UFW
保护会话中同步新增并验证独立 SSH，再删除旧规则。失联时使用阿里云控制台
远程连接恢复，不能临时开放 `0.0.0.0/0`。CloudMonitor 告警只使用确认免费的
既有能力，创建/修改前再次授权；不升级或修改当前有警告的厂商 agent。
