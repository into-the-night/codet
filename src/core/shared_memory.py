"""Shared memory for maintaining cross-codebase context during analysis sessions"""

import logging
from typing import List
from threading import Lock

logger = logging.getLogger(__name__)


class SharedMemory:
    """
    In-memory shared memory for maintaining action items across agent interactions.
    
    Orchestrator can:
    - Add items
    - Remove items
    - Clear all items
    
    Sub-agents can:
    - Read all items
    - Append new items (add only)
    """
    
    def __init__(self):
        """Initialize shared memory with an empty list of action items"""
        self._items: List[str] = []
        self._lock = Lock()
        logger.info("SharedMemory initialized")
    
    def add_items(self, items: List[str]) -> None:
        """
        Add new action items to shared memory.
        
        Args:
            items: List of action item strings to add
        """
        if not items:
            return
        
        with self._lock:
            # Only add unique items to avoid duplicates
            for item in items:
                if item and item.strip() and item not in self._items:
                    self._items.append(item.strip())
                    logger.debug(f"Added to shared memory: {item.strip()}")
    
    def remove_items(self, items: List[str]) -> None:
        """
        Remove specific action items from shared memory.
        Typically used by orchestrator after items are completed.
        
        Args:
            items: List of action item strings to remove
        """
        if not items:
            return
        
        with self._lock:
            for item in items:
                if item in self._items:
                    self._items.remove(item)
                    logger.debug(f"Removed from shared memory: {item}")
    
    def get_all_items(self) -> List[str]:
        """
        Get all current action items in shared memory.
        
        Returns:
            List of action item strings
        """
        with self._lock:
            return self._items.copy()
    
    def clear(self) -> None:
        """Clear all action items from shared memory"""
        with self._lock:
            count = len(self._items)
            self._items.clear()
            logger.info(f"Cleared {count} items from shared memory")
    
    def __len__(self) -> int:
        """Return the number of items in shared memory"""
        with self._lock:
            return len(self._items)
    
    def __str__(self) -> str:
        """String representation of shared memory"""
        with self._lock:
            if not self._items:
                return "SharedMemory: empty"
            return f"SharedMemory: {len(self._items)} items"
    
    def format_items(self) -> str:
        """
        Format all items as a numbered list for display in prompts.
        
        Returns:
            Formatted string with numbered items, or empty string if no items
        """
        with self._lock:
            if not self._items:
                return ""
            
            formatted = []
            for idx, item in enumerate(self._items, 1):
                formatted.append(f"{idx}. {item}")
            
            return "\n".join(formatted)

