"""FastAPI application for Code Quality Intelligence Agent"""

from fastapi import FastAPI, UploadFile, File, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse
from pathlib import Path
from typing import List, Optional, Dict, Any
import tempfile
import shutil
import uuid
from datetime import datetime

from ..analyzers.analyzer import AnalysisResult
from ..core.analysis_engine import AnalysisEngine
from ..core.orchestrator_engine import OrchestratorEngine
from ..core.config import settings
from .models import (
    AnalysisRequest, 
    GitHubAnalysisRequest,
    AnalysisResponse, 
    CodebaseQuestion,
    QuestionResponse,
    ChatRequest,
    ChatResponse,
    CodebaseIndexRequest,
    CodebaseIndexResponse,
    CodebaseSearchRequest,
    CodebaseSearchResponse,
    CodeSearchResult
)
from ..codebase_indexer import MultiLanguageCodebaseParser, QdrantCodebaseIndexer
from ..core.config import settings
from ..utils import FileFilter

app = FastAPI(
    title="codet API",
    description="Analyze code quality and answer questions about your codebase",
    version="0.1.0"
)

# Enable CORS for frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Storage for analysis results (in production, use a database)
analysis_cache: Dict[str, AnalysisResult] = {}


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
async def analyze_repository(request: AnalysisRequest, background_tasks: BackgroundTasks):
    """Analyze a local repository or directory"""
    try:
        path = Path(request.path)
        if not path.exists():
            raise HTTPException(status_code=404, detail=f"Path not found: {request.path}")
        
        # Generate unique analysis ID
        analysis_id = str(uuid.uuid4())
        
        
        if not request.enable_ai:
            raise HTTPException(status_code=400, detail="AI analysis is required")
        
        # Use AI analysis engine
        engine = AnalysisEngine()
        config_path = Path(request.config_path) if hasattr(request, 'config_path') and request.config_path else None
        engine.enable_analysis(config_path)

        # Run async analysis
        result = await engine.analyze_repository(path)
        
        # Cache the result
        analysis_cache[analysis_id] = result
        
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
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload files for analysis"""
    try:
        # Create temporary directory
        temp_dir = Path(tempfile.mkdtemp())
        
        # Save uploaded files
        for file in files:
            file_path = temp_dir / file.filename
            file_path.parent.mkdir(parents=True, exist_ok=True)
            
            with open(file_path, 'wb') as f:
                content = await file.read()
                f.write(content)
        
        # Analyze the uploaded files
        request = AnalysisRequest(path=str(temp_dir))
        response = await analyze_repository(request, BackgroundTasks())
        
        # Clean up temp directory (in background)
        BackgroundTasks().add_task(shutil.rmtree, temp_dir)
        
        return response
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/analyze-github", response_model=AnalysisResponse)
async def analyze_github_repository(request: GitHubAnalysisRequest, background_tasks: BackgroundTasks):
    """Clone and analyze a GitHub repository"""
    import subprocess
    import re
    
    try:
        # Validate GitHub URL
        github_pattern = r'^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:/.*)?$'
        if not re.match(github_pattern, request.github_url):
            raise HTTPException(status_code=400, detail="Invalid GitHub repository URL")
        
        # Create temporary directory for cloning
        temp_dir = Path(tempfile.mkdtemp(prefix="codet_github_"))
        
        try:
            # Clone the repository
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
            
            # Generate unique analysis ID
            analysis_id = str(uuid.uuid4())

            
            if not request.enable_ai:
                raise HTTPException(status_code=400, detail="AI analysis is required")
            
            # Use AI analysis engine
            engine = AnalysisEngine()
            config_path = Path(request.config_path) if hasattr(request, 'config_path') and request.config_path else None
            engine.enable_analysis(config_path)

            # Run async analysis
            result = await engine.analyze_repository(temp_dir)
            
            # Update the project path to show the original GitHub URL
            result.project_path = Path(request.github_url)
            
            # Cache the result
            analysis_cache[analysis_id] = result
            
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
            
            # Add GitHub URL to summary
            response_data.summary['github_url'] = request.github_url
            
            # Schedule cleanup of temp directory
            background_tasks.add_task(shutil.rmtree, temp_dir)
            
            return response_data
            
        except subprocess.TimeoutExpired:
            # Clean up on timeout
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise HTTPException(status_code=408, detail="Repository clone timed out")
        except Exception as e:
            # Clean up on error
            shutil.rmtree(temp_dir, ignore_errors=True)
            raise e
            
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/ask/{analysis_id}", response_model=QuestionResponse)
async def ask_question(analysis_id: str, question: CodebaseQuestion):
    """Ask a question about the analyzed codebase"""
    try:
        if analysis_id not in analysis_cache:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        result = analysis_cache[analysis_id]
        
        # Here you would integrate with an LLM or Q&A system
        # For now, return a mock response
        answer = f"Based on the analysis of {result.project_path}, here's what I found regarding '{question.question}'..."
        
        # Add some context from the analysis
        if "security" in question.question.lower():
            security_issues = [i for i in result.issues if i.category.value == "security"]
            answer += f"\n\nSecurity Analysis: Found {len(security_issues)} security-related issues."
        
        return QuestionResponse(
            question=question.question,
            answer=answer,
            context=[],  # Would include relevant code snippets
            confidence=0.85
        )
        
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/report/{analysis_id}")
async def get_report(analysis_id: str, format: str = "json"):
    """Get the analysis report in specified format"""
    try:
        if analysis_id not in analysis_cache:
            raise HTTPException(status_code=404, detail="Analysis not found")
        
        result = analysis_cache[analysis_id]
        
        if format == "json":
            return {
                "analysis_id": analysis_id,
                "project_path": str(result.project_path),
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


@app.post("/api/chat", response_model=ChatResponse)
async def chat_with_codebase(request: ChatRequest):
    """Chat with the codebase - ask questions and get answers"""
    import subprocess
    import re
    
    try:
        # Trim whitespace from the path
        cleaned_path = request.path.strip()
        
        # Check if the path is a GitHub URL
        github_pattern = r'^https://github\.com/[a-zA-Z0-9_.-]+/[a-zA-Z0-9_.-]+(?:/.*)?$'
        is_github_url = re.match(github_pattern, cleaned_path)
        
        if is_github_url:
            # Handle GitHub URL
            print(f"Processing GitHub URL: {cleaned_path}")
            temp_dir = Path(tempfile.mkdtemp(prefix="codet_chat_github_"))
            
            try:
                # Clone the repository
                clone_result = subprocess.run(
                    ['git', 'clone', cleaned_path, str(temp_dir)],
                    capture_output=True,
                    text=True,
                    timeout=300  # 5 minute timeout
                )
                
                if clone_result.returncode != 0:
                    raise HTTPException(
                        status_code=400, 
                        detail=f"Failed to clone repository: {clone_result.stderr}"
                    )
                
                path = temp_dir
            except subprocess.TimeoutExpired:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise HTTPException(status_code=408, detail="Repository clone timed out")
            except Exception as e:
                shutil.rmtree(temp_dir, ignore_errors=True)
                raise e
        else:
            # Handle local path
            print(f"Processing local path: {cleaned_path}")
            path = Path(cleaned_path)
            if not path.exists():
                raise HTTPException(status_code=404, detail=f"Path not found: {cleaned_path}")
            temp_dir = None
        
        # Initialize orchestrator engine in chat mode
        chat_engine = OrchestratorEngine(mode="chat")
        config_path = Path(request.config_path) if hasattr(request, 'config_path') and request.config_path else None
        chat_engine.initialize_agents(config_path)
        
        # Run chat analysis - use defaults if not provided
        answer = await chat_engine.answer_question(
            question=request.question,
            path=path
        )
        
        # Get analyzed files from the chat engine
        analyzed_files = list(chat_engine.analyzed_files)
        
        # Clean up temporary directory if we cloned from GitHub
        if is_github_url and temp_dir:
            shutil.rmtree(temp_dir, ignore_errors=True)
        
        return ChatResponse(
            question=request.question,
            answer=answer,
            analyzed_files=analyzed_files,
            files_analyzed_count=len(analyzed_files),
            timestamp=datetime.now().isoformat()
        )
        
    except HTTPException:
        if 'temp_dir' in locals() and temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise
    except Exception as e:
        if 'temp_dir' in locals() and temp_dir and temp_dir.exists():
            shutil.rmtree(temp_dir, ignore_errors=True)
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/health")
async def health_check():
    """Health check endpoint"""
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}


# Global indexer instance (in production, consider using dependency injection)
_indexer_instance: Optional[QdrantCodebaseIndexer] = None


def get_indexer(collection_name: str = "codebase") -> QdrantCodebaseIndexer:
    """Get or create indexer instance"""
    global _indexer_instance
    if _indexer_instance is None or _indexer_instance.collection_name != collection_name:
        _indexer_instance = QdrantCodebaseIndexer(
            collection_name=collection_name,
            qdrant_url=settings.qdrant_url,
            qdrant_api_key=settings.qdrant_api_key,
            use_memory=settings.use_memory
        )
    return _indexer_instance


@app.post("/api/index", response_model=CodebaseIndexResponse)
async def index_codebase(
    request: CodebaseIndexRequest,
    background_tasks: BackgroundTasks
):
    """
    Index a codebase into Qdrant for semantic search
    
    This endpoint parses code files in the specified path and creates embeddings
    for functions, classes, methods, and other code constructs.
    
    Supported languages:
    - Python (.py)
    - JavaScript (.js, .jsx, .mjs)
    - TypeScript (.ts, .tsx)
    """
    path = Path(request.path)
    
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Path not found: {path}")
    
    # Parse codebase with file filtering support
    file_filter = FileFilter.from_path(path)
    parser = MultiLanguageCodebaseParser(file_filter=file_filter)
    
    if path.is_file():
        chunks = parser.parse_file(str(path))
    else:
        chunks = parser.parse_directory(str(path))
    
    if not chunks:
        raise HTTPException(status_code=400, detail="No supported files found to index (Python, JavaScript, TypeScript)")
    
    # Index chunks
    indexer = get_indexer(request.collection_name)
    
    # Run indexing in background for large codebases
    def index_task():
        indexer.index_chunks(chunks, batch_size=request.batch_size)
    
    if len(chunks) > 1000:  # Large codebase, run in background
        background_tasks.add_task(index_task)
        status = "indexing_started"
    else:
        index_task()
        status = "completed"
    
    # Get statistics
    stats = indexer.get_statistics()
    
    return CodebaseIndexResponse(
        status=status,
        total_chunks=len(chunks),
        type_counts=stats['type_counts'],
        collection_name=request.collection_name,
        timestamp=datetime.now().isoformat()
    )


@app.post("/api/search", response_model=CodebaseSearchResponse)
async def search_codebase(request: CodebaseSearchRequest):
    """
    Search indexed codebase using semantic search
    
    Supports three search modes:
    - nlp: Natural language search using sentence transformers
    - code: Code-to-code similarity search using code embeddings
    - hybrid: Combines both NLP and code search for best results
    """
    indexer = get_indexer(request.collection_name)
    
    # Check if collection exists
    try:
        stats = indexer.get_statistics()
        if stats['total_chunks'] == 0:
            raise HTTPException(status_code=400, detail="No indexed chunks found. Please index codebase first.")
    except Exception:
        raise HTTPException(status_code=404, detail=f"Collection '{request.collection_name}' not found")
    
    # Perform search
    if request.search_type == "nlp":
        results = indexer.search_nlp(request.query, limit=request.limit, filter_dict=request.filter)
    elif request.search_type == "code":
        results = indexer.search_code(request.query, limit=request.limit, filter_dict=request.filter)
    else:  # hybrid
        hybrid_results = indexer.hybrid_search(
            request.query, 
            nlp_limit=request.limit // 2, 
            code_limit=request.limit
        )
        results = hybrid_results['merged'][:request.limit]
    
    # Convert to response format
    search_results = []
    for result in results:
        # Create code preview
        code_lines = result['code'].split('\n')[:5]
        if len(code_lines) < len(result['code'].split('\n')):
            code_lines.append("...")
        code_preview = '\n'.join(code_lines)
        
        search_results.append(CodeSearchResult(
            name=result['name'],
            signature=result['signature'],
            code_type=result['code_type'],
            file_path=result['context']['file_path'],
            line_from=result['line_from'],
            line_to=result['line_to'],
            score=result.get('score', result.get('nlp_score', 0)),
            docstring=result.get('docstring'),
            code_preview=code_preview
        ))
    
    return CodebaseSearchResponse(
        query=request.query,
        results=search_results,
        total_results=len(search_results),
        search_type=request.search_type,
        timestamp=datetime.now().isoformat()
    )


@app.get("/api/index/stats/{collection_name}")
async def get_index_statistics(collection_name: str = "codebase"):
    """Get statistics about an indexed collection"""
    try:
        indexer = get_indexer(collection_name)
        stats = indexer.get_statistics()
        
        return {
            "collection_name": collection_name,
            "statistics": stats,
            "timestamp": datetime.now().isoformat()
        }
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Collection '{collection_name}' not found or error: {str(e)}")
