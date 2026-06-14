import json
import logging

logger = logging.getLogger(__name__)


def parse_llm_json(content: str, fallback: dict = None) -> dict:
    json_str = content.strip()
    if json_str.startswith("```"):
        json_str = json_str.split("\n", 1)[1] if "\n" in json_str else json_str[3:]
        json_str = json_str.rsplit("```", 1)[0]
    try:
        return json.loads(json_str.strip())
    except json.JSONDecodeError:
        if fallback is not None:
            return fallback
        return {
            "intent_type": "unknown",
            "raw_response": content,
            "confidence": 0.0,
            "clarification_needed": True,
            "clarification_question": "无法解析您的意图，请更详细地描述您的需求"
        }
