#!/bin/bash
echo "========================================"
echo "  躬行启杭 - 学军中学交流平台"
echo "  北京科技大学实践团"
echo "========================================"
echo ""

cd "$(dirname "$0")/.."

# 检查 Python
if ! command -v python3 &> /dev/null && ! command -v python &> /dev/null; then
    echo "[错误] 未找到 Python，请先安装 Python 3.9+"
    exit 1
fi
PYTHON=$(command -v python3 || command -v python)

# 检查 Node.js
if ! command -v node &> /dev/null; then
    echo "[错误] 未找到 Node.js，请先安装 Node.js"
    exit 1
fi

echo "[1/4] 安装后端 Python 依赖..."
cd backend
$PYTHON -m pip install -r requirements.txt -q
cd ..

echo "[2/4] 安装前端依赖..."
cd frontend
npm install
cd ..

echo "[3/4] 启动后端服务 (端口 8000)..."
cd backend
$PYTHON main.py &
BACKEND_PID=$!
cd ..

sleep 3

echo "[4/4] 启动前端服务 (端口 5173)..."
cd frontend
npx vite --host 0.0.0.0 &
FRONTEND_PID=$!
cd ..

echo ""
echo "========================================"
echo "  启动完成！"
echo "  前端地址：http://localhost:5173"
echo "  后端地址：http://localhost:8000"
echo "  管理后台：http://localhost:5173/admin"
echo ""
echo "  按 Ctrl+C 停止所有服务"
echo "========================================"

trap "kill $BACKEND_PID $FRONTEND_PID 2>/dev/null; exit" INT TERM
wait
