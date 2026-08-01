# DigitalOcean 受限测试部署运行手册

> 本文件是阶段 A 生成的无秘密操作模板。它不代表阶段 B 已获批准。
> 任何云资源、DNS、证书或服务器写操作都必须等负责人再次明确批准。

## 1. 阶段 B 前置门禁

执行人先逐项确认：

- 当前发布提交已合并到干净的 `main`，CI 全绿，另一位开发者已复审。
- 资源仍为 SGP1、Ubuntu 24.04 LTS、Basic 1 vCPU / 2 GiB、BLR1
  私有 Spaces，最高预计约 17 美元/月。
- DigitalOcean 和 Namecheap 2FA、离线恢复码、独立成员权限已经完成。
- 负责人已确认 SSH 来源 IP、Basic Auth 用户名单、账单提醒收件人、
  销毁负责人和维护窗口。
- 秘密只在密码管理器、云控制台或服务器无回显终端填写。

创建资源后立即记录 Droplet ID、IPv4、区域、创建时间、预计费用和销毁
责任人，但不把 Token、密钥或密码写入记录。

### 中国大陆访问与境外数据边界

`test.novocaine.me` 使用普通 HTTPS，技术上不要求 VPN；但境外 SGP1
线路可能受运营商、时段和跨境路由影响，不能在部署前承诺固定延迟或始终
可达。不要只在开发者自己的网络测速。上线验收应从中国电信、联通、移动
各至少一个真实网络，以及一个境外网络测试：

```bash
curl -o /dev/null -sS \
  -w 'dns=%{time_namelookup} connect=%{time_connect} tls=%{time_appconnect} first=%{time_starttransfer} total=%{time_total}\n' \
  https://test.novocaine.me/
```

每个网络在工作日白天和晚高峰各测试至少 10 次，记录中位数和最差值，
再用 `mtr`/`traceroute` 辅助定位路由；浏览器同时测首页首屏、JS 下载、
API、PDF 首开和连续下载。Basic Auth 401 也能用于 DNS/TCP/TLS 测时，
但完整页面测试必须由授权测试者进行。若多运营商持续不可接受，再比较
其他区域或国内合规托管，不能仅凭单次 ping 迁移。

Droplet、Spaces、日志和备份均在境外。受限测试只允许虚构昵称、临时
留言、测试 PDF 和非个人数据；不得上传真实联系方式、学生名单、肖像、
成绩或其他个人信息。真实课件也必须先确认版权和内容边界。若未来收集
真实个人数据、面向中国大陆公开运营或改变数据用途，应先单独完成合规、
隐私和数据跨境评审，不能沿用本测试环境结论。

## 2. 主机初始化与网络

使用 Ubuntu 24.04 LTS。首个 root SSH 会话只用于建立运维账户，之后：

1. 为两位开发者分别创建非 root 运维账户，加入 `sudo`，各自安装自己的
   SSH 公钥；禁止共享私钥。
2. 分别验证新账户 SSH 和 sudo 后，再禁用 SSH 密码登录和 root 登录。
3. DigitalOcean Cloud Firewall 入站仅允许：
   - TCP 22：两位开发者当时的可信公网 IP/CIDR；
   - TCP 80、443：所有 IPv4/IPv6；
   - 不开放 8000、5173 或数据库端口。
4. 主机 UFW 建立相同规则，启用前保持一个已验证的 SSH 会话，防止锁死。
5. 出站保留系统更新、DNS、NTP、HTTPS、Spaces 和 DeepSeek 所需访问。
6. 检查 `unattended-upgrades` 与 `apt-daily-upgrade.timer` 已启用，只使用
   Ubuntu 官方安全源；不自动重启，重启需求进入人工维护窗口。

校验命令只记录状态，不记录认证材料：

```bash
ss -lntup
sudo sshd -t
sudo ufw status verbose
systemctl status unattended-upgrades apt-daily-upgrade.timer
```

## 3. 账户、目录和文件安装

建立无登录 `gongxing` 服务用户及下列目录：

```text
/opt/gongxing/releases/             root:gongxing 0750
/opt/gongxing/current               指向当前不可变 release
/var/lib/gongxing/data/             gongxing:gongxing 0750
/var/lib/gongxing/data/uploads/     gongxing:gongxing 0750
/var/lib/gongxing/restore-drill/    root:root 0700
/var/backups/gongxing/              root:root 0700
/etc/gongxing/                      root:gongxing 0750
/var/www/letsencrypt/               root:www-data 0755
```

安装仓库中的 systemd、Nginx snippet、脚本和环境模板时，真实
`gongxing.env` 使用 `root:gongxing 0640`，`backup.env`、
`restic-password` 和 `gongxing.htpasswd` 使用 `root:root 0600`。
这些文件不得复制回开发机、Git、CI 工件或备份。

restic 密码另存一份与 Droplet 和 Spaces 凭据分离的离线恢复副本，并由
负责人实际使用该副本完成恢复演练。Nginx 日志保存在
`/var/log/nginx/gongxing_access.log` 和 `gongxing_error.log`，只允许
root/adm 读取并沿用 logrotate；应用、备份和健康日志进入 systemd
journal。日志保留期在阶段 B 按无真实个人数据的最小化原则确认，任何
日志都不得记录查询字符串、认证头、Cookie、密码、Token 或请求体。

`/etc/gongxing/gongxing.env` 必须逐项填写：

| 变量 | 受限测试值/规则 |
|---|---|
| `APP_ENV` | `production` |
| `TRUSTED_ORIGINS` | 仅 `https://test.novocaine.me` |
| `CORS_ALLOWED_ORIGINS` | 留空，同域不启用 CORS |
| `TRUSTED_PROXY_IPS` | 仅 `127.0.0.1` |
| `ADMIN_PASSWORD` | 密码管理器生成，至少 12 字符 |
| `ADMIN_SESSION_TTL_SECONDS` | `7200`，除非另行评审 |
| `RATE_LIMIT_MAX_BUCKETS` | `20000` |
| `COURSEWARE_MAX_UPLOAD_MB` | `50` |
| `DATABASE_PATH` | `/var/lib/gongxing/data/site.db` |
| `DEEPSEEK_API_KEY` | 负责人直接填写；不测试 AI 时可先留空 |

## 4. 无公开窗口地启用域名与 HTTPS

顺序不可交换：

1. 为每位测试者逐用户运行交互式 `htpasswd -B`，先生成
   `/etc/nginx/gongxing.htpasswd`；禁止 `-b` 和共享账号。
2. 安装并启用 `gongxing-bootstrap.conf`，执行 `nginx -t` 后 reload。
   此时 80 除 ACME challenge 外只返回 503，应用尚未暴露。
3. 使用 Droplet IP 和伪造 Host 验证未知 Host 被拒绝；确认 8000/5173
   无法从公网连接。
4. 才在现有 Namecheap Advanced DNS 增加 `test` A 记录；不迁移
   Nameserver，不创建 DigitalOcean DNS zone。
5. 从中国大陆和至少一个境外网络执行 `nslookup`/`dig`，确认 A 记录
   已解析到目标 IPv4；检查不存在冲突的 AAAA/CNAME。
6. 使用 Certbot webroot 模式签发 `test.novocaine.me` 证书。签发期间
   不允许 Certbot 临时改写为公开应用站点。
7. 安装最终 `gongxing-test.conf`，先执行 `nginx -t`。确认配置已经引用
   Basic Auth 文件后，才第一次启用 443。
8. 匿名请求必须为 401；有效 Basic Auth 才能看到站点。确认后再让
   80 跳转到 HTTPS。

## 5. 构建、首次部署与自动启动

发布物只能来自经过复审的干净提交：

1. 在 Linux Python 3.12、Node 24.18.0、npm 11.16.0 环境运行
   `deploy/scripts/build-release.sh <git-sha> <new-output-dir>`。
2. 核对 `RELEASE_BUILD_MANIFEST.txt` 的 Git SHA 和锁文件哈希；发布包
   不得含 `.env`、数据库、PDF、htpasswd 或备份凭据。
3. 首次部署前只创建空的数据目录和空的 `uploads/`。确认不存在
   `/opt/gongxing/current`、任何旧 release、`site.db`、上传文件或其他
   持久数据，并确认 `gongxing.service` 没有运行。
4. 首次且仅首次使用：

   ```bash
   sudo /usr/local/lib/gongxing/deploy-release.sh --confirm-server \
     --initial-deploy \
     --artifact <发布物绝对路径> \
     --release <Git-SHA>
   ```

   首次模式不接受 `--confirmed-backup`。健康检查通过后服务保持运行并
   解除维护状态；失败时删除错误的 `current` 链接、停止服务并保留维护
   状态。任何已有 release、数据库、上传文件或其他持久数据都会使首次
   模式安全失败，不能把它作为跳过备份的开关。
5. 首次部署和冒烟通过后立即创建、列出并恢复检查第一份 restic snapshot。
   此后的每次升级只允许使用：

   ```bash
   sudo /usr/local/lib/gongxing/deploy-release.sh --confirm-server \
     --confirmed-backup <已验证的-snapshot-ID> \
     --artifact <发布物绝对路径> \
     --release <Git-SHA>
   ```

   后续模式没有有效 snapshot ID 会在修改服务前失败；与
   `--initial-deploy` 同时传入也会拒绝。脚本保持升级前服务状态，失败时
   回退旧链接并保留维护状态等待人工确认。

   cleanup 固定按三阶段执行：先根据主流程结果和最终服务状态确定整个
   部署是否成功；再对已经切换但最终失败的 release 统一停止并回滚；最后
   恢复部署前的运行/停止状态。首次部署即使健康检查曾通过，只要服务在
   最终检查前退出，也会删除 `current` 并保持停止。后续部署如果新 release
   在最终恢复运行时失败，会先切回旧 release，再单独尝试启动旧服务；即使
   旧服务恢复成功，部署命令仍返回失败且维护状态继续保留，必须人工确认。
6. 启用 `gongxing.service`、备份 timer 和健康观察 timer；Nginx
   由系统服务管理。

重启验收：

```bash
sudo systemctl enable nginx gongxing.service
sudo systemctl enable --now gongxing-backup.timer gongxing-health.timer
sudo reboot
```

重连后确认 Nginx、FastAPI 自动启动，数据库和上传目录仍在，匿名访问
仍为 401，认证后 `/api/health` 正常。

## 6. 受限线上冒烟测试

全程只使用临时内容和专门制作的无个人数据测试 PDF：

1. 未认证访问首页、`/api/health`、`/data/...` 均为 401；响应包含
   `X-Robots-Tag: noindex, nofollow`、`Strict-Transport-Security:
   max-age=86400` 和预期安全头；HSTS 不得包含 `includeSubDomains`
   或 `preload`。
2. 验证未知 Host、直接 IP、8000、5173 无法取得应用内容。
3. Basic Auth 后检查首页、路由刷新、404、API 健康和静态资源压缩；
   `/api`、`/data` 的不存在路径不得返回 `index.html`。
4. 在真实浏览器登录管理员，确认 session Cookie 有 `Secure`、
   `HttpOnly`、`SameSite=Strict`、`Path=/api`，无宽泛 `Domain`。
5. 在浏览器开发者工具验证 CSRF：正确 Token 写操作成功，缺失/错误
   Token 为 403；不得复制 Token 到聊天或日志。
6. 上传小型测试 PDF 后下载并校验；超过 50 MiB 的测试文件由应用精确
   返回 413，Nginx 52m 只作为 multipart 外层上限。
7. 从两个实际公网出口分别测试限流；带伪造 `Forwarded`、
   `X-Forwarded-For` 请求不能控制应用看到的来源。对照 Nginx 安全日志
   中的连接 IP，日志不得出现查询字符串、Cookie 或认证信息。Bootstrap
   未知 Host/测试 Host、最终 HTTP 未知 Host/跳转和 HTTPS 未知 SNI
   必须关闭访问日志；只有 HTTPS 应用站点使用 `$uri` 安全日志。
8. 创建临时留言、问答和联系记录，验证后删除；不输入真实个人信息。
9. 触发一次计划备份，确认维护期为 503 且有 `Retry-After`，健康观察
   跳过，不重启后端。
10. 完成一次隔离恢复和 SQLite/PDF 完整性检查，再实际恢复一个 Spaces
    历史版本及一个 delete marker。

所有冒烟结果按 `docs/test-plan.md` 记录浏览器、网络、Git SHA、时间和
结果，不记录秘密。只有以上项目通过，才能按“先公开资料、后课件、
最后仍不得上传真实个人数据”的顺序上传真实课件。测试环境不得直接改成
公开环境。

## 7. 升级、回滚与故障排查

升级：

1. CI 与复审通过；
2. 人工执行并验证备份，记录 snapshot ID；
3. 构建不可变发布物并核对 Git SHA；
4. 在维护窗口调用部署脚本；
5. 运行线上冒烟测试，保留旧 release 至少两个成功发布周期。

回滚优先只切换 `/opt/gongxing/current` 到上一已验证 release；若版本包含
数据库迁移，则必须使用对应恢复方案，当前项目未经单独评审不得引入自动
数据库迁移。恢复数据前先保留故障现场并创建 `.recover-*.hold`，该标记会
阻止备份和部署。

排查顺序：

```text
DNS/证书 -> Cloud Firewall/UFW -> nginx -t 与日志
-> systemd 状态/journal -> 127.0.0.1:8000 健康
-> 环境变量权限 -> 磁盘/内存 -> SQLite/PDF 完整性
```

不要在故障排查时打印完整环境、Cookie、Authorization、Token 或请求体。
HTTP 短暂失败只告警；只有 systemd 观察到进程退出才自动恢复。

## 8. 备份、监控、扩容和销毁

- 每日检查最近一次 restic snapshot；每月执行一次隔离恢复演练，每次
  发布前人工确认可用 snapshot。
- 保留每日 7、每周 4、每月 3；先查看 dry-run，再明确启用 prune。
- Spaces 开启版本控制和生命周期后，实际演练历史版本/delete marker；
  配置用高权限 Key 用后撤销，服务器只留 bucket 范围的备份 Key。
- 告警至少覆盖主机不可达、CPU、内存、磁盘、备份失败、健康失败和
  TLS 到期；账单提醒设为 18 美元并人工核对，不视为硬上限。
- 持续 CPU 超过 70%、内存/磁盘超过 80%、备份窗口明显增长或 SQLite
  锁竞争增多时先分析；单机 2 GiB 不够再评审 Resize。扩大 worker 前
  必须先替换单进程内存会话/限流设计和 SQLite 写入模型。
- 测试结束按 `deploy/phase-b-resource-inventory.md` 删除 DNS、Droplet、
  凭据、Spaces 当前与历史对象、delete marker 和 bucket，并确认账单停止。

## 9. Git 与服务器边界

进入 Git：无秘密的 Nginx/systemd 模板、脚本、CI、锁文件、示例环境、
测试、运行手册和生命周期 JSON。

只留服务器/控制台：production env、Basic Auth 文件、管理员密码、
DeepSeek Key、restic 密码、Spaces/API/Namecheap 凭据、SSH 私钥、
数据库、上传文件、日志、证书私钥和恢复产物。

## 10. 官方参考

- DigitalOcean production-ready Droplet：
  https://docs.digitalocean.com/products/droplets/getting-started/recommended-droplet-setup/
- DigitalOcean Cloud Firewall：
  https://docs.digitalocean.com/products/networking/firewalls/how-to/create/
- DigitalOcean Spaces versioning：
  https://docs.digitalocean.com/products/spaces/how-to/enable-versioning/
- Ubuntu automatic security updates：
  https://ubuntu.com/server/docs/how-to/software/automatic-updates/
- Nginx Basic Auth：
  https://nginx.org/en/docs/http/ngx_http_auth_basic_module.html
