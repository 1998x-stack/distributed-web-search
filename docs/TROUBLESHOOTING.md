# 故障排查速查表

## 容器已启动，其他机器连不上

- 在目标主机上运行 `curl -I http://localhost:8090/`。
- 从另一主机运行 `curl -I http://NODE_IP:8090/`。检查 Docker Desktop/Ubuntu 防火墙是否允许可信来源访问 TCP 8090。
- 查看 `docker compose -f infra/compose.yml --env-file .env ps` 和日志。
- 对 Mac 使用真正的 Wi-Fi/Ethernet IP，而不是 Docker VM 私网 IP。确保 Mac 没有休眠。

## 首页可访问，但 Peer 显示 Virgin

- 在 Network 页检查 `homeweb`，不能是 `freeworld`。
- 检查 `runtime/yacy.init` 的 `network.unit.definition` 是否确实指向私有网络文件。
- 确认 Peer 的 Static IP 是其他机器可访问的地址。
- A 首次没有外部 peers 时需成为 Principal，发布正确 seed 文件后再加入其他节点。
- B/C 无法发现 A 时，检查 `curl -fsS http://IP_A:8090/seed.txt` 与网络定义中的 seedlist0。
- 若错误地在首次启动时进入 freeworld，不建议直接复用受污染的 DATA；先备份隔离，再人工决定是否重建新卷。

## Seed URL 404 / 返回 HTML

- 检查 Seed Upload 设为 File，`seedFilePath=DATA/HTDOCS/seed.txt`。
- 查看 `docker exec route-a-ubuntu-a ls -la /opt/yacy_search_server/DATA/HTDOCS`。
- 检查发布路径 `/seed.txt` 是否由 YaCy 的用户 HTDOCS 提供；实际部署以浏览器和 curl 检查为准。
- 在管理员页面重新保存 seed 设置；有些发行版本的 seed 更新不是立即触发。
- 无有效种子文件时不要启动后续节点。

## 3 个 Peer 可见但跨节点搜索为空

- 分别在每台的 `resource=local` 下验证已索引不同页面。
- 使用 `resource=global` 发起远程搜索，不要混淆 local/global。
- 检查远程搜索设置、网络名单、Peer 状态和请求失败日志。
- 使用明确的独有词而非常见搜索词，等待索引完成。DHT 不产生流量不一定是故障，尤其是 3 节点。

## 爬虫并没有均匀分配

YaCy 的 Remote Crawl 不是中心化的工作队列。必须启用接收端的远程爬取处理，并观察任务转移和实际抓取计数。如果需要全局精确分配、可靠队列和严格去重，请改用 Route B。

## 资源耗尽 / OOM

查看 `docker stats`、`df -h`、YaCy 管理页面内的 Memory/Queues。调整 `.env` 中的 `YACY_JAVASTART_XMX`（例如 `Xmx1200m`），不要给 JVM 分配超过宿主机可用的 RAM。Mac 的 Docker Desktop 还有限制在 Linux VM 内的资源配额。

## 数据卷和备份

```bash
docker volume ls | grep route_a_
bash scripts/backup.sh
```

当前没有提供自动化“清空并恢复”脚本，因为恢复前需要明确选择目标卷和验证备份，以避免误删真实索引数据。建议在隔离的新卷上先试恢复，不能直接覆盖运行中的 YaCy 数据卷。
