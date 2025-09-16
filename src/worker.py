"""Worker process for background job processing"""

import asyncio
import logging
from pathlib import Path
import tempfile
import shutil
import os
import subprocess
from typing import Dict, Any

from datetime import datetime
import json

from src.core.config import settings, RedisConfig
from src.core.redis_client import get_redis_client
from src.core.job_queue import JobQueue, JobStatus
from src.core.analysis_engine import AnalysisEngine
from src.core.orchestrator_engine import OrchestratorEngine
from src.api.models import AnalysisRequest
from src.api.main import serialize_analysis_result, deserialize_analysis_result

# Initialize logger
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Track temporary directories for cleanup
temp_directories = set()

async def handle_chat_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Handle chat/ask job processing"""
    job_data = job["data"]
    
    try:
        # Extract data from job
        analysis_id = job_data["analysis_id"]
        question = job_data["question"]
        session_id = job_data.get("session_id")
        cached_data = job_data["cached_analysis"]
        
        # Deserialize the analysis result
        result = deserialize_analysis_result(cached_data)
        path = Path(result.summary.get('temp_dir'))
        
        if not path.exists():
            return {
                "status": "completed",
                "result": {
                    "question": question,
                    "answer": "Oops! I lost the files. Please analyze again.",
                    "timestamp": datetime.now().isoformat(),
                    "session_id": session_id
                }
            }
        
        # Initialize chat engine
        chat_engine = OrchestratorEngine(
            mode="chat",
            has_indexed_codebase=result.summary.get('indexed', False),
            session_id=session_id
        )
        
        chat_engine.set_cached_analysis(result)
        chat_engine.initialize_agents()

        # Get answer
        answer = await chat_engine.answer_question(
            question=question,
            path=path
        )
        
        # Format response to match job status format
        return {
            "status": "completed",
            "result": {
                "question": question,
                "answer": answer,
                "timestamp": datetime.now().isoformat(),
                "session_id": chat_engine.session_id
            }
        }
        
    except Exception as e:
        logger.error(f"Chat job failed: {str(e)}")
        raise

async def handle_analysis_job(job: Dict[str, Any]) -> Dict[str, Any]:
    """Handle analysis job processing"""
    job_data = job["data"]
    job_type = job["type"]
    
    if job_type == "github_analysis":
        # Create temporary directory for cloning
        temp_dir = Path(tempfile.mkdtemp(prefix="codet_github_"))
        temp_directories.add(str(temp_dir))
        
        try:
            # Clone repository
            clone_result = subprocess.run(
                ['git', 'clone', job_data["github_url"], str(temp_dir)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if clone_result.returncode != 0:
                raise Exception(f"Failed to clone repository: {clone_result.stderr}")
            
            path = temp_dir
        except Exception as e:
            raise Exception(f"Failed to clone repository: {str(e)}")
    else:
        path = Path(job_data["path"])
        if not path.exists():
            raise Exception(f"Path not found: {job_data['path']}")

    try:
        # Use AI analysis engine
        engine = AnalysisEngine()
        config_path = Path(job_data.get("config_path")) if job_data.get("config_path") else None
        engine.enable_analysis(config_path, has_indexed_codebase=False)

        # Run analysis
        result = await engine.analyze_repository(path)
        result.summary['temp_dir'] = str(path)
        result.summary['indexed'] = False
        
        if job_type == "github_analysis":
            result.summary['github_url'] = job_data["github_url"]

        # Count AI-detected issues
        ai_issues_count = len([i for i in result.issues if i.metadata and i.metadata.get('ai_detected')])
        
        # Create response data
        response_data = {
            "status": "completed",
            "summary": result.summary,
            "issues_count": len(result.issues),
            "quality_score": result.summary.get('quality_score', 0),
            "timestamp": result.timestamp,
            "metrics": result.metrics,
            "issues": [
                {
                    "category": issue.category.value,
                    "severity": issue.severity.value,
                    "title": issue.title,
                    "description": issue.description,
                    "file_path": str(issue.file_path),
                    "line_number": issue.line_number,
                    "suggestion": issue.suggestion,
                    "metadata": issue.metadata
                }
                for issue in result.issues
            ]
        }
        
        # Add AI analysis info
        if ai_issues_count > 0:
            response_data["summary"]['ai_issues_count'] = ai_issues_count
            response_data["summary"]['ai_enabled'] = True
        
        redis_client = await get_redis_client(RedisConfig(settings))
        if redis_client:
            await redis_client.set_cache(f"analysis:{job['id']}", serialize_analysis_result(response_data))
        return response_data
        
    except Exception as e:
        raise Exception(f"Analysis failed: {str(e)}")

async def main():
    """Main worker process"""
    try:
        # Initialize Redis client
        redis_config = RedisConfig(settings)
        redis_client = await get_redis_client(redis_config)
        logger.info("Redis client initialized")
        
        # Initialize job queue
        job_queue = JobQueue(redis_client)
    
        # Define job handlers
        handlers = {
            "github_analysis": handle_analysis_job,
            "local_analysis": handle_analysis_job,
            "chat": handle_chat_job
        }
        
        # Start processing jobs
        logger.info("Starting job processing")
        await job_queue.process_jobs(lambda job: handlers[job["type"]](job))
        
    except Exception as e:
        logger.error(f"Worker error: {str(e)}")
        raise
    finally:
        # Cleanup any remaining temp directories
        for temp_dir in temp_directories:
            if os.path.exists(temp_dir):
                try:
                    shutil.rmtree(temp_dir)
                    logger.info(f"Cleaned up temporary directory: {temp_dir}")
                except Exception as e:
                    logger.warning(f"Failed to clean up {temp_dir}: {e}")

if __name__ == "__main__":
    asyncio.run(main())
