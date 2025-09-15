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
from .models import (
    AnalysisRequest, 
    GitHubAnalysisRequest,
    AnalysisResponse, 
    CodebaseQuestion,
)
from ..codebase_indexer import MultiLanguageCodebaseParser, QdrantCodebaseIndexer
from ..utils import check_repository_size
import pickle
import base64

# Initialize logger
logger = logging.getLogger(__name__)

# Redis client for caching analysis results
redis_client = None
parser = MultiLanguageCodebaseParser()

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
        
        
        ######## TURNED OFF INDEXING FOR DEPLOYMENT ########

        # Check repository size to determine if indexing is needed
        # size_check = check_repository_size(str(path))
        # # Auto-index if the codebase is too large
        # if size_check['needs_indexing']:
        #     try:
        #         logger.info(f"Auto-indexing large codebase: {size_check['reason']}")
        #         # Index the codebase for better performance
        #         chunks = parser.parse_directory(str(path))
        #         indexer = QdrantCodebaseIndexer(
        #             collection_name=f"upload_{uuid.uuid4().hex[:8]}",
        #             qdrant_url=settings.qdrant_url,
        #             qdrant_api_key=settings.qdrant_api_key,
        #             use_memory=settings.use_memory
        #         )
        #         indexer.index_chunks(chunks, batch_size=100)
        #         index_result = indexer.get_statistics()
        #         logger.info(f"Indexed {index_result['total_chunks']} chunks")
        #         index = True
        #     except:
        #         logger.error(f"Failed to index codebase:")
        #         index = False
        # else:
        #     index = False

        # Use AI analysis engine
        engine = AnalysisEngine()
        config_path = Path(request.config_path) if hasattr(request, 'config_path') and request.config_path else None
        engine.enable_analysis(config_path, has_indexed_codebase=False)

        # Run async analysis
        result = await engine.analyze_repository(path)
        result.summary['temp_dir'] = str(path)
        result.summary['indexed'] = False

        # Cache the result in Redis
        if redis_client:
            await redis_client.set_cache(f"analysis:{analysis_id}", serialize_analysis_result(result), ttl=3600)  # 1 hour TTL
        else:
            logger.warning("Redis client not available, skipping cache")
        
        # Count AI-detected issues
        ai_issues_count = len([i for i in result.issues if i.metadata and i.metadata.get('ai_detected')])
        
        # Create response
        response_data = AnalysisResponse(
            analysis_id=analysis_id,
            status="completed",
            summary=result.summary,
            issues_count=len(result.issues),
            quality_score=result.summary.get('quality_score', 0),
            timestamp=result.timestamp
        )
        
        # Add AI analysis info to summary
        if ai_issues_count > 0:
            response_data.summary['ai_issues_count'] = ai_issues_count
            response_data.summary['ai_enabled'] = True

        return response_data
        
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
    import subprocess
    import re
    
    try:
        # Validate GitHub URL
        github_pattern = r'^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:/.*)?$'
        github_url = request.github_url.replace('.git', '')
        if not re.match(github_pattern, request.github_url):
            raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
        
        # Create temporary directory for cloning
        temp_dir = Path(tempfile.mkdtemp(prefix="codet_github_"))
        temp_directories.add(str(temp_dir))  # Track for cleanup
        
        try:
            clone_result = subprocess.run(
                ['git', 'clone', request.github_url, str(temp_dir)],
                capture_output=True,
                text=True,
                timeout=300  # 5 minute timeout
            )
            
            if clone_result.returncode != 0:
                raise HTTPException(
                    status_code=400, 
                    detail=f"Failed to clone repository: {clone_result.stderr}"
                )
            
            request = AnalysisRequest(path=str(temp_dir))
            response = await analyze_repository(request)
            
            if redis_client:
                cached_data = await redis_client.get_cache(f"analysis:{response.analysis_id}")
                if cached_data:
                    result = deserialize_analysis_result(cached_data)
                    result.summary['github_url'] = github_url
                    await redis_client.set_cache(f"analysis:{response.analysis_id}", serialize_analysis_result(result), ttl=3600)

            return response
        except Exception as e:
            raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ask/{analysis_id}")
async def ask_question(analysis_id: str, question: CodebaseQuestion):
    """Ask a question about the analyzed codebase"""
    try:
        if not redis_client:
            raise HTTPException(status_code=503, detail="Redis client not available")
        
        cached_data = await redis_client.get_cache(f"analysis:{analysis_id}")
        if not cached_data:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        result = deserialize_analysis_result(cached_data)
        path = Path(result.summary.get('temp_dir'))
        if not path.exists(): # If the API is restarted and has deleted the temp files
            return {
                "question": question.question,
                "answer": "Oops! I lost the files. Please analyze again.",
                "timestamp": datetime.now().isoformat()
            }
        
        chat_engine = OrchestratorEngine(
            mode="chat",
            has_indexed_codebase=result.summary.get('indexed', False)
        )
        
        chat_engine.set_cached_analysis(result)
        chat_engine.initialize_agents()

        answer = await chat_engine.answer_question(
            question=question.question,
            path=path
        )
        
        return {
            "question": question.question,
            "answer": answer,
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


