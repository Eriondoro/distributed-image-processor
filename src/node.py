import sys
import os
import time
import threading
import logging
import signal

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import *
from src.network import network
from src.coordinator import Coordinator
from src.worker import Worker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
)
logger = logging.getLogger("node")


class Node:
    def __init__(self):
        self._running = False
        self._threads = []
        self._coordinator = Coordinator()
        self._image_cache = {}

    def start(self, with_coordinator=True):
        self._running = True
        try:
            network.connect()
        except Exception as e:
            logger.error("Failed to connect to Redis: %s", e)
            return False

        network.register_node()
        logger.info("Node %s registered", NODE_ID)

        t = threading.Thread(target=self._heartbeat_loop, daemon=True)
        t.start()
        self._threads.append(t)

        t = threading.Thread(target=self._leader_loop, daemon=True)
        t.start()
        self._threads.append(t)

        worker = Worker(self._image_cache)
        t = threading.Thread(target=worker.run, daemon=True)
        t.start()
        self._threads.append(t)

        if with_coordinator:
            t = threading.Thread(target=self._coordinator.run, daemon=True)
            t.start()
            self._threads.append(t)

        logger.info("Node %s started", NODE_ID)
        return True

    def stop(self):
        logger.info("Stopping node %s...", NODE_ID)
        self._running = False
        self._coordinator.stop()
        for t in self._threads:
            t.join(timeout=5)
        network.disconnect()

    def _heartbeat_loop(self):
        while self._running:
            try:
                network.heartbeat()
            except Exception:
                pass
            time.sleep(HEARTBEAT_INTERVAL)

    def _leader_loop(self):
        while self._running:
            try:
                if network.is_leader():
                    network.renew_leader()
                else:
                    network.try_become_leader()
            except Exception:
                pass
            time.sleep(LEADER_LOCK_TTL // 2)


def run_node():
    node = Node()

    def handle_signal(sig, frame):
        node.stop()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    if not node.start():
        return

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        pass
    finally:
        node.stop()


if __name__ == "__main__":
    run_node()
