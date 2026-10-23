"""Start Scrapy's asyncio reactor with a long-running Redis-backed spider."""
import os

import scrapy
from scrapy.crawler import CrawlerProcess

from .spider import LanWebSpider


def main():
    worker = os.environ.get("WORKER_ID", "").strip()
    if not worker or not worker.replace("-", "").replace("_", "").isalnum():
        raise SystemExit("WORKER_ID must be a simple non-empty identifier")
    process = CrawlerProcess(settings={
        "BOT_NAME": "DistributedWebSearch",
        "USER_AGENT": "DistributedWebSearchBot/1.0 (+contact: local-search-operator)",
        "ROBOTSTXT_OBEY": True,
        "COOKIES_ENABLED": False,
        "TELNETCONSOLE_ENABLED": False,
        "REDIRECT_ENABLED": False,
        "META_REFRESH_ENABLED": False,
        "HTTPERROR_ALLOW_ALL": True,
        "DOWNLOAD_TIMEOUT": 20,
        "DOWNLOAD_MAXSIZE": 2 * 1024 * 1024,
        "DOWNLOAD_WARNSIZE": 1 * 1024 * 1024,
        "CONCURRENT_REQUESTS": int(os.getenv("WORKER_CONCURRENCY", "4")),
        "CONCURRENT_REQUESTS_PER_DOMAIN": 2,
        "RETRY_ENABLED": False,
        "LOG_LEVEL": os.getenv("SCRAPY_LOG_LEVEL", "INFO"),
        "TWISTED_REACTOR": "twisted.internet.asyncioreactor.AsyncioSelectorReactor",
        "DOWNLOADER_MIDDLEWARES": {
            "services.worker.spider.SafetyAndRateMiddleware": 80,
        },
        "ITEM_PIPELINES": {"services.worker.spider.IngestPipeline": 100},
        "DEPTH_LIMIT": 0,
        "AUTOTHROTTLE_ENABLED": False,  # global Redis domain-slot reservation supersedes per-worker delay
        "DNSCACHE_ENABLED": False,
    })
    process.crawl(LanWebSpider)
    process.start(stop_after_crawl=False)


if __name__ == "__main__":
    main()
