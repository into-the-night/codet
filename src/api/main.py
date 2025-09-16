"""FastAPI application for Codet"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Form
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
from typing import List, Optional
import tempfile
import shutil
import uuid
import asyncio
import logging
from datetime import datetime
from contextlib import asynccontextmanager
import glob
import os

from ..analyzers.analyzer import AnalysisResult
from ..core.analysis_engine import AnalysisEngine
from ..core.orchestrator_engine import OrchestratorEngine
from ..core.config import settings, RedisConfig
from ..core.redis_client import get_redis_client, close_redis_client
from ..core.job_queue import JobQueue, JobStatus
from .models import (
    AnalysisRequest, 
    GitHubAnalysisRequest,
    AnalysisResponse, 
    CodebaseQuestion,
)
# from ..codebase_indexer import MultiLanguageCodebaseParser, QdrantCodebaseIndexer
# from ..utils import check_repository_size
import pickle
import base64

# Initialize logger
logger = logging.getLogger(__name__)

# Redis client for caching analysis results
redis_client = None
# parser = MultiLanguageCodebaseParser()

# Track temporary directories for cleanup
temp_directories = set()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global redis_client
    redis_config = RedisConfig(settings)
    redis_client = await get_redis_client(redis_config)
    logger.info("Redis client initialized")
    
    yield
    
    # Shutdown
    # Clean up tracked temporary directories
    global temp_directories
    logger.info(f"Cleaning up {len(temp_directories)} temporary directories")
    
    for temp_dir in temp_directories:
        if os.path.exists(temp_dir):
            try:
                shutil.rmtree(temp_dir)
                logger.info(f"Cleaned up temporary directory: {temp_dir}")
            except Exception as e:
                logger.warning(f"Failed to clean up {temp_dir}: {e}")
    
    # Also clean up any orphaned temp directories
    try:
        temp_patterns = [
            "/tmp/tmp*",  # Default tempfile pattern
            "/tmp/codet_github_*",  # GitHub clone pattern
        ]
        
        for pattern in temp_patterns:
            temp_dirs = glob.glob(pattern)
            for temp_dir in temp_dirs:
                if os.path.isdir(temp_dir) and temp_dir not in temp_directories:
                    try:
                        shutil.rmtree(temp_dir)
                        logger.info(f"Cleaned up orphaned temporary directory: {temp_dir}")
                    except Exception as e:
                        logger.warning(f"Failed to clean up orphaned {temp_dir}: {e}")
    except Exception as e:
        logger.error(f"Error during orphaned temp file cleanup: {e}")
    
    # Close Redis connection
    await close_redis_client()
    logger.info("Redis client closed")

app = FastAPI(
    title="codet API",
    description="Analyze code quality and answer questions about your codebase",
    version="0.1.0",
    lifespan=lifespan
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Analysis result serialization functions
def serialize_analysis_result(result: AnalysisResult) -> str:
    """Serialize AnalysisResult to string for Redis storage"""
    return base64.b64encode(pickle.dumps(result)).decode('utf-8')

def deserialize_analysis_result(data: str) -> AnalysisResult:
    """Deserialize AnalysisResult from Redis storage"""
    return pickle.loads(base64.b64decode(data.encode('utf-8')))

@app.get("/")
async def root():
    """Root endpoint with API information"""
    return {
        "name": "codet API",
        "version": "0.1.0",
        "endpoints": {
            "analyze": "/api/analyze",
            "analyze_github": "/api/analyze-github",
            "upload": "/api/upload",
            "ask": "/api/ask/{analysis_id}",
            "report": "/api/report/{analysis_id}",
            "chat": "/api/chat"
        }
    }


@app.post("/api/analyze", response_model=AnalysisResponse)
async def analyze_repository(request: AnalysisRequest):
    """Analyze a local repository or directory"""
    try:
        path = Path(request.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Path not found: {request.path}")
        
        # Generate unique analysis ID
        analysis_id = str(uuid.uuid4())
        
        if not request.enable_ai:
            raise HTTPException(status_code=400, detail="AI analysis is required")
        
        # Initialize job queue
        job_queue = JobQueue(redis_client)
        
        # Create job data
        job_data = {
            "path": str(path),
            "config_path": request.config_path if hasattr(request, 'config_path') else None
        }
        
        # Enqueue job
        await job_queue.enqueue_job("local_analysis", job_data, analysis_id)
        
        # Return immediate response with job ID
        return AnalysisResponse(
            analysis_id=analysis_id,
            status="pending",
            summary={"path": str(path)},
            issues_count=0,
            quality_score=0,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/upload")
async def upload_files(
    files: List[UploadFile] = File(...),
    preserve_structure: Optional[bool] = Form(False)
):
    """Upload files for analysis with auto-indexing for large codebases"""
    try:
        # Create temporary directory
        temp_dir = Path(tempfile.mkdtemp())
        temp_directories.add(str(temp_dir))  # Track for cleanup
        
        # Save uploaded files
        for file in files:
            file_path = temp_dir / file.filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'wb') as f:
                content = await file.read()
                f.write(content)

        # Analyze the uploaded files
        request = AnalysisRequest(path=str(temp_dir))
        response = await analyze_repository(request)

        return response
        
    except Exception as e:
        logger.error(f"Upload error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze-github", response_model=AnalysisResponse)
async def analyze_github_repository(request: GitHubAnalysisRequest):
    """Clone and analyze a GitHub repository"""
    import re
    
    try:
        # Validate GitHub URL
        github_pattern = r'^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:/.*)?$'
        github_url = request.github_url.replace('.git', '')
        if not re.match(github_pattern, request.github_url):
            raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
        
        # Generate unique analysis ID
        analysis_id = str(uuid.uuid4())
        
        # Initialize job queue
        job_queue = JobQueue(redis_client)
        
        # Create job data
        job_data = {
            "github_url": request.github_url
        }
        
        # Enqueue job
        await job_queue.enqueue_job("github_analysis", job_data, analysis_id)
        
        # Return immediate response with job ID
        return AnalysisResponse(
            analysis_id=analysis_id,
            status="pending",
            summary={"github_url": github_url},
            issues_count=0,
            quality_score=0,
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ask/{analysis_id}")
async def ask_question(analysis_id: str, question: CodebaseQuestion, session_id: Optional[str] = None):
    """Ask a question about the analyzed codebase"""
    try:
        if not redis_client:
            raise HTTPException(status_code=503, detail="Redis client not available")
        
        cached_data = await redis_client.get_cache(f"analysis:{analysis_id}")
        if not cached_data:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        # Generate unique job ID
        job_id = str(uuid.uuid4())
        
        # Initialize job queue
        job_queue = JobQueue(redis_client)
        
        # Create job data
        job_data = {
            "analysis_id": analysis_id,
            "question": question.question,
            "session_id": session_id,
            "cached_analysis": cached_data  # Pass the cached analysis to avoid re-fetching
        }
        
        # Enqueue job
        await job_queue.enqueue_job("chat", job_data, job_id)
        
        # Return immediate response with job ID
        return {
            "job_id": job_id,
            "status": "pending",
            "question": question.question,
            "timestamp": datetime.now().isoformat()
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in ask_question: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/report/{analysis_id}")
async def get_report(analysis_id: str, format: str = "json"):
    """Get the analysis report in specified format"""
    try:
        if not redis_client:
            raise HTTPException(status_code=503, detail="Redis client not available")
        
        cached_data = await redis_client.get_cache(f"analysis:{analysis_id}")
        if not cached_data:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        result = deserialize_analysis_result(cached_data)
        result.summary['project_path'] = result.summary.get('github_url', result.summary.get('project_path'))
        if format == "json":
            return {
                "analysis_id": analysis_id,
                "project_path": str(result.summary.get('project_path')),
                "timestamp": result.timestamp,
                "summary": result.summary,
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
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported format: {format}")
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/job/{job_id}")
async def get_job_status(job_id: str):
    """Get the status of a background job"""
    try:
        if not redis_client:
            raise HTTPException(status_code=503, detail="Redis client not available")
        
        job_queue = JobQueue(redis_client)
        job_status = await job_queue.get_job_status(job_id)
        
        if not job_status:
            raise HTTPException(status_code=404, detail="Job not found")
        
        # If job is completed, get the result
        if job_status["status"] == JobStatus.COMPLETED.value:
            result = await job_queue.get_job_result(job_id)
            if result:
                return {
                    "status": job_status["status"],
                    "result": result,
                    "created_at": job_status["created_at"],
                    "updated_at": job_status["updated_at"]
                }
        
        # For non-completed jobs, just return the status
        return {
            "status": job_status["status"],
            "created_at": job_status["created_at"],
            "updated_at": job_status["updated_at"]
        }
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    redis_status = "disconnected"
    if redis_client:
        redis_health = await redis_client.health_check()
        redis_status = redis_health.get("status", "disconnected")
    
    return {
        "status": "healthy", 
        "timestamp": datetime.now().isoformat(),
        "redis": redis_status
    }


