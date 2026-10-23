# Route A 设计与能力边界

## 组件及数据流

```text
                     HTTP / TCP 8090 (trusted LAN / VPN)
                      private homeweb network definition
 Ubuntu A                      Ubuntu B                     macOS C
 +----------------+           +----------------+          +----------------+
 | YaCy crawler   | <-------> | YaCy crawler   | <------> | YaCy crawler   |
 | Local Solr     |  peer P2P | Local Solr     | peer P2P | Local Solr     |
 | Search UI/API  | <-------> | Search UI/API  | <------> | Search UI/API  |
 | Seed Principal |           | Seed Principal |          | Non-principal  |
 +----------------+           +----------------+          +----------------+
        |                             |                           |
    DATA volume                   DATA volume                  DATA volume
```

- 每个节点是一个完整的 YaCy 实例，并非共享一个 Solr 数据目录。
- 网络定义一致：`network.unit.name=homeweb`，引导地址是 Ubuntu A/B 在 8090 暴露的 `seed.txt`。
- 在首次启动前将修改后的 `defaults/yacy.init` 和私有 `defaults/yacy.network.route-A.unit` 以只读挂载注入。保留镜像的绝大多数默认值。
- `staticIP` 是**宿主机可互访地址**，不是容器内部地址。
- 每台机器独立持久化存储在 Docker 命名卷中。
- Bootstrap 只用于 Peer 发现，它不是中央分布式调度器，也不是统一的索引数据库。

## 为什么不直接共享单个 DATA？

YaCy 内嵌的 Solr/索引数据库并不是多主共享文件系统模型。三个容器挂载同一个 DATA 路径会造成索引并发访问与损坏风险。该方案采用各节点本地索引、通过 YaCy 的远程搜索及 P2P 协议实现联合能力。

## 三机可验证什么

1. 节点发现与网络隔离：是。
2. 三机可分别抓取互联网网页：是（需合法合规和站点许可）。
3. 跨节点搜索：可通过 `resource=global` 验证。
4. 远程抓取协作：可以配置 YaCy Remote Crawl，但不会自动将所有 URL 公平分配给三机。
5. 分布式 DHT：YaCy 支持，但**三机无法保证实际发生 DHT 数据块再平衡**。正式验收必须查看 DHT send/receive 统计。
6. 节点级持久化：每机独立卷，重启仍保留本地数据。
7. HA：不是强可用架构；当前没有自动故障迁移、索引副本完整性保证或搜索网关。

## 为什么不用旧版 ARM 镜像

官方 Docker Hub 目前的 `yacy/yacy_search_server:latest` 有 amd64 和 arm64 镜像；已不必为 Apple Silicon 选择多年未更新的 `aarch64-latest`。当需要严格复现时，在三机各自核对镜像 digest，并在部署前配置固定 `YACY_IMAGE`。

## 正式产品下一阶段

一旦 L0–L5 验收完成，可增加统一搜索入口、授权访问、HTTPS、搜索日志和站点级全局限速。若需要严格的分布式 URL Frontier、任务恢复与数据分片，请沿 Route B（独立调度 + OpenSearch）演进，而不是假设三节点 YaCy 自动具备所有这些特性。
