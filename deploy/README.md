# 阿里云香港公开 V1 部署资产

本目录只保存无秘密、可审查的仓库部署资产。平台迁移边界见
`docs/alicloud-hk-deployment-assets.md`，实际服务器操作顺序见
`docs/deployment-runbook.md`。

```text
deploy/
  env/          服务器环境变量示例
  nginx/        共用 HTTP 配置、正式公开站与保留的受限测试站配置
  scripts/      构建、打包、校验、部署、备份、恢复和健康观察脚本
  systemd/      FastAPI、备份与健康观察 units
  tests/        部署资产静态契约测试
```

仓库脚本不修改阿里云控制面、DNS 或证书。开放端口、CloudMonitor、DNS、
证书签发和站外备份存储都需要执行时再次获得负责人授权。

发布链路为：可信 Linux/WSL 构建 release 和 wheelhouse，生成单一归档及
归档外 SHA-256，上传两者，在服务器以 `verify-release-package.sh` 安全解包
并生成目录完整性清单，最后把清单交给 `deploy-release.sh`。部署脚本会在
同一把操作锁内复核目录，离线安装 Python wheel，并在切换 `current` 前执行
production 配置检查。

`deploy-release.sh` 的部署门禁互斥：

- 只有绝对空状态的第一次部署使用 `--initial-deploy`；
- 后续部署默认使用 `--confirmed-backup <已验证 snapshot ID>`；
- 负责人每次明确接受数据丢失风险时，可改用
  `--accept-no-backup-data-loss-risk`，但不能与 snapshot ID 同时使用；
- 首次模式不能与后续发布参数共用，也不能用于已有 release 或持久数据。

备份与恢复脚本只有在 `OFFSITE_BACKUP_APPROVED=1` 且 restic 仓库为已审批
的非本机远程地址时才运行；服务器同盘目录不构成站外备份。
