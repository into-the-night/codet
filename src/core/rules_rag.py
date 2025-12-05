"""RAG system for custom rules with vector embeddings and semantic search"""

import hashlib
import re
import logging
from pathlib import Path
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from sentence_transformers import SentenceTransformer
from qdrant_client import QdrantClient
from qdrant_client.models import (
    Distance, VectorParams, PointStruct,
    Filter, FieldCondition, MatchValue, MatchAny
)

logger = logging.getLogger(__name__)


@dataclass
class RuleChunk:
    """Represents a chunk of a custom rule with metadata"""
    content: str
    metadata: Dict[str, Any]
    natural_language: str
    
    def __post_init__(self):
        """Validate metadata has required fields"""
        required_fields = ['category', 'file_patterns', 'language', 'keywords']
        for field in required_fields:
            if field not in self.metadata:
                self.metadata[field] = [] if field in ['file_patterns', 'keywords'] else 'general'


class RulesRAG:
    """RAG system for chunking, indexing, and querying custom rules"""
    
    def __init__(
        self,
        collection_name: str = "codet_custom_rules",
        qdrant_url: Optional[str] = None,
        qdrant_api_key: Optional[str] = None,
        use_memory: bool = True
    ):
        """
        Initialize the Rules RAG system
        
        Args:
            collection_name: Name of the Qdrant collection for rules
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
                https=qdrant_url and qdrant_url.startswith("https"),
                timeout=30000,
            )
        
        # Initialize embedding model (use lightweight model for rules)
        self.embedding_model = SentenceTransformer('sentence-transformers/all-MiniLM-L6-v2')
        self.embedding_dim = self.embedding_model.get_sentence_embedding_dimension()
        
        # Create collection if it doesn't exist
        self._create_collection()
        
        # Rule chunks cache
        self.chunks: List[RuleChunk] = []
    
    def _create_collection(self):
        """Create Qdrant collection for rules"""
        try:
            collections = self.client.get_collections().collections
            collection_exists = any(col.name == self.collection_name for col in collections)
            
            if not collection_exists:
                self.client.create_collection(
                    collection_name=self.collection_name,
                    vectors_config=VectorParams(
                        size=self.embedding_dim,
                        distance=Distance.COSINE
                    )
                )
                logger.info(f"Created Qdrant collection: {self.collection_name}")
        except Exception as e:
            logger.error(f"Error creating collection: {e}")
            raise
    
    def chunk_rules(self, rules_content: str, source_file: str = "custom_rules") -> List[RuleChunk]:
        """
        Chunk markdown rules into semantic chunks with metadata
        
        Args:
            rules_content: Full content of rules markdown file
            source_file: Name of the source file for tracking
            
        Returns:
            List of RuleChunk objects
        """
        chunks = []
        lines = rules_content.split('\n')
        
        current_chunk = []
        current_category = 'general'
        current_subcategory = None
        
        i = 0
        while i < len(lines):
            line = lines[i]
            
            # Detect category headers (# or ##)
            if line.startswith('# ') and not line.startswith('## '):
                # Main category
                if current_chunk:
                    # Save previous chunk
                    chunk = self._create_chunk_from_lines(
                        current_chunk, current_category, current_subcategory, source_file
                    )
                    if chunk:
                        chunks.append(chunk)
                    current_chunk = []
                
                current_category = line[2:].strip().lower()
                current_subcategory = None
                current_chunk.append(line)
            
            elif line.startswith('## '):
                # Subcategory - start new chunk
                if current_chunk:
                    chunk = self._create_chunk_from_lines(
                        current_chunk, current_category, current_subcategory, source_file
                    )
                    if chunk:
                        chunks.append(chunk)
                    current_chunk = []
                
                current_subcategory = line[3:].strip()
                current_chunk.append(line)
            
            elif line.startswith('### '):
                # Sub-subcategory - start new chunk
                if current_chunk:
                    chunk = self._create_chunk_from_lines(
                        current_chunk, current_category, current_subcategory, source_file
                    )
                    if chunk:
                        chunks.append(chunk)
                    current_chunk = []
                
                current_chunk.append(line)
            
            else:
                # Regular content
                current_chunk.append(line)
            
            i += 1
        
        # Save last chunk
        if current_chunk:
            chunk = self._create_chunk_from_lines(
                current_chunk, current_category, current_subcategory, source_file
            )
            if chunk:
                chunks.append(chunk)
        
        self.chunks = chunks
        logger.info(f"Created {len(chunks)} rule chunks from {source_file}")
        return chunks
    
    def _create_chunk_from_lines(
        self,
        lines: List[str],
        category: str,
        subcategory: Optional[str],
        source_file: str
    ) -> Optional[RuleChunk]:
        """Create a RuleChunk from a list of lines"""
        # Filter out empty lines at start/end
        while lines and not lines[0].strip():
            lines.pop(0)
        while lines and not lines[-1].strip():
            lines.pop()
        
        if not lines:
            return None
        
        content = '\n'.join(lines)
        
        # Extract metadata
        metadata = self._extract_metadata(content, category, subcategory, source_file)
        
        # Generate natural language representation
        natural_language = self._to_natural_language(content, metadata)
        
        return RuleChunk(
            content=content,
            metadata=metadata,
            natural_language=natural_language
        )
    
    def _extract_metadata(
        self,
        content: str,
        category: str,
        subcategory: Optional[str],
        source_file: str
    ) -> Dict[str, Any]:
        """Extract metadata from rule content"""
        metadata = {
            'category': category,
            'subcategory': subcategory or '',
            'source_file': source_file,
            'file_patterns': [],
            'language': 'general',
            'keywords': [],
            'is_test_related': False,
            'priority': 'medium'
        }
        
        content_lower = content.lower()
        
        # Detect language from subcategory or content
        language_mapping = {
            'python': ['python', '.py', 'django', 'flask'],
            'javascript': ['javascript', '.js', 'node', 'react', 'vue'],
            'typescript': ['typescript', '.ts', 'angular'],
            'java': ['java', '.java'],
            'go': ['go', 'golang', '.go'],
            'rust': ['rust', '.rs'],
            'cpp': ['c++', 'cpp', '.cpp'],
        }
        
        for lang, keywords in language_mapping.items():
            if any(kw in content_lower for kw in keywords):
                metadata['language'] = lang
                break
        
        # Extract file patterns
        # Look for patterns like *.py, test_*.py, etc.
        pattern_matches = re.findall(r'\*\.\w+|\w+_\*\.\w+|\*_\w+\.\w+', content)
        if pattern_matches:
            metadata['file_patterns'] = pattern_matches
        else:
            # Infer from language
            lang_to_patterns = {
                'python': ['*.py'],
                'javascript': ['*.js', '*.jsx'],
                'typescript': ['*.ts', '*.tsx'],
                'java': ['*.java'],
                'go': ['*.go'],
                'rust': ['*.rs'],
                'cpp': ['*.cpp', '*.h'],
            }
            metadata['file_patterns'] = lang_to_patterns.get(metadata['language'], ['*'])
        
        # Detect test-related rules
        test_keywords = ['test', 'testing', 'spec', 'unit test', 'integration test']
        metadata['is_test_related'] = any(kw in content_lower for kw in test_keywords)
        
        # Extract keywords (function/class names, important terms)
        # Look for camelCase, snake_case, and PascalCase identifiers
        keywords = re.findall(r'\b[a-z_][a-z0-9_]*\b|\b[A-Z][a-zA-Z0-9]*\b', content)
        # Filter common words
        common_words = {'the', 'a', 'an', 'and', 'or', 'but', 'in', 'on', 'at', 'to', 'for', 'of', 'with', 'by'}
        keywords = [kw for kw in keywords if kw.lower() not in common_words and len(kw) > 2]
        metadata['keywords'] = list(set(keywords))[:20]  # Limit to 20 unique keywords
        
        # Detect priority from content
        priority_keywords = {
            'critical': ['critical', 'must', 'required', 'always', 'never', 'security'],
            'high': ['important', 'should', 'recommended', 'vulnerability'],
            'low': ['consider', 'optional', 'suggestion', 'prefer']
        }
        
        for priority, keywords in priority_keywords.items():
            if any(kw in content_lower for kw in keywords):
                metadata['priority'] = priority
                break
        
        return metadata
    
    def _to_natural_language(self, content: str, metadata: Dict[str, Any]) -> str:
        """Convert rule content to natural language for better embeddings"""
        parts = []
        
        # Add category context
        category = metadata.get('category', 'general')
        subcategory = metadata.get('subcategory', '')
        if subcategory:
            parts.append(f"{category} - {subcategory}")
        else:
            parts.append(category)
        
        # Add language context
        language = metadata.get('language', 'general')
        if language != 'general':
            parts.append(f"for {language} files")
        
        # Add test context
        if metadata.get('is_test_related'):
            parts.append("related to testing")
        
        # Add priority
        priority = metadata.get('priority', 'medium')
        if priority in ['critical', 'high']:
            parts.append(f"[{priority} priority]")
        
        # Add the actual content (first 200 chars for summary)
        content_summary = content[:200].replace('\n', ' ').strip()
        parts.append(content_summary)
        
        return '. '.join(parts)
    
    def index_rules(self, chunks: Optional[List[RuleChunk]] = None, batch_size: int = 32):
        """
        Index rule chunks into Qdrant with vector embeddings
        
        Args:
            chunks: List of RuleChunk objects (uses self.chunks if None)
            batch_size: Batch size for indexing
        """
        if chunks is None:
            chunks = self.chunks
        
        if not chunks:
            logger.warning("No chunks to index")
            return
        
        points = []
        for chunk in chunks:
            # Generate unique ID
            chunk_id = self._generate_chunk_id(chunk)
            
            # Generate embedding from natural language representation
            embedding = self.embedding_model.encode(chunk.natural_language)
            
            # Create payload
            payload = {
                'content': chunk.content,
                'natural_language': chunk.natural_language,
                **chunk.metadata
            }
            
            # Create point
            point = PointStruct(
                id=chunk_id,
                vector=embedding.tolist(),
                payload=payload
            )
            points.append(point)
        
        # Upload in batches
        for i in range(0, len(points), batch_size):
            batch = points[i:i + batch_size]
            self.client.upload_points(
                collection_name=self.collection_name,
                points=batch,
                wait=True
            )
        
        logger.info(f"Indexed {len(points)} rule chunks into Qdrant")
    
    def index_rules_from_files(self, rule_file_paths: List[str]):
        """
        Load, chunk, and index rules from multiple files
        
        Args:
            rule_file_paths: List of paths to markdown rule files
        """
        all_chunks = []
        
        for file_path in rule_file_paths:
            try:
                path = Path(file_path)
                if not path.exists():
                    logger.warning(f"Rule file not found: {file_path}")
                    continue
                
                with open(path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                chunks = self.chunk_rules(content, source_file=path.name)
                all_chunks.extend(chunks)
                logger.info(f"Loaded {len(chunks)} chunks from {path.name}")
                
            except Exception as e:
                logger.error(f"Error loading rule file {file_path}: {e}")
                continue
        
        if all_chunks:
            self.index_rules(all_chunks)
    
    def query_rules(
        self,
        file_path: str,
        functions: Optional[List[str]] = None,
        classes: Optional[List[str]] = None,
        is_test: bool = False,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        Query relevant rules for a file using semantic search
        
        Args:
            file_path: Path to the file being analyzed
            functions: List of function names in the file
            classes: List of class names in the file
            is_test: Whether this is a test file
            limit: Maximum number of rules to return
            
        Returns:
            List of relevant rule chunks with scores
        """
        # Build semantic query from file context
        query_text = self._build_query_context(file_path, functions, classes, is_test)
        
        # Generate query embedding
        query_embedding = self.embedding_model.encode(query_text)
        
        # For now, don't use metadata filters - rely on semantic search
        # This gives better results as rules might be general
        
        # Perform search
        results = self.client.search(
            collection_name=self.collection_name,
            query_vector=query_embedding.tolist(),
            limit=limit * 2,  # Get more results for re-ranking
            with_payload=True
        )
        
        # Re-rank by relevance and priority
        ranked_results = self._rerank_results(results, file_path, functions, classes)
        
        return ranked_results[:limit]
    
    def _build_query_context(
        self,
        file_path: str,
        functions: Optional[List[str]],
        classes: Optional[List[str]],
        is_test: bool
    ) -> str:
        """Build semantic query text from file context"""
        parts = []
        
        # File extension and type
        path = Path(file_path)
        extension = path.suffix
        
        if extension:
            parts.append(f"rules for {extension} files")
        
        # Test file context
        if is_test:
            parts.append("testing and test files")
        
        # Function context
        if functions:
            func_list = ', '.join(functions[:5])  # Limit to first 5
            parts.append(f"with functions: {func_list}")
        
        # Class context
        if classes:
            class_list = ', '.join(classes[:5])
            parts.append(f"with classes: {class_list}")
        
        # File name context (extract meaningful parts)
        file_name = path.stem
        name_parts = re.split(r'[_\-.]', file_name)
        meaningful_parts = [p for p in name_parts if len(p) > 2 and p not in ['test', 'spec']]
        if meaningful_parts:
            parts.append(f"related to: {' '.join(meaningful_parts[:3])}")
        
        query = '. '.join(parts) if parts else f"rules for {file_path}"
        return query
    
    def _build_query_filter(self, file_path: str, is_test: bool) -> Optional[Filter]:
        """Build Qdrant filter for metadata matching"""
        conditions = []
        
        # Match file extension
        path = Path(file_path)
        extension = path.suffix
        
        if extension:
            # Try to match file patterns
            pattern = f"*{extension}"
            conditions.append(
                FieldCondition(
                    key="file_patterns",
                    match=MatchAny(any=[pattern])
                )
            )
        
        # Prefer test-related rules for test files
        if is_test:
            # Don't make it a hard filter, just prefer test rules in ranking
            pass
        
        if conditions:
            return Filter(should=conditions)  # Use 'should' for soft matching
        
        return None
    
    def _rerank_results(
        self,
        results: List[Any],
        file_path: str,
        functions: Optional[List[str]],
        classes: Optional[List[str]]
    ) -> List[Dict[str, Any]]:
        """Re-rank results based on additional relevance signals"""
        ranked = []
        
        functions_set = set(functions or [])
        classes_set = set(classes or [])
        
        for hit in results:
            payload = hit.payload
            score = hit.score
            
            # Boost score based on keyword matches
            keywords = set(payload.get('keywords', []))
            keyword_overlap = len(keywords & (functions_set | classes_set))
            if keyword_overlap > 0:
                score += 0.1 * keyword_overlap
            
            # Boost based on priority
            priority = payload.get('priority', 'medium')
            priority_boost = {'critical': 0.2, 'high': 0.1, 'medium': 0.0, 'low': -0.05}
            score += priority_boost.get(priority, 0.0)
            
            ranked.append({
                'score': score,
                'content': payload.get('content', ''),
                'category': payload.get('category', 'general'),
                'subcategory': payload.get('subcategory', ''),
                'language': payload.get('language', 'general'),
                'priority': priority,
                'file_patterns': payload.get('file_patterns', []),
                'keywords': list(keywords)
            })
        
        # Sort by adjusted score
        ranked.sort(key=lambda x: x['score'], reverse=True)
        
        return ranked
    
    def _generate_chunk_id(self, chunk: RuleChunk) -> str:
        """Generate unique ID for a rule chunk"""
        unique_str = f"{chunk.metadata.get('source_file', '')}:{chunk.metadata.get('category', '')}:{chunk.content[:50]}"
        return hashlib.md5(unique_str.encode()).hexdigest()
    
    def get_collection_size(self) -> int:
        """Get the number of indexed rule chunks"""
        try:
            collection_info = self.client.get_collection(self.collection_name)
            return collection_info.points_count
        except Exception as e:
            logger.error(f"Error getting collection size: {e}")
            return 0
    
    def clear_collection(self):
        """Clear all indexed rules"""
        try:
            self.client.delete_collection(self.collection_name)
            self._create_collection()
            self.chunks = []
            logger.info("Cleared rules collection")
        except Exception as e:
            logger.error(f"Error clearing collection: {e}")
