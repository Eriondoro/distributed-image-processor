import os
import sys
import socket
import uuid

REDIS_HOST = os.environ.get("REDIS_HOST", "localhost")
REDIS_PORT = int(os.environ.get("REDIS_PORT", "6379"))
REDIS_DB = int(os.environ.get("REDIS_DB", "0"))

NODE_ID = os.environ.get("NODE_ID", f"{socket.gethostname()}-{uuid.uuid4().hex[:8]}")

HEARTBEAT_INTERVAL = 2
HEARTBEAT_TTL = 6
LEADER_LOCK_TTL = 8
TASK_TIMEOUT = 30
JOB_TIMEOUT = 300

PREFIX = "dip:"

KEY_NODES = f"{PREFIX}nodes"
KEY_HEARTBEAT = f"{PREFIX}hb:"
KEY_LEADER = f"{PREFIX}leader"
KEY_JOBS_QUEUE = f"{PREFIX}jobs:queue"
KEY_JOB = f"{PREFIX}job:"
KEY_TASKS_PENDING = f"{PREFIX}tasks:pending"
CHAN_NEW_JOB = f"{PREFIX}new_job"
CHAN_JOB_DONE = f"{PREFIX}job_done"

DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")

PARTITION_MODES = ["1d_horizontal", "1d_vertical", "2d_grid"]
