#!/usr/bin/env python3
"""Install Docker on remote server and deploy AgentHub"""
import paramiko
import os
import time
import sys

HOST = "47.96.133.207"
USER = "root"
PASSWORD = "@201314tyQ"
REMOTE_DIR = "/opt/agenthub"
LOCAL_ROOT = os.path.dirname(os.path.abspath(__file__))

EXCLUDE_DIRS = {
    "node_modules", ".git", "__pycache__", ".vite", "dist",
    ".agents", ".trae", ".vscode", ".idea",
    "chroma_data", ".pytest_cache",
}
EXCLUDE_FILES = {".env"}
EXCLUDE_PATTERNS = {".pyc", ".pyo", ".log", ".lock"}


def should_exclude(rel_path: str) -> bool:
    parts = rel_path.replace("\\", "/").split("/")
    for part in parts:
        if part in EXCLUDE_DIRS:
            return True
    filename = parts[-1] if parts else ""
    if filename in EXCLUDE_FILES:
        return True
    for ext in EXCLUDE_PATTERNS:
        if filename.endswith(ext):
            return True
    return False


def ssh_exec(client, cmd, timeout=300):
    """Execute command on remote server and return output"""
    print(f"  > {cmd[:100]}...")
    stdin, stdout, stderr = client.exec_command(cmd, timeout=timeout)
    exit_code = stdout.channel.recv_exit_status()
    out = stdout.read().decode().strip()
    err = stderr.read().decode().strip()
    return exit_code, out, err


def get_client():
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy)
    client.connect(HOST, username=USER, password=PASSWORD, timeout=30)
    return client


def install_docker(client):
    """Install Docker and Docker Compose on Ubuntu/Alibaba Cloud Linux"""
    print("\n[STEP] Installing Docker and Docker Compose...")

    # Check OS
    code, out, err = ssh_exec(client, "cat /etc/os-release | head -5")
    print(f"  OS: {out[:150]}")

    # Check if Docker already installed
    code, out, err = ssh_exec(client, "docker --version 2>/dev/null")
    if code == 0 and out:
        print(f"  [OK] Docker already installed: {out}")
        code, out2, err2 = ssh_exec(client, "docker compose version 2>/dev/null")
        if code == 0 and out2:
            print(f"  [OK] Docker Compose already installed: {out2}")
            return True

    # Install Docker using official script
    print("  Installing Docker via official script...")
    cmds = [
        "curl -fsSL https://get.docker.com -o /tmp/get-docker.sh",
        "sh /tmp/get-docker.sh 2>&1 | tail -10",
        "systemctl start docker && systemctl enable docker",
        "docker --version",
        "docker compose version 2>/dev/null || docker-compose --version 2>/dev/null",
    ]
    for cmd in cmds:
        code, out, err = ssh_exec(client, cmd, timeout=600)
        if out:
            print(f"  {out[:200]}")
        if code != 0 and "version" not in cmd:
            # Try alternative for Alibaba Cloud Linux
            if "get.docker.com" in cmd or "get-docker" in cmd:
                print("  Trying alternative Docker installation...")
                alt_cmds = [
                    "yum install -y yum-utils 2>/dev/null || apt-get install -y apt-transport-https ca-certificates curl software-properties-common 2>/dev/null",
                    "yum-config-manager --add-repo https://mirrors.aliyun.com/docker-ce/linux/centos/docker-ce.repo 2>/dev/null || curl -fsSL https://mirrors.aliyun.com/docker-ce/linux/ubuntu/gpg | apt-key add - 2>/dev/null",
                    "yum install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin 2>/dev/null || apt-get install -y docker-ce docker-ce-cli containerd.io docker-compose-plugin 2>/dev/null",
                    "systemctl start docker && systemctl enable docker",
                ]
                for acmd in alt_cmds:
                    code, out, err = ssh_exec(client, acmd, timeout=600)
                    if out:
                        print(f"  {out[:200]}")

    # Verify
    code, out, err = ssh_exec(client, "docker --version && docker compose version")
    if code == 0:
        print(f"  [OK] Docker installed: {out}")
        return True
    else:
        print(f"  [ERROR] Docker installation failed: {err[:200]}")
        return False


def sync_files(client):
    """Sync project files to remote server"""
    print("\n[STEP] Syncing project files...")

    # Create remote directory
    ssh_exec(client, f"mkdir -p {REMOTE_DIR}")

    sftp = client.open_sftp()

    def _sync(local_dir, remote_dir):
        try:
            sftp.stat(remote_dir)
        except FileNotFoundError:
            sftp.mkdir(remote_dir)

        for item in os.listdir(local_dir):
            local_path = os.path.join(local_dir, item)
            rel_path = os.path.relpath(local_path, LOCAL_ROOT)

            if should_exclude(rel_path):
                continue

            remote_path = f"{remote_dir}/{item}"

            if os.path.isdir(local_path):
                _sync(local_path, remote_path)
            elif os.path.isfile(local_path):
                try:
                    try:
                        remote_stat = sftp.stat(remote_path)
                        local_size = os.path.getsize(local_path)
                        if remote_stat.st_size == local_size:
                            continue
                    except FileNotFoundError:
                        pass
                    sftp.put(local_path, remote_path)
                except Exception as e:
                    print(f"  [WARN] Failed: {rel_path}: {e}")

    _sync(LOCAL_ROOT, REMOTE_DIR)
    sftp.close()
    print("  [OK] File sync completed")


def configure_env(client):
    """Configure .env on remote server"""
    print("\n[STEP] Configuring .env...")

    local_env = os.path.join(LOCAL_ROOT, ".env")
    if not os.path.exists(local_env):
        print("  [WARN] No local .env, creating from template...")
        env_content = """APP_NAME=NetOps_Intent_System
APP_VERSION=1.0.0
DEBUG=false
ENVIRONMENT=production

POSTGRES_HOST=postgres
POSTGRES_PORT=5432
POSTGRES_DB=agenthub
POSTGRES_USER=agenthub_app
POSTGRES_PASSWORD=AgentHub2024Secure!

REDIS_PASSWORD=AgentHub2024Redis!

INFLUXDB_URL=http://localhost:8086
INFLUXDB_TOKEN=
INFLUXDB_ORG=netops
INFLUXDB_BUCKET=telemetry

OPENAI_API_KEY=
OPENAI_MODEL=gpt-4-turbo-preview
LLM_MAX_TOKENS=4096
LLM_TIMEOUT=30

DEEPSEEK_API_KEY=
DEEPSEEK_API_URL=https://api.deepseek.com/v1/chat/completions
DEEPSEEK_MODEL=deepseek-chat

ZHIPU_API_KEY=
ZHIPU_API_URL=https://open.bigmodel.cn/api/paas/v4/chat/completions
ZHIPU_MODEL=glm-4-flash

LLM_PROVIDER_PRIORITY=zhipu,deepseek

SECRET_KEY=
CORS_ORIGINS=http://47.96.133.207,http://localhost:5173
ACCESS_TOKEN_EXPIRE_MINUTES=30
REFRESH_TOKEN_EXPIRE_DAYS=7

MAX_REQUESTS_PER_MINUTE=60
"""
    else:
        with open(local_env, "r") as f:
            env_content = f.read()
        # Override for production
        env_content = env_content.replace("ENVIRONMENT=development", "ENVIRONMENT=production")
        # Set Docker internal hostnames
        env_content = env_content.replace("POSTGRES_HOST=localhost", "POSTGRES_HOST=postgres")
        env_content = env_content.replace("REDIS_HOST=localhost", "REDIS_HOST=redis")

    # Write .env to remote
    cmd = f"""cat > {REMOTE_DIR}/.env << 'ENVEOF'
{env_content}
ENVEOF"""
    ssh_exec(client, cmd)
    print("  [OK] .env configured")


def start_services(client):
    """Build and start Docker Compose services"""
    print("\n[STEP] Building and starting Docker Compose...")

    # Add REDIS_PASSWORD to .env if missing
    ssh_exec(client, f"grep -q REDIS_PASSWORD {REMOTE_DIR}/.env || echo 'REDIS_PASSWORD=AgentHub2024Redis!' >> {REMOTE_DIR}/.env")

    # Stop existing services
    ssh_exec(client, f"cd {REMOTE_DIR} && docker compose down --remove-orphans 2>/dev/null || true")

    # Build and start
    code, out, err = ssh_exec(client, f"cd {REMOTE_DIR} && docker compose up -d --build 2>&1", timeout=900)
    if out:
        for line in out.split("\n")[-15:]:
            print(f"  {line}")
    if err and "error" in err.lower():
        for line in err.split("\n")[-10:]:
            print(f"  [ERR] {line}")

    print("  [OK] Docker Compose services started")


def verify_services(client):
    """Verify services are running"""
    print("\n[STEP] Verifying services...")
    time.sleep(15)

    code, out, err = ssh_exec(client, f"cd {REMOTE_DIR} && docker compose ps --format 'table {{{{.Name}}}}\t{{{{.Status}}}}\t{{{{.Ports}}}}'")
    if out:
        print(f"  {out}")
    else:
        code, out, err = ssh_exec(client, f"cd {REMOTE_DIR} && docker compose ps")
        print(f"  {out}")

    # Health check
    time.sleep(5)
    code, out, err = ssh_exec(client, "curl -sf http://localhost:8000/api/health 2>/dev/null || echo 'PENDING'")
    print(f"  Health: {out[:200]}")

    # Configure Nginx
    print("\n[STEP] Configuring Nginx...")
    code, out, err = ssh_exec(client, "which nginx 2>/dev/null")
    if code == 0:
        ssh_exec(client, f"cp {REMOTE_DIR}/nginx_agenthub.conf /etc/nginx/conf.d/agenthub.conf 2>/dev/null || true")
        code, out, err = ssh_exec(client, "nginx -t 2>&1")
        if "successful" in out or "successful" in err:
            ssh_exec(client, "nginx -s reload 2>&1")
            print("  [OK] Nginx configured and reloaded")
        else:
            print(f"  [WARN] Nginx config test: {out} {err}")
    else:
        print("  [INFO] Nginx not installed, installing...")
        ssh_exec(client, "apt-get update -qq && apt-get install -y nginx 2>/dev/null || yum install -y nginx 2>/dev/null", timeout=300)
        ssh_exec(client, f"cp {REMOTE_DIR}/nginx_agenthub.conf /etc/nginx/conf.d/agenthub.conf 2>/dev/null || cp {REMOTE_DIR}/nginx_agenthub.conf /etc/nginx/sites-available/agenthub 2>/dev/null")
        ssh_exec(client, "systemctl enable nginx && systemctl start nginx")
        code, out, err = ssh_exec(client, "nginx -t 2>&1 && nginx -s reload 2>&1")
        print(f"  [OK] Nginx installed and configured")

    # Open firewall
    ssh_exec(client, "ufw allow 80/tcp 2>/dev/null || firewall-cmd --permanent --add-port=80/tcp 2>/dev/null && firewall-cmd --reload 2>/dev/null || true")
    # Alibaba Cloud Security Group needs manual config


def main():
    print("=" * 60)
    print("AgentHub Deployment to Remote Server")
    print(f"Server: {HOST}")
    print(f"Remote: {REMOTE_DIR}")
    print("=" * 60)

    client = get_client()
    print("[OK] SSH connected")

    # 1. Install Docker
    if not install_docker(client):
        print("[FATAL] Cannot proceed without Docker")
        client.close()
        return

    # 2. Sync files
    sync_files(client)

    # 3. Configure .env
    configure_env(client)

    # 4. Start services
    start_services(client)

    # 5. Verify
    verify_services(client)

    client.close()
    print(f"\n{'=' * 60}")
    print(f"Deployment completed!")
    print(f"Frontend: http://{HOST}")
    print(f"API:      http://{HOST}:8000")
    print(f"API Docs: http://{HOST}:8000/docs")
    print(f"Note: Make sure Alibaba Cloud Security Group allows ports 80, 8000")
    print(f"{'=' * 60}")


if __name__ == "__main__":
    main()
