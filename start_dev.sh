#!/bin/bash

# Start development environment for codet
echo "🚀 Starting codet development environment..."

# Get the directory of this script
SCRIPT_DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$SCRIPT_DIR"

# Check if uv is installed
if ! command -v uv &> /dev/null; then
    echo "❌ uv is not installed. Please install uv first."
    echo "   Visit: https://docs.astral.sh/uv/getting-started/installation/"
    exit 1
fi

# Check if Node.js is installed
if ! command -v node &> /dev/null; then
    echo "❌ Node.js is not installed. Please install Node.js first."
    echo "   Visit: https://nodejs.org/"
    exit 1
fi

# Check if .env file exists
if [ ! -f .env ]; then
    echo "⚠️  .env file not found. Creating from config/env.example..."
    if [ -f config/env.example ]; then
        cp config/env.example .env
        echo "   Please edit .env and add your API keys."
    else
        echo "❌ config/env.example not found. Please create .env manually."
        exit 1
    fi
fi

# Check if Docker is installed and running
if command -v docker &> /dev/null && docker info &> /dev/null; then
    # Start Redis if not running
    if ! docker ps | grep -q codet-redis; then
        echo "🔴 Starting Redis..."
        docker-compose -f docker/docker-compose.redis.yml up -d
    else
        echo "✅ Redis already running"
    fi
    
    # Start Qdrant if not running
    if ! docker ps | grep -q codet-qdrant; then
        echo "🔍 Starting Qdrant..."
        docker-compose -f docker/docker-compose.qdrant.yml up -d
    else
        echo "✅ Qdrant already running"
    fi
else
    echo "⚠️  Docker not found or not running. Redis and Qdrant will not be started."
    echo "   For caching and indexing features, please install Docker."
fi

# Install Python dependencies if needed
if [ ! -d "src.egg-info" ] && [ ! -d "code_quality_intelligence.egg-info" ]; then
    echo "📦 Installing Python dependencies..."
    uv pip install -e .
fi

# Install frontend dependencies if needed
if [ ! -d "frontend/node_modules" ]; then
    echo "📦 Installing frontend dependencies..."
    cd frontend
    npm install
    cd ..
fi

# Start backend in background
echo "🔧 Starting backend server..."
uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 3

# Start frontend
echo "🎨 Starting frontend development server..."
cd frontend
npm start &
FRONTEND_PID=$!
cd ..

echo ""
echo "✅ Development environment started!"
echo "   Backend: http://localhost:8000"
echo "   Frontend: http://localhost:3000"
echo "   API Docs: http://localhost:8000/docs"
if command -v docker &> /dev/null && docker ps | grep -q codet-redis-commander; then
    echo "   Redis Commander: http://localhost:8081"
fi
echo ""
echo "Press Ctrl+C to stop all servers"

# Function to cleanup on exit
cleanup() {
    echo ""
    echo "🛑 Stopping servers..."
    kill $BACKEND_PID 2>/dev/null
    kill $FRONTEND_PID 2>/dev/null
    echo "✅ Servers stopped"
    exit 0
}

# Set trap to cleanup on script exit
trap cleanup SIGINT SIGTERM

# Wait for both processes
wait