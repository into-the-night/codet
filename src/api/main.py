"""FastAPI application for Codet"""

from fastapi import FastAPI, UploadFile, File, HTTPException, Form, WebSocket, WebSocketDisconnect
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

from ..agents.schemas import AnalysisResult
from ..core.analysis_engine import AnalysisEngine
from ..core.orchestrator_engine import OrchestratorEngine
from ..core.config import RedisConfig, get_settings
from ..core.redis_client import get_redis_client, close_redis_client
from .models import (
    AnalysisRequest, 
    GitHubAnalysisRequest,
    AnalysisResponse, 
    CodebaseQuestion,
)
from ..indexer import MultiLanguageCodebaseParser, CodebaseIndexer
from ..utils import check_repository_size
import pickle
import base64

# Initialize logger
logger = logging.getLogger(__name__)

settings = get_settings()

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
        
        # Check repository size to determine if indexing is needed
        size_check = check_repository_size(str(path))
            
        # Auto-index if the codebase is too large
        if size_check['needs_indexing']:
            try:
                logger.info(f"Auto-indexing large codebase: {size_check['reason']}")
                # Index the codebase for better performance
                chunks = parser.parse_directory(str(path))
                indexer = CodebaseIndexer(
                    collection_name=f"upload_{uuid.uuid4().hex[:8]}",
                    qdrant_url=settings.qdrant_url,
                    qdrant_api_key=settings.qdrant_api_key,
                    use_memory=settings.use_memory
                )
                indexer.index_chunks(chunks, batch_size=100)
                index_result = indexer.get_statistics()
                logger.info(f"Indexed {index_result['total_chunks']} chunks")
                index = True
            except:
                logger.error(f"Failed to index codebase:")
                index = False
        else:
            index = False

        # Use AI analysis engine
        engine = AnalysisEngine()
        config_path = Path(request.config_path) if hasattr(request, 'config_path') and request.config_path else None
        engine.enable_analysis(config_path, has_indexed_codebase=index)

        # Run async analysis
        result = await engine.analyze_repository(path)
        result.summary['temp_dir'] = str(path)
        result.summary['indexed'] = index

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

        return {"path": str(temp_dir)}
        
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
async def ask_question(analysis_id: str, question: CodebaseQuestion, session_id: Optional[str] = None):
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
                "timestamp": datetime.now().isoformat(),
                "session_id": session_id
            }
        
        chat_engine = OrchestratorEngine(
            mode="chat",
            has_indexed_codebase=result.summary.get('indexed', False),
            session_id=session_id
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
            "timestamp": datetime.now().isoformat(),
            "session_id": chat_engine.session_id
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


@app.websocket("/api/ws/chat/{analysis_id}")
async def websocket_chat(websocket: WebSocket, analysis_id: str):
    """WebSocket endpoint for real-time chat with event streaming"""
    await websocket.accept()
    
    # Message queue for thread-safe/async-safe sending
    send_queue = asyncio.Queue()
    
    async def sender():
        try:
            while True:
                message = await send_queue.get()
                if message is None:
                    break
                await websocket.send_json(message)
                send_queue.task_done()
        except Exception as e:
            logger.error(f"WebSocket sender error: {e}")

    sender_task = asyncio.create_task(sender())
    
    try:
        if not redis_client:
            await send_queue.put({"type": "error", "message": "Redis client not available"})
            return
        
        cached_data = await redis_client.get_cache(f"analysis:{analysis_id}")
        if not cached_data:
            await send_queue.put({"type": "error", "message": "Analysis not found"})
            return
        
        result = deserialize_analysis_result(cached_data)
        path_str = result.summary.get('temp_dir') or result.summary.get('project_path')
        if not path_str:
             await send_queue.put({"type": "error", "message": "Source path missing in analysis result."})
             return

        path = Path(path_str)
        if not path.exists():
            await send_queue.put({"type": "error", "message": "Codeshare files lost. Please re-analyze."})
            return

        while True:
            # Receive question from client
            try:
                data = await websocket.receive_json()
            except WebSocketDisconnect:
                break
                
            question = data.get("question")
            session_id = data.get("session_id")
            
            if not question:
                continue

            # Initialize chat engine
            chat_engine = OrchestratorEngine(
                mode="chat",
                has_indexed_codebase=result.summary.get('indexed', False),
                session_id=session_id
            )
            
            chat_engine.set_cached_analysis(result)
            chat_engine.initialize_agents()

            # Set up event callback to stream events to queue
            def event_callback(event_type, event_data):
                # Use call_soon_threadsafe to be safe if called from other threads
                try:
                    loop = asyncio.get_event_loop()
                    loop.call_soon_threadsafe(send_queue.put_nowait, {
                        "type": "event",
                        "event_type": event_type,
                        "data": event_data
                    })
                except Exception as e:
                    logger.error(f"Error putting event in queue: {e}")

            chat_engine.set_event_callback(event_callback)

            try:
                # Get answer
                answer = await chat_engine.answer_question(
                    question=question,
                    path=path
                )
                
                # Send final answer
                await send_queue.put({
                    "type": "answer",
                    "answer": answer,
                    "session_id": chat_engine.session_id,
                    "timestamp": datetime.now().isoformat()
                })
            except Exception as e:
                logger.error(f"Error in websocket chat processing: {str(e)}")
                await send_queue.put({"type": "error", "message": str(e)})

    except WebSocketDisconnect:
        logger.info(f"WebSocket disconnected for analysis {analysis_id}")
    except Exception as e:
        logger.error(f"WebSocket error: {str(e)}")
    finally:
        # Cleanup
        await send_queue.put(None)
        await sender_task
        try:
            await websocket.close()
        except:
            pass



@app.websocket("/api/ws/analyze")
async def websocket_analyze(websocket: WebSocket):
    """WebSocket endpoint for real-time analysis with event streaming"""
    await websocket.accept()
    
    send_queue = asyncio.Queue()
    
    async def sender():
        try:
            while True:
                message = await send_queue.get()
                if message is None: break
                await websocket.send_json(message)
                send_queue.task_done()
        except: pass

    sender_task = asyncio.create_task(sender())
    
    try:
        data = await websocket.receive_json()
        github_url = data.get("github_url")
        path_str = data.get("path")
        
        analysis_path = None
        
        if github_url:
            import re
            
            # Validate GitHub URL
            github_pattern = r'^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:/.*)?$'
            github_url_fixed = github_url.replace('.git', '')
            if not re.match(github_pattern, github_url):
                await send_queue.put({"type": "error", "message": "Invalid GitHub repository URL"})
                return
            
            # Create temporary directory for cloning
            temp_dir = Path(tempfile.mkdtemp(prefix="codet_github_"))
            temp_directories.add(str(temp_dir))
            
            await send_queue.put({"type": "info", "message": f"Cloning repository {github_url_fixed}..."})
            
            try:
                # Use asyncio for non-blocking clone
                process = await asyncio.create_subprocess_exec(
                    'git', 'clone', github_url, str(temp_dir),
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, stderr = await process.communicate()
                
                if process.returncode != 0:
                    await send_queue.put({"type": "error", "message": f"Failed to clone: {stderr.decode()}"})
                    return
                
                analysis_path = temp_dir
            except Exception as e:
                await send_queue.put({"type": "error", "message": str(e)})
                return
        elif path_str:
            analysis_path = Path(path_str)
            if not analysis_path.exists():
                await send_queue.put({"type": "error", "message": f"Path not found: {path_str}"})
                return
        else:
            await send_queue.put({"type": "error", "message": "No github_url or path provided"})
            return

        # Start Analysis
        analysis_id = str(uuid.uuid4())
        
        # Check repository size
        size_check = check_repository_size(str(analysis_path))
        index = False
            
        if size_check['needs_indexing']:
            await send_queue.put({"type": "info", "message": "Large codebase detected, indexing..."})
            try:
                chunks = parser.parse_directory(str(analysis_path))
                indexer = CodebaseIndexer(
                    collection_name=f"upload_{uuid.uuid4().hex[:8]}",
                    qdrant_url=settings.qdrant_url,
                    qdrant_api_key=settings.qdrant_api_key,
                    use_memory=settings.use_memory
                )
                indexer.index_chunks(chunks, batch_size=100)
                index = True
                await send_queue.put({"type": "info", "message": "Indexing complete"})
            except Exception as e:
                logger.error(f"Failed to index codebase: {e}")
        
        engine = AnalysisEngine()
        engine.enable_analysis(has_indexed_codebase=index)
        
        # Set up event callback
        def event_callback(event_type, event_data):
            try:
                loop = asyncio.get_event_loop()
                loop.call_soon_threadsafe(send_queue.put_nowait, {
                    "type": "event",
                    "event_type": event_type,
                    "data": event_data
                })
            except: pass
        
        engine.set_event_callback(event_callback)
        
        # Run analysis
        result = await engine.analyze_repository(analysis_path)
        result.summary['temp_dir'] = str(analysis_path)
        result.summary['indexed'] = index
        if github_url:
            result.summary['github_url'] = github_url.replace('.git', '')

        # Cache the result
        if redis_client:
            await redis_client.set_cache(f"analysis:{analysis_id}", serialize_analysis_result(result), ttl=3600)
        
        # Send final completion
        await send_queue.put({
            "type": "completed",
            "analysis_id": analysis_id,
            "summary": result.summary,
            "issues_count": len(result.issues)
        })

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected during analysis")
    except Exception as e:
        logger.error(f"WebSocket analysis error: {str(e)}")
        try:
            await send_queue.put({"type": "error", "message": str(e)})
        except: pass
    finally:
        await send_queue.put(None)
        await sender_task
        try:
            await websocket.close()
        except: pass





