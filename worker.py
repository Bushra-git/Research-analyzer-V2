import os

from rq import Worker

from queue_resources import analysis_queue, redis_connection



if __name__ == "__main__":
    worker_name = os.getenv("RQ_WORKER_NAME", f"analysis-worker-{os.getpid()}")
    worker = Worker([analysis_queue], connection=redis_connection, name=worker_name)
    worker.work()