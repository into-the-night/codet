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

from .core.analysis_engine import AnalysisEngine
from .analyzers.analyzer import IssueSeverity


console = Console()


def show_banner():
    """Display a colorful ASCII banner for Codet"""
    banner = """
    ╔═══════════════════════════════════════════════╗
    ║                                               ║
    ║     ░█████╗░░█████╗░██████╗░███████╗████████╗ ║
    ║     ██╔══██╗██╔══██╗██╔══██╗██╔════╝╚══██╔══╝ ║
    ║     ██║░░╚═╝██║░░██║██║░░██║█████╗░░░░░██║░░░ ║
    ║     ██║░░██╗██║░░██║██║░░██║██╔══╝░░░░░██║░░░ ║
    ║     ╚█████╔╝╚█████╔╝██████╔╝███████╗░░░██║░░░ ║
    ║     ░╚════╝░░╚════╝░╚═════╝░╚══════╝░░░╚═╝░░░ ║
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
    
    # Top issues with better styling
    if result.issues:
        console.print("\n[bold magenta]🔍 Top Issues:[/bold magenta]")
        
        issues_table = Table(show_header=True, header_style="bold magenta", box=None)
        issues_table.add_column("🚨 Severity", width=12)
        issues_table.add_column("📂 Category", width=18)
        issues_table.add_column("📄 File", width=35)
        issues_table.add_column("💬 Issue", width=50)
        
        # Show top 10 issues with icons
        for issue in result.issues[:10]:
            severity_color = severity_colors.get(issue.severity.value, 'white')
            icon = severity_icons.get(issue.severity.value, '📌')
            file_name = issue.file_path.name
            if issue.line_number:
                file_name += f":[bold]{issue.line_number}[/bold]"
            
            issues_table.add_row(
                f"{icon} [{severity_color}]{issue.severity.value.upper()}[/{severity_color}]",
                f"[dim]{issue.category.value}[/dim]",
                f"[italic]{file_name}[/italic]",
                Text(issue.title, overflow="ellipsis")
            )
        
        console.print(issues_table)
        
        if len(result.issues) > 10:
            console.print(f"\n[dim]... and {len(result.issues) - 10} more issues[/dim]")


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
def interactive():
    """🎯 Interactive mode - Analyze with a guided experience
    
    Step-by-step analysis with prompts and suggestions!
    """
    console.print()
    console.print(Panel(
        "[bold cyan]🎯 Welcome to Codet Interactive Mode![/bold cyan]\n\n"
        "I'll guide you through analyzing your codebase step by step.",
        title="[bold]Interactive Analysis[/bold]",
        border_style="cyan",
        padding=(1, 2)
    ))
    console.print()
    
    # Get path interactively
    path = Prompt.ask("📁 Enter the path to analyze", default=".")
    path = Path(path)
    
    if not path.exists():
        console.print(f"[red]❌ Error: Path '{path}' does not exist![/red]")
        return
    
    # Ask about languages
    console.print("\n[bold]🗣️  Language Detection[/bold]")
    auto_detect = Confirm.ask("Should I auto-detect languages?", default=True)
    
    # Ask about AI analysis
    console.print("\n[bold]🤖 AI Analysis[/bold]")
    enable_ai = Confirm.ask("Enable AI-powered analysis?", default=True)
    
    use_local = False
    ollama_model = "llama3.2"
    config_path = None
    
    if enable_ai:
        # Ask about local vs cloud LLM
        use_local = Confirm.ask("Use local Ollama LLM instead of Google Gemini?", default=False)
        
        if use_local:
            ollama_model = Prompt.ask("Ollama model to use", default="llama3.2")
            console.print(f"[green]✓ Will use local Ollama model: {ollama_model}[/green]")
        
        use_config = Confirm.ask("Do you have a configuration file?", default=False)
        if use_config:
            config_path = Prompt.ask("Configuration file path")
            config_path = Path(config_path)
            if not config_path.exists():
                console.print(f"[yellow]⚠️  Warning: Config file not found. Using defaults.[/yellow]")
                config_path = None
    
    # Ask about output format
    console.print("\n[bold]📊 Output Options[/bold]")
    save_report = Confirm.ask("Save report to file?", default=False)
    
    output_file = None
    output_format = "console"
    if save_report:
        output_format = Prompt.ask(
            "Output format",
            choices=["json", "html"],
            default="json"
        )
        output_file = Prompt.ask(
            "Output file name",
            default=f"codet_report.{output_format}"
        )
    
    # Confirm and run analysis
    console.print()
    llm_info = ""
    if enable_ai:
        if use_local:
            llm_info = f"\n🏠 LLM Mode: Local (Ollama - {ollama_model})"
        else:
            llm_info = "\n☁️  LLM Mode: Cloud (Google Gemini)"
    
    console.print(Panel(
        f"[bold]Ready to analyze![/bold]\n\n"
        f"📁 Path: {path.absolute()}\n"
        f"🤖 AI Analysis: {'Enabled' if enable_ai else 'Disabled'}{llm_info}\n"
        f"📊 Output: {output_format}" + (f" → {output_file}" if output_file else ""),
        title="[bold]Confirmation[/bold]",
        border_style="green",
        padding=(1, 2)
    ))
    console.print()
    
    if not Confirm.ask("Proceed with analysis?", default=True):
        console.print("[yellow]Analysis cancelled.[/yellow]")
        return
    
    # Run the analysis
    ctx = click.get_current_context()
    ctx.invoke(
        analyze,
        path=str(path),
        output=output_file,
        format=output_format,
        ai=enable_ai,
        config=str(config_path) if config_path else None,
        use_local=use_local,
        ollama_model=ollama_model
    )


if __name__ == '__main__':
    main()
