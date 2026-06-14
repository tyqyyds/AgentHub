from typing import List, Dict, Optional, Any
from datetime import datetime
from backend.agents.base import AgentMetadata, ToolDescription
import json
import os
import hashlib
from collections import defaultdict


class AgentRegistryError(Exception):
    pass

_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
_STORAGE_PATH = os.path.join(_PROJECT_ROOT, "data", "agents.json")

class AgentRegistry:
    def __init__(self):
        self.agents: Dict[str, AgentMetadata] = {}
        self.capability_index: Dict[str, List[str]] = defaultdict(list)
        self._load_from_storage()
    
    def _load_from_storage(self):
        if os.path.exists(_STORAGE_PATH):
            with open(_STORAGE_PATH, "r") as f:
                data = json.load(f)
                for agent_id, meta in data.items():
                    self.agents[agent_id] = AgentMetadata(**meta)
    
    def _save_to_storage(self):
        os.makedirs(os.path.dirname(_STORAGE_PATH), exist_ok=True)
        with open(_STORAGE_PATH, "w") as f:
            data = {}
            for k, v in self.agents.items():
                if hasattr(v, 'model_dump'):
                    data[k] = v.model_dump()
                else:
                    data[k] = v.dict()
            json.dump(data, f, indent=2)
    
    def register_agent(self, metadata: AgentMetadata) -> bool:
        if metadata.agent_id in self.agents:
            raise AgentRegistryError(f"Agent {metadata.agent_id} already exists")
        
        self.agents[metadata.agent_id] = metadata
        
        for cap in metadata.capabilities:
            self.capability_index[cap.lower()].append(metadata.agent_id)
        
        self._save_to_storage()
        return True
    
    def unregister_agent(self, agent_id: str) -> bool:
        if agent_id not in self.agents:
            raise AgentRegistryError(f"Agent {agent_id} not found")
        
        agent = self.agents.pop(agent_id)
        
        for cap in agent.capabilities:
            if agent_id in self.capability_index[cap.lower()]:
                self.capability_index[cap.lower()].remove(agent_id)
        
        self._save_to_storage()
        return True
    
    def get_agent(self, agent_id: str) -> Optional[AgentMetadata]:
        return self.agents.get(agent_id)
    
    def list_agents(self) -> List[AgentMetadata]:
        return list(self.agents.values())
    
    def discover_by_capability(self, capability: str) -> List[AgentMetadata]:
        capability = capability.lower()
        agent_ids = self.capability_index.get(capability, [])
        
        matched = []
        for agent_id in agent_ids:
            agent = self.agents.get(agent_id)
            if agent and agent.status == "online":
                matched.append(agent)
        
        return matched
    
    def semantic_discover(self, query: str) -> List[Dict[str, Any]]:
        results = []
        
        for agent_id, agent in self.agents.items():
            if agent.status != "online":
                continue
            
            score = self._calculate_similarity(query, agent)
            if score > 0.3:
                results.append({
                    "agent": agent.dict(),
                    "similarity_score": score
                })
        
        results.sort(key=lambda x: x["similarity_score"], reverse=True)
        return results
    
    def _calculate_similarity(self, query: str, agent: AgentMetadata) -> float:
        query_lower = query.lower()
        score = 0
        
        if query_lower in agent.name.lower():
            score += 0.3
        if query_lower in agent.description.lower():
            score += 0.4
        for cap in agent.capabilities:
            if query_lower in cap.lower():
                score += 0.1
        
        return min(score, 1.0)
    
    def heartbeat(self, agent_id: str) -> bool:
        if agent_id not in self.agents:
            return False
        
        self.agents[agent_id].last_heartbeat = datetime.now().isoformat()
        self.agents[agent_id].status = "online"
        
        self._save_to_storage()
        return True
    
    def cleanup_offline_agents(self, timeout_minutes: int = 5):
        now = datetime.now()
        offline_ids = []
        
        for agent_id, agent in self.agents.items():
            if agent.last_heartbeat:
                heartbeat_time = datetime.fromisoformat(agent.last_heartbeat)
                if (now - heartbeat_time).total_seconds() > timeout_minutes * 60:
                    agent.status = "offline"
                    offline_ids.append(agent_id)
        
        self._save_to_storage()
        return offline_ids
