import threading


class JobManager:
    """Thread-safe job status tracking replacing global dicts."""

    def __init__(self):
        self._jobs: dict[str, dict[str, dict]] = {
            "crawl": {},
            "preprocess": {},
            "train": {},
            "cluster": {},
            "embed": {},
            "persona": {},
        }
        self._lock = threading.Lock()

    def get(self, job_type: str, sid: str) -> dict:
        with self._lock:
            return self._jobs.get(job_type, {}).get(sid, {"status": "not_found"})

    def set(self, job_type: str, sid: str, data: dict) -> None:
        with self._lock:
            self._jobs[job_type][sid] = data

    def update(self, job_type: str, sid: str, **kwargs) -> None:
        with self._lock:
            if sid in self._jobs.get(job_type, {}):
                self._jobs[job_type][sid].update(kwargs)

    def request_stop(self, job_type: str, sid: str) -> bool:
        """Set stop_requested flag. Returns True if job was running."""
        with self._lock:
            job = self._jobs.get(job_type, {}).get(sid)
            if job and job.get("status") == "running":
                job["stop_requested"] = True
                return True
            return False

    def is_stop_requested(self, job_type: str, sid: str) -> bool:
        with self._lock:
            job = self._jobs.get(job_type, {}).get(sid)
            return bool(job and job.get("stop_requested"))


job_manager = JobManager()
