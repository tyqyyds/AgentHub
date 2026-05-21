#!/usr/bin/env python3
"""
智维 AgentHub - 网络自愈与运维系统启动脚本
"""

import subprocess
import sys
import os

def start_docker_services():
    """启动Docker容器服务"""
    print("🚀 启动Docker服务...")
    try:
        subprocess.run(
            ["docker-compose", "up", "-d"],
            check=True,
            capture_output=True,
            text=True
        )
        print("✅ Docker服务启动成功")
    except subprocess.CalledProcessError as e:
        print(f"❌ Docker服务启动失败: {e.stderr}")
        sys.exit(1)

def start_backend():
    """启动后端API服务"""
    print("🚀 启动后端API服务...")
    env = os.environ.copy()
    env["PYTHONPATH"] = "backend"
    
    subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--reload"],
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print("✅ 后端API服务启动成功")

def start_frontend():
    """启动前端开发服务器"""
    print("🚀 启动前端开发服务器...")
    subprocess.Popen(
        ["npm", "run", "dev"],
        cwd="frontend",
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE
    )
    print("✅ 前端开发服务器启动成功")

def main():
    print("=" * 60)
    print("智维 AgentHub - 网络自愈与运维系统")
    print("=" * 60)
    
    print("\n📋 启动步骤:")
    print("1. 启动Docker服务 (PostgreSQL, InfluxDB, Redis)")
    print("2. 启动后端API服务")
    print("3. 启动前端开发服务器")
    
    print("\n⏳ 请稍候...")
    
    start_docker_services()
    start_backend()
    start_frontend()
    
    print("\n🎉 服务启动完成！")
    print("📡 后端API: http://localhost:8000")
    print("🌐 前端界面: http://localhost:5173")
    print("\n按 Ctrl+C 停止所有服务")
    
    try:
        while True:
            pass
    except KeyboardInterrupt:
        print("\n👋 正在停止服务...")
        subprocess.run(["docker-compose", "down"])
        print("✅ 所有服务已停止")

if __name__ == "__main__":
    main()