    ╔═══════════════════════════════════════════════╗
    ║                                               ║
    ║   ░█████╗░░█████╗░██████╗░███████╗████████╗   ║
    ║   ██╔══██╗██╔══██╗██╔══██╗██╔════╝╚══██╔══╝   ║
    ║   ██║░░╚═╝██║░░██║██║░░██║█████╗░░░░░██║░░░   ║
    ║   ██║░░██╗██║░░██║██║░░██║██╔══╝░░░░░██║░░░   ║
    ║   ╚█████╔╝╚█████╔╝██████╔╝███████╗░░░██║░░░   ║
    ║   ░╚════╝░░╚════╝░╚═════╝░╚══════╝░░░╚═╝░░░   ║
    ║                                               ║
    ║       🔍 Code Quality Intelligence Tool 🔍    ║
    ║                                               ║
    ╚═══════════════════════════════════════════════╝

An intelligent code quality analysis tool with AI-powered insights and semantic search.

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
- Local or Cloud Redis
- Local or Cloud Qdrant (for Vector Embeddings only)

### Setup

1. **Clone the repo**
```bash
# Clone and setup
git clone https://github.com/yourusername/codet.git
cd codet
cp config/env.example .env
```

2. **Install dependencies**
```bash
# Backend + CLI
uv venv
source .venv/bin/activate
uv pip install -r requirements.txt
uv pip install -e .

# Frontend
cd frontend && npm install && cd ..
```

3. **Configure environment**
```bash
cp config/env.example .env
# Add your GOOGLE_API_KEY to .env & QDRANT_URL , QDRANT_API_KEY for using Qdrant cloud VectorStore
```

## Usage

### CLI
```bash
# Analyze code
uv run codet analyze /path/to/code

# Large codebase is auto-indexed but to force use RAG, use the --index flag
uv run codet chat --index /path/to/project
```

### Web Interface
```bash
# Backend
uvicorn src.api.main:app --reload

# Frontend
cd frontend && npm start
```

1. Go to http://localhost:3000
2. Enter GitHub URL or upload files/folder
3. Click "Start Analysis"

## License

MIT