"""Job queue implementation using Redis"""

import json
import asyncio
from enum import Enum
from typing import Optional, Dict, Any
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class JobStatus(Enum):
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"

class JobQueue:
    def __init__(self, redis_client):
        self.redis = redis_client
        self.job_queue_key = "codet:job_queue"
        self.job_status_key_prefix = "codet:job:"
        self.job_result_key_prefix = "codet:result:"

    async def enqueue_job(self, job_type: str, job_data: Dict[str, Any], job_id: str) -> str:
        """Add a job to the queue"""
        job = {
            "id": job_id,
            "type": job_type,
            "data": job_data,
            "status": JobStatus.PENDING.value,
            "created_at": datetime.now().isoformat(),
            "updated_at": datetime.now().isoformat()
        }
        
        # Store job status
        await self.redis.set_cache(
            f"{self.job_status_key_prefix}{job_id}",
            json.dumps(job),
            ttl=3600  # 1 hour TTL
        )
        
        # Add to queue
        await self.redis._client.rpush(self.job_queue_key, job_id)
        
        return job_id

    async def get_job_status(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the status of a job"""
        job_data = await self.redis.get_cache(f"{self.job_status_key_prefix}{job_id}")
        if job_data:
            return json.loads(job_data)
        return None

    async def update_job_status(self, job_id: str, status: JobStatus, result: Optional[Dict[str, Any]] = None) -> None:
        """Update the status of a job"""
        job_data = await self.get_job_status(job_id)
        if job_data:
            job_data["status"] = status.value
            job_data["updated_at"] = datetime.now().isoformat()
            
            if result:
                # Store result separately to avoid size limits
                await self.redis.set_cache(
                    f"{self.job_result_key_prefix}{job_id}",
                    json.dumps(result),
                    ttl=3600  # 1 hour TTL
                )
                job_data["result_key"] = f"{self.job_result_key_prefix}{job_id}"
            
            await self.redis.set_cache(
                f"{self.job_status_key_prefix}{job_id}",
                json.dumps(job_data),
                ttl=3600  # 1 hour TTL
            )

    async def get_job_result(self, job_id: str) -> Optional[Dict[str, Any]]:
        """Get the result of a completed job"""
        job_data = await self.get_job_status(job_id)
        if job_data and "result_key" in job_data:
            result_data = await self.redis.get_cache(job_data["result_key"])
            if result_data:
                return json.loads(result_data)
        return None

    async def dequeue_job(self) -> Optional[Dict[str, Any]]:
        """Get the next job from the queue"""
        job_id = await self.redis._client.lpop(self.job_queue_key)
        if job_id:
            return await self.get_job_status(job_id)
        return None

    async def process_jobs(self, handler):
        """Process jobs from the queue"""
        while True:
            try:
                job = await self.dequeue_job()
                if job:
                    job_id = job["id"]
                    logger.info(f"Processing job {job_id}")
                    
                    # Update status to processing
                    await self.update_job_status(job_id, JobStatus.PROCESSING)
                    
                    try:
                        # Process the job
                        result = await handler(job)
                        await self.update_job_status(job_id, JobStatus.COMPLETED, result)
                        logger.info(f"Job {job_id} completed successfully")
                    except Exception as e:
                        logger.error(f"Job {job_id} failed: {str(e)}")
                        await self.update_job_status(job_id, JobStatus.FAILED, {"error": str(e)})
                
                # Small delay to prevent busy waiting
                await asyncio.sleep(1)
            except Exception as e:
                logger.error(f"Error processing jobs: {str(e)}")
                await asyncio.sleep(5)  # Longer delay on error
