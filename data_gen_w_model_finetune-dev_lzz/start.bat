@echo off
chcp 65001 >nul
echo ============================================================
echo   数据治理 ^& 模型微调平台 启动脚本
echo ============================================================
echo.

REM 关闭旧的进程
echo [0/4] 关闭旧进程...
REM 杀掉后端窗口标题
taskkill /fi "WINDOWTITLE eq Backend*" /f 2>nul
taskkill /fi "WINDOWTITLE eq Frontend*" /f 2>nul
REM 杀掉占用端口的进程
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :8000') do taskkill /pid %%a /f 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5173') do taskkill /pid %%a /f 2>nul
for /f "tokens=5" %%a in ('netstat -ano ^| findstr :5174') do taskkill /pid %%a /f 2>nul
REM 杀掉 python 后端进程（兜底）
taskkill /fi "IMAGENAME eq python.exe" /fi "WINDOWTITLE eq Backend" /f 2>nul
timeout /t 2 >nul
echo.

REM 激活 conda 环境
call conda activate aivmw 2>nul
set KMP_DUPLICATE_LIB_OK=TRUE

REM --- 先启动后端，等待就绪后再启动前端 ---
echo [1/3] 启动后端服务...
start "Backend" cmd /k "cd /d %~dp0 && call conda activate aivmw && set KMP_DUPLICATE_LIB_OK=TRUE && python -m backend.main"

echo [2/3] 等待后端就绪 (8000)...
:check_backend
timeout /t 2 >nul
curl -s http://localhost:8000/api/health >nul 2>&1
if %ERRORLEVEL% NEQ 0 (
    echo   等待中...
    goto :check_backend
)
echo   后端已就绪！
echo.

REM --- 启动前端 ---
echo [3/3] 启动前端界面...
start "Frontend" cmd /k "cd /d %~dp0frontend && npm run dev"

timeout /t 3 >nul

echo.
echo ============================================================
echo   启动完成！
echo   后端 API:  http://localhost:8000/docs
echo   前端界面:  http://localhost:5173
echo ============================================================
echo.
pause >nul
