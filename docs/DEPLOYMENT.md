# 部署手册：Ubuntu A / Ubuntu B / macOS

## 1. 网络与系统准备

在三台机器上确认 `docker info`、`docker compose version` 成功。Ubuntu 建议使用 Docker Engine，macOS 使用 Docker Desktop。两台 Ubuntu 的 IPv4 可使用 `hostname -I` 查询，macOS Wi-Fi 通常可用 `ipconfig getifaddr en0`（以真实网卡为准）。

三台机器必须在**同一个可互访的网络地址空间**中，例如同一 LAN 或受控的 VPN/overlay。主机地址不可在启动后频繁改变，YaCy 会通过 `staticIP` 对外通告它。Docker 容器的 172.x 地址不能直接拿来给其他宿主机用。

为下列示例替换真实 IP（**三个命令必须一致**）：

| 节点 | 示例 IP | 主职责 |
|---|---|---|
| Ubuntu A | 192.168.1.101 | 第一个 Principal / Seed Bootstrap |
| Ubuntu B | 192.168.1.102 | 第二个 Principal / 搜索与抓取 |
| Mac C | 192.168.1.103 | 搜索与抓取 |

每台机器的 `8090/tcp` 必须可从**其他两台机器**访问。示例 Ubuntu UFW 规则（如果已启用 UFW）：

```bash
sudo ufw allow from 192.168.1.102 to any port 8090 proto tcp
sudo ufw allow from 192.168.1.103 to any port 8090 proto tcp
```

此例仅适用于 Ubuntu A；其余 Ubuntu 主机应根据允许的客户端修改来源。**不建议**直接 `ufw allow 8090/tcp` 暴露给整个互联网。macOS 需检查系统防火墙是否允许 Docker Desktop 代理接收端口连接。

## 2. 第一台：Ubuntu A

```bash
git clone --branch route-A --single-branch https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
bash scripts/deploy.sh ubuntu-a 192.168.1.101 192.168.1.102 192.168.1.103
```

部署脚本会：拉取 `yacy/yacy_search_server:latest`（当前支持 amd64/arm64）；提取官方 `defaults/yacy.init`；渲染私有网络配置与当前节点配置；检查现有数据卷是否属于同一个网络；创建可写 `DATA/HTDOCS`；启动一个 Compose 服务。

访问 `http://IP_A:8090/` 并立即修改默认密码（admin / yacy）。在 `Settings_p.html?page=seed` 检查：

- Upload method = `File`
- Seed file path = `DATA/HTDOCS/seed.txt`
- Seed URL = `http://IP_A:8090/seed.txt`
- Static IP = `IP_A`（在 `Settings_p.html?page=ServerAccess`）
- 网络名 = `homeweb`，状态晋级为 Principal。

如以上值尚未生效，通过 YaCy 管理界面保存并重新检查。只有当以下命令**返回 YaCy 实际 Seed 数据**（HTTP 200 且非 HTML、非空）才继续：

```bash
curl -fsS http://192.168.1.101:8090/seed.txt
```

首次新网络没有其他可 ping 的 peer，因此 A 必须能够公布自身的静态私有 IPv4 并成功发布 Seed List。不要用空字符串或随便写的 `seed.txt` 代替。

## 3. 第二台：Ubuntu B

```bash
git clone --branch route-A --single-branch https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
bash scripts/deploy.sh ubuntu-b 192.168.1.101 192.168.1.102 192.168.1.103
```

打开 `http://192.168.1.102:8090/Network.html`：确认网络是 `homeweb`，能够看见 Ubuntu A。B 也配置为 Seed File publisher，检查 `http://192.168.1.102:8090/seed.txt` 返回有效数据，且晋级为 Principal。B 的 Seed URL 是所有节点网络定义中已配置的备用入口。

## 4. 第三台：Mac C

```bash
git clone --branch route-A --single-branch https://github.com/1998x-stack/distributed-web-search.git
cd distributed-web-search
bash scripts/deploy.sh macos-c 192.168.1.101 192.168.1.102 192.168.1.103
open http://localhost:8090
```

Mac 使用 Docker Desktop 的 Linux 虚拟机运行 YaCy。镜像统一采用当前多架构 `latest`，而不是老旧的 ARM 专用镜像标签。实际通告的 `staticIP` 必须是其他机器可到达的 Mac LAN/VPN IP，而不是容器内部 IP。

允许的情况：Mac 进入睡眠后其本地爬取停止。非允许的情况：因为 Mac 下线，Ubuntu A/B 也无法运行或网页搜索全部消失。

## 5. 联通与数据校验

从任意装有 curl 的机器运行：

```bash
bash scripts/cluster-check.sh 192.168.1.101 192.168.1.102 192.168.1.103
```

然后按 [VERIFY.md](VERIFY.md) 人工确认全部三个节点出现在私有网络里，并验证远程搜索的真实结果（比三个 HTTP 200 更重要）。

## 6. 资源与 JVM

默认容器 `YACY_JAVASTART_XMX=Xmx1500m`（YaCy 启动脚本需要传完整 `Xmx...` 字符串）。它不是总内存上限；Java 堆以外仍需操作系统和索引缓存，建议每台提供至少 4GB 空闲内存。可在本机 `.env` 中改为 `Xmx2500m` 等后重启 Compose 服务。部署脚本再次运行会重建 `.env`，所以更新配置建议直接编辑 `.env` 并使用 Compose，而非再次运行部署脚本。

```bash
docker compose -f infra/compose.yml --env-file .env up -d
```

## 7. 运维、备份、升级

```bash
bash scripts/status.sh
bash scripts/backup.sh
docker compose -f infra/compose.yml --env-file .env logs --tail=150 -f
docker compose -f infra/compose.yml --env-file .env restart
```

备份脚本先停止 YaCy、使用临时 BusyBox 容器把命名数据卷存为 `backups/NODE_TIMESTAMP.tar.gz`、再启动。请单独保存备份到其他机器或离线盘，并定期验证文件可解压：

```bash
tar -tzf backups/NODE_TIMESTAMP.tar.gz | head
```

升级时先逐机备份，然后使用新镜像并逐台重建容器。YaCy 索引和配置在 Docker 数据卷中。**不要直接删除 Docker volume 来清理容器**，也不要在新建分支中重新初始化已使用中的旧索引。

## 8. 生产化之前

使用防火墙保护管理界面，避免直接暴露互联网。给所有节点配置不同的强管理员密码。需要对外开放普通搜索时，应使用可信代理提供 HTTPS、访问限制，以及将管理端与搜索端隔离。这里仅给出受信任 LAN/VPN 的实验部署。
