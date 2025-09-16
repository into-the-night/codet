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

from .core.config import settings
from .core.analysis_engine import AnalysisEngine
from .core.orchestrator_engine import OrchestratorEngine
from .codebase_indexer import MultiLanguageCodebaseParser, QdrantCodebaseIndexer
from .utils import FileFilter, RepoSizeChecker


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
            model_names = [m.get("name", "").split(":")[0] for m in models]
            
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
@click.option('--use-local', is_flag=True, help='🏠 Use local Ollama LLM instead of Gemini')
@click.option('--ollama-model', default='llama3.2', help='🤖 Ollama model to use (default: llama3.2)')
@click.option('--index', is_flag=True, help='🔍 Index codebase for RAG before analysis')
@click.option('--collection', default=None, help='📦 Qdrant collection name (used with --index)')
@click.option('--qdrant-url', default=None, help='🌐 Qdrant server URL (used with --index)')
@click.option('--qdrant-api-key', default=None, help='🔑 Qdrant API key (used with --index)')
def analyze(path, output, format, config, use_local, ollama_model, index, collection, qdrant_url, qdrant_api_key):
    """🎯 Analyze code quality using intelligent orchestrator flow
    
    Uses an intelligent orchestrator that strategically selects files to analyze
    and coordinates the analysis process for comprehensive coverage.
    
    Large repositories are automatically indexed into Qdrant for RAG
    (Retrieval-Augmented Generation) to enable semantic search capabilities
    for more context-aware analysis. Use --index to force indexing for smaller repos.
    """                                                                                                                                                                                                                     
    import tempfile
    import shutil
    
    path = Path(path)
    original_path = path
    
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

    if use_local:
        llm_mode = "Local (Ollama)"
        llm_model = ollama_model
    else:
        llm_mode = "Cloud (Gemini)"
        llm_model = settings.gemini_model
    
    info_text = (
        f"[bold cyan]📁 Analyzing:[/bold cyan] {path.absolute()}\n"
        f"[bold cyan]🎯 Analysis Mode:[/bold cyan] Orchestrator Flow\n"
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
        collection = collection.replace('.', '_').replace('/', '_').replace('\\', '_')
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
    
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold cyan]{task.description}[/bold cyan]"),
        BarColumn(bar_width=40),
        TaskProgressColumn(),
        TimeRemainingColumn(),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("🚀 Initializing analysis engine...", total=100)
        
        progress.update(task, description="🧠 Initializing AI analysis...")
        engine = AnalysisEngine()
        progress.update(task, advance=20)
        
        progress.update(task, description="🧠 Configuring orchestrator analysis...")
        
        if use_local:
            import yaml
            
            config_data = {}
            if config:
                with open(config, 'r') as f:
                    config_data = yaml.safe_load(f) or {}
            
            if 'agent' not in config_data:
                config_data['agent'] = {}
            
            config_data['agent']['use_local'] = True
            config_data['agent']['ollama_model'] = ollama_model
            
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(config_data, f)
                temp_config_path = f.name
            
            config_path = Path(temp_config_path)
        else:
            config_path = Path(config) if config else None
        
        engine.enable_analysis(
            config_path,
            has_indexed_codebase=index or needs_indexing,
            collection_name=collection
        )
        
        if not engine.enable_orchestrator:
            console.print("[red]❌ Error: Orchestrator analysis could not be enabled.[/red]")
            return
        progress.update(task, advance=20)
        
        progress.update(task, description="🌳 Constructing repository tree...")
        progress.update(task, advance=20)
        
        progress.update(task, description="🎯 Orchestrator analyzing files...")
        result = asyncio.run(engine.analyze_repository(path))
        progress.update(task, advance=40)
        
        progress.update(task, completed=100)
    
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
    
    # Count orchestrator-managed issues
    orchestrator_issues = [i for i in result.issues if i.metadata and i.metadata.get('orchestrator_managed')]
    file_analysis_issues = [i for i in result.issues if i.metadata and i.metadata.get('file_analysis_agent')]
    
    summary_text = f"[bold green]✅ Orchestrator Analysis Complete![/bold green]\n\n"
    summary_text += f"📊 Total issues found: [bold]{len(result.issues)}[/bold]\n"
    if orchestrator_issues:
        summary_text += f"🎯 Orchestrator-managed issues: [bold]{len(orchestrator_issues)}[/bold]\n"
    if file_analysis_issues:
        summary_text += f"🔍 File analysis issues: [bold]{len(file_analysis_issues)}[/bold]\n"
    
    summary_text += f"\n📁 Files analyzed: [bold]{result.summary.get('files_analyzed', 'Unknown')}[/bold]\n"
    summary_text += f"🔄 Orchestrator iterations: [bold]{result.summary.get('orchestrator_iterations', 'Unknown')}[/bold]\n"
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
        
        if use_local:
            import yaml

            config_data = {}
            if config:
                with open(config, 'r') as f:
                    config_data = yaml.safe_load(f) or {}
            
            # Update with local LLM settings
            if 'agent' not in config_data:
                config_data['agent'] = {}
            
            config_data['agent']['use_local'] = True
            config_data['agent']['ollama_model'] = ollama_model
            
            # Write temporary config
            with tempfile.NamedTemporaryFile(mode='w', suffix='.yaml', delete=False) as f:
                yaml.dump(config_data, f)
                temp_config_path = f.name
            
            config_path = Path(temp_config_path)
        else:
            config_path = Path(config) if config else None
        
        chat_engine.initialize_agents(config_path)
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

    # Chat loop
    while True:
        question = Prompt.ask("[bold cyan]You[/bold cyan]")
        
        if question.lower() in ['exit', 'quit', 'bye', 'q']:
            console.print("\n[yellow]👋 Thanks for chatting! Goodbye![/yellow]")
            break
        
        console.print()
        with Progress(
            SpinnerColumn(style="cyan"),
            TextColumn("[bold cyan]🤔 Thinking...[/bold cyan]"),
            console=console,
            transient=True
        ) as progress:
            task = progress.add_task("Analyzing codebase...", total=None)
            
            try:
                # Get answer using the persistent loop
                answer = loop.run_until_complete(chat_engine.answer_question(
                    question=question,
                    path=path
                ))
                
                console.print(f"\n[bold green]Codet[/bold green]: {answer}\n")
                
            except Exception as e:
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
