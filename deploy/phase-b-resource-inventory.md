# 阶段 B 资源与二次授权清单

本文件只用于阶段 B 授权。没有负责人再次明确同意时，不得创建下列资源。

| 资源 | 地区 | 预计月费 | 测试结束时销毁 |
|---|---|---:|---|
| Ubuntu 24.04 LTS Basic 1 vCPU / 2 GiB Droplet | SGP1 | $12 | Droplet及其磁盘 |
| 私有 Spaces bucket | BLR1 | $5 | 当前对象、历史版本、delete marker、bucket |
| Cloud Firewall与Monitoring | SGP1 | $0 | 防火墙、监控和告警 |
| Namecheap `test` A记录 | 现有Namecheap DNS | $0 | A记录 |

预计合计：约 `$17/月`，不含税费、域名既有费用和超额流量。

不启用自动 Droplet Backup，因为整机镜像无法排除 Basic Auth、
production env 和备份凭据。SQLite与有效PDF使用restic加密至Spaces。

创建前必须再次确认：

- [ ] 负责人明确批准阶段 B 和上述最高月费。
- [ ] DigitalOcean与Namecheap已启用2FA。
- [ ] 两位协作者使用独立账号或团队权限。
- [ ] SSH来源IP、销毁负责人和账单提醒收件人已经确定。
- [ ] Basic Auth逐用户名单由负责人在密码管理器准备。
- [ ] 没有任何秘密粘贴到Codex、Git、CI或聊天。

销毁完成标准：

- [ ] 删除Namecheap `test` A记录。
- [ ] 删除Droplet并确认停止计算费用。
- [ ] 撤销SSH/API/Spaces和应用凭据。
- [ ] 删除Spaces当前对象、历史版本和delete marker。
- [ ] 删除bucket；如果这是最后一个bucket，确认Spaces订阅停止。
- [ ] 检查最终账单并记录销毁时间。
