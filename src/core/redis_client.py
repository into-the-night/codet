"""Redis client wrapper for caching and message history"""

import ssl
import json
import logging
import asyncio
from typing import Any, Dict, List, Optional, Union
from datetime import datetime, timedelta
import redis.asyncio as redis
from redis.asyncio import ConnectionPool

from .config import RedisConfig

logger = logging.getLogger(__name__)


class RedisClient:
    """Async Redis client wrapper with connection pooling and error handling"""
    
    def __init__(self, config: RedisConfig):
        self.config = config
        self._pool: Optional[ConnectionPool] = None
        self._client: Optional[redis.Redis] = None
        self._connected = False
    
    async def connect(self) -> bool:
        """Establish connection to Redis"""
        try:
            # Create connection pool
            if self.config.redis_url:
                # Check if SSL is needed (common for cloud Redis providers)
                use_ssl = (
                    self.config.port == 28510 or  # Common Heroku Redis SSL port
                    'heroku' in self.config.host.lower() or
                    'amazonaws' in self.config.host.lower() or
                    'redis.cloud' in self.config.host.lower()
                )
                pool_kwargs = {
                    'host': self.config.host,
                    'port': self.config.port,
                    'db': self.config.db,
                    'password': self.config.password,
                    'decode_responses': self.config.decode_responses,
                    'socket_connect_timeout': self.config.socket_connect_timeout,
                    'socket_timeout': self.config.socket_timeout,
                    'retry_on_timeout': self.config.retry_on_timeout,
                    'max_connections': self.config.max_connections
                }
                # Add SSL configuration if needed
                if use_ssl:
                    pool_kwargs['connection_class'] = redis.SSLConnection
                    pool_kwargs['ssl_cert_reqs'] = "none"
                    logger.info("Using SSL connection for Redis")
                                
                # Create connection pool
                self._pool = ConnectionPool(**pool_kwargs)

                self._client = redis.StrictRedis(connection_pool=self._pool)
            
            else:
                # Fall back to individual connection parameters
                self._pool = ConnectionPool(
                    host=self.config.host,
                    port=self.config.port,
                    db=self.config.db,
                    password=self.config.password,
                    decode_responses=self.config.decode_responses,
                    socket_connect_timeout=self.config.socket_connect_timeout,
                    socket_timeout=self.config.socket_timeout,
                    retry_on_timeout=self.config.retry_on_timeout,
                    max_connections=self.config.max_connections
                )
            
                # Create Redis client
                self._client = redis.Redis(connection_pool=self._pool)
            
            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.config.host}:{self.config.port}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False
    
    async def disconnect(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
        if self._pool:
            await self._pool.disconnect()
        self._connected = False
        logger.info("Disconnected from Redis")
    
    async def is_connected(self) -> bool:
        """Check if Redis is connected"""
        if not self._connected or not self._client:
            return False
        
        try:
            await self._client.ping()
            return True
        except Exception:
            self._connected = False
            return False
    
    async def _ensure_connected(self):
        """Ensure Redis connection is active"""
        if not await self.is_connected():
            await self.connect()
    
    # Cache operations
    async def get_cache(self, key: str) -> Optional[Any]:
        """Get value from cache"""
        if not self.config.enable_caching:
            return None
        
        try:
            await self._ensure_connected()
            value = await self._client.get(f"cache:{key}")
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.error(f"Error getting cache key {key}: {e}")
            return None
    
    async def set_cache(self, key: str, value: Any, ttl: Optional[int] = None) -> bool:
        """Set value in cache with optional TTL"""
        if not self.config.enable_caching:
            return False
        
        try:
            await self._ensure_connected()
            ttl = ttl or self.config.cache_ttl
            serialized_value = json.dumps(value, default=str)
            await self._client.setex(f"cache:{key}", ttl, serialized_value)
            return True
        except Exception as e:
            logger.error(f"Error setting cache key {key}: {e}")
            return False
    
    async def delete_cache(self, key: str) -> bool:
        """Delete cache key"""
        try:
            await self._ensure_connected()
            await self._client.delete(f"cache:{key}")
            return True
        except Exception as e:
            logger.error(f"Error deleting cache key {key}: {e}")
            return False
    
    async def clear_cache_pattern(self, pattern: str) -> int:
        """Clear cache keys matching pattern"""
        try:
            await self._ensure_connected()
            keys = await self._client.keys(f"cache:{pattern}")
            if keys:
                return await self._client.delete(*keys)
            return 0
        except Exception as e:
            logger.error(f"Error clearing cache pattern {pattern}: {e}")
            return 0
    
    # Message history operations
    async def add_message(self, session_id: str, message: Dict[str, Any]) -> bool:
        """Add message to session history"""
        if not self.config.enable_message_history:
            return False
        
        try:
            await self._ensure_connected()
            message['timestamp'] = datetime.now().isoformat()
            message_json = json.dumps(message, default=str)
            
            # Add to list
            await self._client.lpush(f"messages:{session_id}", message_json)
            
            # Set TTL on the session
            await self._client.expire(f"messages:{session_id}", self.config.message_history_ttl)
            
            return True
        except Exception as e:
            logger.error(f"Error adding message to session {session_id}: {e}")
            return False
    
    async def get_message_history(self, session_id: str, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        """Get message history for session"""
        if not self.config.enable_message_history:
            return []
        
        try:
            await self._ensure_connected()
            messages = await self._client.lrange(f"messages:{session_id}", 0, limit - 1 if limit else -1)
            
            # Parse messages (they're stored in reverse order, so reverse them)
            parsed_messages = []
            for message_json in reversed(messages):
                try:
                    message = json.loads(message_json)
                    parsed_messages.append(message)
                except json.JSONDecodeError:
                    continue
            
            return parsed_messages
        except Exception as e:
            logger.error(f"Error getting message history for session {session_id}: {e}")
            return []
    
    async def clear_message_history(self, session_id: str) -> bool:
        """Clear message history for session"""
        try:
            await self._ensure_connected()
            await self._client.delete(f"messages:{session_id}")
            return True
        except Exception as e:
            logger.error(f"Error clearing message history for session {session_id}: {e}")
            return False
    
    async def get_session_info(self, session_id: str) -> Dict[str, Any]:
        """Get session information"""
        try:
            await self._ensure_connected()
            message_count = await self._client.llen(f"messages:{session_id}")
            ttl = await self._client.ttl(f"messages:{session_id}")
            
            return {
                'session_id': session_id,
                'message_count': message_count,
                'ttl': ttl,
                'created_at': datetime.now().isoformat() if message_count > 0 else None
            }
        except Exception as e:
            logger.error(f"Error getting session info for {session_id}: {e}")
            return {'session_id': session_id, 'message_count': 0, 'ttl': -1}
    
    # Session management
    async def create_session(self, session_id: str, metadata: Optional[Dict[str, Any]] = None) -> bool:
        """Create a new session"""
        try:
            await self._ensure_connected()
            session_data = {
                'session_id': session_id,
                'created_at': datetime.now().isoformat(),
                'metadata': metadata or {}
            }
            
            await self._client.setex(
                f"session:{session_id}",
                self.config.message_history_ttl,
                json.dumps(session_data, default=str)
            )
            
            return True
        except Exception as e:
            logger.error(f"Error creating session {session_id}: {e}")
            return False
    
    async def get_session(self, session_id: str) -> Optional[Dict[str, Any]]:
        """Get session data"""
        try:
            await self._ensure_connected()
            session_data = await self._client.get(f"session:{session_id}")
            if session_data:
                return json.loads(session_data)
            return None
        except Exception as e:
            logger.error(f"Error getting session {session_id}: {e}")
            return None
    
    async def update_session_metadata(self, session_id: str, metadata: Dict[str, Any]) -> bool:
        """Update session metadata"""
        try:
            await self._ensure_connected()
            session_data = await self.get_session(session_id)
            if session_data:
                session_data['metadata'].update(metadata)
                session_data['updated_at'] = datetime.now().isoformat()
                
                await self._client.setex(
                    f"session:{session_id}",
                    self.config.message_history_ttl,
                    json.dumps(session_data, default=str)
                )
                return True
            return False
        except Exception as e:
            logger.error(f"Error updating session metadata for {session_id}: {e}")
            return False
    
    async def delete_session(self, session_id: str) -> bool:
        """Delete session and all associated data"""
        try:
            await self._ensure_connected()
            # Delete session data and message history
            await self._client.delete(f"session:{session_id}")
            await self._client.delete(f"messages:{session_id}")
            return True
        except Exception as e:
            logger.error(f"Error deleting session {session_id}: {e}")
            return False
    
    # Utility methods
    async def get_stats(self) -> Dict[str, Any]:
        """Get Redis statistics"""
        try:
            await self._ensure_connected()
            info = await self._client.info()
            
            # Count cache keys
            cache_keys = await self._client.keys("cache:*")
            message_keys = await self._client.keys("messages:*")
            session_keys = await self._client.keys("session:*")
            
            return {
                'connected': True,
                'cache_keys': len(cache_keys),
                'message_sessions': len(message_keys),
                'active_sessions': len(session_keys),
                'redis_info': {
                    'used_memory': info.get('used_memory_human', 'N/A'),
                    'connected_clients': info.get('connected_clients', 0),
                    'total_commands_processed': info.get('total_commands_processed', 0)
                }
            }
        except Exception as e:
            logger.error(f"Error getting Redis stats: {e}")
            return {
                'connected': False,
                'error': str(e)
            }
    
    async def health_check(self) -> Dict[str, Any]:
        """Perform health check"""
        try:
            await self._ensure_connected()
            start_time = datetime.now()
            await self._client.ping()
            response_time = (datetime.now() - start_time).total_seconds()
            
            return {
                'status': 'healthy',
                'response_time_ms': round(response_time * 1000, 2),
                'connected': True
            }
        except Exception as e:
            return {
                'status': 'unhealthy',
                'error': str(e),
                'connected': False
            }


# Global Redis client instance
_redis_client: Optional[RedisClient] = None


async def get_redis_client(config: RedisConfig) -> RedisClient:
    """Get or create global Redis client instance"""
    global _redis_client
    
    if _redis_client is None:
        _redis_client = RedisClient(config)
        await _redis_client.connect()
    
    return _redis_client


async def close_redis_client():
    """Close global Redis client"""
    global _redis_client
    
    if _redis_client:
        await _redis_client.disconnect()
        _redis_client = None
