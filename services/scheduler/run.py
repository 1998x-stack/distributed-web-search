"""Single scheduler loop. Lua dispatch is atomic so multiple instances are safe."""
import logging
import os
import signal
import time
from redis import Redis
from packages.dws_core.frontier_v2 import FrontierV2

logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"),
                    format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("dws.scheduler")
RUN = True


def stop(*_args):
    global RUN
    RUN = False


def main():
    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    client = Redis(host=os.environ.get("REDIS_HOST", "redis"),
                   password=os.environ["REDIS_PASSWORD"],
                   socket_connect_timeout=3, socket_timeout=5, decode_responses=True)
    frontier = FrontierV2(client)
    while RUN:
        try:
            frontier.initialize()
            count = frontier.dispatch_due(50)
            if count:
                log.info("Moved %d delayed/recrawl URLs into stream", count)
            time.sleep(0.5 if count else 2)
        except Exception:
            log.exception("Scheduler cannot reach Redis; retrying")
            time.sleep(5)


if __name__ == "__main__":
    main()
