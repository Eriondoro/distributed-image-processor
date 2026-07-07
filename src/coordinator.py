import json
import time
import logging

from src.config import *
from src.network import network
from src.partitioner import partition_image_coords
from src.image_processor import draw_result, get_image_dimensions
from src.metrics import save_metrics

logger = logging.getLogger(__name__)


class Coordinator:
    def __init__(self):
        self.active_jobs = {}
        self._running = False

    def run(self):
        self._running = True
        self._recover_active_jobs()

        while self._running:
            if not network.is_leader():
                time.sleep(LEADER_LOCK_TTL // 2)
                continue

            network.renew_leader()

            job_id = network.wait_for_job(timeout=3)
            if job_id:
                self._handle_new_job(job_id)

            self._monitor_active_jobs()

    def stop(self):
        self._running = False

    def _recover_active_jobs(self):
        for job_id in network.scan_active_jobs():
            config = network.get_job_config(job_id)
            total = network.get_job_total_tasks(job_id)
            if config and total:
                tasks = network.get_task_list(job_id) or []
                image_bytes = network.get_job_image(job_id)
                self.active_jobs[job_id] = {
                    "total_tasks": total,
                    "start_time": time.time(),
                    "last_result_time": time.time(),
                    "last_completed_count": 0,
                    "tasks": tasks,
                    "config": config,
                    "image_bytes": image_bytes,
                    "recovered": True,
                }
                completed_ids = set(network.get_job_results(job_id).keys())
                if tasks:
                    for task in tasks:
                        tid = task["task_id"]
                        if tid not in completed_ids and not network.is_task_locked(tid):
                            network.push_task(task)
                            logger.info("Recovered and re-queued task %s for job %s", tid, job_id)
                logger.info("Recovered job %s (%d tasks, %d already completed)",
                            job_id, total, len(completed_ids))

    def _handle_new_job(self, job_id):
        config = network.get_job_config(job_id)
        if not config:
            logger.error("No config for job %s", job_id)
            return

        image_bytes = network.get_job_image(job_id)
        if not image_bytes:
            logger.error("No image for job %s", job_id)
            return

        mode = config.get("mode", "1d_horizontal")
        n_parts = config.get("n_parts", 1)
        multiplier = config.get("multiplier", 1)
        total_parts = n_parts * multiplier

        partitions = partition_image_coords(image_bytes, total_parts, mode)

        tasks = []
        for p in partitions:
            task = {
                "job_id": job_id,
                "task_id": p["task_id"],
                "offset_x": p["offset_x"],
                "offset_y": p["offset_y"],
                "width": p["width"],
                "height": p["height"],
                "part_index": p["part_index"],
            }
            tasks.append(task)

        network.set_job_total_tasks(job_id, len(tasks))
        network.set_job_status(job_id, "processing")
        network.store_task_list(job_id, tasks)
        network.push_tasks_batch(tasks)

        self.active_jobs[job_id] = {
            "total_tasks": len(tasks),
            "start_time": time.time(),
            "last_result_time": time.time(),
            "last_completed_count": 0,
            "tasks": tasks,
            "config": config,
            "image_bytes": image_bytes,
            "recovered": False,
        }

        w, h = get_image_dimensions(image_bytes)
        logger.info(
            "Job %s: %d tasks, image %dx%d, mode=%s",
            job_id, len(tasks), w, h, mode,
        )

    def _monitor_active_jobs(self):
        for job_id in list(self.active_jobs.keys()):
            job = self.active_jobs[job_id]
            completed = network.get_job_result_count(job_id)

            if completed >= job["total_tasks"]:
                self._finalize_job(job_id, job)
                continue

            last_count = job.get("last_completed_count", 0)
            if completed > last_count:
                job["last_result_time"] = time.time()
                job["last_completed_count"] = completed

            elapsed_since_result = time.time() - job["last_result_time"]

            if elapsed_since_result > TASK_TIMEOUT:
                results = network.get_job_results(job_id)
                completed_ids = set(results.keys())
                job["last_completed_count"] = len(completed_ids)

                if job.get("tasks"):
                    for task in job["tasks"]:
                        tid = task["task_id"]
                        if tid not in completed_ids and not network.is_task_locked(tid):
                            network.push_task(task)
                            logger.info("Re-queued lost task %s", tid)

                job["last_result_time"] = time.time()

    def _finalize_job(self, job_id, job):
        results = network.get_job_results(job_id)
        all_objects = []
        total_proc_time = 0.0
        worker_stats = {}

        for task_id, result in results.items():
            objects = result.get("objects", [])
            proc_time = result.get("processing_time", 0)
            node_id = result.get("node_id", "unknown")

            all_objects.extend(objects)
            total_proc_time += proc_time
            worker_stats[node_id] = worker_stats.get(node_id, 0) + 1

        total_time = time.time() - job["start_time"]

        if job.get("image_bytes") and job.get("tasks"):
            result_image = draw_result(job["image_bytes"], job["tasks"], all_objects)
            network.set_job_result_image(job_id, result_image)

        network.set_job_status(job_id, "completed")
        network.publish(CHAN_JOB_DONE, json.dumps({
            "job_id": job_id,
            "status": "completed",
            "total_objects": len(all_objects),
            "total_time": round(total_time, 3),
            "total_proc_time": round(total_proc_time, 3),
        }))

        w, h = 0, 0
        if job.get("image_bytes"):
            w, h = get_image_dimensions(job["image_bytes"])

        metric = {
            "job_id": job_id,
            "image_size": f"{w}x{h}",
            "image_width": w,
            "image_height": h,
            "mode": job.get("config", {}).get("mode", "unknown"),
            "n_parts": job.get("config", {}).get("n_parts", 0),
            "multiplier": job.get("config", {}).get("multiplier", 1),
            "total_tasks": job["total_tasks"],
            "total_time": round(total_time, 3),
            "total_proc_time": round(total_proc_time, 3),
            "objects_detected": len(all_objects),
            "workers_used": len(worker_stats),
            "worker_names": list(worker_stats.keys()),
            "worker_task_counts": worker_stats,
            "recovered": job.get("recovered", False),
            "failures": 0,
        }
        network.store_metrics(job_id, metric)
        save_metrics(metric)

        logger.info(
            "Job %s completed: %d objects, %.2fs, %d tasks by %d workers",
            job_id, len(all_objects), total_time, job["total_tasks"], len(worker_stats),
        )

        network.set_job_total_tasks(job_id, 0)
        del self.active_jobs[job_id]
