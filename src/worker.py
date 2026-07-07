import time
import logging

from src.config import *
from src.network import network
from src.image_processor import detect_red_in_chunk

logger = logging.getLogger(__name__)


class Worker:
    def __init__(self, job_cache):
        self._running = False
        self._image_cache = job_cache

    def run(self):
        self._running = True
        while self._running:
            try:
                task = network.pop_task(timeout=3)
                if task:
                    self._process_task(task)
            except Exception:
                logger.exception("Worker error")
                time.sleep(1)

    def stop(self):
        self._running = False

    def _process_task(self, task):
        task_id = task["task_id"]
        job_id = task["job_id"]

        if network.get_job_status(job_id) == "completed":
            return

        if not network.acquire_task_lock(task_id):
            return

        already = network.get_job_results(job_id)
        if task_id in already:
            network.release_task_lock(task_id)
            return

        image_bytes = self._image_cache.get(job_id)
        if image_bytes is None:
            image_bytes = network.get_job_image(job_id)
            if image_bytes:
                self._image_cache[job_id] = image_bytes

        if not image_bytes:
            logger.error("No image for job %s task %s", job_id, task_id)
            network.release_task_lock(task_id)
            return

        try:
            objects, proc_time = detect_red_in_chunk(
                image_bytes,
                task["offset_x"],
                task["offset_y"],
                task["width"],
                task["height"],
            )

            result = {
                "task_id": task_id,
                "node_id": NODE_ID,
                "objects": objects,
                "processing_time": round(proc_time, 4),
                "part_index": task.get("part_index", -1),
            }

            network.store_result(job_id, task_id, result)
            logger.debug("Task %s done by %s (%.4fs, %d objects)", task_id, NODE_ID, proc_time, len(objects))

        except Exception:
            logger.exception("Failed to process task %s", task_id)
        finally:
            network.release_task_lock(task_id)
