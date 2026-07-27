@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion

set "ROOT=%~dp0.."

echo ========================================
echo   躬行启杭 - 学军中学交流平台
echo   北京科技大学实践团
echo ========================================
echo.

:: 检查 Python
where python >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Python，请先安装 Python 3.9+
    echo 下载地址：https://www.python.org/downloads/
    pause
    exit /b 1
)

:: 检查 Node.js
where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [错误] 未找到 Node.js，请先安装 Node.js
    echo 下载地址：https://nodejs.org/
    pause
    exit /b 1
)

echo [1/4] 安装后端 Python 依赖...
pushd "%ROOT%\backend"
pip install -r requirements.txt -q 2>&1
popd

echo [2/4] 安装前端依赖...
pushd "%ROOT%\frontend"
call npm install
popd

echo [3/4] 启动后端服务 ^(端口 8000^)...
start "躬行启杭-后端" cmd /k "cd /d "%ROOT%\backend" && python main.py"

echo 等待后端服务启动...
timeout /t 3 >nul

echo [4/4] 启动前端服务 ^(端口 5173^)...
start "躬行启杭-前端" cmd /k "cd /d "%ROOT%\frontend" && npx vite --host 0.0.0.0"

echo.
echo ========================================
echo   启动完成！
echo.
echo   请在浏览器打开：http://localhost:5173
echo   管理后台：http://localhost:5173/admin
echo.
echo   直接关闭那两个黑窗口即可停止服务
echo ========================================
pause
