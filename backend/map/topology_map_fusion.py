import math
from typing import Dict, List, Optional
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.models import Device, DeviceLink
from backend.map.poi_database import poi_db
import logging

logger = logging.getLogger(__name__)

LAYER_POSITIONS = {
    "core": {"x": 0.5, "y": 0.15},
    "aggregation": {"x": 0.5, "y": 0.45},
    "access": {"x": 0.5, "y": 0.75},
}

LAYER_SPREAD = {
    "core": 0.15,
    "aggregation": 0.25,
    "access": 0.35,
}


def _resolve_geo(location: Optional[str]) -> Dict:
    if not location:
        return {"lat": None, "lng": None, "location": None}
    for city in poi_db._pois:
        meta = city.get("metadata", {})
        if location in (city.get("name_local", ""), city.get("name", ""),
                        meta.get("city", ""), meta.get("city_en", ""),
                        meta.get("region", ""), city.get("address", "")):
            return {"lat": city["lat"], "lng": city["lng"], "location": location}
    for city_data in [
        {"name": "北京", "lat": 39.9042, "lng": 116.4074},
        {"name": "上海", "lat": 31.2304, "lng": 121.4737},
        {"name": "广州", "lat": 23.1291, "lng": 113.2644},
        {"name": "深圳", "lat": 22.5431, "lng": 114.0579},
        {"name": "成都", "lat": 30.5728, "lng": 104.0668},
        {"name": "杭州", "lat": 30.2741, "lng": 120.1551},
        {"name": "武汉", "lat": 30.5928, "lng": 114.3055},
        {"name": "南京", "lat": 32.0603, "lng": 118.7969},
        {"name": "重庆", "lat": 29.4316, "lng": 106.9123},
        {"name": "贵阳", "lat": 26.6470, "lng": 106.6302},
        {"name": "西安", "lat": 34.3416, "lng": 108.9398},
    ]:
        if location in (city_data["name"], city_data["name"].lower()):
            return {"lat": city_data["lat"], "lng": city_data["lng"], "location": location}
    return {"lat": None, "lng": None, "location": location}


def _compute_logical_positions(devices: List[Dict]) -> Dict[str, Dict]:
    layer_groups: Dict[str, List[Dict]] = {"core": [], "aggregation": [], "access": []}
    for d in devices:
        dt = d.get("device_type", "access")
        if dt not in layer_groups:
            dt = "access"
        layer_groups[dt].append(d)

    positions = {}
    for layer, members in layer_groups.items():
        base = LAYER_POSITIONS[layer]
        spread = LAYER_SPREAD[layer]
        count = len(members)
        for i, d in enumerate(members):
            if count == 1:
                x = base["x"]
            else:
                x = base["x"] - spread + (2 * spread * i / (count - 1))
            positions[d["device_id"]] = {"x": round(x, 4), "y": base["y"]}
    return positions


def _geodesic_points(lat1: float, lng1: float, lat2: float, lng2: float, num: int = 20) -> List[Dict[str, float]]:
    if num < 2:
        return [{"lat": lat1, "lng": lng1}, {"lat": lat2, "lng": lng2}]
    lat1_r = math.radians(lat1)
    lng1_r = math.radians(lng1)
    lat2_r = math.radians(lat2)
    lng2_r = math.radians(lng2)
    d = 2 * math.asin(
        math.sqrt(
            math.sin((lat2_r - lat1_r) / 2) ** 2
            + math.cos(lat1_r) * math.cos(lat2_r) * math.sin((lng2_r - lng1_r) / 2) ** 2
        )
    )
    if d < 1e-10:
        return [{"lat": lat1, "lng": lng1}, {"lat": lat2, "lng": lng2}]
    points = []
    for i in range(num + 1):
        f = i / num
        A = math.sin((1 - f) * d) / math.sin(d)
        B = math.sin(f * d) / math.sin(d)
        x = A * math.cos(lat1_r) * math.cos(lng1_r) + B * math.cos(lat2_r) * math.cos(lng2_r)
        y = A * math.cos(lat1_r) * math.sin(lng1_r) + B * math.cos(lat2_r) * math.sin(lng2_r)
        z = A * math.sin(lat1_r) + B * math.sin(lat2_r)
        lat_r = math.atan2(z, math.sqrt(x ** 2 + y ** 2))
        lng_r = math.atan2(y, x)
        points.append({"lat": round(math.degrees(lat_r), 6), "lng": round(math.degrees(lng_r), 6)})
    return points


class TopologyMapFusion:
    async def get_device_geo_positions(self, db: AsyncSession) -> List[dict]:
        result = await db.execute(select(Device))
        devices = result.scalars().all()
        output = []
        for d in devices:
            geo = _resolve_geo(d.location)
            output.append({
                "device_id": d.device_id,
                "name": d.name,
                "ip_address": d.ip_address,
                "status": d.status,
                "location": d.location,
                "lat": geo["lat"],
                "lng": geo["lng"],
                "device_type": d.device_type,
                "vendor": d.vendor,
            })
        return output

    async def get_link_status_overlay(self, db: AsyncSession) -> List[dict]:
        devices_result = await db.execute(select(Device))
        devices = devices_result.scalars().all()
        device_map = {d.device_id: d for d in devices}

        links_result = await db.execute(select(DeviceLink))
        links = links_result.scalars().all()

        output = []
        for link in links:
            src = device_map.get(link.source_device_id)
            tgt = device_map.get(link.target_device_id)
            if not src or not tgt:
                continue
            src_geo = _resolve_geo(src.location)
            tgt_geo = _resolve_geo(tgt.location)
            output.append({
                "source_device_id": src.device_id,
                "source_name": src.name,
                "source_lat": src_geo["lat"],
                "source_lng": src_geo["lng"],
                "target_device_id": tgt.device_id,
                "target_name": tgt.name,
                "target_lat": tgt_geo["lat"],
                "target_lng": tgt_geo["lng"],
                "status": link.status,
                "bandwidth": link.bandwidth,
                "current_load": link.current_load,
                "link_type": link.link_type,
            })
        return output

    async def get_combined_view(self, db: AsyncSession, view_mode: str = "geographic") -> dict:
        devices = await self.get_device_geo_positions(db)
        links = await self.get_link_status_overlay(db)

        if view_mode == "logical":
            logical_pos = _compute_logical_positions(devices)
            for d in devices:
                pos = logical_pos.get(d["device_id"], {"x": 0.5, "y": 0.5})
                d["logical_x"] = pos["x"]
                d["logical_y"] = pos["y"]
            for link in links:
                link["line_type"] = "straight"

        elif view_mode == "hybrid":
            logical_pos = _compute_logical_positions(devices)
            for d in devices:
                pos = logical_pos.get(d["device_id"], {"x": 0.5, "y": 0.5})
                d["logical_x"] = pos["x"]
                d["logical_y"] = pos["y"]
                d["layer"] = d["device_type"]
            for link in links:
                src_lat = link.get("source_lat")
                src_lng = link.get("source_lng")
                tgt_lat = link.get("target_lat")
                tgt_lng = link.get("target_lng")
                if src_lat is not None and src_lng is not None and tgt_lat is not None and tgt_lng is not None:
                    link["polyline"] = _geodesic_points(src_lat, src_lng, tgt_lat, tgt_lng)
                link["line_type"] = "geodesic"

        elif view_mode == "geographic":
            for link in links:
                src_lat = link.get("source_lat")
                src_lng = link.get("source_lng")
                tgt_lat = link.get("target_lat")
                tgt_lng = link.get("target_lng")
                if src_lat is not None and src_lng is not None and tgt_lat is not None and tgt_lng is not None:
                    link["polyline"] = _geodesic_points(src_lat, src_lng, tgt_lat, tgt_lng)
                link["line_type"] = "geodesic"

        else:
            view_mode = "geographic"
            for link in links:
                link["line_type"] = "geodesic"

        return {
            "devices": devices,
            "links": links,
            "view_mode": view_mode,
            "metadata": {
                "total_devices": len(devices),
                "total_links": len(links),
                "devices_with_geo": sum(1 for d in devices if d["lat"] is not None and d["lng"] is not None),
            },
        }

    async def get_device_detail_with_links(self, db: AsyncSession, device_id: str) -> Optional[dict]:
        result = await db.execute(select(Device).where(Device.device_id == device_id))
        device = result.scalars().first()
        if not device:
            return None

        geo = _resolve_geo(device.location)

        src_links = await db.execute(
            select(DeviceLink).where(DeviceLink.source_device_id == device_id)
        )
        tgt_links = await db.execute(
            select(DeviceLink).where(DeviceLink.target_device_id == device_id)
        )

        all_device_ids = set()
        link_data = []
        for link in src_links.scalars().all():
            all_device_ids.add(link.target_device_id)
            link_data.append({
                "link_id": f"{link.source_device_id}->{link.target_device_id}",
                "direction": "outgoing",
                "remote_device_id": link.target_device_id,
                "status": link.status,
                "bandwidth": link.bandwidth,
                "current_load": link.current_load,
                "link_type": link.link_type,
            })
        for link in tgt_links.scalars().all():
            all_device_ids.add(link.source_device_id)
            link_data.append({
                "link_id": f"{link.source_device_id}->{link.target_device_id}",
                "direction": "incoming",
                "remote_device_id": link.source_device_id,
                "status": link.status,
                "bandwidth": link.bandwidth,
                "current_load": link.current_load,
                "link_type": link.link_type,
            })

        neighbors = []
        if all_device_ids:
            neighbor_result = await db.execute(
                select(Device).where(Device.device_id.in_(all_device_ids))
            )
            for n in neighbor_result.scalars().all():
                n_geo = _resolve_geo(n.location)
                neighbors.append({
                    "device_id": n.device_id,
                    "name": n.name,
                    "ip_address": n.ip_address,
                    "status": n.status,
                    "device_type": n.device_type,
                    "vendor": n.vendor,
                    "lat": n_geo["lat"],
                    "lng": n_geo["lng"],
                })

        return {
            "device_id": device.device_id,
            "name": device.name,
            "ip_address": device.ip_address,
            "status": device.status,
            "device_type": device.device_type,
            "vendor": device.vendor,
            "location": device.location,
            "lat": geo["lat"],
            "lng": geo["lng"],
            "cpu_usage": device.cpu_usage,
            "memory_usage": device.memory_usage,
            "uptime": device.uptime,
            "links": link_data,
            "neighbors": neighbors,
        }

    async def get_network_health_summary(self, db: AsyncSession) -> dict:
        devices_result = await db.execute(select(Device))
        devices = devices_result.scalars().all()

        links_result = await db.execute(select(DeviceLink))
        links = links_result.scalars().all()

        device_status = {"healthy": 0, "warning": 0, "critical": 0, "error": 0}
        location_issues: Dict[str, List[dict]] = {}

        for d in devices:
            s = d.status if d.status in device_status else "critical"
            device_status[s] += 1
            if s in ("warning", "critical", "error"):
                loc = d.location or "未知"
                if loc not in location_issues:
                    location_issues[loc] = []
                location_issues[loc].append({
                    "device_id": d.device_id,
                    "name": d.name,
                    "status": s,
                })

        link_status = {"active": 0, "degraded": 0, "down": 0, "warning": 0, "error": 0}
        for link in links:
            s = link.status
            if s in ("active",):
                link_status["active"] += 1
            elif s in ("warning",):
                link_status["degraded"] += 1
            elif s in ("error",):
                link_status["down"] += 1
            else:
                link_status.setdefault(s, 0)
                link_status[s] += 1

        geo_issues = []
        for loc, issues in location_issues.items():
            geo = _resolve_geo(loc)
            geo_issues.append({
                "location": loc,
                "lat": geo["lat"],
                "lng": geo["lng"],
                "issue_count": len(issues),
                "devices": issues,
            })

        total_devices = len(devices)
        total_links = len(links)
        healthy_pct = round(device_status["healthy"] / total_devices * 100, 1) if total_devices else 0
        active_link_pct = round(link_status["active"] / total_links * 100, 1) if total_links else 0

        return {
            "devices": {
                "total": total_devices,
                "healthy": device_status["healthy"],
                "warning": device_status["warning"],
                "critical": device_status.get("critical", 0) + device_status.get("error", 0),
            },
            "links": {
                "total": total_links,
                "active": link_status["active"],
                "degraded": link_status["degraded"],
                "down": link_status["down"],
            },
            "health_score": round((healthy_pct + active_link_pct) / 2, 1),
            "geographic_distribution": geo_issues,
        }

    async def search_devices_on_map(self, db: AsyncSession, query: str) -> List[dict]:
        q = query.lower()
        escaped_q = q.replace('%', '\\%').replace('_', '\\_')
        result = await db.execute(
            select(Device).where(
                (Device.name.ilike(f"%{escaped_q}%", escape='\\')) |
                (Device.ip_address.ilike(f"%{escaped_q}%", escape='\\')) |
                (Device.location.ilike(f"%{escaped_q}%", escape='\\'))
            )
        )
        devices = result.scalars().all()

        output = []
        for d in devices:
            geo = _resolve_geo(d.location)
            output.append({
                "device_id": d.device_id,
                "name": d.name,
                "ip_address": d.ip_address,
                "status": d.status,
                "location": d.location,
                "lat": geo["lat"],
                "lng": geo["lng"],
                "device_type": d.device_type,
                "vendor": d.vendor,
            })
        return output


_topology_map_fusion: Optional[TopologyMapFusion] = None


def get_topology_map_fusion() -> TopologyMapFusion:
    global _topology_map_fusion
    if _topology_map_fusion is None:
        _topology_map_fusion = TopologyMapFusion()
    return _topology_map_fusion
