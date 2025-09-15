# """Qdrant codebase indexer for vector storage and retrieval"""

# import os  # pyright: ignore[reportUnusedImport]
# import hashlib
# from typing import List, Dict, Any, Optional
# from sentence_transformers import SentenceTransformer
# from qdrant_client import QdrantClient
# from qdrant_client.models import (
#     Distance, VectorParams, PointStruct, 
#     Filter, FieldCondition, MatchValue
# )
# from ..agents.schemas import CodeChunk
# import time


# class QdrantCodebaseIndexer:
#     """Indexer for storing and retrieving code embeddings using Qdrant"""
    
#     def __init__(self, 
#                  collection_name: str = "codebase",
#                  qdrant_url: Optional[str] = None,
#                  qdrant_api_key: Optional[str] = None,
#                  use_memory: bool = True):
#         """
#         Initialize the Qdrant codebase indexer
        
#         Args:
#             collection_name: Name of the Qdrant collection
#             qdrant_url: URL of Qdrant server (None for in-memory)
#             qdrant_api_key: API key for Qdrant cloud
#             use_memory: Use in-memory storage (for testing)
#         """
#         self.collection_name = collection_name
        
#         # Initialize Qdrant client
#         if use_memory:
#             self.client = QdrantClient(":memory:")
#         else:
#             self.client = QdrantClient(
#                 url=qdrant_url,
#                 api_key=qdrant_api_key,
#                 https=True,
#                 timeout=300000,
#             )
        
#         # Initialize embedding models
#         print("Loading embedding models...")
#         self.nlp_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
#         self.code_model = SentenceTransformer('jinaai/jina-embeddings-v2-base-code')
        
#         # Get embedding dimensions
#         self.nlp_dim = self.nlp_model.get_sentence_embedding_dimension()
#         self.code_dim = self.code_model.get_sentence_embedding_dimension()
        
#         # Create collection if it doesn't exist
#         self._create_collection()
    
#     def _create_collection(self):
#         """Create Qdrant collection with multiple vectors"""
#         try:
#             collections = self.client.get_collections().collections
#             collection_exists = any(col.name == self.collection_name for col in collections)
            
#             if collection_exists:
#                 print(f"Collection '{self.collection_name}' already exists")
#                 # Check if the existing collection has the correct vector configuration
#                 try:
#                     self.client.get_collection(self.collection_name)
#                     # If we can get the collection info, it's valid, so we'll use it
#                     print(f"Using existing collection '{self.collection_name}'")
#                 except Exception:
#                     # If we can't get collection info, try to recreate it
#                     print(f"Existing collection '{self.collection_name}' appears corrupted, recreating...")
#                     self.client.delete_collection(self.collection_name)
#                     collection_exists = False
            
#             if not collection_exists:
#                 # Create collection with multiple named vectors
#                 self.client.create_collection(
#                     collection_name=self.collection_name,
#                     vectors_config={
#                         "nlp": VectorParams(size=self.nlp_dim, distance=Distance.COSINE),
#                         "code": VectorParams(size=self.code_dim, distance=Distance.COSINE),
#                     }
#                 )
#                 print(f"Created collection '{self.collection_name}'")
#         except Exception as e:
#             print(f"Error creating collection: {e}")
    
#     def index_chunks(self, chunks: List[CodeChunk], batch_size: int = 32):
#         """Index code chunks into Qdrant"""
#         print(f"Indexing {len(chunks)} chunks...")
        
#         for i in range(0, len(chunks), batch_size):
#             batch = chunks[i:i + batch_size]
#             points = []
            
#             for chunk in batch:
#                 # Generate unique ID for the chunk
#                 chunk_id = self._generate_chunk_id(chunk)
                
#                 # Generate embeddings
#                 nlp_text = chunk.natural_language or self._chunk_to_natural_language(chunk)
#                 nlp_embedding = self.nlp_model.encode(nlp_text)
#                 code_embedding = self.code_model.encode(chunk.code)
                
#                 # Create payload
#                 payload = {
#                     "name": chunk.name,
#                     "signature": chunk.signature,
#                     "code_type": chunk.code_type,
#                     "docstring": chunk.docstring,
#                     "code": chunk.code,
#                     "line": chunk.line,
#                     "line_from": chunk.line_from,
#                     "line_to": chunk.line_to,
#                     "context": chunk.context,
#                     "natural_language": nlp_text
#                 }
                
#                 # Create point with multiple vectors
#                 point = PointStruct(
#                     id=chunk_id,
#                     vector={
#                         "nlp": nlp_embedding.tolist(),
#                         "code": code_embedding.tolist()
#                     },
#                     payload=payload
#                 )
#                 points.append(point)
            
#             # Upload points to Qdrant
#             self.client.upload_points(
#                 collection_name=self.collection_name,
#                 points=points,
#                 batch_size=batch_size,
#                 wait=True
#             )
            
#             print(f"Indexed batch {i//batch_size + 1}/{(len(chunks) + batch_size - 1)//batch_size}")
        
#         print(f"Successfully indexed {len(chunks)} chunks")
    
#     def search_nlp(self, query: str, limit: int = 10, filter_dict: Optional[Dict] = None) -> List[Dict[str, Any]]:
#         """Search using natural language query"""
#         # Generate query embedding
#         query_embedding = self.nlp_model.encode(query)
        
#         # Build filter if provided
#         filter_obj = None
#         if filter_dict:
#             filter_obj = self._build_filter(filter_dict)
        
#         # Search
#         results = self.client.search(
#             collection_name=self.collection_name,
#             query_vector=("nlp", query_embedding.tolist()),
#             limit=limit,
#             with_payload=True,
#             query_filter=filter_obj
#         )
        
#         return [{"score": hit.score, **hit.payload} for hit in results]
    
#     def search_code(self, code_snippet: str, limit: int = 10, filter_dict: Optional[Dict] = None) -> List[Dict[str, Any]]:
#         """Search using code snippet"""
#         # Generate query embedding
#         query_embedding = self.code_model.encode(code_snippet)
        
#         # Build filter if provided
#         filter_obj = None
#         if filter_dict:
#             filter_obj = self._build_filter(filter_dict)
        
#         # Search
#         results = self.client.search(
#             collection_name=self.collection_name,
#             query_vector=("code", query_embedding.tolist()),
#             limit=limit,
#             with_payload=True,
#             query_filter=filter_obj
#         )
        
#         return [{"score": hit.score, **hit.payload} for hit in results]
    
#     def hybrid_search(self, query: str, code_snippet: Optional[str] = None, 
#                      nlp_limit: int = 5, code_limit: int = 20) -> Dict[str, List[Dict[str, Any]]]:
#         """
#         Perform hybrid search using both NLP and code embeddings
        
#         Args:
#             query: Natural language query
#             code_snippet: Optional code snippet for code search
#             nlp_limit: Number of results from NLP search
#             code_limit: Number of results from code search
        
#         Returns:
#             Dictionary with 'nlp' and 'code' results
#         """
#         results = {}
        
#         # NLP search
#         results['nlp'] = self.search_nlp(query, limit=nlp_limit)
        
#         # Code search
#         if code_snippet:
#             results['code'] = self.search_code(code_snippet, limit=code_limit)
#         else:
#             # Use the query as code snippet if not provided
#             results['code'] = self.search_code(query, limit=code_limit)
        
#         # Merge and deduplicate results
#         results['merged'] = self._merge_results(results['nlp'], results['code'])
        
#         return results
    
#     def search_by_type(self, code_type: str, limit: int = 50) -> List[Dict[str, Any]]:
#         """Search for all chunks of a specific type"""
#         filter_dict = {"code_type": code_type}
        
#         # Use scroll to get all results
#         results = self.client.scroll(
#             collection_name=self.collection_name,
#             scroll_filter=self._build_filter(filter_dict),
#             limit=limit,
#             with_payload=True,
#             with_vectors=False
#         )
        
#         return [{"id": str(hit.id), **hit.payload} for hit in results[0]]
    
#     def search_by_file(self, file_path: str) -> List[Dict[str, Any]]:
#         """Get all chunks from a specific file"""
#         filter_dict = {"context.file_path": file_path}
        
#         results = self.client.scroll(
#             collection_name=self.collection_name,
#             scroll_filter=self._build_filter(filter_dict),
#             with_payload=True,
#             with_vectors=False
#         )
        
#         chunks = [{"id": str(hit.id), **hit.payload} for hit in results[0]]
        
#         # Sort by line number
#         return sorted(chunks, key=lambda x: x.get('line_from', 0))
    
#     def delete_by_file(self, file_path: str):
#         """Delete all chunks from a specific file"""
#         filter_dict = {"context.file_path": file_path}
        
#         self.client.delete(
#             collection_name=self.collection_name,
#             points_selector=self._build_filter(filter_dict)
#         )
    
#     def get_statistics(self) -> Dict[str, Any]:
#         """Get statistics about the indexed codebase"""
#         collection_info = self.client.get_collection(self.collection_name)
        
#         # Get counts by type
#         type_counts = {}
#         for code_type in ["function", "method", "class", "module", "property", "enum"]:
#             count = self.client.count(
#                 collection_name=self.collection_name,
#                 count_filter=self._build_filter({"code_type": code_type})
#             )
#             type_counts[code_type] = count.count
        
#         return {
#             "total_chunks": collection_info.points_count,
#             "vectors_count": collection_info.vectors_count,
#             "type_counts": type_counts,
#             "collection_info": {
#                 "status": collection_info.status,
#                 "vectors_config": collection_info.config.params.vectors
#             }
#         }
    
#     def _generate_chunk_id(self, chunk: CodeChunk) -> str:
#         """Generate unique ID for a code chunk"""
#         # Create a unique string from chunk properties
#         unique_str = f"{chunk.context.get('file_path', '')}:{chunk.name}:{chunk.line_from}:{chunk.code_type}"
#         return hashlib.md5(unique_str.encode()).hexdigest()
    
#     def _chunk_to_natural_language(self, chunk: CodeChunk) -> str:
#         """Convert chunk to natural language if not already provided"""
#         parts = []
        
#         # Add code type and name
#         parts.append(f"{chunk.code_type} {chunk.name}")
        
#         # Add docstring if available
#         if chunk.docstring:
#             first_line = chunk.docstring.strip().split('\n')[0]
#             parts.append(first_line)
        
#         # Add file context
#         if chunk.context.get('class_name'):
#             parts.append(f"in class {chunk.context['class_name']}")
        
#         parts.append(f"from {chunk.context.get('module', 'unknown module')}")
        
#         return '. '.join(parts)
    
#     def _build_filter(self, filter_dict: Dict[str, Any]) -> Filter:
#         """Build Qdrant filter from dictionary"""
#         conditions = []
        
#         for key, value in filter_dict.items():
#             if '.' in key:
#                 # Nested field
#                 conditions.append(
#                     FieldCondition(
#                         key=key,
#                         match=MatchValue(value=value)
#                     )
#                 )
#             else:
#                 conditions.append(
#                     FieldCondition(
#                         key=key,
#                         match=MatchValue(value=value)
#                     )
#                 )
        
#         return Filter(must=conditions)
    
#     def _merge_results(self, nlp_results: List[Dict], code_results: List[Dict]) -> List[Dict[str, Any]]:
#         """Merge and deduplicate results from NLP and code search"""
#         # Create a map to track unique results
#         unique_results = {}
        
#         # Add NLP results with higher priority
#         for result in nlp_results:
#             key = (result['context']['file_path'], result['name'], result['line_from'])
#             if key not in unique_results:
#                 unique_results[key] = {**result, 'search_type': 'nlp', 'nlp_score': result['score']}
        
#         # Add code results
#         for result in code_results:
#             key = (result['context']['file_path'], result['name'], result['line_from'])
#             if key in unique_results:
#                 # Merge scores if already exists
#                 unique_results[key]['code_score'] = result['score']
#                 unique_results[key]['search_type'] = 'both'
#             else:
#                 unique_results[key] = {**result, 'search_type': 'code', 'code_score': result['score']}
        
#         # Convert back to list and sort by relevance
#         merged = list(unique_results.values())
        
#         # Sort by combined score (prioritize results found by both methods)
#         def sort_key(item):
#             if item['search_type'] == 'both':
#                 return (0, -(item.get('nlp_score', 0) + item.get('code_score', 0)))
#             elif item['search_type'] == 'nlp':
#                 return (1, -item.get('nlp_score', 0))
#             else:
#                 return (2, -item.get('code_score', 0))
        
#         return sorted(merged, key=sort_key)
