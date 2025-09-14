#!/bin/bash

# Start development environment for codet
echo "🚀 Starting codet development environment..."

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

# Check if Docker is installed and running
if command -v docker &> /dev/null; then
    # Start Redis if not running
    if ! docker ps | grep -q codet-redis; then
        echo "🔴 Starting Redis..."
        docker-compose -f docker-compose.redis.yml up -d
    else
        echo "✅ Redis already running"
    fi
    
    # Start Qdrant if not running
    if ! docker ps | grep -q codet-qdrant; then
        echo "🔍 Starting Qdrant..."
        docker-compose -f docker-compose.qdrant.yml up -d
    else
        echo "✅ Qdrant already running"
    fi
else
    echo "⚠️  Docker not found. Redis and Qdrant will not be started."
    echo "   For caching and indexing features, please install Docker."
fi

# Start backend in background
echo "🔧 Starting backend server..."
cd /home/abhay/code/codet
uv run uvicorn src.api.main:app --reload --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait a moment for backend to start
sleep 3

# Start frontend
echo "🎨 Starting frontend development server..."
cd /home/abhay/code/codet/frontend
npm start &
FRONTEND_PID=$!

echo "✅ Development environment started!"
echo "   Backend: http://localhost:8000"
echo "   Frontend: http://localhost:3000"
echo "   API Docs: http://localhost:8000/docs"
echo ""
echo "Press Ctrl+C to stop both servers"

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
