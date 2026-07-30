# 受限测试部署模板

本目录只保存无秘密的阶段 A 模板。完整边界、执行顺序和验收要求见
`docs/deployment-stage-a.md`，阶段 B 获批后的逐步操作见
`docs/deployment-runbook.md`。

```text
deploy/
  env/          服务器环境变量示例
  nginx/        证书前 bootstrap 与最终受限站点配置
  scripts/      构建、部署、备份、恢复演练和健康观察脚本
  spaces/       阶段 B 批准后才可使用的版本控制生命周期模板
  systemd/      FastAPI、备份与健康观察 units
  tests/        部署资产静态契约测试
```

任何带 `--apply`、`--confirm-server` 或云平台写权限的操作都属于阶段 B。
阶段 A 不运行这些操作。

`deploy-release.sh` 的部署门禁互斥：

- 只有绝对空状态的第一次部署使用 `--initial-deploy`；
- 后续部署必须使用 `--confirmed-backup <已验证 snapshot ID>`；
- 两个参数不能同时出现，首次模式也不能用于已有 release 或持久数据。
