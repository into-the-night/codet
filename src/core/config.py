"""Configuration management for Codet"""

from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    """Application settings loaded from environment variables"""
    # Gemini configuration (default cloud LLM)
    google_api_key: Optional[str] = Field(None, alias="GOOGLE_API_KEY")
    gemini_model: str = Field("gemini-2.5-flash", alias="GEMINI_MODEL")
    
    # Agent settings
    agent_temperature: float = Field(0.1, alias="AGENT_TEMPERATURE")
    agent_max_tokens: int = Field(8192, alias="AGENT_MAX_TOKENS")
    agent_timeout: int = Field(60, alias="AGENT_TIMEOUT")
    enable_caching: bool = Field(True, alias="ENABLE_CACHING")
    cache_dir: Path = Field(Path.home() / ".cqi" / "cache", alias="CACHE_DIR")
    
    # Ollama/Local LLM
    use_local_llm: bool = Field(False, alias="USE_LOCAL_LLM")
    ollama_model: str = Field("llama3.2", alias="OLLAMA_MODEL")
    
    # Qdrant settings
    qdrant_url: str = Field("http://localhost:6333", alias="QDRANT_URL")
    qdrant_api_key: Optional[str] = Field(None, alias="QDRANT_API_KEY")
    use_memory: bool = Field(False, alias="USE_MEMORY")
    
    # Redis settings
    redis_url: str = Field("redis://localhost:6379", alias="REDIS_URL")
    redis_host: str = Field("localhost", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_db: int = Field(0, alias="REDIS_DB")
    redis_password: Optional[str] = Field(None, alias="REDIS_PASSWORD")
    redis_decode_responses: bool = Field(True, alias="REDIS_DECODE_RESPONSES")
    redis_socket_connect_timeout: int = Field(5, alias="REDIS_CONNECT_TIMEOUT")
    redis_socket_timeout: int = Field(5, alias="REDIS_SOCKET_TIMEOUT")
    redis_retry_on_timeout: bool = Field(True, alias="REDIS_RETRY_ON_TIMEOUT")
    redis_max_connections: int = Field(20, alias="REDIS_MAX_CONNECTIONS")
    redis_enable_message_history: bool = Field(True, alias="REDIS_ENABLE_MESSAGE_HISTORY")
    redis_enable_caching: bool = Field(True, alias="REDIS_ENABLE_CACHING")
    redis_message_history_ttl: int = Field(86400, alias="REDIS_MESSAGE_HISTORY_TTL")  # 24 hours
    redis_cache_ttl: int = Field(3600, alias="REDIS_CACHE_TTL")  # 1 hour
    
    # Analyzer settings
    enable_parallel: bool = Field(True, alias="ENABLE_PARALLEL")
    max_workers: int = Field(4, alias="MAX_WORKERS")
    severity_threshold: str = Field("low", alias="SEVERITY_THRESHOLD")
    
    # Repository size thresholds for indexing
    repo_file_count_threshold: int = Field(100, alias="REPO_FILE_COUNT_THRESHOLD")
    repo_total_size_threshold: float = Field(10.0, alias="REPO_TOTAL_SIZE_THRESHOLD")  # MB
    repo_single_file_threshold: float = Field(1.0, alias="REPO_SINGLE_FILE_THRESHOLD")  # MB
    
    # General settings
    verbose: bool = Field(False, alias="VERBOSE")
    project_root: Path = Field(Path.cwd(), alias="PROJECT_ROOT")
    output_dir: Path = Field(Path.cwd() / "cqi_reports", alias="OUTPUT_DIR")
    
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore"
    )
    
    def validate_settings(self) -> bool:
        """Validate configuration"""
        # Check API key requirements based on provider
        if not self.use_local_llm:
            if not self.google_api_key:
                raise ValueError("Google API key not configured. Set GOOGLE_API_KEY environment variable.")

        if not self.project_root.exists():
            raise ValueError(f"Project root does not exist: {self.project_root}")
        
        # Ensure cache directory exists
        if self.enable_caching:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
        
        return True


# Create a single global instance
settings = Settings()


# Compatibility layer for old code
class AgentConfig:
    """Compatibility wrapper for agent config"""
    def __init__(self, s: Settings):
        self.temperature = s.agent_temperature
        self.max_tokens = s.agent_max_tokens
        self.timeout = s.agent_timeout
        self.enable_caching = s.enable_caching
        self.cache_dir = s.cache_dir
        self.use_local = s.use_local_llm
        self.ollama_model = s.ollama_model
        self.google_api_key = s.google_api_key
        self.gemini_model = s.gemini_model
        self.qdrant_url = s.qdrant_url
        self.qdrant_api_key = s.qdrant_api_key
        self.use_memory = s.use_memory


class RedisConfig:
    """Compatibility wrapper for redis config"""
    def __init__(self, s: Settings):
        self.redis_url = s.redis_url
        self.host = s.redis_host
        self.port = s.redis_port
        self.db = s.redis_db
        self.password = s.redis_password
        self.decode_responses = s.redis_decode_responses
        self.socket_connect_timeout = s.redis_socket_connect_timeout
        self.socket_timeout = s.redis_socket_timeout
        self.retry_on_timeout = s.redis_retry_on_timeout
        self.max_connections = s.redis_max_connections
        self.enable_message_history = s.redis_enable_message_history
        self.enable_caching = s.redis_enable_caching
        self.message_history_ttl = s.redis_message_history_ttl
        self.cache_ttl = s.redis_cache_ttl


class AnalyzerConfig:
    """Compatibility wrapper for analyzer config"""
    def __init__(self, s: Settings):
        self.enable_parallel = s.enable_parallel
        self.max_workers = s.max_workers
        self.severity_threshold = s.severity_threshold
        self.ignore_patterns = []
        self.custom_rules = {}


class Config:
    """Compatibility wrapper for old Config class"""
    def __init__(self, s: Settings):
        self.agent = AgentConfig(s)
        self.redis = RedisConfig(s)
        self.analyzer = AnalyzerConfig(s)
        self.project_root = s.project_root
        self.output_dir = s.output_dir
        self.verbose = s.verbose
        
    @classmethod
    def load(cls, config_path=None):
        """Load configuration (compatibility method)"""
        return cls(settings)
        
    def validate(self):
        """Validate configuration (compatibility method)"""
        return settings.validate_settings()