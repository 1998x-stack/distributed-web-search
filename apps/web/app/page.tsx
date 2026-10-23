"use client";

import { FormEvent, useEffect, useState } from "react";

type Hit = {
  title: string; url: string; domain: string; snippet: string;
  score: number; fetched_at?: string;
};
type SearchResult = {
  q: string; total: number; page: number; size: number;
  took_ms: number; results: Hit[];
};
type Cluster = { status: string; number_of_nodes: number; number_of_data_nodes: number; nodes: string[] };
type Status = {
  indexed_pages: number; known_urls: number; deadletters: number;
  pending_acks: number; workers: { id: string; inflight: number; seen_at: number }[];
};

export default function Home() {
  const [query, setQuery] = useState("");
  const [activeQuery, setActiveQuery] = useState("");
  const [page, setPage] = useState(1);
  const [data, setData] = useState<SearchResult | null>(null);
  const [status, setStatus] = useState<Status | null>(null);
  const [cluster, setCluster] = useState<Cluster | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  useEffect(() => {
    fetch("/api/v1/stats").then(r => r.ok ? r.json() : Promise.reject())
      .then((json: Status) => setStatus(json)).catch(() => {});
    fetch("/api/v1/cluster").then(r => r.ok ? r.json() : Promise.reject())
      .then((json: Cluster) => setCluster(json)).catch(() => {});
  }, []);

  useEffect(() => {
    if (!activeQuery) return;
    const controller = new AbortController();
    setLoading(true); setError("");
    const params = new URLSearchParams({ q: activeQuery, page: String(page), size: "10" });
    fetch("/api/v1/search?" + params.toString(), { signal: controller.signal })
      .then(async res => {
        if (!res.ok) throw new Error("搜索服务暂不可用（HTTP " + res.status + "）");
        return await res.json() as SearchResult;
      })
      .then(setData)
      .catch(e => { if (e.name !== "AbortError") setError(e.message); })
      .finally(() => { if (!controller.signal.aborted) setLoading(false); });
    return () => controller.abort();
  }, [activeQuery, page]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const q = query.trim();
    if (!q) return;
    setPage(1);
    setActiveQuery(q);
    setData(null);
  }
  return (
    <main>
      <header className="topbar">
        <span className="brand">✦ <strong>Atlas Search</strong></span>
        <span className="topmeta">独立网页索引 · LAN Cluster V1</span>
      </header>
      <section className={activeQuery ? "hero compact" : "hero"}>
        <div className="eyebrow">BUILT FROM YOUR OWN CRAWLED WEB</div>
        <h1>探索属于自己的<span>互联网</span></h1>
        <p className="intro">三台计算机并行抓取，OpenSearch 中文全文检索，独立构建的搜索结果。</p>
        <form onSubmit={submit} className="searchform">
          <label htmlFor="search" className="visuallyhidden">搜索网页</label>
          <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8"><circle cx="11" cy="11" r="7" /><path d="m16 16 5 5" /></svg>
          <input id="search" placeholder="搜索文章、技术博客、开源文档…" value={query} onChange={e => setQuery(e.target.value)} maxLength={200} />
          <button type="submit" disabled={loading || !query.trim()}>搜索</button>
        </form>
        <div className="hint">不会将你的查询转发至 Google 或百度</div>
      </section>
      {status && <div className="cluster">
        <span><i className="dot" /> <strong>{status.workers.length}</strong> 个在线 Worker</span>
        <span><strong>{status.indexed_pages.toLocaleString()}</strong> 已索引页面</span>
        <span><strong>{status.known_urls.toLocaleString()}</strong> 已发现 URL</span>
        <span><strong>{status.pending_acks.toLocaleString()}</strong> 正在处理</span>
        {cluster && <span><i className="dot" /> <strong>{cluster.number_of_data_nodes}</strong> 个索引数据节点 · {cluster.status}</span>}
      </div>}
      {activeQuery && <section className="results">
        <div className="resultmeta">{loading ? "正在搜索…" : data ? `找到 ${data.total.toLocaleString()} 条结果 · ${data.took_ms} ms` : ""}</div>
        {error && <div className="error" role="alert">{error}</div>}
        {!loading && data?.results.length === 0 && <div className="empty">暂无结果。可先通过管理 API 添加允许爬取的网站，再运行爬虫。</div>}
        {data?.results.map(hit => <article className="hit" key={hit.url}>
          <div className="site">{hit.domain} · {hit.fetched_at ? new Date(hit.fetched_at).toLocaleDateString("zh-CN") : "已索引"}</div>
          <a href={hit.url} target="_blank" rel="noopener noreferrer nofollow" className="hitTitle">{hit.title}</a>
          <div className="snippet">{hit.snippet}</div>
          <div className="url">{hit.url}</div>
        </article>)}
        {data && data.total > data.size && <nav className="pages" aria-label="搜索结果分页">
          <button onClick={() => setPage(v => Math.max(1, v - 1))} disabled={page <= 1 || loading}>上一页</button>
          <span>第 {page} 页</span>
          <button onClick={() => setPage(v => v + 1)} disabled={page * data.size >= data.total || loading}>下一页</button>
        </nav>}
      </section>}
      <footer>Atlas Search V1 · Scrapy · Redis Streams · OpenSearch · FastAPI · Next.js</footer>
    </main>
  );
}
