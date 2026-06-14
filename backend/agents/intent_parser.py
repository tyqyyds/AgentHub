import asyncio
import logging
from typing import Dict, Any, Optional, List, Union
from backend.agents.base import IntentContext, DeviceInfo
from backend.agents.llm_gateway import get_llm_gateway, TaskType
from backend.agents.failed_intent_store import get_failed_intent_store
from backend.agents.clarification import ClarificationResult, get_clarification_agent
from pydantic import BaseModel, Field
import re
import json

logger = logging.getLogger(__name__)

class ParsedIntent(BaseModel):
    intent_type: str = Field(description="意图类型")
    target_subnet: Optional[str] = Field(description="目标子网")
    bandwidth: Optional[int] = Field(description="带宽值(MB)")
    duration: Optional[str] = Field(description="持续时间")
    priority: str = Field(default="medium", description="优先级")
    actions: List[Dict[str, Any]] = Field(default_factory=list, description="动作列表")
    entities: Dict[str, str] = Field(default_factory=dict, description="提取的实体")

class IntentParserAgent:
    def __init__(self):
        self.gateway = get_llm_gateway()
        self.llm = None
        self._init_llm()
        self.system_prompt = """你是一个专业的网络运维意图解析专家。请将用户的自然语言运维需求解析为结构化的意图数据。

## 意图类型列表:
1. bandwidth_guarantee - 带宽保障
2. access_control - 访问控制
3. qos_policy - QoS策略配置
4. link_management - 链路管理
5. device_config - 设备配置
6. traffic_shaping - 流量整形
7. fault_diagnosis - 故障诊断
8. performance_monitoring - 性能监控

## 输出格式要求:
必须输出JSON格式，包含以下字段:
- intent_type: 意图类型
- target_subnet: 目标子网名称
- bandwidth: 带宽值(整数，单位MB)
- duration: 持续时间(如"1天", "24小时")
- priority: 优先级(high/medium/low)
- actions: 动作列表，每个动作包含type和params
- entities: 提取的实体字典

## 示例:
输入: "为研发子网的Git克隆流量保障500M带宽"
输出:
{
  "intent_type": "bandwidth_guarantee",
  "target_subnet": "研发子网",
  "bandwidth": 500,
  "duration": "持续",
  "priority": "high",
  "actions": [{"type": "qos_config", "params": {"min_bw": "500M", "protocol": "git"}}],
  "entities": {"子网": "研发子网", "带宽": "500M", "用途": "Git克隆"}
}

## 思考链:
1. 分析用户输入的自然语言
2. 识别关键实体(子网、带宽、时间等)
3. 判断意图类型
4. 生成对应的动作列表
5. 按照JSON格式输出"""
    
    def _init_llm(self):
        try:
            from langchain_openai import ChatOpenAI
            import os
            api_key = os.environ.get("OPENAI_API_KEY", "")
            if api_key:
                self.llm = ChatOpenAI(model="gpt-4", temperature=0, api_key=api_key)
        except Exception:
            self.llm = None

    async def _record_parse_failure(
        self,
        user_input: str,
        method: str,
        reason: str,
        raw_response: Optional[str] = None
    ):
        try:
            store = get_failed_intent_store()
            await store.record_failure(
                user_input=user_input,
                parse_method=method,
                failure_reason=reason,
                raw_response=raw_response
            )
        except Exception as e:
            logger.warning(f"Failed to record parse failure: {e}")
    
    def parse(self, user_input: str) -> IntentContext:
        if self.gateway.deepseek.available or self.gateway.zhipu.available:
            try:
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                
                if loop and loop.is_running():
                    import concurrent.futures
                    with concurrent.futures.ThreadPoolExecutor() as pool:
                        result = pool.submit(asyncio.run, self.gateway.parse_intent(user_input)).result()
                else:
                    result = asyncio.run(self.gateway.parse_intent(user_input))
                    
                if result and result.get("intent_type") != "unknown":
                    intent_id = f"intent_{hash(user_input) % 1000000:06d}"
                    parsed = ParsedIntent(
                        intent_type=result.get("intent_type", "unknown"),
                        target_subnet=result.get("target_subnet"),
                        bandwidth=result.get("bandwidth"),
                        duration=result.get("duration", "持续"),
                        priority=result.get("priority", "medium"),
                        actions=result.get("actions", []),
                        entities=result.get("entities", {})
                    )
                    return IntentContext(
                        intent_id=intent_id,
                        user_input=user_input,
                        parsed_intent=parsed.model_dump(),
                        target_devices=[],
                        actions=parsed.actions,
                        conflict_detected=False
                    )
            except Exception as e:
                logger.warning(f"LLM意图解析失败: {e}")
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    asyncio.ensure_future(self._record_parse_failure(user_input, "llm_gateway", str(e)))
                else:
                    asyncio.run(self._record_parse_failure(user_input, "llm_gateway", str(e)))
        
        if self.llm:
            try:
                result = self._llm_parse(user_input)
                if result:
                    intent_id = f"intent_{hash(user_input) % 1000000:06d}"
                    return IntentContext(
                        intent_id=intent_id,
                        user_input=user_input,
                        parsed_intent=result.model_dump(),
                        target_devices=[],
                        actions=result.actions,
                        conflict_detected=False
                    )
            except Exception as e:
                logger.warning(f"LangChain意图解析失败: {e}")
                try:
                    loop = asyncio.get_running_loop()
                except RuntimeError:
                    loop = None
                if loop and loop.is_running():
                    asyncio.ensure_future(self._record_parse_failure(user_input, "langchain", str(e)))
                else:
                    asyncio.run(self._record_parse_failure(user_input, "langchain", str(e)))
        
        return self._fallback_parse_to_context(user_input)
    
    async def parse_async(self, user_input: str) -> IntentContext:
        if self.gateway.deepseek.available or self.gateway.zhipu.available:
            try:
                result = await self.gateway.parse_intent(user_input)
                if result and result.get("intent_type") != "unknown":
                    intent_id = f"intent_{hash(user_input) % 1000000:06d}"
                    parsed = ParsedIntent(
                        intent_type=result.get("intent_type", "unknown"),
                        target_subnet=result.get("target_subnet"),
                        bandwidth=result.get("bandwidth"),
                        duration=result.get("duration", "持续"),
                        priority=result.get("priority", "medium"),
                        actions=result.get("actions", []),
                        entities=result.get("entities", {})
                    )
                    return IntentContext(
                        intent_id=intent_id,
                        user_input=user_input,
                        parsed_intent=parsed.model_dump(),
                        target_devices=[],
                        actions=parsed.actions,
                        conflict_detected=False
                    )
                else:
                    await self._record_parse_failure(
                        user_input, "llm_gateway",
                        "LLM returned unknown intent_type",
                        raw_response=str(result) if result else None
                    )
            except Exception as e:
                logger.warning(f"LLM异步意图解析失败: {e}")
                await self._record_parse_failure(user_input, "llm_gateway", str(e))
        
        return self._fallback_parse_to_context(user_input)
    
    def _llm_parse(self, user_input: str) -> Optional[ParsedIntent]:
        from langchain.prompts import ChatPromptTemplate
        from langchain.output_parsers import PydanticOutputParser
        
        parser = PydanticOutputParser(pydantic_object=ParsedIntent)
        prompt = ChatPromptTemplate.from_messages([
            ("system", self.system_prompt),
            ("human", "请解析以下运维意图:\n{input}"),
            ("human", "输出格式要求:\n{format_instructions}")
        ])
        
        chain = prompt | self.llm | parser
        result = chain.invoke({
            "input": user_input,
            "format_instructions": parser.get_format_instructions()
        })
        return result
    
    def _fallback_parse_to_context(self, user_input: str) -> IntentContext:
        result = self._fallback_parse(user_input)
        intent_id = f"intent_{hash(user_input) % 1000000:06d}"

        if result.intent_type == "unknown":
            try:
                loop = asyncio.get_running_loop()
            except RuntimeError:
                loop = None
            if loop and loop.is_running():
                asyncio.ensure_future(self._record_parse_failure(
                    user_input, "regex", "Fallback regex parsing returned unknown intent_type"
                ))
            else:
                asyncio.run(self._record_parse_failure(
                    user_input, "regex", "Fallback regex parsing returned unknown intent_type"
                ))

        return IntentContext(
            intent_id=intent_id,
            user_input=user_input,
            parsed_intent=result.model_dump(),
            target_devices=[],
            actions=result.actions,
            conflict_detected=False
        )
    
    def _fallback_parse(self, user_input: str) -> ParsedIntent:
        entities: Dict[str, str] = {}
        intent_type = "unknown"
        actions: List[Dict[str, Any]] = []
        priority = "medium"
        target_subnet = None
        bandwidth = None
        
        subnet_match = re.search(r"([\u4e00-\u9fa5]+子网)", user_input)
        if subnet_match:
            target_subnet = subnet_match.group(1)
            entities["子网"] = target_subnet
        
        bw_match = re.search(r"(\d+)\s*[Mm]", user_input)
        if bw_match:
            bandwidth = int(bw_match.group(1))
            entities["带宽"] = f"{bandwidth}M"
        
        time_match = re.search(r"(\d+)\s*(天|小时|分钟)", user_input)
        if time_match:
            entities["时间"] = time_match.group(0)
        
        if "带宽" in user_input or "保障" in user_input or "QoS" in user_input.upper():
            intent_type = "bandwidth_guarantee"
            priority = "high"
            actions.append({
                "type": "qos_config",
                "params": {"min_bw": f"{bandwidth or 100}M", "protocol": "any"}
            })
        elif "访问" in user_input or "ACL" in user_input.upper() or "权限" in user_input:
            intent_type = "access_control"
            actions.append({"type": "acl_config", "params": {"direction": "inbound"}})
        elif "链路" in user_input or "路由" in user_input:
            intent_type = "link_management"
            actions.append({"type": "link_config", "params": {}})
        elif "故障" in user_input or "诊断" in user_input:
            intent_type = "fault_diagnosis"
            actions.append({"type": "diagnose", "params": {}})
        elif "监控" in user_input or "性能" in user_input:
            intent_type = "performance_monitoring"
            actions.append({"type": "monitor", "params": {}})
        elif "流量" in user_input or "整形" in user_input:
            intent_type = "traffic_shaping"
            actions.append({"type": "traffic_config", "params": {}})
        
        return ParsedIntent(
            intent_type=intent_type,
            target_subnet=target_subnet,
            bandwidth=bandwidth,
            duration=entities.get("时间", "持续"),
            priority=priority,
            actions=actions,
            entities=entities
        )

    async def parse_with_clarification(self, user_input: str) -> Union[IntentContext, ClarificationResult]:
        intent_context = self._fallback_parse_to_context(user_input)
        parsed_dict = intent_context.parsed_intent or {}

        confidence = parsed_dict.get("confidence", 0.0)
        if isinstance(confidence, str):
            try:
                confidence = float(confidence)
            except (ValueError, TypeError):
                confidence = 0.0

        if self.gateway.deepseek.available or self.gateway.zhipu.available:
            try:
                result = await self.gateway.parse_intent(user_input)
                if result:
                    confidence = result.get("confidence", 0.0)
                    if isinstance(confidence, str):
                        try:
                            confidence = float(confidence)
                        except (ValueError, TypeError):
                            confidence = 0.0
                    parsed_dict = result
            except Exception as e:
                logger.warning(f"parse_with_clarification LLM解析失败: {e}")

        clarification_agent = get_clarification_agent()
        clarification_result = clarification_agent.analyze_confidence(parsed_dict)

        if not clarification_result.needs_clarification:
            intent_id = f"intent_{hash(user_input) % 1000000:06d}"
            parsed = ParsedIntent(
                intent_type=parsed_dict.get("intent_type", "unknown"),
                target_subnet=parsed_dict.get("target_subnet"),
                bandwidth=parsed_dict.get("bandwidth"),
                duration=parsed_dict.get("duration", "持续"),
                priority=parsed_dict.get("priority", "medium"),
                actions=parsed_dict.get("actions", []),
                entities=parsed_dict.get("entities", {})
            )
            return IntentContext(
                intent_id=intent_id,
                user_input=user_input,
                parsed_intent=parsed.model_dump(),
                target_devices=[],
                actions=parsed.actions,
                conflict_detected=False
            )

        session_data = clarification_agent.create_clarification_session(user_input, parsed_dict)
        dynamic_questions = await clarification_agent.generate_clarification_questions(
            user_input, parsed_dict, clarification_result.missing_fields
        )
        clarification_result.questions = dynamic_questions
        clarification_result.session_id = session_data["session_id"]

        if session_data["session_id"] in clarification_agent._sessions:
            clarification_agent._sessions[session_data["session_id"]].questions = dynamic_questions

        return clarification_result

    async def resolve_and_parse(self, session_id: str, user_response: str) -> Union[IntentContext, ClarificationResult]:
        clarification_agent = get_clarification_agent()
        result = await clarification_agent.process_clarification_response(session_id, user_response)

        if result.get("resolved"):
            parsed_intent = result.get("parsed_intent", {})
            intent_id = f"intent_{hash(parsed_intent.get('user_input', '')) % 1000000:06d}"
            parsed = ParsedIntent(
                intent_type=parsed_intent.get("intent_type", "unknown"),
                target_subnet=parsed_intent.get("target_subnet"),
                bandwidth=parsed_intent.get("bandwidth"),
                duration=parsed_intent.get("duration", "持续"),
                priority=parsed_intent.get("priority", "medium"),
                actions=parsed_intent.get("actions", []),
                entities=parsed_intent.get("entities", {})
            )
            return IntentContext(
                intent_id=intent_id,
                user_input=parsed_intent.get("user_input", ""),
                parsed_intent=parsed.model_dump(),
                target_devices=[],
                actions=parsed.actions,
                conflict_detected=False
            )

        return ClarificationResult(
            needs_clarification=True,
            confidence=result.get("parsed_intent", {}).get("confidence", 0.0),
            missing_fields=result.get("missing_fields", []),
            questions=result.get("questions", []),
            session_id=session_id
        )
