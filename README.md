# Codet

An intelligent code quality analysis tool that analyzes codebases, identifies quality issues, and provides interactive Q&A capabilities.

## Features

### 🔍 Comprehensive Code Analysis
- **Multi-language support**: Python, JavaScript/TypeScript, and more
- **Repository-wide analysis**: Analyze entire codebases or specific files
- **Relationship understanding**: Understands connections between different parts of code
- **🎯 Orchestrator Flow**: Intelligent file selection and iterative analysis for comprehensive coverage

### 🛡️ Quality Issue Detection
- **Security vulnerabilities**: SQL injection, hardcoded credentials, weak crypto
- **Performance bottlenecks**: Inefficient algorithms, resource leaks
- **Code duplication**: Within files and across the codebase
- **Complexity issues**: High cyclomatic complexity, deep nesting
- **Testing gaps**: Missing tests, low coverage areas
- **Documentation issues**: Missing docstrings, outdated comments

### 📊 Detailed Reports
- **Comprehensive analysis**: Detailed explanations of issues
- **Actionable suggestions**: How to fix each issue
- **Priority-based sorting**: Issues ranked by severity and impact
- **Multiple formats**: JSON, HTML, Console output

### 💬 Interactive Q&A
- Natural language questions about your codebase
- Conversational responses with code context
- Follow-up questions and clarifications
- **Redis Integration**: Message history and response caching for improved performance

## Project Structure

```
codet/
├── src/                    # Main source code
│   ├── core/              # Core analysis engine
│   │   ├── analyzer.py    # Base analyzer interface
│   │   ├── engine.py      # Main analysis orchestrator
│   │   └── repository.py  # Repository management
│   ├── analyzers/         # Language-specific analyzers
│   │   ├── python_analyzer.py
│   │   ├── javascript_analyzer.py
│   │   ├── security_analyzer.py
│   │   ├── complexity_analyzer.py
│   │   └── duplication_analyzer.py
│   ├── reports/           # Report generation
│   ├── api/              # REST API
│   │   ├── main.py       # FastAPI application
│   │   └── models.py     # Pydantic models
│   └── cli.py            # Command-line interface
├── frontend/             # React web interface
│   ├── src/
│   │   ├── components/   # React components
│   │   ├── pages/       # Page components
│   │   └── services/    # API services
│   └── public/
├── tests/               # Test suite
├── config/             # Configuration files
├── docs/              # Documentation
└── data/             # Sample projects and cache
```

## Installation

### Prerequisites
- Python 3.9+
- Node.js 16+ (for frontend)
- uv (Python package manager) [[memory:5461534]]
- Redis server (optional, for caching and message history)

### Backend Setup

1. Clone the repository:
```bash
git clone <repository-url>
cd codet
```

2. Install Python dependencies using uv:
```bash
uv pip install -e .
```

Or using pip:
```bash
pip install -e .
```

3. (Optional) Start Redis server for caching and message history:
```bash
# Using Docker Compose
docker-compose -f docker-compose.redis.yml up -d

# Or install Redis locally
# Ubuntu/Debian: sudo apt-get install redis-server
# macOS: brew install redis
```

### Frontend Setup

1. Navigate to frontend directory:
```bash
cd frontend
```

2. Install dependencies:
```bash
npm install
```

## Usage

### Command Line Interface

Analyze a repository using the intelligent orchestrator flow:
```bash
codet analyze /path/to/your/code --config config.yaml
```

Analyze specific languages:
```bash
codet analyze /path/to/your/code -l python -l javascript --config config.yaml
```

Generate JSON report:
```bash
codet analyze /path/to/your/code -f json -o report.json --config config.yaml
```

With file limits and other options:
```bash
codet analyze /path/to/your/code \
  --config config.yaml \
  --languages python javascript \
  --max-files 50 \
  --output report.json \
  --format json
```

### Web Interface

Start the API server:
```bash
codet serve
```

In a separate terminal, start the frontend:
```bash
cd frontend
npm start
```

Access the web interface at `http://localhost:3000`

### API Usage

The REST API is available at `http://localhost:8000` when running the server.

Example API call:
```bash
curl -X POST "http://localhost:8000/api/analyze" \
  -H "Content-Type: application/json" \
  -d '{"path": "/path/to/code", "languages": ["python", "javascript"]}'
```

API documentation is available at `http://localhost:8000/docs`

## How It Works

The analysis uses an intelligent orchestrator flow that provides comprehensive coverage of your codebase:

1. **Strategic File Selection**: The orchestrator intelligently selects which files to analyze based on importance:
   - Entry points (main.py, index.js, app.py, etc.)
   - Core business logic files
   - Configuration files (config.py, package.json, requirements.txt)
   - Test files and test configuration
   - Documentation files
   - Large or complex files

2. **Individual File Analysis**: Each selected file is analyzed by a specialized agent that focuses on:
   - Code quality and maintainability
   - Security vulnerabilities
   - Performance issues
   - Architectural concerns
   - Testing gaps
   - Documentation issues

3. **Iterative Process**: The analysis continues in iterations until comprehensive coverage is achieved:
   - First pass: Critical files (entry points, core logic, config)
   - Second pass: Supporting files and utilities
   - Third pass: Test files and documentation
   - Final pass: Any remaining important files

4. **Result Aggregation**: All analysis results are collected, prioritized, and returned with detailed metrics.

### Benefits

- **Better Coverage**: Ensures all important files are analyzed
- **Higher Efficiency**: Focuses on critical files first
- **Scalability**: Handles large repositories effectively
- **Intelligence**: AI-powered file selection and analysis coordination

The orchestrator flow ensures comprehensive coverage while being efficient and scalable.

## Configuration

Edit `config/default.yaml` to customize:
- Analysis thresholds
- File patterns to include/exclude
- Analyzer-specific settings
- API configuration
- Redis settings (for caching and message history)

### Redis Configuration

For Redis integration, see [REDIS_INTEGRATION.md](REDIS_INTEGRATION.md) for detailed setup and configuration options.

## Development

### Running Tests

```bash
pytest tests/
```

### Code Quality

Run linters:
```bash
black src/
isort src/
mypy src/
pylint src/
```

## Architecture

The system follows a modular architecture:

1. **Core Engine**: Orchestrates analysis across multiple analyzers
2. **Analyzers**: Pluggable modules for different languages and quality aspects
3. **Repository Manager**: Handles file discovery and filtering
4. **Report Generator**: Creates formatted output in various formats
5. **API Layer**: RESTful interface for web integration
6. **CLI**: Command-line interface for terminal usage

## Roadmap

- [x] LLM integration for Q&A functionality
- [x] Redis integration for caching and message history
- [ ] More language support (Java, C++, Go, Rust)
- [ ] IDE plugins (VS Code, IntelliJ)
- [ ] CI/CD integration (GitHub Actions, GitLab CI)
- [ ] Real-time analysis during development
- [ ] Team collaboration features
- [ ] Historical trend analysis
- [ ] Custom rule creation

## Contributing

Contributions are welcome! Please read our contributing guidelines before submitting PRs.

## License

This project is licensed under the MIT License - see the LICENSE file for details.

## Support

For issues, questions, or suggestions, please open an issue on GitHub.
