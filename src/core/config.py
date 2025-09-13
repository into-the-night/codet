"""Configuration management for Code Quality Intelligence Agent"""

import os
from pathlib import Path
from typing import Optional, Dict, Any
from dataclasses import dataclass
import json
import yaml
from dotenv import load_dotenv


@dataclass
class RedisConfig:
    """Configuration for Redis connection"""
    host: str = "localhost"
    port: int = 6379
    db: int = 0
    password: Optional[str] = None
    decode_responses: bool = True
    socket_connect_timeout: int = 5
    socket_timeout: int = 5
    retry_on_timeout: bool = True
    max_connections: int = 20
    enable_message_history: bool = True
    enable_caching: bool = True
    message_history_ttl: int = 86400  # 24 hours
    cache_ttl: int = 3600  # 1 hour


@dataclass
class AgentConfig:
    """Configuration for AI agents"""
    google_api_key: Optional[str] = None
    model_name: str = "gemini-2.5-flash"
    temperature: float = 0.1
    max_tokens: int = 8192
    timeout: int = 60
    enable_caching: bool = True
    cache_dir: Path = Path.home() / ".cqi" / "cache"
    
    # Ollama/Local LLM configuration
    use_local: bool = False
    ollama_model: str = "llama3.2"


@dataclass
class AnalyzerConfig:
    """Configuration for analyzers"""
    enable_parallel: bool = True
    max_workers: int = 4
    severity_threshold: str = "low"
    ignore_patterns: list = None
    custom_rules: Dict[str, Any] = None


@dataclass
class Config:
    """Main configuration class"""
    agent: AgentConfig
    analyzer: AnalyzerConfig
    redis: RedisConfig
    project_root: Path
    output_dir: Path
    verbose: bool = False
    
    @classmethod
    def load(cls, config_path: Optional[Path] = None) -> 'Config':
        """Load configuration from environment and files"""
        # Load environment variables
        load_dotenv()
        
        # Default configuration
        config_dict = {
            'agent': {
                'google_api_key': os.getenv('GOOGLE_API_KEY'),
                'model_name': os.getenv('GOOGLE_MODEL_NAME', 'gemini-2.5-flash'),
                'temperature': float(os.getenv('AGENT_TEMPERATURE', '0.1')),
                'max_tokens': int(os.getenv('AGENT_MAX_TOKENS', '8192')),
                'timeout': int(os.getenv('AGENT_TIMEOUT', '60')),
                'enable_caching': os.getenv('ENABLE_CACHING', 'true').lower() == 'true',
                'use_local': os.getenv('USE_LOCAL_LLM', 'false').lower() == 'true',
                'ollama_model': os.getenv('OLLAMA_MODEL', 'llama3.2'),
            },
            'analyzer': {
                'enable_parallel': os.getenv('ENABLE_PARALLEL', 'true').lower() == 'true',
                'max_workers': int(os.getenv('MAX_WORKERS', '4')),
                'severity_threshold': os.getenv('SEVERITY_THRESHOLD', 'low'),
                'ignore_patterns': [],
                'custom_rules': {}
            },
            'redis': {
                'host': os.getenv('REDIS_HOST', 'localhost'),
                'port': int(os.getenv('REDIS_PORT', '6379')),
                'db': int(os.getenv('REDIS_DB', '0')),
                'password': os.getenv('REDIS_PASSWORD'),
                'decode_responses': os.getenv('REDIS_DECODE_RESPONSES', 'true').lower() == 'true',
                'socket_connect_timeout': int(os.getenv('REDIS_CONNECT_TIMEOUT', '5')),
                'socket_timeout': int(os.getenv('REDIS_SOCKET_TIMEOUT', '5')),
                'retry_on_timeout': os.getenv('REDIS_RETRY_ON_TIMEOUT', 'true').lower() == 'true',
                'max_connections': int(os.getenv('REDIS_MAX_CONNECTIONS', '20')),
                'enable_message_history': os.getenv('REDIS_ENABLE_MESSAGE_HISTORY', 'true').lower() == 'true',
                'enable_caching': os.getenv('REDIS_ENABLE_CACHING', 'true').lower() == 'true',
                'message_history_ttl': int(os.getenv('REDIS_MESSAGE_HISTORY_TTL', '86400')),
                'cache_ttl': int(os.getenv('REDIS_CACHE_TTL', '3600')),
            },
            'project_root': Path.cwd(),
            'output_dir': Path.cwd() / 'cqi_reports',
            'verbose': os.getenv('VERBOSE', 'false').lower() == 'true'
        }
        
        # Load from config file if provided
        if config_path and config_path.exists():
            with open(config_path, 'r') as f:
                if config_path.suffix == '.json':
                    file_config = json.load(f)
                elif config_path.suffix in ['.yaml', '.yml']:
                    file_config = yaml.safe_load(f)
                else:
                    raise ValueError(f"Unsupported config file format: {config_path.suffix}")
                
                # Merge file config with defaults
                config_dict = cls._merge_configs(config_dict, file_config)
        
        # Create config objects
        agent_config = AgentConfig(**config_dict['agent'])
        analyzer_config = AnalyzerConfig(**config_dict['analyzer'])
        redis_config = RedisConfig(**config_dict['redis'])
        
        # Ensure cache directory exists
        if agent_config.enable_caching:
            agent_config.cache_dir.mkdir(parents=True, exist_ok=True)
        
        return cls(
            agent=agent_config,
            analyzer=analyzer_config,
            redis=redis_config,
            project_root=Path(config_dict['project_root']),
            output_dir=Path(config_dict['output_dir']),
            verbose=config_dict['verbose']
        )
    
    @staticmethod
    def _merge_configs(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
        """Recursively merge configuration dictionaries"""
        result = base.copy()
        
        for key, value in override.items():
            if key in result and isinstance(result[key], dict) and isinstance(value, dict):
                result[key] = Config._merge_configs(result[key], value)
            else:
                result[key] = value
        
        return result
    
    def validate(self) -> bool:
        """Validate configuration"""
        # Only require Google API key if not using local LLM
        if not self.agent.use_local and not self.agent.google_api_key:
            raise ValueError("Google API key not configured. Set GOOGLE_API_KEY environment variable or use --use-local flag.")
        
        if not self.project_root.exists():
            raise ValueError(f"Project root does not exist: {self.project_root}")
        
        return True
