from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from pydantic import BaseModel
from typing import Optional, List
from ..database.connection import get_db_session
from ..database.models import Device, DeviceLink, DeviceVendor, DeviceType, DeviceStatus, LinkType, LinkStatus
from .deps import get_current_user

router = APIRouter()


class DeviceCreate(BaseModel):
    name: str
    ip: str
    vendor: str
    device_type: str
    location: Optional[str] = None
    snmp_community: Optional[str] = None
    ssh_port: int = 22


class DeviceUpdate(BaseModel):
    name: Optional[str] = None
    ip: Optional[str] = None
    status: Optional[str] = None
    location: Optional[str] = None


class LinkCreate(BaseModel):
    source_device_id: int
    target_device_id: int
    link_type: str
    bandwidth: Optional[str] = None
    latency_ms: Optional[float] = None


@router.get("/devices")
async def list_devices(
    vendor: Optional[str] = Query(None),
    device_type: Optional[str] = Query(None),
    status: Optional[str] = Query(None),
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    query = select(Device)
    if vendor:
        try:
            query = query.where(Device.vendor == DeviceVendor(vendor))
        except ValueError:
            pass
    if device_type:
        try:
            query = query.where(Device.device_type == DeviceType(device_type))
        except ValueError:
            pass
    if status:
        try:
            query = query.where(Device.status == DeviceStatus(status))
        except ValueError:
            pass
    query = query.offset(skip).limit(limit)
    result = await db.execute(query)
    devices = result.scalars().all()
    return {"status": "success", "data": [{"id": d.id, "name": d.name, "ip": d.ip, "vendor": d.vendor.value, "device_type": d.device_type.value, "status": d.status.value, "location": d.location} for d in devices]}


@router.get("/devices/{device_id}")
async def get_device(
    device_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    return {"status": "success", "data": {"id": device.id, "name": device.name, "ip": device.ip, "vendor": device.vendor.value, "device_type": device.device_type.value, "status": device.status.value, "location": device.location, "ssh_port": device.ssh_port}}


@router.post("/devices")
async def create_device(
    req: DeviceCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    try:
        vendor = DeviceVendor(req.vendor)
        dtype = DeviceType(req.device_type)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    device = Device(name=req.name, ip=req.ip, vendor=vendor, device_type=dtype, location=req.location, snmp_community=req.snmp_community, ssh_port=req.ssh_port)
    db.add(device)
    await db.commit()
    await db.refresh(device)
    return {"status": "success", "data": {"id": device.id}}


@router.put("/devices/{device_id}")
async def update_device(
    device_id: int,
    req: DeviceUpdate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    if req.name is not None:
        device.name = req.name
    if req.ip is not None:
        device.ip = req.ip
    if req.status is not None:
        try:
            device.status = DeviceStatus(req.status)
        except ValueError:
            raise HTTPException(status_code=400, detail="Invalid status")
    if req.location is not None:
        device.location = req.location
    await db.commit()
    return {"status": "success"}


@router.delete("/devices/{device_id}")
async def delete_device(
    device_id: int,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(Device).where(Device.id == device_id))
    device = result.scalar_one_or_none()
    if not device:
        raise HTTPException(status_code=404, detail="Device not found")
    await db.delete(device)
    await db.commit()
    return {"status": "success"}


@router.get("/links")
async def list_links(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    result = await db.execute(select(DeviceLink))
    links = result.scalars().all()
    return {"status": "success", "data": [{"id": l.id, "source_device_id": l.source_device_id, "target_device_id": l.target_device_id, "link_type": l.link_type.value, "bandwidth": l.bandwidth, "status": l.status.value, "latency_ms": l.latency_ms} for l in links]}


@router.post("/links")
async def create_link(
    req: LinkCreate,
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    try:
        link_type = LinkType(req.link_type)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid link type")
    link = DeviceLink(source_device_id=req.source_device_id, target_device_id=req.target_device_id, link_type=link_type, bandwidth=req.bandwidth, latency_ms=req.latency_ms)
    db.add(link)
    await db.commit()
    await db.refresh(link)
    return {"status": "success", "data": {"id": link.id}}


@router.get("/graph")
async def get_topology_graph(
    db: AsyncSession = Depends(get_db_session),
    current_user=Depends(get_current_user),
):
    dev_result = await db.execute(select(Device))
    devices = dev_result.scalars().all()
    link_result = await db.execute(select(DeviceLink))
    links = link_result.scalars().all()
    nodes = [{"id": d.id, "name": d.name, "ip": d.ip, "type": d.device_type.value, "status": d.status.value} for d in devices]
    edges = [{"source": l.source_device_id, "target": l.target_device_id, "type": l.link_type.value, "status": l.status.value} for l in links]
    return {"status": "success", "data": {"nodes": nodes, "edges": edges}}
