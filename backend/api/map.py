from fastapi import APIRouter, Depends, Query, HTTPException
from pydantic import BaseModel
from typing import List, Optional, Dict
from backend.core.security.rbac import get_current_user, requires_permission
from backend.map.poi_database import poi_db

import hashlib
import time
from backend.core.config import settings
import logging

logger = logging.getLogger(__name__)
router = APIRouter()

AMAP_KEY = settings.amap_key
AMAP_SECURITY_CODE = settings.amap_security_code


class POI(BaseModel):
    id: str
    name: str
    category: str
    lat: float
    lng: float
    address: str = ""
    description: str = ""
    metadata: Dict = {}


class POISearchRequest(BaseModel):
    query: str
    category: Optional[str] = None
    bounds: Optional[Dict[str, float]] = None
    limit: int = 50


class MapMarker(BaseModel):
    id: str
    lat: float
    lng: float
    title: str
    description: str = ""
    icon: str = "default"
    category: str = "custom"
    agent_id: Optional[str] = None


class MarkerBatchRequest(BaseModel):
    markers: List[MapMarker]


class TileProxyParams(BaseModel):
    layer: str = "standard"
    z: int
    x: int
    y: int


@router.get("/poi/search")
async def search_pois(
    q: str = Query(..., min_length=1),
    category: Optional[str] = None,
    lat: Optional[float] = None,
    lng: Optional[float] = None,
    radius: float = 50.0,
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user)
):
    results = poi_db.search(q, category=category, lat=lat, lng=lng, radius=radius, limit=limit)
    return {"status": "success", "data": results, "total": len(results)}


@router.get("/poi/nearby")
async def nearby_pois(
    lat: float = Query(...),
    lng: float = Query(...),
    radius: float = 50.0,
    category: Optional[str] = None,
    limit: int = Query(50, ge=1, le=200),
    current_user=Depends(get_current_user)
):
    results = poi_db.nearby(lat, lng, radius=radius, category=category, limit=limit)
    return {"status": "success", "data": results, "total": len(results)}


@router.get("/poi/categories")
async def poi_categories(current_user=Depends(get_current_user)):
    return {"status": "success", "data": poi_db.categories()}


@router.get("/amap/config")
async def amap_config(current_user=Depends(get_current_user)):
    if not AMAP_KEY:
        return {
            "status": "warning",
            "data": {
                "key_available": False,
                "message": "AMAP_KEY not configured. Set AMAP_KEY and AMAP_SECURITY_CODE environment variables.",
                "plugins": [
                    "AMap.Scale",
                    "AMap.ToolBar",
                    "AMap.Geolocation",
                    "AMap.PlaceSearch",
                    "AMap.Driving",
                    "AMap.Walking",
                    "AMap.Transfer",
                    "AMap.AutoComplete",
                    "AMap.MarkerCluster",
                ]
            }
        }
    ts = str(int(time.time()))
    sig = hashlib.md5(f"{AMAP_SECURITY_CODE}{ts}".encode()).hexdigest()
    return {
        "status": "success",
        "data": {
            "key": AMAP_KEY,
            "signature": sig,
            "timestamp": ts,
            "version": "2.0",
            "plugins": [
                "AMap.Scale",
                "AMap.ToolBar",
                "AMap.Geolocation",
                "AMap.PlaceSearch",
                "AMap.Driving",
                "AMap.Walking",
                "AMap.Transfer",
                "AMap.AutoComplete",
                "AMap.MarkerCluster",
            ]
        }
    }


@router.get("/layers")
async def map_layers(current_user=Depends(get_current_user)):
    return {
        "status": "success",
        "data": [
            {"id": "amap-standard", "name": "高德标准", "description": "高德地图标准图层", "attribution": "© 高德地图"},
            {"id": "amap-satellite", "name": "高德卫星", "description": "高德卫星影像图层", "attribution": "© 高德地图"},
            {"id": "amap-traffic", "name": "高德交通", "description": "高德实时交通图层", "attribution": "© 高德地图"},
            {"id": "standard", "name": "OSM标准", "description": "OpenStreetMap标准图层(备用)", "attribution": "© OpenStreetMap"},
            {"id": "satellite", "name": "ESRI卫星", "description": "ESRI卫星影像图层(备用)", "attribution": "© Esri"},
            {"id": "topology", "name": "暗色拓扑", "description": "暗色拓扑网络图层", "attribution": "© CartoDB"},
        ]
    }


@router.get("/agents/geo")
async def agent_geolocations(current_user=Depends(get_current_user)):
    from backend.cross_domain.registry import registry_center
    agents = registry_center.list_all()
    geo_data = []
    for a in agents:
        geo = poi_db.get_agent_geo(a.agent_id)
        geo_data.append({
            "agent_id": a.agent_id,
            "lat": geo["lat"],
            "lng": geo["lng"],
            "city": geo["city"],
            "status": a.status,
            "capabilities": a.capabilities,
            "cpu_load": a.cpu_load,
            "memory_free": a.memory_free,
        })
    return {"status": "success", "data": geo_data}


class AgentGeoRegister(BaseModel):
    agent_id: str
    capabilities: List[str] = []
    lat: float
    lng: float
    city: str
    endpoint: str = ""
    ws_endpoint: str = ""


@router.post("/agents/register")
async def register_agent_with_geo(req: AgentGeoRegister, current_user=Depends(get_current_user), _: None = Depends(requires_permission("agents:manage"))):
    from backend.cross_domain.registry import registry_center
    try:
        agent = registry_center.register({
            "agent_id": req.agent_id,
            "capabilities": req.capabilities,
            "endpoint": req.endpoint,
            "ws_endpoint": req.ws_endpoint,
            "tags": {"city": req.city, "type": "domain_agent"},
        })
        poi_db.set_agent_geo(req.agent_id, req.lat, req.lng, req.city)
        geo = poi_db.get_agent_geo(req.agent_id)
        return {
            "status": "success",
            "data": {
                "agent_id": agent.agent_id,
                "lat": geo["lat"],
                "lng": geo["lng"],
                "city": geo["city"],
                "status": agent.status,
                "capabilities": agent.capabilities,
                "cpu_load": agent.cpu_load,
                "memory_free": agent.memory_free,
            }
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Register agent with geo failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Internal server error")


@router.post("/markers/batch")
async def batch_markers(req: MarkerBatchRequest, current_user=Depends(get_current_user), _: None = Depends(requires_permission("agents:manage"))):
    saved = poi_db.save_markers(req.markers)
    return {"status": "success", "data": {"saved": saved}}


@router.get("/markers")
async def list_markers(
    category: Optional[str] = None,
    current_user=Depends(get_current_user)
):
    markers = poi_db.list_markers(category=category)
    return {"status": "success", "data": markers}


@router.delete("/markers/{marker_id}")
async def delete_marker(marker_id: str, current_user=Depends(get_current_user), _: None = Depends(requires_permission("agents:manage"))):
    success = poi_db.delete_marker(marker_id)
    if not success:
        from fastapi import HTTPException
        raise HTTPException(status_code=404, detail="Marker not found")
    return {"status": "success", "data": {"deleted": marker_id}}
