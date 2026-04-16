"""Shared memory for multi-agent code analysis sessions.

Inspired by how Claude Code handles memory. The model has three layers:

- Notes: short, durable observations about the codebase (like CLAUDE.md
  entries). Agents append; the orchestrator can prune.
- Todos: action items with an explicit status lifecycle
  (pending -> in_progress -> done), similar to TodoWrite. Agents add todos,
  claim them, and mark them done. The orchestrator manages the overall list.
- File cache: per-file analysis results. Prevents re-analyzing the same file
  and lets agents look up what another agent already found.

Each agent works through a ``MemoryView`` - a capability-scoped facade that
controls what it can read and modify. The underlying ``SharedMemory`` store
is the single source of truth; agents never mutate it directly.

Roles:
- "orchestrator": full read/write; manages todo lifecycle, prunes, resets.
- "file_analysis": read-all, append notes/todos, update only its own todos
  (or todos targeting its scoped file), cache analysis only for its scoped
  file.
"""

import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from threading import RLock
from typing import Any, Dict, List, Literal, Optional

logger = logging.getLogger(__name__)

TodoStatus = Literal["pending", "in_progress", "done"]

ROLE_ORCHESTRATOR = "orchestrator"
ROLE_FILE_ANALYSIS = "file_analysis"


@dataclass
class Note:
    """A durable observation about the codebase."""
    content: str
    source: str
    tags: List[str] = field(default_factory=list)
    file_path: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def format(self) -> str:
        loc = f" [{self.file_path}]" if self.file_path else ""
        tag_str = f" ({', '.join(self.tags)})" if self.tags else ""
        return f"{self.content}{loc}{tag_str}"


@dataclass
class Todo:
    """Actionable item an agent should complete."""
    id: str
    content: str
    source: str
    status: TodoStatus = "pending"
    owner: Optional[str] = None
    target_file: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())
    updated_at: str = field(default_factory=lambda: datetime.now().isoformat())

    def format(self) -> str:
        icon = {"pending": "[ ]", "in_progress": "[~]", "done": "[x]"}[self.status]
        target = f" -> {self.target_file}" if self.target_file else ""
        return f"{icon} {self.content}{target}"


class SharedMemory:
    """Authoritative memory store. Agents should access it via ``view_for``."""

    def __init__(self):
        self._notes: List[Note] = []
        self._todos: Dict[str, Todo] = {}
        self._file_cache: Dict[str, Dict[str, Any]] = {}
        self._lock = RLock()
        logger.info("SharedMemory initialized")

    # --- Internal state mutation (invoked through MemoryView) -----------

    def _add_note(self, note: Note) -> bool:
        with self._lock:
            for existing in self._notes:
                if existing.content == note.content and existing.file_path == note.file_path:
                    return False
            self._notes.append(note)
            logger.debug(f"note+ [{note.source}] {note.content}")
            return True

    def _remove_note(self, content: str) -> bool:
        with self._lock:
            for i, n in enumerate(self._notes):
                if n.content == content:
                    del self._notes[i]
                    return True
            return False

    def _get_notes(self, *, tags: Optional[List[str]] = None,
                   file_path: Optional[str] = None) -> List[Note]:
        with self._lock:
            notes = list(self._notes)
        if tags:
            notes = [n for n in notes if any(t in n.tags for t in tags)]
        if file_path is not None:
            notes = [n for n in notes if n.file_path == file_path]
        return notes

    def _add_todo(self, todo: Todo) -> str:
        with self._lock:
            for existing in self._todos.values():
                if existing.content.strip() == todo.content.strip():
                    return existing.id
            self._todos[todo.id] = todo
            logger.debug(f"todo+ [{todo.source}] {todo.content}")
            return todo.id

    def _update_todo(self, todo_id: str, *, status: Optional[TodoStatus] = None,
                     owner: Optional[str] = None) -> bool:
        with self._lock:
            todo = self._todos.get(todo_id)
            if not todo:
                return False
            if status is not None:
                todo.status = status
            if owner is not None:
                todo.owner = owner
            todo.updated_at = datetime.now().isoformat()
            return True

    def _remove_todo(self, todo_id: str) -> bool:
        with self._lock:
            return self._todos.pop(todo_id, None) is not None

    def _get_todos(self, *, status: Optional[TodoStatus] = None,
                   target_file: Optional[str] = None) -> List[Todo]:
        with self._lock:
            todos = list(self._todos.values())
        if status is not None:
            todos = [t for t in todos if t.status == status]
        if target_file is not None:
            todos = [t for t in todos if t.target_file == target_file]
        return todos

    def _cache_file(self, file_path: str, analysis: Dict[str, Any]) -> None:
        with self._lock:
            self._file_cache[file_path] = analysis

    def _get_file_cache(self, file_path: str) -> Optional[Dict[str, Any]]:
        with self._lock:
            return self._file_cache.get(file_path)

    def _analyzed_files(self) -> List[str]:
        with self._lock:
            return list(self._file_cache.keys())

    # --- Session-level controls ----------------------------------------

    def clear(self) -> None:
        """Reset memory for a new analysis session."""
        with self._lock:
            self._notes.clear()
            self._todos.clear()
            self._file_cache.clear()
            logger.info("SharedMemory cleared for new session")

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            return {
                "notes": len(self._notes),
                "todos": len(self._todos),
                "files_analyzed": len(self._file_cache),
            }

    # --- View factory --------------------------------------------------

    def view_for(self, role: str, file_scope: Optional[str] = None) -> "MemoryView":
        return MemoryView(self, role=role, file_scope=file_scope)


class MemoryView:
    """Capability-scoped facade over SharedMemory."""

    def __init__(self, memory: SharedMemory, role: str,
                 file_scope: Optional[str] = None):
        self._memory = memory
        self._role = role
        self._file_scope = file_scope

    # -- reads (all roles) ----------------------------------------------

    def notes(self, *, tags: Optional[List[str]] = None,
              file_path: Optional[str] = None) -> List[Note]:
        return self._memory._get_notes(tags=tags, file_path=file_path)

    def todos(self, *, status: Optional[TodoStatus] = None,
              target_file: Optional[str] = None) -> List[Todo]:
        return self._memory._get_todos(status=status, target_file=target_file)

    def file_cache(self, file_path: str) -> Optional[Dict[str, Any]]:
        return self._memory._get_file_cache(file_path)

    def analyzed_files(self) -> List[str]:
        return self._memory._analyzed_files()

    def summary(self) -> Dict[str, int]:
        return {
            "notes": len(self.notes()),
            "todos_pending": len(self.todos(status="pending")),
            "todos_in_progress": len(self.todos(status="in_progress")),
            "todos_done": len(self.todos(status="done")),
            "files_analyzed": len(self.analyzed_files()),
        }

    # -- append (all roles) ---------------------------------------------

    def add_note(self, content: str, *, tags: Optional[List[str]] = None,
                 file_path: Optional[str] = None) -> bool:
        if not content or not content.strip():
            return False
        note = Note(
            content=content.strip(),
            source=self._role,
            tags=list(tags or []),
            file_path=file_path if file_path is not None else self._file_scope,
        )
        return self._memory._add_note(note)

    def add_notes(self, contents: List[str], *, tags: Optional[List[str]] = None,
                  file_path: Optional[str] = None) -> int:
        added = 0
        for c in contents or []:
            if self.add_note(c, tags=tags, file_path=file_path):
                added += 1
        return added

    def add_todo(self, content: str, *, target_file: Optional[str] = None) -> Optional[str]:
        if not content or not content.strip():
            return None
        todo = Todo(
            id=uuid.uuid4().hex[:8],
            content=content.strip(),
            source=self._role,
            target_file=target_file if target_file is not None else self._file_scope,
        )
        return self._memory._add_todo(todo)

    def add_todos(self, contents: List[str], *, target_file: Optional[str] = None) -> List[str]:
        ids = []
        for c in contents or []:
            tid = self.add_todo(c, target_file=target_file)
            if tid:
                ids.append(tid)
        return ids

    # -- todo lifecycle (scoped) ----------------------------------------

    def claim_todo(self, todo_id: str) -> bool:
        if not self._can_touch_todo(todo_id):
            logger.debug(f"role={self._role} denied claim of todo {todo_id}")
            return False
        return self._memory._update_todo(todo_id, status="in_progress", owner=self._role)

    def complete_todo(self, todo_id: str) -> bool:
        if not self._can_touch_todo(todo_id):
            logger.debug(f"role={self._role} denied complete of todo {todo_id}")
            return False
        return self._memory._update_todo(todo_id, status="done", owner=self._role)

    # -- file cache (scoped for file_analysis) --------------------------

    def cache_file_analysis(self, file_path: str, analysis: Dict[str, Any]) -> bool:
        if self._role == ROLE_FILE_ANALYSIS and self._file_scope is not None \
                and file_path != self._file_scope:
            logger.debug(
                f"role={self._role} denied cache write for {file_path} "
                f"(scope={self._file_scope})"
            )
            return False
        self._memory._cache_file(file_path, analysis)
        return True

    # -- orchestrator-only ----------------------------------------------

    def remove_note(self, content: str) -> bool:
        if self._role != ROLE_ORCHESTRATOR:
            return False
        return self._memory._remove_note(content)

    def remove_todo(self, todo_id: str) -> bool:
        if self._role != ROLE_ORCHESTRATOR:
            return False
        return self._memory._remove_todo(todo_id)

    def reset(self) -> bool:
        if self._role != ROLE_ORCHESTRATOR:
            return False
        self._memory.clear()
        return True

    # -- prompt rendering -----------------------------------------------

    def format_notes(self, *, limit: Optional[int] = None,
                     file_path: Optional[str] = None) -> str:
        notes = self.notes(file_path=file_path)
        if limit:
            notes = notes[-limit:]
        if not notes:
            return ""
        return "\n".join(f"- {n.format()}" for n in notes)

    def format_todos(self, *, status: Optional[TodoStatus] = None,
                     target_file: Optional[str] = None) -> str:
        todos = self.todos(status=status, target_file=target_file)
        if not todos:
            return ""
        return "\n".join(f"{t.id}: {t.format()}" for t in todos)

    def format_for_prompt(self, *, file_path: Optional[str] = None) -> str:
        """Render the memory as a single block suitable for injecting into a prompt.

        Only sections with content are included.
        """
        sections = []

        notes_block = self.format_notes(file_path=file_path)
        if notes_block:
            sections.append(f"### Notes (codebase observations)\n{notes_block}")

        pending = self.format_todos(status="pending", target_file=file_path)
        in_progress = self.format_todos(status="in_progress", target_file=file_path)
        if pending or in_progress:
            todo_lines = []
            if pending:
                todo_lines.append(pending)
            if in_progress:
                todo_lines.append(in_progress)
            sections.append(
                "### Pending Todos (address these where relevant)\n"
                + "\n".join(todo_lines)
            )

        analyzed = self.analyzed_files()
        if analyzed:
            preview = ", ".join(analyzed[:15])
            if len(analyzed) > 15:
                preview += f", ... (+{len(analyzed) - 15} more)"
            sections.append(f"### Already Analyzed Files\n{preview}")

        return "\n\n".join(sections)

    # -- internals ------------------------------------------------------

    def _can_touch_todo(self, todo_id: str) -> bool:
        if self._role == ROLE_ORCHESTRATOR:
            return True
        todo = next((t for t in self.todos() if t.id == todo_id), None)
        if todo is None:
            return False
        if self._role == ROLE_FILE_ANALYSIS:
            if todo.source == self._role:
                return True
            if self._file_scope is not None and todo.target_file == self._file_scope:
                return True
        return False
