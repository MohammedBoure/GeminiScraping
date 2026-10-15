import os
import json
import time
import uuid
from typing import Optional, List, Dict, Any
from filelock import FileLock

DEFAULT_JOBS_FILE = "jobs.json"
DEFAULT_LOCK_FILE = "jobs.json.lock"
DEFAULT_OUTPUT_DIR = "./generated_videos"


class JobManager:
    """
    Thread/process-safe job management system backed by a local JSON file
    using filelock to track state transitions (pending, processing, completed, failed).
    """

    def __init__(self, jobs_file: str = DEFAULT_JOBS_FILE, lock_file: str = DEFAULT_LOCK_FILE, output_dir: str = DEFAULT_OUTPUT_DIR):
        self.jobs_file = jobs_file
        self.lock_file = lock_file
        self.output_dir = output_dir
        self.lock = FileLock(self.lock_file, timeout=10)
        os.makedirs(self.output_dir, exist_ok=True)
        self._ensure_file()

    def _ensure_file(self):
        with self.lock:
            if not os.path.exists(self.jobs_file):
                with open(self.jobs_file, "w", encoding="utf-8") as f:
                    json.dump([], f, indent=2)

    def _read_jobs(self) -> List[Dict[str, Any]]:
        if not os.path.exists(self.jobs_file):
            return []
        try:
            with open(self.jobs_file, "r", encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, FileNotFoundError):
            return []

    def _write_jobs(self, jobs: List[Dict[str, Any]]):
        temp_file = f"{self.jobs_file}.tmp"
        with open(temp_file, "w", encoding="utf-8") as f:
            json.dump(jobs, f, indent=2, ensure_ascii=False)
        os.replace(temp_file, self.jobs_file)

    def add_job(self, prompt: str, filename: Optional[str] = None) -> Dict[str, Any]:
        """
        Creates and enqueues a new pending job.
        """
        with self.lock:
            jobs = self._read_jobs()
            timestamp_str = time.strftime("%Y%m%d_%H%M%S")
            short_id = uuid.uuid4().hex[:6]
            job_id = f"vid_{timestamp_str}_{short_id}"

            if not filename:
                filename = f"{job_id}.mp4"
            elif not filename.lower().endswith(".mp4"):
                filename = f"{filename}.mp4"

            output_path = os.path.normpath(os.path.join(self.output_dir, filename))

            new_job = {
                "job_id": job_id,
                "prompt": prompt.strip(),
                "filename": filename,
                "status": "pending",
                "created_at": time.time(),
                "started_at": None,
                "completed_at": None,
                "error": None,
                "output_path": output_path
            }

            jobs.append(new_job)
            self._write_jobs(jobs)
            return new_job

    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves a job by its unique job_id.
        """
        with self.lock:
            jobs = self._read_jobs()
            for job in jobs:
                if job.get("job_id") == job_id:
                    return job
            return None

    def list_jobs(self, status: Optional[str] = None) -> List[Dict[str, Any]]:
        """
        Lists all jobs, optionally filtered by status.
        """
        with self.lock:
            jobs = self._read_jobs()
            if status:
                return [j for j in jobs if j.get("status") == status.lower()]
            return jobs

    def acquire_next_pending(self) -> Optional[Dict[str, Any]]:
        """
        Atomically finds the first pending job, marks its status as 'processing',
        records the started_at timestamp, and returns the acquired job.
        """
        with self.lock:
            jobs = self._read_jobs()
            for job in jobs:
                if job.get("status") == "pending":
                    job["status"] = "processing"
                    job["started_at"] = time.time()
                    self._write_jobs(jobs)
                    return job
            return None

    def update_job(self, job_id: str, **kwargs) -> Optional[Dict[str, Any]]:
        """
        Updates arbitrary fields for a specified job.
        """
        with self.lock:
            jobs = self._read_jobs()
            for job in jobs:
                if job.get("job_id") == job_id:
                    for key, val in kwargs.items():
                        job[key] = val
                    self._write_jobs(jobs)
                    return job
            return None

    def mark_completed(self, job_id: str, output_path: str) -> Optional[Dict[str, Any]]:
        """
        Marks a job as completed and stores the finalized output file path.
        """
        return self.update_job(
            job_id,
            status="completed",
            completed_at=time.time(),
            output_path=os.path.normpath(output_path),
            error=None
        )

    def mark_failed(self, job_id: str, error: str) -> Optional[Dict[str, Any]]:
        """
        Marks a job as failed and records the error description.
        """
        return self.update_job(
            job_id,
            status="failed",
            completed_at=time.time(),
            error=str(error)
        )
