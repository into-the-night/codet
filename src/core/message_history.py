"""Message history management for AI agents"""

import json
import logging
import uuid
from typing import Dict, List, Optional, Any, Union
from datetime import datetime
from dataclasses import dataclass, asdict
from enum import Enum

from .redis_client import RedisClient
from .config import RedisConfig

logger = logging.getLogger(__name__)


class MessageRole(Enum):
    """Message roles in conversation"""
    SYSTEM = "system"
    HUMAN = "human"
    AI = "ai"
    FUNCTION = "function"


@dataclass
class Message:
    """Individual message in conversation history"""
    role: MessageRole
    content: str
    timestamp: datetime
    message_id: str
    metadata: Optional[Dict[str, Any]] = None
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'role': self.role.value,
            'content': self.content,
            'timestamp': self.timestamp.isoformat(),
            'message_id': self.message_id,
            'metadata': self.metadata or {}
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Message':
        """Create from dictionary"""
        return cls(
            role=MessageRole(data['role']),
            content=data['content'],
            timestamp=datetime.fromisoformat(data['timestamp']),
            message_id=data['message_id'],
            metadata=data.get('metadata')
        )


@dataclass
class ConversationSession:
    """Conversation session with metadata"""
    session_id: str
    created_at: datetime
    updated_at: datetime
    agent_name: str
    metadata: Dict[str, Any]
    message_count: int = 0
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary for serialization"""
        return {
            'session_id': self.session_id,
            'created_at': self.created_at.isoformat(),
            'updated_at': self.updated_at.isoformat(),
            'agent_name': self.agent_name,
            'metadata': self.metadata,
            'message_count': self.message_count
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'ConversationSession':
        """Create from dictionary"""
        return cls(
            session_id=data['session_id'],
            created_at=datetime.fromisoformat(data['created_at']),
            updated_at=datetime.fromisoformat(data['updated_at']),
            agent_name=data['agent_name'],
            metadata=data.get('metadata', {}),
            message_count=data.get('message_count', 0)
        )


class MessageHistoryManager:
    """Manages message history and conversation sessions using Redis"""
    
    def __init__(self, redis_client: RedisClient, config: RedisConfig):
        self.redis_client = redis_client
        self.config = config
    
    async def create_session(self, agent_name: str, metadata: Optional[Dict[str, Any]] = None) -> str:
        """Create a new conversation session"""
        session_id = str(uuid.uuid4())
        now = datetime.now()
        
        session = ConversationSession(
            session_id=session_id,
            created_at=now,
            updated_at=now,
            agent_name=agent_name,
            metadata=metadata or {}
        )
        
        # Store session metadata
        await self.redis_client._client.setex(
            f"session:{session_id}",
            self.config.message_history_ttl,
            json.dumps(session.to_dict(), default=str)
        )
        
        logger.info(f"Created new session {session_id} for agent {agent_name}")
        return session_id
    
    async def get_session(self, session_id: str) -> Optional[ConversationSession]:
        """Get session information"""
        try:
            session_data = await self.redis_client._client.get(f"session:{session_id}")
            if session_data:
                return ConversationSession.from_dict(json.loads(session_data))
            return None
        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None
    
    async def add_message(self, session_id: str, role: MessageRole, content: str, 
                         metadata: Optional[Dict[str, Any]] = None) -> str:
        """Add a message to the conversation history"""
        message_id = str(uuid.uuid4())
        now = datetime.now()
        
        message = Message(
            role=role,
            content=content,
            timestamp=now,
            message_id=message_id,
            metadata=metadata
        )
        
        # Add message to Redis list
        await self.redis_client._client.lpush(
            f"messages:{session_id}",
            json.dumps(message.to_dict(), default=str)
        )
        
        # Update session metadata
        await self._update_session_metadata(session_id, {'message_count': await self._get_message_count(session_id)})
        
        # Set TTL on the message list
        await self.redis_client._client.expire(f"messages:{session_id}", self.config.message_history_ttl)
        
        logger.debug(f"Added {role.value} message to session {session_id}")
        return message_id
    
    async def get_messages(self, session_id: str, limit: Optional[int] = None) -> List[Message]:
        """Get messages from conversation history"""
        try:
            # Get messages from Redis (they're stored in reverse order)
            messages_data = await self.redis_client._client.lrange(
                f"messages:{session_id}", 0, limit - 1 if limit else -1
            )
            
            # Parse and reverse to get chronological order
            messages = []
            for message_json in reversed(messages_data):
                try:
                    message_data = json.loads(message_json)
                    messages.append(Message.from_dict(message_data))
                except (json.JSONDecodeError, KeyError) as e:
                    logger.warning(f"Failed to parse message: {e}")
                    continue
            
            return messages
        except Exception as e:
            logger.error(f"Error getting messages for session {session_id}: {e}")
            return []
    
    async def get_recent_messages(self, session_id: str, count: int = 10) -> List[Message]:
        """Get recent messages from conversation"""
        return await self.get_messages(session_id, limit=count)
    
    async def get_messages_by_role(self, session_id: str, role: MessageRole) -> List[Message]:
        """Get messages filtered by role"""
        all_messages = await self.get_messages(session_id)
        return [msg for msg in all_messages if msg.role == role]
    
    async def clear_session(self, session_id: str) -> bool:
        """Clear all messages from a session"""
        try:
            await self.redis_client._client.delete(f"messages:{session_id}")
            await self._update_session_metadata(session_id, {'message_count': 0})
            logger.info(f"Cleared messages for session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing session {session_id}: {e}")
            return False
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session and all associated data"""
        try:
            await self.redis_client._client.delete(f"session:{session_id}")
            await self.redis_client._client.delete(f"messages:{session_id}")
            logger.info(f"Deleted session {session_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False
    
    async def get_session_summary(self, session_id: str) -> Dict[str, Any]:
        """Get summary of session activity"""
        session = await self.get_session(session_id)
        if not session:
            return {'error': 'Session not found'}
        
        messages = await self.get_messages(session_id)
        
        # Count messages by role
        role_counts = {}
        for message in messages:
            role = message.role.value
            role_counts[role] = role_counts.get(role, 0) + 1
        
        return {
            'session_id': session_id,
            'agent_name': session.agent_name,
            'created_at': session.created_at.isoformat(),
            'updated_at': session.updated_at.isoformat(),
            'total_messages': len(messages),
            'role_counts': role_counts,
            'metadata': session.metadata
        }
    
    async def search_messages(self, session_id: str, query: str, limit: int = 10) -> List[Message]:
        """Search messages by content"""
        messages = await self.get_messages(session_id)
        query_lower = query.lower()
        
        matching_messages = []
        for message in messages:
            if query_lower in message.content.lower():
                matching_messages.append(message)
                if len(matching_messages) >= limit:
                    break
        
        return matching_messages
    
    async def get_conversation_context(self, session_id: str, max_messages: int = 20) -> str:
        """Get formatted conversation context for AI agents"""
        messages = await self.get_recent_messages(session_id, max_messages)
        
        context_parts = []
        for message in messages:
            role_prefix = {
                MessageRole.SYSTEM: "System",
                MessageRole.HUMAN: "Human",
                MessageRole.AI: "AI",
                MessageRole.FUNCTION: "Function"
            }.get(message.role, "Unknown")
            
            context_parts.append(f"{role_prefix}: {message.content}")
        
        return "\n".join(context_parts)
    
    async def _get_message_count(self, session_id: str) -> int:
        """Get message count for session"""
        try:
            return await self.redis_client._client.llen(f"messages:{session_id}")
        except Exception:
            return 0
    
    async def _update_session_metadata(self, session_id: str, updates: Dict[str, Any]) -> bool:
        """Update session metadata"""
        try:
            session = await self.get_session(session_id)
            if session:
                session.metadata.update(updates)
                session.updated_at = datetime.now()
                
                await self.redis_client._client.setex(
                    f"session:{session_id}",
                    self.config.message_history_ttl,
                    json.dumps(session.to_dict(), default=str)
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating session metadata for {session_id}: {e}")
            return False
    
    async def get_all_sessions(self, agent_name: Optional[str] = None) -> List[ConversationSession]:
        """Get all sessions, optionally filtered by agent"""
        try:
            session_keys = await self.redis_client._client.keys("session:*")
            sessions = []
            
            for key in session_keys:
                try:
                    session_data = await self.redis_client._client.get(key)
                    if session_data:
                        session = ConversationSession.from_dict(json.loads(session_data))
                        if agent_name is None or session.agent_name == agent_name:
                            sessions.append(session)
                except Exception as e:
                    logger.warning(f"Failed to parse session data: {e}")
                    continue
            
            # Sort by updated_at descending
            sessions.sort(key=lambda s: s.updated_at, reverse=True)
            return sessions
        except Exception as e:
            logger.error(f"Error getting all sessions: {e}")
            return []
    
    async def cleanup_expired_sessions(self) -> int:
        """Clean up expired sessions (Redis TTL handles this automatically, but this is for manual cleanup)"""
        # Redis automatically handles TTL, but we can add manual cleanup logic here if needed
        return 0
