"""Rich console status display for real-time agent processing feedback"""

from rich.console import Console, Group
from rich.live import Live
from rich.panel import Panel
from rich.table import Table
from rich.text import Text
from rich.spinner import Spinner
from rich.style import Style
from rich.align import Align
from typing import Optional, List, Dict, Any
from datetime import datetime
import threading


class ProcessingEvent:
    """Represents a single processing event"""
    def __init__(self, event_type: str, data: dict):
        self.type = event_type
        self.data = data
        self.timestamp = datetime.now()
    
    def __repr__(self):
        return f"ProcessingEvent({self.type}, {self.data})"


class CLIProcessingStatus:
    """
    Rich console display for real-time agent processing feedback.
    
    Shows tool calls, reasoning, memory updates, and progress in a 
    visually appealing format using Rich's Live display.
    """
    
    EVENT_ICONS = {
        'tool_start': '🔧',
        'tool_complete': '✅',
        'tool_error': '❌',
        'reasoning': '💭',
        'memory_update': '🧠',
        'file_analysis': '📄',
        'search': '🔍',
        'iteration': '🔄',
        'thinking': '⏳',
        'connected': '🔗',
        'complete': '✨',
        'error': '❌',
        'info': '📌',
    }
    
    EVENT_COLORS = {
        'tool_start': 'yellow',
        'tool_complete': 'green',
        'tool_error': 'red',
        'reasoning': 'magenta',
        'memory_update': 'cyan',
        'file_analysis': 'blue',
        'search': 'cyan',
        'iteration': 'bright_magenta',
        'thinking': 'dim',
        'connected': 'green',
        'complete': 'bright_green',
        'error': 'red',
        'info': 'white',
    }
    
    def __init__(self, console: Optional[Console] = None, max_visible_events: int = 8):
        self.console = console or Console()
        self.max_visible_events = max_visible_events
        self.events: List[ProcessingEvent] = []
        self.current_iteration = 0
        self.max_iterations = 10
        self.files_analyzed = 0
        self.is_processing = False
        self._lock = threading.Lock()
        self._live: Optional[Live] = None
        self._title = "Processing..."
    
    def set_title(self, title: str):
        """Set the title for the processing panel"""
        self._title = title
    
    def add_event(self, event_type: str, data: dict):
        """Add a new processing event"""
        with self._lock:
            event = ProcessingEvent(event_type, data)
            self.events.append(event)
            
            # Update iteration tracking
            if event_type == 'iteration':
                self.current_iteration = data.get('current', self.current_iteration)
                self.max_iterations = data.get('max', self.max_iterations)
                self.files_analyzed = data.get('files_analyzed', self.files_analyzed)
            elif event_type == 'file_analysis':
                self.files_analyzed += 1
            
            # Update the live display if active
            if self._live:
                self._live.update(self._build_display())
    
    def on_event(self, event_type: str, data: dict):
        """Callback handler for agent events - matches the expected signature"""
        self.add_event(event_type, data)
    
    def _format_event(self, event: ProcessingEvent) -> Text:
        """Format a single event for display"""
        icon = self.EVENT_ICONS.get(event.type, '📌')
        color = self.EVENT_COLORS.get(event.type, 'white')
        
        text = Text()
        text.append(f" {icon} ", style=color)
        
        # Format based on event type
        if event.type == 'file_analysis':
            file_path = event.data.get('file_path', 'unknown')
            focus = event.data.get('focus', '')
            text.append("Analyzing ", style="dim")
            text.append(file_path, style=f"bold {color}")
            if focus and focus != "general":
                text.append(f" ({focus})", style="dim")
        
        elif event.type == 'tool_start':
            tool_name = event.data.get('tool_name', 'unknown')
            text.append("Calling ", style="dim")
            text.append(tool_name, style=f"bold {color}")
            args = event.data.get('args', {})
            if args:
                args_str = ", ".join(f"{k}={v}" for k, v in list(args.items())[:2])
                if len(args) > 2:
                    args_str += "..."
                text.append(f" ({args_str})", style="dim")
        
        elif event.type == 'tool_complete':
            tool_name = event.data.get('tool_name', 'unknown')
            summary = event.data.get('summary', '')
            text.append(tool_name, style=f"bold {color}")
            text.append(" completed", style="dim")
            if summary:
                text.append(f" - {summary}", style="dim italic")
        
        elif event.type == 'reasoning':
            message = event.data.get('message', '')
            text.append(message[:80], style=f"italic {color}")
            if len(message) > 80:
                text.append("...", style="dim")
        
        elif event.type == 'memory_update':
            action = event.data.get('action', 'Updated')
            message = event.data.get('message', '')[:50]
            text.append(f"{action}: ", style=f"bold {color}")
            text.append(message, style="italic")
            if len(event.data.get('message', '')) > 50:
                text.append("...", style="dim")
        
        elif event.type == 'search':
            query = event.data.get('query', '')[:40]
            text.append("Searching: ", style="dim")
            text.append(f'"{query}"', style=f"italic {color}")
        
        elif event.type == 'iteration':
            current = event.data.get('current', '?')
            max_iter = event.data.get('max', '?')
            files = event.data.get('files_analyzed', 0)
            text.append(f"Iteration {current}/{max_iter}", style=f"bold {color}")
            if files > 0:
                text.append(f" ({files} files analyzed)", style="dim")
        
        elif event.type == 'thinking':
            message = event.data.get('message', 'Processing...')
            text.append(message, style=f"italic {color}")
        
        elif event.type == 'error':
            message = event.data.get('message', 'An error occurred')
            text.append(message, style=f"bold {color}")
        
        else:
            message = event.data.get('message', str(event.data))
            text.append(message[:60], style=color)
        
        # Add timestamp
        time_str = event.timestamp.strftime("%H:%M:%S")
        text.append(f"  [{time_str}]", style="dim")
        
        return text
    
    def _build_display(self) -> Panel:
        """Build the rich display panel"""
        visible_events = self.events[-self.max_visible_events:]
        hidden_count = len(self.events) - len(visible_events)
        
        # Create content
        content_parts = []
        
        # Header with progress
        header = Text()
        if self.is_processing:
            header.append("● ", style="green bold")
            header.append("Agent is working", style="bold")
        else:
            header.append("✓ ", style="green bold")
            header.append("Processing complete", style="bold")
        
        header.append(f"  │  ", style="dim")
        header.append(f"Iteration {self.current_iteration}/{self.max_iterations}", style="cyan")
        header.append(f"  │  ", style="dim")
        header.append(f"{self.files_analyzed} files", style="cyan")
        header.append(f"  │  ", style="dim")
        header.append(f"{len(self.events)} steps", style="cyan")
        
        content_parts.append(header)
        content_parts.append(Text("─" * 60, style="dim"))
        
        # Show hidden events count
        if hidden_count > 0:
            hidden_text = Text()
            hidden_text.append(f"  ↑ {hidden_count} earlier ", style="dim")
            hidden_text.append("steps hidden", style="dim italic")
            content_parts.append(hidden_text)
        
        # Add events
        for event in visible_events:
            content_parts.append(self._format_event(event))
        
        # Add current processing indicator if still working
        if self.is_processing:
            current = Text()
            current.append("  ⋯ ", style="cyan")
            current.append("Processing", style="italic dim")
            current.append(" ●", style="blink cyan")
            content_parts.append(current)
        
        # Combine into group
        content = Group(*content_parts)
        
        return Panel(
            content,
            title=f"[bold cyan]{self._title}[/bold cyan]",
            border_style="cyan" if self.is_processing else "green",
            padding=(0, 1)
        )
    
    def start(self, title: str = "🤖 Agent Processing"):
        """Start the live display"""
        self._title = title
        self.is_processing = True
        self.events = []
        self.current_iteration = 0
        self.files_analyzed = 0
        self._live = Live(
            self._build_display(),
            console=self.console,
            refresh_per_second=4,
            transient=False
        )
        self._live.start()
    
    def stop(self):
        """Stop the live display"""
        self.is_processing = False
        if self._live:
            self._live.update(self._build_display())
            self._live.stop()
            self._live = None
    
    def __enter__(self):
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.stop()
        return False


class SimpleProcessingStatus:
    """
    Simpler non-live processing status that prints events as they happen.
    
    Use this when Live display is not suitable (e.g., logging environments).
    """
    
    EVENT_ICONS = CLIProcessingStatus.EVENT_ICONS
    EVENT_COLORS = CLIProcessingStatus.EVENT_COLORS
    
    def __init__(self, console: Optional[Console] = None):
        self.console = console or Console()
        self.event_count = 0
        self.files_analyzed = 0
        self.current_iteration = 0
    
    def add_event(self, event_type: str, data: dict):
        """Add and immediately print a new processing event"""
        self.event_count += 1
        icon = self.EVENT_ICONS.get(event_type, '📌')
        color = self.EVENT_COLORS.get(event_type, 'white')
        
        # Update tracking
        if event_type == 'iteration':
            self.current_iteration = data.get('current', self.current_iteration)
        elif event_type == 'file_analysis':
            self.files_analyzed += 1
        
        # Format message
        if event_type == 'file_analysis':
            file_path = data.get('file_path', 'unknown')
            msg = f"Analyzing {file_path}"
        elif event_type == 'tool_complete':
            tool_name = data.get('tool_name', 'unknown')
            summary = data.get('summary', '')
            msg = f"{tool_name} completed - {summary}"
        elif event_type == 'iteration':
            current = data.get('current', '?')
            max_iter = data.get('max', '?')
            files = data.get('files_analyzed', 0)
            msg = f"Iteration {current}/{max_iter} ({files} files analyzed)"
        elif event_type == 'reasoning':
            msg = data.get('message', '')[:80]
        elif event_type == 'memory_update':
            action = data.get('action', 'Updated')
            message = data.get('message', '')[:50]
            msg = f"{action}: {message}"
        elif event_type == 'thinking':
            msg = data.get('message', 'Processing...')
        else:
            msg = data.get('message', str(data))[:60]
        
        self.console.print(f"  [{color}]{icon}[/{color}] {msg}")
    
    def on_event(self, event_type: str, data: dict):
        """Callback handler for agent events"""
        self.add_event(event_type, data)
    
    def start(self, title: str = "🤖 Agent Processing"):
        """Print start header"""
        self.console.print(f"\n[bold cyan]{title}[/bold cyan]")
        self.console.print("[dim]─" * 50 + "[/dim]")
    
    def stop(self):
        """Print completion footer"""
        self.console.print("[dim]─" * 50 + "[/dim]")
        self.console.print(f"[green]✅ Complete[/green] - {self.event_count} steps, {self.files_analyzed} files analyzed")
