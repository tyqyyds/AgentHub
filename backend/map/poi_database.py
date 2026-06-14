import math
import uuid
from typing import Dict, List, Optional
import logging

logger = logging.getLogger(__name__)


def haversine(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    R = 6371.0
    dlat = math.radians(lat2 - lat1)
    dlng = math.radians(lng2 - lng1)
    a = math.sin(dlat / 2) ** 2 + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(dlng / 2) ** 2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c


CITIES = [
    {"name": "北京", "name_en": "Beijing", "lat": 39.9042, "lng": 116.4074, "country": "CN", "region": "华北"},
    {"name": "上海", "name_en": "Shanghai", "lat": 31.2304, "lng": 121.4737, "country": "CN", "region": "华东"},
    {"name": "广州", "name_en": "Guangzhou", "lat": 23.1291, "lng": 113.2644, "country": "CN", "region": "华南"},
    {"name": "深圳", "name_en": "Shenzhen", "lat": 22.5431, "lng": 114.0579, "country": "CN", "region": "华南"},
    {"name": "成都", "name_en": "Chengdu", "lat": 30.5728, "lng": 104.0668, "country": "CN", "region": "西南"},
    {"name": "武汉", "name_en": "Wuhan", "lat": 30.5928, "lng": 114.3055, "country": "CN", "region": "华中"},
    {"name": "南京", "name_en": "Nanjing", "lat": 32.0603, "lng": 118.7969, "country": "CN", "region": "华东"},
    {"name": "杭州", "name_en": "Hangzhou", "lat": 30.2741, "lng": 120.1551, "country": "CN", "region": "华东"},
    {"name": "西安", "name_en": "Xi'an", "lat": 34.3416, "lng": 108.9398, "country": "CN", "region": "西北"},
    {"name": "重庆", "name_en": "Chongqing", "lat": 29.4316, "lng": 106.9123, "country": "CN", "region": "西南"},
    {"name": "天津", "name_en": "Tianjin", "lat": 39.3434, "lng": 117.3616, "country": "CN", "region": "华北"},
    {"name": "苏州", "name_en": "Suzhou", "lat": 31.2990, "lng": 120.5853, "country": "CN", "region": "华东"},
    {"name": "郑州", "name_en": "Zhengzhou", "lat": 34.7466, "lng": 113.6254, "country": "CN", "region": "华中"},
    {"name": "长沙", "name_en": "Changsha", "lat": 28.2282, "lng": 112.9388, "country": "CN", "region": "华中"},
    {"name": "济南", "name_en": "Jinan", "lat": 36.6512, "lng": 116.9972, "country": "CN", "region": "华东"},
    {"name": "青岛", "name_en": "Qingdao", "lat": 36.0671, "lng": 120.3826, "country": "CN", "region": "华东"},
    {"name": "大连", "name_en": "Dalian", "lat": 38.9140, "lng": 121.6147, "country": "CN", "region": "东北"},
    {"name": "沈阳", "name_en": "Shenyang", "lat": 41.8057, "lng": 123.4315, "country": "CN", "region": "东北"},
    {"name": "哈尔滨", "name_en": "Harbin", "lat": 45.8038, "lng": 126.5350, "country": "CN", "region": "东北"},
    {"name": "昆明", "name_en": "Kunming", "lat": 25.0389, "lng": 102.7183, "country": "CN", "region": "西南"},
    {"name": "贵阳", "name_en": "Guiyang", "lat": 26.6470, "lng": 106.6302, "country": "CN", "region": "西南"},
    {"name": "兰州", "name_en": "Lanzhou", "lat": 36.0611, "lng": 103.8343, "country": "CN", "region": "西北"},
    {"name": "乌鲁木齐", "name_en": "Urumqi", "lat": 43.8256, "lng": 87.6168, "country": "CN", "region": "西北"},
    {"name": "福州", "name_en": "Fuzhou", "lat": 26.0745, "lng": 119.2965, "country": "CN", "region": "华东"},
    {"name": "厦门", "name_en": "Xiamen", "lat": 24.4798, "lng": 118.0894, "country": "CN", "region": "华东"},
    {"name": "合肥", "name_en": "Hefei", "lat": 31.8206, "lng": 117.2272, "country": "CN", "region": "华东"},
    {"name": "南昌", "name_en": "Nanchang", "lat": 28.6820, "lng": 115.8579, "country": "CN", "region": "华东"},
    {"name": "南宁", "name_en": "Nanning", "lat": 22.8170, "lng": 108.3665, "country": "CN", "region": "华南"},
    {"name": "海口", "name_en": "Haikou", "lat": 20.0440, "lng": 110.1999, "country": "CN", "region": "华南"},
    {"name": "石家庄", "name_en": "Shijiazhuang", "lat": 38.0428, "lng": 114.5149, "country": "CN", "region": "华北"},
    {"name": "太原", "name_en": "Taiyuan", "lat": 37.8706, "lng": 112.5489, "country": "CN", "region": "华北"},
    {"name": "呼和浩特", "name_en": "Hohhot", "lat": 40.8414, "lng": 111.7519, "country": "CN", "region": "华北"},
]


class POIDatabase:
    def __init__(self):
        self._pois: List[Dict] = []
        self._markers: Dict[str, Dict] = {}
        self._agent_geo_map: Dict[str, Dict] = {}
        self._init_pois()
        self._init_agent_geo()

    def _init_pois(self):
        poi_id = 0
        for city in CITIES:
            for category, suffix, desc_tmpl in [
                ("datacenter", "DC", "{}数据中心"),
                ("network_hub", "NH", "{}网络枢纽"),
                ("agent_node", "AN", "{}智能体节点"),
            ]:
                poi_id += 1
                lat_offset = (poi_id % 7 - 3) * 0.008
                lng_offset = ((poi_id * 3) % 7 - 3) * 0.008
                self._pois.append({
                    "id": f"poi-{poi_id:04d}",
                    "name": f"{city['name_en']}-{suffix}",
                    "name_local": desc_tmpl.format(city["name"]),
                    "category": category,
                    "lat": round(city["lat"] + lat_offset, 4),
                    "lng": round(city["lng"] + lng_offset, 4),
                    "address": f"{city['name']}, {city['country']}",
                    "description": f"{desc_tmpl.format(city['name'])} - {city['region']}",
                    "metadata": {
                        "city": city["name"],
                        "city_en": city["name_en"],
                        "country": city["country"],
                        "region": city["region"],
                    },
                })

    def _init_agent_geo(self):
        agent_cities = [
            ("agent_bandwidth_guarantor", 39.9, 116.4, "北京"),
            ("agent_fault_diagnostician", 31.2, 121.5, "上海"),
            ("agent_config_generator", 23.1, 113.3, "广州"),
            ("agent_security_scanner", 22.5, 114.1, "深圳"),
            ("agent_healing_executor", 30.6, 104.1, "成都"),
            ("agent_topology_analyzer", 30.6, 114.3, "武汉"),
            ("agent_sla_predictor", 32.1, 118.8, "南京"),
            ("agent_intent_parser", 30.3, 120.2, "杭州"),
            ("agent_traffic_shaper", 34.3, 108.9, "西安"),
            ("agent_link_manager", 29.6, 106.5, "重庆"),
            ("agent_performance_monitor", 28.2, 113.0, "长沙"),
            ("agent_access_controller", 26.6, 106.7, "贵阳"),
        ]
        for agent_id, lat, lng, city in agent_cities:
            self._agent_geo_map[agent_id] = {"lat": lat, "lng": lng, "city": city}

    def search(self, query: str, category: Optional[str] = None,
               lat: Optional[float] = None, lng: Optional[float] = None,
               radius: float = 50.0, limit: int = 50) -> List[Dict]:
        q = query.lower()
        results = []
        for poi in self._pois:
            if category and poi["category"] != category:
                continue
            if q not in poi["name"].lower() and q not in poi.get("name_local", "").lower() and q not in poi["address"].lower():
                if q not in poi.get("metadata", {}).get("city_en", "").lower() and q not in poi.get("metadata", {}).get("city", "").lower() and q not in poi.get("metadata", {}).get("region", "").lower():
                    continue
            if lat is not None and lng is not None:
                dist = haversine(lat, lng, poi["lat"], poi["lng"])
                if dist > radius:
                    continue
                poi_copy = dict(poi)
                poi_copy["distance"] = round(dist, 2)
                poi_copy["display_name"] = poi_copy.get("name_local", poi_copy["name"])
                results.append(poi_copy)
            else:
                poi_copy = dict(poi)
                poi_copy["display_name"] = poi_copy.get("name_local", poi_copy["name"])
                results.append(poi_copy)
            if len(results) >= limit:
                break
        if lat is not None and lng is not None:
            results.sort(key=lambda x: x.get("distance", float("inf")))
        return results

    def nearby(self, lat: float, lng: float, radius: float = 50.0,
               category: Optional[str] = None, limit: int = 50) -> List[Dict]:
        results = []
        for poi in self._pois:
            if category and poi["category"] != category:
                continue
            dist = haversine(lat, lng, poi["lat"], poi["lng"])
            if dist <= radius:
                poi_copy = dict(poi)
                poi_copy["distance"] = round(dist, 2)
                poi_copy["display_name"] = poi_copy.get("name_local", poi_copy["name"])
                results.append(poi_copy)
            if len(results) >= limit:
                break
        results.sort(key=lambda x: x.get("distance", float("inf")))
        return results[:limit]

    def categories(self) -> List[Dict]:
        return [
            {"id": "datacenter", "name": "数据中心", "description": "云数据中心与IDC机房"},
            {"id": "network_hub", "name": "网络枢纽", "description": "核心网络交换与路由节点"},
            {"id": "agent_node", "name": "智能体节点", "description": "Agent部署与运行节点"},
            {"id": "custom", "name": "自定义标记", "description": "用户自定义地图标记"},
        ]

    def get_agent_geo(self, agent_id: str) -> Dict:
        if agent_id in self._agent_geo_map:
            return self._agent_geo_map[agent_id]
        default = self._agent_geo_map.get("agent_access_controller", {"lat": 26.6, "lng": 106.7, "city": "贵阳"})
        self._agent_geo_map[agent_id] = dict(default)
        return self._agent_geo_map[agent_id]

    def set_agent_geo(self, agent_id: str, lat: float, lng: float, city: str) -> Dict:
        self._agent_geo_map[agent_id] = {"lat": lat, "lng": lng, "city": city}
        return self._agent_geo_map[agent_id]

    def save_markers(self, markers: list) -> int:
        saved = 0
        for marker in markers:
            marker_id = getattr(marker, "id", None) or str(uuid.uuid4())
            marker_dict = {
                "id": marker_id,
                "lat": marker.lat,
                "lng": marker.lng,
                "title": marker.title,
                "description": getattr(marker, "description", ""),
                "icon": getattr(marker, "icon", "default"),
                "category": getattr(marker, "category", "custom"),
                "agent_id": getattr(marker, "agent_id", None),
            }
            self._markers[marker_id] = marker_dict
            saved += 1
        return saved

    def list_markers(self, category: Optional[str] = None) -> List[Dict]:
        markers = list(self._markers.values())
        if category:
            markers = [m for m in markers if m.get("category") == category]
        return markers

    def delete_marker(self, marker_id: str) -> bool:
        if marker_id in self._markers:
            del self._markers[marker_id]
            return True
        return False


poi_db = POIDatabase()
