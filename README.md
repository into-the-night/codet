# Codet

An intelligent code quality analysis tool with AI-powered insights and semantic search.

## Quick Start

```bash
# Clone and setup
git clone https://github.com/yourusername/codet.git
cd codet
cp config/env.example .env  # Add your GOOGLE_API_KEY, (QDRANT_URL & QDRANT_API_KEY if using QDRANT cloud [PREFERRED])
```

## Features

- 🔍 **Multi-language Analysis** - Python, JavaScript, TypeScript
- 🛡️ **Quality Detection** - Security, performance, complexity issues  
- 💬 **Interactive Q&A** - Ask questions about your codebase
- 🔎 **Semantic Search** - Find code by meaning, not just text
- 📊 **Detailed Reports** - Actionable insights with fix suggestions

## Installation

### Prerequisites
- Python 3.9+
- Node.js 16+
- [uv](https://docs.astral.sh/uv/) package manager
- Docker (optional, for Redis/Qdrant)

### Setup

1. **Install dependencies**
```bash
# Backend
uv pip install -e .

# Frontend
cd frontend && npm install && cd ..
```

2. **Configure environment**
```bash
cp config/env.example .env
# Add your GOOGLE_API_KEY to .env & QDRANT_URL , QDRANT_API_KEY for using Qdrant cloud VectorStore
```

3. **Start services**
```bash
# Option 1: Everything with Docker
docker-compose -f docker/docker-compose.yml up -d

# Option 2: Development mode
./start_dev.sh
```

## Usage

### CLI
```bash
# Analyze code
uv run codet analyze /path/to/code

# Chat with codebase
uv run codet chat /path/to/code

# Index flag for RAG
uv run codet chat --index /path/to/project
```

### Web Interface
1. Go to http://localhost:3000
2. Enter GitHub URL or local path
3. Click "Start Analysis"

### API
```bash
curl -X POST http://localhost:8000/api/analyze \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/code"}'
```

API docs: http://localhost:8000/docs

## Configuration

Create `config.yaml`:
```yaml
agent:
  google_api_key: ${GOOGLE_API_KEY}
  gemini_model: gemini-2.5-flash
  
analyzer:
  severity_threshold: low
  ignore_patterns:
    - "node_modules/**"
    - "*.min.js"
```

## Docker Services

- **API**: Port 8000
- **Frontend**: Port 3000 (if using Docker)
- **Redis**: Port 6379 (caching)
- **Qdrant**: Port 6333 (vector search)

```bash
# Start all
docker-compose -f docker/docker-compose.yml up -d

# Stop all
docker-compose -f docker/docker-compose.yml down
```

## Development

```bash
# Run tests
pytest

# Format code
black src/
```

## License

MIT