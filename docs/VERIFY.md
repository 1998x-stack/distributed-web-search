# 三节点组网与搜索验收

## 验收等级（由弱到强）

| 等级 | 需观察到的事实 | 表示什么 |
|---|---|---|
| L0 配置正确 | 三份网络定义完全一致，且网络名 homeweb | 防止误连公用网络 |
| L1 服务可用 | 三个独立的 YaCy 搜索首页可访问 | 容器健康，不代表组网 |
| L2 Bootstrap 成功 | Ubuntu A/B Seed List 非空、可远程读取 | 新节点具备入口 |
| L3 Peer 收敛 | 每台 Network 页面均看到另外两台，且没有 freeworld 公共 Peer | 独立 P2P 网络 |
| L4 分布式搜索 | 各节点拥有不同本地文档，global 搜索返回远端命中 | 联合检索成立 |
| L5 协作爬取 | 远程爬取任务实际在其他节点执行 | Remote Crawl 机制成立 |
| L6 DHT 交换 | 可观察到实际的索引块发送/接收 | DHT 数据交换成立（不可仅靠小规模 3 节点推断） |

**特别说明：YaCy DHT 在小网络上的分布式索引行为有规模门槛和实现细节。三台机器的 L4 成功不等价于 L6 成功；不要把 Remote Search 误认为 DHT 索引已经在三机间分布。**

## L0：隔离性

各机器检查本地 `runtime/yacy.network.route-A.unit`：

```bash
grep -E '^(network.unit.name|network.unit.dht|network.unit.bootstrap.seedlist)' runtime/yacy.network.route-A.unit
grep '^network.unit.definition=' runtime/yacy.init
```

预期 `homeweb`，DHT 配置 `true`，两条 bootstrap URL 只指向 IP_A/IP_B（端口 8090）。如果安装前已有 YaCy 数据卷属于 freeworld，本项目会拒绝重用。

## L1–L2：服务与种子列表

```bash
bash scripts/cluster-check.sh IP_A IP_B IP_C
curl -i http://IP_A:8090/seed.txt
curl -i http://IP_B:8090/seed.txt
```

Seed 文件必须包含 YaCy 的 peer seed 信息；HTTP 200、非空只能作为初步证据，若内容是错误 HTML 则仍失败。如果 A 还是 Virgin，请检查 Static IP、File 上传方式、文件所在目录与读写权限。

## L3：Peer 收敛

分别打开：

- `http://IP_A:8090/Network.html`
- `http://IP_B:8090/Network.html`
- `http://IP_C:8090/Network.html`

核对三个节点名称、Peer 状态、Peer 地址均正确。允许 Mac 因端口/睡眠限制临时处于 Junior；若始终 Virgin，检查容器端口映射和网络发现。**仅仅看到三份容器日志不能通过 L3。**

## L4：验证真正的跨节点搜索

1. 在 Ubuntu A、Ubuntu B 分别使用 `CrawlStart_p.html`，爬取两个你有权限抓取且允许 robots.txt 抓取的公开测试网站，各限制 10～20 页、抓取深度 0–1；不要在 A、B 上导入完全相同的网站。
2. 待两节点本地索引完成，用 YaCy 的原生搜索 API 对比 `resource=local` 与 `resource=global`。选择在 B 本地能搜索到、A 本地搜索不到的专有词汇。

```bash
# A 节点，只搜索本地索引
curl -G 'http://IP_A:8090/yacysearch.json' \
  --data-urlencode 'query=TEST_UNIQUE_TERM' \
  --data-urlencode 'resource=local'

# A 节点，联合查询网络其他 peers
curl -G 'http://IP_A:8090/yacysearch.json' \
  --data-urlencode 'query=TEST_UNIQUE_TERM' \
  --data-urlencode 'resource=global'
```

若 A 的 global 查询成功返回 B 的文档而 A local 无命中，便验证了**跨节点检索**。这个判断需要真实响应和文档 URL，不能只看 HTTP 状态码。

## L5：远程爬取

在 Ubuntu A 的 YaCy 管理界面确认 Remote Crawl 策略已开启，B/C 节点允许接受并处理远程抓取任务。通过 Crawl/Queue 监控观察：任务在 A 被分发，B/C 的远程队列和抓取计数相应增加。请避免同时让三个节点以高并发抓取同一外部站点；默认没有 Redis 那样的强一致去重/全局站点限速。

## L6：DHT 分发

在 Network/Performance/DHT 监控中持续观察索引发送与接收统计。**三 Peer 不保证产生可观测的 DHT 数据交换**；YaCy 某些版本的小网络优先采用网络范围搜索。不要为制造假象而强制修改接收计数。系统的能力边界可见 [ARCHITECTURE.md](ARCHITECTURE.md)。

## 故障注入

- 停掉 Mac：Ubuntu A/B 仍可访问本地搜索，Mac 爬虫中止；记录 A/B global 搜索退化。
- 停掉 B：A Seed List 仍可供新 Peer Bootstrap，但 B 的本地索引不能凭空复制到 A。
- 停掉 A：已经相互发现的 B/C 可能继续；新节点可尝试 B 的 Seed List，但这依赖 B 先晋级 Principal。
- 恢复各节点：确认 Persistent DATA 数据仍存在、Peer 列表收敛、搜索不因重启全部丢失。
