<#
算力节点模拟器启动脚本

使用方法：
.\start_node_simulator.ps1 -NodeId "node-gpu-01" -Region "beijing" -NodeType "gpu" -Port 8081

参数：
- NodeId: 节点ID（默认：node-sim-001）
- Region: 节点地域（默认：beijing）
- NodeType: 节点类型（cpu/gpu/edge，默认：cpu）
- Port: 监听端口（默认：8080）
#>

param(
    [string]$NodeId = "node-sim-001",
    [string]$Region = "beijing",
    [string]$NodeType = "cpu",
    [int]$Port = 8080
)

$env:NODE_ID = $NodeId
$env:NODE_REGION = $Region
$env:NODE_TYPE = $NodeType
$env:NODE_PORT = $Port

Write-Host "🚀 启动算力节点模拟器 $NodeId"
Write-Host "📍 节点类型: $NodeType"
Write-Host "🌍 节点地域: $Region"
Write-Host "🔌 监听端口: $Port"
Write-Host "=" * 50

python simulator/node_server.py