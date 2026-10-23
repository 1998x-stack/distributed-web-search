#!/usr/bin/env python3
"""Render dedicated, LAN-routable OpenSearch config per machine.

Never join existing V1 storage; each node has its own volume and node.name.
Initial cluster-manager bootstrap is ONLY for a brand-new cluster. Remove it
after first successful formation using --post-bootstrap.
"""
from __future__ import annotations

import argparse
import ipaddress
from pathlib import Path

import yaml


def private_ip(raw: str) -> str:
    address = ipaddress.ip_address(raw)
    if not isinstance(address, ipaddress.IPv4Address):
        raise ValueError("V2 currently expects LAN IPv4 only")
    if not address.is_private or address.is_loopback or address.is_link_local:
        raise ValueError("IP must be private, non-loopback, non-link-local")
    return str(address)


def create_config(node: str, addresses: tuple[str, str, str],
                  bootstrap: bool = True) -> dict:
    if node not in ("os-a", "os-b", "os-c"):
        raise ValueError("Unknown node name")
    ips = tuple(private_ip(s) for s in addresses)
    if len(set(ips)) != 3:
        raise ValueError("The three hosts need distinct LAN IP addresses")
    ip = ips[("os-a", "os-b", "os-c").index(node)]
    props = {
        "cluster.name": "dws-route-b-v2",
        "node.name": node,
        "node.roles": ["cluster_manager", "data", "ingest"]
            if node in ("os-a", "os-b") else ["cluster_manager"],
        "network.host": "0.0.0.0",
        "transport.port": 9300,
        "transport.publish_host": ip,
        "http.port": 9200,
        "discovery.seed_hosts": [f"{addr}:9300" for addr in ips],
        "plugins.security.disabled": True,
        "action.auto_create_index": False,
        "cluster.routing.allocation.disk.threshold_enabled": True,
    }
    if bootstrap:
        props["cluster.initial_cluster_manager_nodes"] = ["os-a", "os-b", "os-c"]
    return props


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("node", choices=["os-a", "os-b", "os-c"])
    parser.add_argument("ip_a")
    parser.add_argument("ip_b")
    parser.add_argument("ip_c")
    parser.add_argument("--post-bootstrap", action="store_true",
                        help="Remove initial cluster bootstrap configuration after cluster is formed")
    parser.add_argument("--out", default="runtime")
    args = parser.parse_args()
    config = create_config(args.node, (args.ip_a, args.ip_b, args.ip_c),
                           bootstrap=not args.post_bootstrap)
    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)
    existing = out / "opensearch.yml"
    if existing.exists() and not args.post_bootstrap:
        raise SystemExit(f"{existing} exists. Keep node config stable; use --post-bootstrap after formation")
    existing.write_text(yaml.safe_dump(config, sort_keys=False), encoding="utf-8")
    existing.chmod(0o644)  # Contains no secrets; container user must read it.
    env = out / "search.env"
    env.write_text(
        f"OS_PUBLISH_IP={config['transport.publish_host']}\n"
        f"OS_NODE={args.node}\n"
        f"OS_HEAP={'512m' if args.node == 'os-c' else '1g'}\n",
        encoding="utf-8",
    )
    env.chmod(0o600)
    print(f"Configured {args.node} publish={config['transport.publish_host']} bootstrap={not args.post_bootstrap}")


if __name__ == "__main__":
    main()
