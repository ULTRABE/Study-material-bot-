"""
Worker pool: async task queue with priority support and concurrency control.
Manages up to 50-100 concurrent processing jobs.
"""
import asyncio
import logging
from typing import Optional, Dict, Callable, Awaitable
from concurrent.futures import ProcessPoolExecutor

from app.config import settings
from app.workers.job_models import ProcessingJob, JobStatus

logger = logging.getLogger(__name__)

_worker_pool: Optional["WorkerPool"] = None


def get_worker_pool() -> "WorkerPool":
    """Get the global worker pool instance."""
    global _worker_pool
    if _worker_pool is None:
        _worker_pool = WorkerPool()
    return _worker_pool


class WorkerPool:
    """
    Async worker pool for media processing jobs.
    Uses asyncio semaphore for concurrency control.
    Supports priority queue (premium users get high priority).
    """

    def __init__(self):
        self._semaphore = asyncio.Semaphore(settings.WORKER_POOL_SIZE)
        self._active_jobs: Dict[str, asyncio.Task] = {}
        self._high_queue: asyncio.Queue = asyncio.Queue()
        self._normal_queue: asyncio.Queue = asyncio.Queue()
        self._running = False
        self._dispatcher_task: Optional[asyncio.Task] = None
        self._process_executor = ProcessPoolExecutor(
            max_workers=max(2, settings.WORKER_POOL_SIZE // 2)
        )

    async def start(self) -> None:
        """Start the worker pool dispatcher."""
        self._running = True
        self._dispatcher_task = asyncio.create_task(self._dispatcher())
        logger.info(
            f"Worker pool started: {settings.WORKER_POOL_SIZE} workers, "
            f"max {settings.MAX_CONCURRENT_JOBS} concurrent jobs"
        )

    async def stop(self) -> None:
        """Gracefully stop the worker pool."""
        self._running = False
        if self._dispatcher_task:
            self._dispatcher_task.cancel()
            try:
                await self._dispatcher_task
            except asyncio.CancelledError:
                pass

        # Cancel all active jobs
        for job_id, task in list(self._active_jobs.items()):
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        self._process_executor.shutdown(wait=False)
        logger.info("Worker pool stopped")

    async def submit_job(
        self,
        job: ProcessingJob,
        handler: Callable[[ProcessingJob], Awaitable[None]],
    ) -> None:
        """
        Submit a job to the appropriate queue.
        Premium jobs go to high-priority queue.
        """
        if job.is_premium:
            await self._high_queue.put((job, handler))
            logger.debug(f"Job {job.job_id[:8]} queued (HIGH priority)")
        else:
            await self._normal_queue.put((job, handler))
            logger.debug(f"Job {job.job_id[:8]} queued (NORMAL priority)")

    async def _dispatcher(self) -> None:
        """
        Main dispatcher loop.
        Pulls jobs from queues (high priority first) and executes them.
        """
        while self._running:
            try:
                # Try high priority queue first
                job_tuple = None
                try:
                    job_tuple = self._high_queue.get_nowait()
                except asyncio.QueueEmpty:
                    pass

                # Fall back to normal queue
                if job_tuple is None:
                    try:
                        job_tuple = self._normal_queue.get_nowait()
                    except asyncio.QueueEmpty:
                        await asyncio.sleep(0.1)
                        continue

                job, handler = job_tuple
                task = asyncio.create_task(
                    self._execute_job(job, handler)
                )
                self._active_jobs[job.job_id] = task
                task.add_done_callback(
                    lambda t, jid=job.job_id: self._active_jobs.pop(jid, None)
                )

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Dispatcher error: {e}")
                await asyncio.sleep(1)

    async def _execute_job(
        self,
        job: ProcessingJob,
        handler: Callable[[ProcessingJob], Awaitable[None]],
    ) -> None:
        """Execute a single job with semaphore control."""
        async with self._semaphore:
            try:
                logger.info(f"Executing job {job.job_id[:8]} for user {job.user_id}")
                await handler(job)
            except asyncio.CancelledError:
                job.status = JobStatus.CANCELLED
                logger.info(f"Job {job.job_id[:8]} cancelled")
            except Exception as e:
                job.status = JobStatus.FAILED
                job.error_message = str(e)
                logger.error(f"Job {job.job_id[:8]} failed: {e}")

    def get_stats(self) -> dict:
        """Get current worker pool statistics."""
        return {
            "active_jobs": len(self._active_jobs),
            "high_queue_size": self._high_queue.qsize(),
            "normal_queue_size": self._normal_queue.qsize(),
            "pool_size": settings.WORKER_POOL_SIZE,
            "running": self._running,
        }

    def get_active_job_count(self) -> int:
        """Get number of currently executing jobs."""
        return len(self._active_jobs)

    def is_at_capacity(self) -> bool:
        """Check if pool is at maximum capacity."""
        return len(self._active_jobs) >= settings.MAX_CONCURRENT_JOBS

    async def flush_queues(self) -> int:
        """Flush all pending jobs from queues. Returns count flushed."""
        count = 0
        while not self._high_queue.empty():
            try:
                self._high_queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break
        while not self._normal_queue.empty():
            try:
                self._normal_queue.get_nowait()
                count += 1
            except asyncio.QueueEmpty:
                break
        logger.info(f"Flushed {count} pending jobs from queues")
        return count
