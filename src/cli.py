"""Command-line interface for Codet"""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.prompt import Prompt
import json
import logging
import asyncio

import httpx

from .core.config import get_settings
from .core.analysis_engine import AnalysisEngine
from .core.orchestrator_engine import OrchestratorEngine
from .codebase_indexer import MultiLanguageCodebaseParser, QdrantCodebaseIndexer
from .utils import FileFilter, RepoSizeChecker, load_and_summarize_rules_sync
from .utils.cli_status import CLIProcessingStatus, SimpleProcessingStatus


console = Console()
logger = logging.getLogger(__name__)


def check_ollama_running(model: str = "llama3.2") -> bool:
    """Check if Ollama is running by attempting to connect to its API"""
    try:
        # Check if Ollama API is accessible
        response = httpx.get("http://localhost:11434/api/tags", timeout=2.0)
        if response.status_code == 200:
            # Check if the specified model is available
            models = response.json().get("models", [])
            model_names = [m.get("name", "") for m in models]
            
            if model in model_names:
                return True
            else:
                console.print(f"[bold red]❌ Ollama is running but model '{model}' is not installed.[/bold red]")
                console.print(f"[yellow]Available models: {', '.join(model_names)}[/yellow]")
                console.print(f"[yellow]To install the model, run: [bold]ollama pull {model}[/bold][/yellow]")
                return False
        return False
    except (httpx.ConnectError, httpx.TimeoutException):
        return False
    except Exception as e:
        logger.debug(f"Error checking Ollama status: {e}")
        return False


def show_banner():
    """Display a colorful ASCII banner for Codet"""
    banner = """
    ╔═══════════════════════════════════════════════╗
    ║                                               ║
    ║   ░█████╗░░█████╗░██████╗░███████╗████████╗   ║
    ║   ██╔══██╗██╔══██╗██╔══██╗██╔════╝╚══██╔══╝   ║
    ║   ██║░░╚═╝██║░░██║██║░░██║█████╗░░░░░██║░░░   ║
    ║   ██║░░██╗██║░░██║██║░░██║██╔══╝░░░░░██║░░░   ║
    ║   ╚█████╔╝╚█████╔╝██████╔╝███████╗░░░██║░░░   ║
    ║   ░╚════╝░░╚════╝░╚═════╝░╚══════╝░░░╚═╝░░░   ║
    ║                                               ║
    ║       🔍 Code Quality Intelligence Tool 🔍    ║
    ║                                               ║
    ╚═══════════════════════════════════════════════╝
    """
    
    styled_banner = Text(banner, style="bold cyan")
    console.print(Align.center(styled_banner))
    console.print()


@click.group()
@click.version_option(version='0.1.0')
def main():
    """🚀 Codet - Your AI-powered code quality companion
    
    Analyze, understand, and improve your codebase with style!
    """
    show_banner()


@main.command()
@click.argument('path', type=click.Path(exists=True))
@click.option('--output', '-o', type=click.Path(), help='💾 Output file for report')
@click.option('--format', '-f', type=click.Choice(['console', 'json']), default='console', help='📊 Output format')
@click.option('--config', '-c', type=click.Path(exists=True), help='⚙️  Configuration file path')
@click.option('--use-parallel-agents', is_flag=True, help='🔃 Use agents parallely (set to False by default to avoid hitting RPM quotas early)')
@click.option('--use-local', is_flag=True, help='🏠 Use local Ollama LLM instead of Gemini')
@click.option('--ollama-model', default='llama3.2', help='🤖 Ollama model to use (default: llama3.2)')
@click.option('--index', is_flag=True, help='🔍 Index codebase for RAG before analysis')
@click.option('--collection', default=None, help='📦 Qdrant collection name (used with --index)')
@click.option('--qdrant-url', default=None, help='🌐 Qdrant server URL (used with --index)')
@click.option('--qdrant-api-key', default=None, help='🔑 Qdrant API key (used with --index)')
@click.option('--rules', '-r', multiple=True, type=click.Path(exists=True, dir_okay=False), help='📋 Custom rule markdown files (can be specified multiple times)')
def analyze(path, output, format, config, use_parallel_agents, use_local, ollama_model, index, collection, qdrant_url, qdrant_api_key, rules):
    """🎯 Analyze code quality using intelligent orchestrator flow
    
    Uses an intelligent orchestrator that strategically selects files to analyze
    and coordinates the analysis process for comprehensive coverage.
    
    Large repositories are automatically indexed into Qdrant forf RAG
    (Retrieval-Augmented Generation) to enable semantic search capabilities
    for more context-aware analysis. Use --index to force indexing for smaller repos.
    """                                                                                                                                                                                                                     
    import tempfile
    import shutil
    import time

    start_time = time.time()
    path = Path(path)
    original_path = path

    if use_local:
        llm_mode = "Local (Ollama)"
        llm_model = ollama_model

        env_data = []
        if config:
            with open(config, 'r') as f:
                env_data = f.readlines()
        
        # Add or update local LLM settings
        env_data.extend([
            'USE_LOCAL_LLM=true\n',
            f'OLLAMA_MODEL={ollama_model}\n'
        ])
        
        with tempfile.NamedTemporaryFile(mode='w', suffix='.env', delete=False) as f:
            f.writelines(env_data)
            temp_config_path = f.name
        
        config_path = Path(temp_config_path)
        settings = get_settings(config_path)
    else:
        llm_mode = "Cloud (Gemini)"
        config_path = Path(config) if config else None
        settings = get_settings(config_path)
        llm_model = settings.gemini_model
    
    
    # Check if path is a file, if so create temp directory and copy file
    if path.is_file():
        temp_dir = Path(tempfile.mkdtemp(prefix="codet_file_"))
        
        # Copy the file to temp directory, preserving the filename
        temp_file_path = temp_dir / path.name
        shutil.copy2(path, temp_file_path)
        
        # Update path to point to temp directory
        path = temp_dir
        console.print(f"[cyan]📄 Analyzing file:[/cyan] {original_path.name}")
    else:
        console.print(f"[cyan]📁 Analyzing directory:[/cyan] {path.name}")
    
    # Check if repository needs indexing
    size_checker = RepoSizeChecker(
        file_count_threshold=settings.repo_file_count_threshold,
        total_size_threshold=settings.repo_total_size_threshold,
        single_file_threshold=settings.repo_single_file_threshold
    )
    
    size_check = size_checker.check_repository(path)
    needs_indexing = size_check['needs_indexing'] or index

    info_text = (
        f"[bold cyan]📁 Analyzing:[/bold cyan] {path.absolute()}\n"
        f"[bold cyan]🔃 Parallel Agents:[/bold cyan] {'Enabled' if use_parallel_agents else 'Disabled'}\n"
        f"[bold cyan]🤖 LLM Mode:[/bold cyan] {llm_mode} ({llm_model})"
    )
    
    if needs_indexing:
        qdrant_url = qdrant_url or settings.qdrant_url
        qdrant_api_key = qdrant_api_key or settings.qdrant_api_key
        if not collection:
            if path == Path('.'):
                collection = Path.cwd().name  # Use current directory name
            else:
                collection = path
        collection = Path(str(collection).replace('.', '_').replace('/', '_').replace('\\', '_'))
        info_text += f"\n[bold cyan]🔍 RAG Mode:[/bold cyan] Enabled (Collection: {collection})"
    
    console.print(Panel.fit(
        info_text,
        title="[bold]Analysis Configuration[/bold]",
        border_style="cyan"
    ))
    console.print()
    
    if use_local:
        if not check_ollama_running(ollama_model):
            console.print("[bold red]❌ Ollama is not running or not accessible.[/bold red]")
            console.print("[yellow]Please ensure Ollama is running with the following command:[/yellow]")
            console.print("[bold]ollama serve[/bold]")
            console.print()
            console.print("[yellow]Then ensure your model is installed:[/yellow]")
            console.print(f"[bold]ollama pull {ollama_model}[/bold]")
            console.print()
            console.print("[dim]For more information, visit: https://ollama.ai[/dim]")
            raise click.Abort()
    else:
        if not settings.google_api_key:
            console.print("[bold red]❌ Google API key not found.[/bold red]")
            console.print("[yellow]Please set the GOOGLE_API_KEY environment variable:[/yellow]")
            console.print("[bold]export GOOGLE_API_KEY='your-api-key'[/bold]")
            console.print()
            console.print("[dim]Get your API key at: https://aistudio.google.com/app/apikey[/dim]")
            raise click.Abort()
    
    # Index codebase
    if index or needs_indexing:
        console.print("[bold cyan]🔍 Indexing codebase for RAG...[/bold cyan]")
        with Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(style="cyan"),
            TaskProgressColumn(),
            console=console
        ) as progress:
            task = progress.add_task("🔍 Parsing codebase...", total=None)
            file_filter = FileFilter.from_path(path)
            parser = MultiLanguageCodebaseParser(file_filter=file_filter)
            
            if path.is_file():
                chunks = parser.parse_file(str(path))
            else:
                chunks = parser.parse_directory(str(path))
            
            progress.update(task, completed=True)
            console.print(f"[green]✅ Found {len(chunks)} code chunks[/green]")
            
            if chunks:
                # Initialize indexer
                task = progress.add_task("🚀 Initializing Qdrant indexer...", total=None)
                indexer = QdrantCodebaseIndexer(
                    collection_name=collection,
                    qdrant_url=qdrant_url,
                    qdrant_api_key=qdrant_api_key,
                    use_memory=settings.use_memory
                )
                progress.update(task, completed=True)

                task = progress.add_task("📥 Indexing chunks...", total=len(chunks))
                batch_size = 64
                indexer.index_chunks(chunks, batch_size=batch_size)
                progress.update(task, completed=True)
                console.print("[green]✅ Indexing complete![/green]\n")
            else:
                console.print("[yellow]⚠️  No supported files found to index[/yellow]\n")
    
    
    # Load and index custom rules if provided
    rules_rag = None
    if rules:
        console.print(f"[cyan]📋 Loading and indexing {len(rules)} custom rule file(s)...[/cyan]")
        from .core.rules_rag import RulesRAG
        
        try:
            # Create RulesRAG instance
            # Use in-memory for simplicity, or Qdrant if available
            rules_rag = RulesRAG(
                collection_name="codet_custom_rules",
                qdrant_url=qdrant_url if needs_indexing else None,
                qdrant_api_key=qdrant_api_key if needs_indexing else None,
                use_memory=not needs_indexing  # Use in-memory if not using Qdrant for codebase
            )
            
            # Index rules from files
            rules_rag.index_rules_from_files(list(rules))
            
            num_rules = rules_rag.get_collection_size()
            console.print(f"[green]✅ Indexed {num_rules} rule chunks successfully[/green]\n")
        except Exception as e:
            logger.error(f"Error indexing custom rules: {e}")
            console.print(f"[yellow]⚠️  Failed to index custom rules: {e}[/yellow]\n")
            rules_rag = None
    
    # Initialize the analysis engine
    console.print("[bold cyan]🚀 Initializing analysis engine...[/bold cyan]")
    
    engine = AnalysisEngine()
    
    engine.enable_analysis(
        config_path,
        use_parallel=use_parallel_agents,
        has_indexed_codebase=index or needs_indexing,
        collection_name=collection,
        rules_rag=rules_rag  # Pass RulesRAG instance instead of text
    )
    
    if not engine.enable_orchestrator:
        console.print("[red]❌ Error: Orchestrator analysis could not be enabled.[/red]")
        return
    
    # Create and use rich processing status for analysis
    processing_status = CLIProcessingStatus(console=console)
    
    # Set up event callback before starting analysis
    engine.set_event_callback(processing_status.on_event)
    
    # Start the processing status display
    processing_status.start(title="🎯 Orchestrator Analysis")
    
    try:
        result = asyncio.run(engine.analyze_repository(path))
    finally:
        processing_status.stop()
    
    end_time = time.time()
    
    # Display results based on format
    if format == 'console':
        _display_console_report(result)
    elif format == 'json':
        report_data = {
            'project_path': str(result.project_path),
            'timestamp': result.timestamp,
            'summary': result.summary,
            'issues': [
                {
                    'category': issue.category.value,
                    'severity': issue.severity.value,
                    'title': issue.title,
                    'description': issue.description,
                    'file_path': str(issue.file_path),
                    'line_number': issue.line_number,
                    'suggestion': issue.suggestion
                }
                for issue in result.issues
            ],
            'metrics': result.metrics
        }
        
        if output:
            with open(output, 'w') as f:
                json.dump(report_data, f, indent=2)
            console.print(f"[green]Report saved to {output}[/green]")
        else:
            console.print_json(data=report_data)
    
    # Show summary with emojis and better formatting
    console.print()
    
    summary_text = f"[bold green]✅ Orchestrator Analysis Complete![/bold green]\n\n"
    summary_text += f"📊 Total issues found: [bold]{len(result.issues)}[/bold]\n"

    summary_text += f"\n📁 Files analyzed: [bold]{result.summary.get('files_analyzed', 'Unknown')}[/bold]\n"
    summary_text += f"🔄 Orchestrator iterations: [bold]{result.summary.get('orchestrator_iterations', 'Unknown')}[/bold]\n"
    summary_text += f"🕰️ Analysis Time: [bold cyan]{end_time - start_time:.2f} seconds[/bold cyan]\n"
    summary_text += f"🏆 Quality score: [bold cyan]{result.summary['quality_score']:.1f}/100[/bold cyan]"
    
    summary_panel = Panel(
        summary_text,
        title="[bold]Summary[/bold]",
        border_style="green",
        padding=(1, 2)
    )
    console.print(summary_panel)

    # Initialize chat engine
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold cyan]{task.description}[/bold cyan]"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("🚀 Initializing chat engine...", total=100)
        
        chat_engine = OrchestratorEngine(
            mode="chat",
            has_indexed_codebase=index,
            collection_name=collection
        )
        chat_engine.set_cached_analysis(result)
        progress.update(task, advance=50)
        
        chat_engine.initialize_agents(config_path, use_parallel=use_parallel_agents)
        progress.update(task, advance=50)
        progress.update(task, completed=100)
        
        # Clean up temporary config file if created
        if use_local and 'temp_config_path' in locals():
            import os
            try:
                os.unlink(temp_config_path)
            except:
                pass
    
    console.print("[green]✅ Chat engine ready! Ask me anything about your codebase.[/green]\n")
    
    # Create and persist a single event loop for the chat session
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    
    # Create processing status display
    processing_status = CLIProcessingStatus(console=console)

    # Chat loop
    while True:
        question = Prompt.ask("[bold cyan]You[/bold cyan]")
        
        if question.lower() in ['exit', 'quit', 'bye', 'q']:
            console.print("\n[yellow]👋 Thanks for chatting! Goodbye![/yellow]")
            break
        
        console.print()
        
        try:
            # Start the processing status display
            processing_status.start(title="🤖 Analyzing your question...")
            
            # Set up event callback for real-time updates
            chat_engine.set_event_callback(processing_status.on_event)
            
            # Get answer using the persistent loop
            answer = loop.run_until_complete(chat_engine.answer_question(
                question=question,
                path=path
            ))
            
            # Stop the processing status display
            processing_status.stop()
            
            console.print(f"\n[bold green]Codet[/bold green]: {answer}\n")
            
        except Exception as e:
            processing_status.stop()
            console.print(f"\n[red]❌ Error: {str(e)}[/red]\n")
            logger.error(f"Chat error: {e}", exc_info=True)

    # Gracefully shutdown the event loop after chat session ends
    try:
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        loop.close()



def _display_console_report(result):
    """Display analysis results in console with enhanced formatting"""
    console.print()
    console.print(Panel(
        f"[bold cyan]📊 Codet Report[/bold cyan]\n\n"
        f"📁 Project: [bold]{result.project_path}[/bold]\n"
        f"📄 Analyzed: [bold]{result.summary['files_analyzed']}[/bold] files\n"
        f"🏆 Quality Score: [bold cyan]{result.summary['quality_score']:.1f}/100[/bold cyan]",
        title="[bold]Report[/bold]",
        border_style="cyan",
        padding=(1, 2)
    ))
    console.print()
    
    # Summary table with emojis
    summary_table = Table(title="📊 Issue Summary", title_style="bold magenta")
    summary_table.add_column("Severity", style="cyan", width=20)
    summary_table.add_column("Count", justify="right", style="bold")
    summary_table.add_column("Icon", justify="center", width=5)
    
    severity_colors = {
        'critical': 'red',
        'high': 'orange3',
        'medium': 'yellow',
        'low': 'green',
        'info': 'blue'
    }
    
    severity_icons = {
        'critical': '🚨',
        'high': '⚠️ ',
        'medium': '⚡',
        'low': '💡',
        'info': 'ℹ️ '
    }
    
    for severity, count in result.summary['by_severity'].items():
        color = severity_colors.get(severity, 'white')
        icon = severity_icons.get(severity, '📌')
        summary_table.add_row(
            f"[{color}]{severity.upper()}[/{color}]",
            str(count),
            icon
        )
    
    console.print(summary_table)
    
    # All issues with better styling  
    if result.issues:
        console.print(f"\n[bold magenta]🔍 All Issues Found ({len(result.issues)} total):[/bold magenta]")
        
        issues_by_severity = {}
        for issue in result.issues:
            severity = issue.severity.value
            if severity not in issues_by_severity:
                issues_by_severity[severity] = []
            issues_by_severity[severity].append(issue)
        
        # Display issues grouped by severity
        for severity in ['critical', 'high', 'medium', 'low', 'info']:
            if severity not in issues_by_severity or not issues_by_severity[severity]:
                continue
                
            severity_color = severity_colors.get(severity, 'white')
            icon = severity_icons.get(severity, '📌')
            
            console.print(f"\n[{severity_color}]{icon} {severity.upper()} ({len(issues_by_severity[severity])} issues)[/{severity_color}]")
            console.print("-" * 80)
            
            issues_table = Table(show_header=True, header_style=f"bold {severity_color}", box=None)
            issues_table.add_column("📂 Category", width=15)
            issues_table.add_column("📄 File", width=30)
            issues_table.add_column("💬 Issue", width=40)
            issues_table.add_column("💡 Suggestion", width=35)
            
            for issue in issues_by_severity[severity]:
                file_name = issue.file_path.name
                if issue.line_number:
                    file_name += f":[bold]{issue.line_number}[/bold]"
                
                issues_table.add_row(
                    f"[dim]{issue.category.value}[/dim]",
                    f"[italic]{file_name}[/italic]",
                    Text(issue.title, overflow="fold"),
                    Text(issue.suggestion or "N/A", overflow="fold", style="dim")
                )
            
            console.print(issues_table)


@main.command()
@click.option('--host', default='0.0.0.0', help='🌐 Host to bind to')
@click.option('--port', default=8000, help='🔌 Port to bind to')
def serve(host, port):
    """🚀 Start the web server for interactive analysis
    
    Launch a powerful web interface for real-time code analysis!
    """
    import uvicorn
    
    console.print()
    console.print(Panel(
        f"[bold green]🚀 Starting Codet API Server[/bold green]\n\n"
        f"🌐 Server: [bold cyan]http://{host}:{port}[/bold cyan]\n"
        f"📚 API Docs: [bold cyan]http://{host}:{port}/docs[/bold cyan]\n\n"
        f"[dim]Press CTRL+C to stop the server[/dim]",
        title="[bold]Server Status[/bold]",
        border_style="green",
        padding=(1, 2)
    ))
    console.print()
    
    uvicorn.run(
        "src.api.main:app",
        host=host,
        port=port,
        reload=True
    )

if __name__ == '__main__':
    main()
