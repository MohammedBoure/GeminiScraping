import asyncio
import logging
import os
import signal
import time
from typing import Optional
from core.browser import browser_manager
from core.job_manager import JobManager
from core.gemini_page import generate_video

logger = logging.getLogger("WorkerPool")


class WorkerPool:
    """
    Asynchronous worker pool orchestrating up to max_tabs concurrent workers.
    Each worker continuously pulls pending jobs from JobManager, spawns an isolated
    browser tab, generates the video, saves the result, and cleans up the tab.
    """

    def __init__(self, max_tabs: int = 3, timeout: int = 360, job_manager: Optional[JobManager] = None):
        self.max_tabs = max(1, max_tabs)
        self.timeout = timeout
        self.job_manager = job_manager or JobManager()
        self._stop_event = asyncio.Event()
        self._active_workers = []

    async def _worker_loop(self, worker_id: int):
        logger.info(f"[Worker-{worker_id}] Started and listening for jobs.")
        while not self._stop_event.is_set():
            job = None
            try:
                job = self.job_manager.acquire_next_pending()
            except Exception as e:
                logger.error(f"[Worker-{worker_id}] Error acquiring pending job: {e}")

            if not job:
                # No pending jobs currently, wait before checking queue again
                try:
                    await asyncio.wait_for(self._stop_event.wait(), timeout=2.5)
                    break
                except asyncio.TimeoutError:
                    continue

            job_id = job.get("job_id")
            prompt = job.get("prompt", "")
            output_path = job.get("output_path")

            logger.info(f"[Worker-{worker_id}] Processing Job '{job_id}' (Prompt: {prompt[:60]}...)")

            page = None
            try:
                page = await browser_manager.open_worker_tab()
                final_path = await generate_video(
                    page=page,
                    prompt=prompt,
                    output_path=output_path,
                    timeout=self.timeout
                )
                self.job_manager.mark_completed(job_id, final_path)
                logger.info(f"[Worker-{worker_id}] [✓] Job '{job_id}' completed successfully -> {final_path}")
            except Exception as e:
                logger.error(f"[Worker-{worker_id}] [✗] Job '{job_id}' failed: {e}")
                self.job_manager.mark_failed(job_id, str(e))
            finally:
                if page:
                    await browser_manager.close_tab(page)

        logger.info(f"[Worker-{worker_id}] Stopped.")

    async def run(self):
        """
        Runs the worker pool until stopped or interrupted.
        """
        logger.info(f"Starting Worker Pool with {self.max_tabs} concurrent tab worker(s)...")
        # Ensure CDP connection is established first
        await browser_manager.connect()

        tasks = [
            asyncio.create_task(self._worker_loop(i + 1))
            for i in range(self.max_tabs)
        ]
        self._active_workers = tasks

        try:
            await asyncio.gather(*tasks)
        except asyncio.CancelledError:
            logger.info("Worker pool tasks cancelled.")
        finally:
            await browser_manager.close()

    def stop(self):
        """
        Signals all workers to stop gracefully.
        """
        logger.info("Signaling worker pool to stop...")
        self._stop_event.set()


async def generate_oneshot(prompt: str, output_path: Optional[str] = None, timeout: int = 360) -> dict:
    """
    Performs a one-shot blocking generation: opens a single dedicated tab,
    generates and downloads the video, prints the result, and cleans up.
    """
    jm = JobManager()
    custom_filename = os.path.basename(output_path) if output_path else None
    job = jm.add_job(prompt=prompt, filename=custom_filename)
    if output_path:
        job = jm.update_job(job["job_id"], output_path=os.path.normpath(output_path))

    job_id = job["job_id"]
    jm.update_job(job_id, status="processing", started_at=time.time())

    page = None
    try:
        await browser_manager.connect()
        page = await browser_manager.open_worker_tab()
        final_path = await generate_video(
            page=page,
            prompt=job["prompt"],
            output_path=job["output_path"],
            timeout=timeout
        )
        updated = jm.mark_completed(job_id, final_path)
        return updated
    except Exception as e:
        updated = jm.mark_failed(job_id, str(e))
        raise RuntimeError(f"Generation failed: {e}") from e
    finally:
        if page:
            await browser_manager.close_tab(page)
        await browser_manager.close()
