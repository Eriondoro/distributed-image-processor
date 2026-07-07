import json
import time
import threading

import redis

from src.config import *


class NetworkManager:
    def __init__(self):
        self._raw = None
        self._text = None
        self._pubsub = None
        self._lock = threading.Lock()

    def connect(self):
        self._raw = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=False
        )
        self._text = redis.Redis(
            host=REDIS_HOST, port=REDIS_PORT, db=REDIS_DB, decode_responses=True
        )
        self._pubsub = self._text.pubsub()

    def disconnect(self):
        if self._pubsub:
            self._pubsub.close()
        if self._raw:
            self._raw.close()
        if self._text:
            self._text.close()

    @property
    def raw(self):
        return self._raw

    @property
    def text(self):
        return self._text

    # ── Node registration ────────────────────────────────────────────

    def register_node(self):
        data = json.dumps({
            "id": NODE_ID,
            "hostname": socket.gethostname(),
            "registered_at": time.time(),
        })
        self._raw.hset(KEY_NODES, NODE_ID, data)

    def heartbeat(self):
        self._raw.setex(f"{KEY_HEARTBEAT}{NODE_ID}", HEARTBEAT_TTL, b"1")

    def get_active_nodes(self):
        nodes = {}
        raw_data = self._raw.hgetall(KEY_NODES)
        for nid, data in raw_data.items():
            nid_str = nid.decode() if isinstance(nid, bytes) else nid
            if self._raw.exists(f"{KEY_HEARTBEAT}{nid_str}"):
                parsed = json.loads(data.decode() if isinstance(data, bytes) else data)
                nodes[nid_str] = parsed
        return nodes

    def is_node_alive(self, node_id):
        return self._raw.exists(f"{KEY_HEARTBEAT}{node_id}")

    # ── Leader election ──────────────────────────────────────────────

    def try_become_leader(self):
        return self._raw.set(KEY_LEADER, NODE_ID, nx=True, ex=LEADER_LOCK_TTL) or False

    def renew_leader(self):
        current = self._raw.get(KEY_LEADER)
        if current and (current.decode() if isinstance(current, bytes) else current) == NODE_ID:
            self._raw.expire(KEY_LEADER, LEADER_LOCK_TTL)
            return True
        return False

    def is_leader(self):
        current = self._raw.get(KEY_LEADER)
        if current:
            return (current.decode() if isinstance(current, bytes) else current) == NODE_ID
        return False

    def get_leader_id(self):
        current = self._raw.get(KEY_LEADER)
        if current:
            return current.decode() if isinstance(current, bytes) else current
        return None

    # ── Job lifecycle ────────────────────────────────────────────────

    def submit_job(self, image_bytes, config_dict):
        job_id = f"job_{int(time.time() * 1000)}_{uuid.uuid4().hex[:6]}"
        self._raw.set(f"{KEY_JOB}{job_id}:image", image_bytes)
        self._raw.set(f"{KEY_JOB}{job_id}:config", json.dumps(config_dict))
        self._raw.set(f"{KEY_JOB}{job_id}:status", "pending")
        self._raw.rpush(KEY_JOBS_QUEUE, job_id)
        self._raw.publish(CHAN_NEW_JOB, job_id)
        return job_id

    def wait_for_job(self, timeout=30):
        result = self._raw.blpop(KEY_JOBS_QUEUE, timeout=timeout)
        if result:
            return result[1].decode() if isinstance(result[1], bytes) else result[1]
        return None

    def get_job_image(self, job_id):
        return self._raw.get(f"{KEY_JOB}{job_id}:image")

    def get_job_config(self, job_id):
        raw = self._raw.get(f"{KEY_JOB}{job_id}:config")
        if raw:
            return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        return None

    def get_job_status(self, job_id):
        raw = self._raw.get(f"{KEY_JOB}{job_id}:status")
        if raw:
            return raw.decode() if isinstance(raw, bytes) else raw
        return None

    def set_job_status(self, job_id, status):
        self._raw.set(f"{KEY_JOB}{job_id}:status", status)

    def set_job_total_tasks(self, job_id, total):
        self._raw.set(f"{KEY_JOB}{job_id}:total_tasks", total)

    def get_job_total_tasks(self, job_id):
        raw = self._raw.get(f"{KEY_JOB}{job_id}:total_tasks")
        if raw:
            return int(raw.decode() if isinstance(raw, bytes) else raw)
        return 0

    def store_task_list(self, job_id, tasks):
        tasks_storable = []
        for t in tasks:
            tasks_storable.append({
                "job_id": t["job_id"],
                "task_id": t["task_id"],
                "offset_x": t["offset_x"],
                "offset_y": t["offset_y"],
                "width": t["width"],
                "height": t["height"],
                "part_index": t.get("part_index", -1),
            })
        self._raw.set(f"{KEY_JOB}{job_id}:tasks_list", json.dumps(tasks_storable))

    def get_task_list(self, job_id):
        raw = self._raw.get(f"{KEY_JOB}{job_id}:tasks_list")
        if raw:
            return json.loads(raw.decode() if isinstance(raw, bytes) else raw)
        return None

    def clean_job(self, job_id):
        keys = self._raw.keys(f"{KEY_JOB}{job_id}:*")
        if keys:
            self._raw.delete(*keys)

    # ── Task queue ───────────────────────────────────────────────────

    def push_task(self, task):
        self._raw.rpush(KEY_TASKS_PENDING, json.dumps(task))

    def pop_task(self, timeout=5):
        result = self._raw.blpop(KEY_TASKS_PENDING, timeout=timeout)
        if result:
            return json.loads(result[1].decode() if isinstance(result[1], bytes) else result[1])
        return None

    def push_tasks_batch(self, tasks):
        pipe = self._raw.pipeline()
        for t in tasks:
            pipe.rpush(KEY_TASKS_PENDING, json.dumps(t))
        pipe.execute()

    # ── Task locking (for failover) ──────────────────────────────────

    def acquire_task_lock(self, task_id):
        return self._raw.set(f"{PREFIX}task_lock:{task_id}", NODE_ID, nx=True, ex=TASK_TIMEOUT)

    def release_task_lock(self, task_id):
        lock_key = f"{PREFIX}task_lock:{task_id}"
        current = self._raw.get(lock_key)
        if current and (current.decode() if isinstance(current, bytes) else current) == NODE_ID:
            self._raw.delete(lock_key)

    def is_task_locked(self, task_id):
        return self._raw.exists(f"{PREFIX}task_lock:{task_id}")

    # ── Results ──────────────────────────────────────────────────────

    def store_result(self, job_id, task_id, result_dict):
        self._raw.hset(f"{KEY_JOB}{job_id}:results", task_id, json.dumps(result_dict))

    def get_job_results(self, job_id):
        raw = self._raw.hgetall(f"{KEY_JOB}{job_id}:results")
        results = {}
        for k, v in raw.items():
            key = k.decode() if isinstance(k, bytes) else k
            val = json.loads(v.decode() if isinstance(v, bytes) else v)
            results[key] = val
        return results

    def get_job_result_count(self, job_id):
        return self._raw.hlen(f"{KEY_JOB}{job_id}:results")

    def set_job_result_image(self, job_id, image_bytes):
        self._raw.set(f"{KEY_JOB}{job_id}:result", image_bytes)

    def get_job_result_image(self, job_id):
        return self._raw.get(f"{KEY_JOB}{job_id}:result")

    # ── Metrics ──────────────────────────────────────────────────────

    def store_metrics(self, job_id, metrics_dict):
        self._raw.set(f"{KEY_JOB}{job_id}:metrics", json.dumps(metrics_dict))
        self._raw.rpush(f"{PREFIX}metrics_list", json.dumps(metrics_dict))

    def get_all_metrics(self):
        raw_list = self._raw.lrange(f"{PREFIX}metrics_list", 0, -1)
        return [json.loads(m.decode() if isinstance(m, bytes) else m) for m in raw_list]

    # ── Pub/Sub helpers ──────────────────────────────────────────────

    def subscribe(self, channel):
        self._pubsub.subscribe(channel)

    def get_message(self, timeout=1.0):
        return self._pubsub.get_message(timeout=timeout)

    def publish(self, channel, message):
        self._raw.publish(channel, message)

    # ── Scanning for active jobs (leader failover) ───────────────────

    def scan_active_jobs(self):
        active = []
        for key in self._raw.scan_iter(f"{KEY_JOB}*:status"):
            status = self._raw.get(key)
            if status:
                st = status.decode() if isinstance(status, bytes) else status
                if st == "processing":
                    job_id = (key.decode() if isinstance(key, bytes) else key).split(":")[1]
                    active.append(job_id)
        return active


network = NetworkManager()
