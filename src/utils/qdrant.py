"""Base Qdrant client utility for vector storage and retrieval"""

import hashlib
import logging
from typing import List, Dict, Any, Optional, Union
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct, 
    Filter, FieldCondition, MatchValue
)

logger = logging.getLogger(__name__)

class QdrantBase:
    """Base class for Qdrant operations to be shared across indexers"""
    
    def __init__(self, 
                 collection_name: str,
                 qdrant_url: Optional[str] = None,
                 qdrant_api_key: Optional[str] = None,
                 use_memory: bool = True):
        """
        Initialize the Qdrant base client
        
        Args:
            collection_name: Name of the Qdrant collection
            qdrant_url: URL of Qdrant server (None for in-memory)
            qdrant_api_key: API key for Qdrant cloud
            use_memory: Use in-memory storage (for testing)
        """
        self.collection_name = collection_name
        
        # Initialize Qdrant client
        if use_memory:
            self.client = QdrantClient(":memory:")
        else:
            self.client = QdrantClient(
                url=qdrant_url or "http://localhost:6333",
                api_key=qdrant_api_key,
                https=qdrant_url.startswith("https") if qdrant_url else False,
                timeout=300000,
            )
            
    def _collection_exists(self) -> bool:
        """Check if the collection exists"""
        try:
            collections = self.client.get_collections().collections
            return any(col.name == self.collection_name for col in collections)
        except Exception as e:
            logger.error(f"Error checking collection existence: {e}")
            return False

    def create_collection(self, vectors_config: Union[VectorParams, Dict[str, VectorParams]]):
        """Create Qdrant collection if it doesn't exist"""
        try:
            if not self._collection_exists():
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=vectors_config
                )
                logger.info(f"Created collection: {self.collection_name}")
            else:
                # Basic validation if collection exists
                try:
                    self.client.get_collection(self.collection_name)
                except Exception:
                    logger.warning(f"Collection {self.collection_name} exists but is inaccessible. Recreating.")
                    self.client.delete_collection(self.collection_name)
                    self.client.create_collection(
                        collection_name=self.collection_name,
                        vectors_config=vectors_config
                    )
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise

    def _build_filter(self, filter_dict: Dict[str, Any], must: bool = True) -> Filter:
        """Build Qdrant filter from dictionary"""
        from qdrant_client.models import MatchAny
        conditions = []
        for key, value in filter_dict.items():
            if isinstance(value, list):
                match = MatchAny(any=value)
            else:
                match = MatchValue(value=value)
                
            conditions.append(
                FieldCondition(
                    key=key,
                    match=match
                )
            )
        
        if must:
            return Filter(must=conditions)
        else:
            return Filter(should=conditions)

    def delete_collection(self):
        """Delete the entire collection"""
        try:
            self.client.delete_collection(self.collection_name)
            logger.info(f"Deleted collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error deleting collection: {e}")

    def generate_id(self, input_str: str) -> str:
        """Generate a consistent UUID-like ID from a string"""
        return hashlib.md5(input_str.encode()).hexdigest()

    def count(self, filter_dict: Optional[Dict[str, Any]] = None) -> int:
        """Count points in the collection (optionally with filter)"""
        try:
            filter_obj = self._build_filter(filter_dict) if filter_dict else None
            result = self.client.count(
                collection_name=self.collection_name,
                count_filter=filter_obj
            )
            return result.count
        except Exception as e:
            logger.error(f"Error counting points: {e}")
            return 0

    def get_info(self):
        """Get collection information"""
        try:
            return self.client.get_collection(self.collection_name)
        except Exception as e:
            logger.error(f"Error getting collection info: {e}")
            return None
