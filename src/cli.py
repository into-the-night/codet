"""Command-line interface for Code Quality Intelligence Agent"""

import click
from pathlib import Path
from rich.console import Console
from rich.table import Table
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn, TimeRemainingColumn
from rich.panel import Panel
from rich.text import Text
from rich.align import Align
from rich.prompt import Confirm, Prompt
import json
import logging
import yaml

from .core.analysis_engine import AnalysisEngine
from .analyzers.analyzer import IssueSeverity


console = Console()
logger = logging.getLogger(__name__)


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
@click.option('--format', '-f', type=click.Choice(['console', 'json', 'html']), default='console', help='📊 Output format')
@click.option('--ai/--no-ai', default=True, help='🤖 Enable AI-powered analysis (requires GOOGLE_API_KEY)')
@click.option('--config', '-c', type=click.Path(exists=True), help='⚙️  Configuration file path')
@click.option('--use-local', is_flag=True, help='🏠 Use local Ollama LLM instead of Google Gemini')
@click.option('--ollama-model', default='llama3.2', help='🤖 Ollama model to use (default: llama3.2)')
def analyze(path, output, format, ai, config, use_local, ollama_model):
    """🎯 Analyze code quality using intelligent orchestrator flow
    
    Uses an intelligent orchestrator that strategically selects files to analyze
    and coordinates the analysis process for comprehensive coverage.
    """                                                                                                                                                                                                                     
    path = Path(path)                                                                   
    
    # Show initial info
    llm_mode = "Local (Ollama)" if use_local else "Cloud (Google Gemini)"
    llm_model = ollama_model if use_local else "gemini-2.5-flash"
    
    console.print(Panel.fit(
        f"[bold cyan]📁 Analyzing:[/bold cyan] {path.absolute()}\n"
        f"[bold cyan]🎯 Analysis Mode:[/bold cyan] Orchestrator Flow\n"
        f"[bold cyan]🤖 LLM Mode:[/bold cyan] {llm_mode} ({llm_model})",
        title="[bold]Analysis Configuration[/bold]",
        border_style="cyan"
    ))
    console.print()
    
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
        
        # Create temporary config with local LLM settings if needed
        if use_local:
            import tempfile
            import yaml
            
            # Load existing config or create new one
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
        
        engine.enable_analysis(config_path)
        
        if not engine.enable_orchestrator:
            console.print("[red]❌ Error: Orchestrator analysis could not be enabled.[/red]")
            return
        progress.update(task, advance=20)
        
        progress.update(task, description="🌳 Constructing repository tree...")
        progress.update(task, advance=20)
        
        progress.update(task, description="🎯 Orchestrator analyzing files...")
        # Run async analysis
        import asyncio
        result = asyncio.run(engine.analyze_repository(path))
        progress.update(task, advance=40)
        
        progress.update(task, completed=100)
        
        # Clean up temporary config file if created
        if use_local and 'temp_config_path' in locals():
            import os
            try:
                os.unlink(temp_config_path)
            except:
                pass
    
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


def _display_console_report(result):
    """Display analysis results in console with enhanced formatting"""
    console.print()
    console.print(Panel(
        f"[bold cyan]📊 Code Quality Analysis Report[/bold cyan]\n\n"
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
        
        # Group issues by severity for better organization
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


@main.command()
@click.argument('path', type=click.Path(exists=True), required=False)
@click.option('--config', '-c', type=click.Path(exists=True), help='⚙️  Configuration file path')
@click.option('--use-local', is_flag=True, help='🏠 Use local Ollama LLM instead of Google Gemini')
@click.option('--ollama-model', default='llama3.2', help='🤖 Ollama model to use (default: llama3.2)')
def chat(path, config, use_local, ollama_model):
    """💬 Chat with your codebase - Ask questions and get AI-powered answers
    
    Have a conversation with your code! Ask questions about architecture,
    functionality, or get help understanding any part of your codebase.

    """
    import asyncio
    from .core.orchestrator_engine import OrchestratorEngine
    
    # Get path if not provided
    if not path:
        path = Prompt.ask("📁 Enter the path to analyze", default=".")
    path = Path(path)
    
    if not path.exists():
        console.print(f"[red]❌ Error: Path '{path}' does not exist![/red]")
        return
    
    # Show chat interface
    console.print()
    console.print(Panel(
        "[bold cyan]💬 Welcome to Codet Chat Mode![/bold cyan]\n\n"
        f"📁 Repository: [bold]{path.absolute()}[/bold]\n"
        f"🤖 LLM Mode: [bold]{'Local (Ollama)' if use_local else 'Cloud (Google Gemini)'}[/bold]\n\n"
        "[dim]Type 'exit' or 'quit' to end the conversation[/dim]",
        title="[bold]Chat Interface[/bold]",
        border_style="cyan",
        padding=(1, 2)
    ))
    console.print()
    
    # Initialize chat engine
    with Progress(
        SpinnerColumn(style="cyan"),
        TextColumn("[bold cyan]{task.description}[/bold cyan]"),
        console=console,
        transient=True
    ) as progress:
        task = progress.add_task("🚀 Initializing chat engine...", total=100)
        
        chat_engine = OrchestratorEngine(mode="chat")
        progress.update(task, advance=50)
        
        # Create temporary config with local LLM settings if needed
        if use_local:
            import tempfile
            import yaml
            
            # Load existing config or create new one
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
    import asyncio
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # Chat loop
    while True:
        # Get user question
        question = Prompt.ask("[bold cyan]You[/bold cyan]")
        
        # Check for exit commands
        if question.lower() in ['exit', 'quit', 'bye', 'q']:
            console.print("\n[yellow]👋 Thanks for chatting! Goodbye![/yellow]")
            break
        
        # Process the question
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
                
                # Show analyzed files
                if chat_engine.analyzed_files:
                    console.print(f"\n[dim]📂 Analyzed {len(chat_engine.analyzed_files)} files[/dim]")
                
                # Display answer
                console.print(f"\n[bold green]Codet[/bold green]: {answer}\n")
                
            except Exception as e:
                console.print(f"\n[red]❌ Error: {str(e)}[/red]\n")
                logger.error(f"Chat error: {e}", exc_info=True)

    # Gracefully shutdown the event loop after chat session ends
    try:
        loop.run_until_complete(loop.shutdown_asyncgens())
    finally:
        loop.close()


if __name__ == '__main__':
    main()
