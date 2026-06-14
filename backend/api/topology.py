from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
import asyncio
from backend.database.connection import get_db_session
from backend.database.models import Device, DeviceLink
from backend.core.security.rbac import get_current_user
from backend.map.topology_map_fusion import get_topology_map_fusion
from backend.api.response import success_response

router = APIRouter()

DEFAULT_DEVICES = [
    {"device_id": "central", "name": "核心交换机", "device_type": "core", "vendor": "huawei", "ip_address": "10.0.0.1", "status": "healthy", "cpu_usage": 35.2, "memory_usage": 42.1},
    {"device_id": "core1", "name": "核心路由器-1", "device_type": "core", "vendor": "cisco", "ip_address": "10.0.0.2", "status": "healthy", "cpu_usage": 28.5, "memory_usage": 38.7},
    {"device_id": "core2", "name": "核心路由器-2", "device_type": "core", "vendor": "cisco", "ip_address": "10.0.0.3", "status": "healthy", "cpu_usage": 31.8, "memory_usage": 45.3},
    {"device_id": "agg1", "name": "汇聚交换机-1", "device_type": "aggregation", "vendor": "huawei", "ip_address": "10.0.1.1", "status": "healthy", "cpu_usage": 22.1, "memory_usage": 30.5},
    {"device_id": "agg2", "name": "汇聚交换机-2", "device_type": "aggregation", "vendor": "huawei", "ip_address": "10.0.1.2", "status": "healthy", "cpu_usage": 25.4, "memory_usage": 33.2},
    {"device_id": "agg3", "name": "汇聚交换机-3", "device_type": "aggregation", "vendor": "h3c", "ip_address": "10.0.1.3", "status": "warning", "cpu_usage": 78.9, "memory_usage": 72.1},
    {"device_id": "acc1", "name": "接入交换机-1", "device_type": "access", "vendor": "huawei", "ip_address": "10.0.2.1", "status": "healthy", "cpu_usage": 15.3, "memory_usage": 22.8},
    {"device_id": "acc2", "name": "接入交换机-2", "device_type": "access", "vendor": "h3c", "ip_address": "10.0.2.2", "status": "warning", "cpu_usage": 68.2, "memory_usage": 55.4},
    {"device_id": "acc3", "name": "接入交换机-3", "device_type": "access", "vendor": "huawei", "ip_address": "10.0.2.3", "status": "healthy", "cpu_usage": 18.7, "memory_usage": 25.1},
    {"device_id": "acc4", "name": "接入交换机-4", "device_type": "access", "vendor": "h3c", "ip_address": "10.0.2.4", "status": "error", "cpu_usage": 95.1, "memory_usage": 88.3},
]

DEFAULT_LINKS = [
    {"source_device_id": "central", "target_device_id": "core1", "status": "active", "bandwidth": "40G", "current_load": 65.0, "latency": 1.2},
    {"source_device_id": "central", "target_device_id": "core2", "status": "active", "bandwidth": "40G", "current_load": 58.0, "latency": 1.5},
    {"source_device_id": "core1", "target_device_id": "core2", "status": "active", "bandwidth": "10G", "current_load": 82.0, "latency": 2.1},
    {"source_device_id": "core1", "target_device_id": "agg1", "status": "active", "bandwidth": "10G", "current_load": 31.0, "latency": 3.5},
    {"source_device_id": "core1", "target_device_id": "agg2", "status": "active", "bandwidth": "10G", "current_load": 45.0, "latency": 4.2},
    {"source_device_id": "core2", "target_device_id": "agg2", "status": "active", "bandwidth": "10G", "current_load": 28.0, "latency": 3.8},
    {"source_device_id": "core2", "target_device_id": "agg3", "status": "warning", "bandwidth": "10G", "current_load": 75.0, "latency": 8.5},
    {"source_device_id": "agg1", "target_device_id": "acc1", "status": "active", "bandwidth": "1G", "current_load": 45.0, "latency": 5.3},
    {"source_device_id": "agg1", "target_device_id": "acc2", "status": "active", "bandwidth": "1G", "current_load": 68.0, "latency": 6.8},
    {"source_device_id": "agg2", "target_device_id": "acc2", "status": "active", "bandwidth": "1G", "current_load": 52.0, "latency": 5.9},
    {"source_device_id": "agg2", "target_device_id": "acc3", "status": "active", "bandwidth": "1G", "current_load": 38.0, "latency": 4.7},
    {"source_device_id": "agg3", "target_device_id": "acc3", "status": "active", "bandwidth": "1G", "current_load": 41.0, "latency": 7.2},
    {"source_device_id": "agg3", "target_device_id": "acc4", "status": "error", "bandwidth": "1G", "current_load": 95.0, "latency": 25.6},
]


_default_data_initialized = False
_default_data_lock = asyncio.Lock()

async def ensure_default_data(db: AsyncSession):
    global _default_data_initialized
    if _default_data_initialized:
        return
    async with _default_data_lock:
        if _default_data_initialized:
            return
        result = await db.execute(select(Device).limit(1))
        if result.scalars().first():
            _default_data_initialized = True
            return
        for d in DEFAULT_DEVICES:
            db.add(Device(**d))
        for l in DEFAULT_LINKS:
            db.add(DeviceLink(**l))
        await db.commit()
        _default_data_initialized = True


@router.get("")
async def get_topology(db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    await ensure_default_data(db)

    devices_result = await db.execute(select(Device))
    devices = devices_result.scalars().all()

    links_result = await db.execute(select(DeviceLink))
    links = links_result.scalars().all()

    nodes = []
    for d in devices:
        nodes.append({
            "id": d.device_id,
            "name": d.name,
            "type": d.device_type,
            "status": d.status,
            "ip": d.ip_address,
            "vendor": d.vendor,
            "cpu_usage": d.cpu_usage,
            "memory_usage": d.memory_usage,
            "uptime": d.uptime,
            "location": d.location,
        })

    link_list = []
    for l in links:
        link_list.append({
            "source": l.source_device_id,
            "target": l.target_device_id,
            "status": l.status,
            "bandwidth": l.bandwidth,
            "currentLoad": l.current_load,
            "latency": l.latency,
            "link_type": l.link_type,
        })

    return {
        "status": "success",
        "data": {
            "nodes": nodes,
            "links": link_list
        }
    }


@router.get("/devices")
async def get_devices(db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    await ensure_default_data(db)
    result = await db.execute(select(Device))
    devices = result.scalars().all()
    return {
        "status": "success",
        "data": [{
            "id": d.device_id,
            "name": d.name,
            "type": d.device_type,
            "vendor": d.vendor,
            "ip": d.ip_address,
            "status": d.status,
            "cpu_usage": d.cpu_usage,
            "memory_usage": d.memory_usage,
            "os_type": d.os_type,
            "ssh_port": d.ssh_port,
            "netconf_port": d.netconf_port,
            "uptime": d.uptime,
            "location": d.location,
        } for d in devices]
    }


@router.get("/devices/{device_id}")
async def get_device(device_id: str, db: AsyncSession = Depends(get_db_session), current_user=Depends(get_current_user)):
    result = await db.execute(select(Device).where(Device.device_id == device_id))
    device = result.scalars().first()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {
        "status": "success",
        "data": {
            "id": device.device_id,
            "name": device.name,
            "type": device.device_type,
            "vendor": device.vendor,
            "ip": device.ip_address,
            "status": device.status,
            "cpu_usage": device.cpu_usage,
            "memory_usage": device.memory_usage,
            "os_type": device.os_type,
            "ssh_port": device.ssh_port,
            "netconf_port": device.netconf_port,
            "uptime": device.uptime,
            "location": device.location,
        }
    }


@router.get("/links")
async def get_link_status_overlay(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user)
):
    await ensure_default_data(db)
    fusion = get_topology_map_fusion()
    links = await fusion.get_link_status_overlay(db)
    return success_response(data=links)


@router.get("/view")
async def get_combined_view(
    view_mode: str = Query("geographic", regex="^(geographic|logical|hybrid)$"),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user)
):
    await ensure_default_data(db)
    fusion = get_topology_map_fusion()
    view = await fusion.get_combined_view(db, view_mode=view_mode)
    return success_response(data=view)


@router.get("/health")
async def get_network_health_summary(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user)
):
    await ensure_default_data(db)
    fusion = get_topology_map_fusion()
    summary = await fusion.get_network_health_summary(db)
    return success_response(data=summary)


@router.get("/search")
async def search_devices_on_map(
    q: str = Query(..., min_length=1),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user)
):
    await ensure_default_data(db)
    fusion = get_topology_map_fusion()
    results = await fusion.search_devices_on_map(db, q)
    return success_response(data={"items": results, "total": len(results)})
