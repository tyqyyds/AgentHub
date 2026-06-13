"""多模态处理器：文本/图像/表格多模态输入处理

负责处理用户输入的多种模态数据，包括：
- 文本意图解析
- 网络拓扑图/架构图识别
- 设备配置表格解析
- 多模态融合推理
- 模态转换与标准化
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import Enum
import asyncio
import json
import re

from ..core.config import settings

logger = logging.getLogger(__name__)


# ──────────────────────── 内部枚举与数据类 ────────────────────────


class ModalityType(str, Enum):
    """模态类型"""
    TEXT = "text"
    IMAGE = "image"
    TABLE = "table"
    STRUCTURED_DATA = "structured_data"
    MIXED = "mixed"


class ImageContentType(str, Enum):
    """图像内容类型"""
    NETWORK_TOPOLOGY = "network_topology"       # 网络拓扑图
    DEVICE_PANEL = "device_panel"               # 设备面板截图
    CONFIGURATION_SCREEN = "configuration"       # 配置界面截图
    CHART_GRAPH = "chart_graph"                  # 图表/曲线图
    LOG_OUTPUT = "log_output"                    # 日志输出截图
    PHOTO = "photo"                              # 现场照片
    UNKNOWN = "unknown"


class ProcessingStatus(str, Enum):
    """处理状态"""
    PENDING = "pending"
    PROCESSING = "processing"
    COMPLETED = "completed"
    FAILED = "failed"
    PARTIAL = "partial"


@dataclass
class BoundingBox:
    """边界框"""
    x_min: float
    y_min: float
    x_max: float
    y_max: float
    confidence: float = 0.0


@dataclass
class DetectedEntity:
    """检测到的实体"""
    entity_type: str          # device / link / label / metric / port
    label: str
    bounding_box: Optional[BoundingBox] = None
    attributes: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0


@dataclass
class TableCell:
    """表格单元格"""
    row: int
    col: int
    value: str
    header: bool = False
    confidence: float = 1.0


@dataclass
class ParsedTable:
    """解析后的表格"""
    headers: List[str]
    rows: List[List[str]]
    row_count: int = 0
    col_count: int = 0
    confidence: float = 0.0
    source_region: Optional[BoundingBox] = None


@dataclass
class ModalityInput:
    """模态输入"""
    modality: ModalityType
    content: Any
    metadata: Dict[str, Any] = field(default_factory=dict)
    source: str = "user"  # user / system / file_upload


@dataclass
class ModalityOutput:
    """模态处理输出"""
    input_modality: ModalityType
    status: ProcessingStatus
    extracted_text: str = ""
    extracted_entities: List[DetectedEntity] = field(default_factory=list)
    parsed_tables: List[ParsedTable] = field(default_factory=list)
    intent_hints: List[str] = field(default_factory=list)
    device_references: List[str] = field(default_factory=list)
    confidence: float = 0.0
    error: Optional[str] = None
    processing_time_ms: int = 0


@dataclass
class FusionResult:
    """多模态融合结果"""
    primary_intent: Optional[str] = None
    confidence: float = 0.0
    text_contribution: float = 0.0
    image_contribution: float = 0.0
    table_contribution: float = 0.0
    combined_entities: List[DetectedEntity] = field(default_factory=list)
    combined_device_refs: List[str] = field(default_factory=list)
    combined_intent_hints: List[str] = field(default_factory=list)
    contradictions: List[str] = field(default_factory=list)


@dataclass
class MultimodalProcessorConfig:
    """多模态处理器配置"""
    max_image_size_bytes: int = 10 * 1024 * 1024  # 10MB
    supported_image_formats: List[str] = field(
        default_factory=lambda: ["png", "jpg", "jpeg", "gif", "bmp", "webp"]
    )
    ocr_confidence_threshold: float = 0.6
    entity_detection_threshold: float = 0.5
    table_parsing_confidence: float = 0.7
    fusion_text_weight: float = 0.5
    fusion_image_weight: float = 0.3
    fusion_table_weight: float = 0.2
    enable_ocr: bool = True
    enable_entity_detection: bool = True
    enable_table_parsing: bool = True


# ──────────────────────── 设备名称模式 ────────────────────────

DEVICE_NAME_PATTERNS = [
    re.compile(r"(Router|Switch|Firewall|AC|AP|OLT|OTN)[-\s]?([A-Z]\d+)", re.IGNORECASE),
    re.compile(r"([A-Z]{2,4})[-\s]?(\d{1,4}[A-Z]?)", re.IGNORECASE),
    re.compile(r"(\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3})"),  # IP地址
]

# 意图关键词映射
INTENT_KEYWORD_MAP: Dict[str, List[str]] = {
    "带宽保障": ["带宽", "保障", "限速", "QoS", "流量控制", "bandwidth"],
    "故障自愈": ["故障", "中断", "宕机", "告警", "异常", "自愈", "恢复"],
    "流量调度": ["调度", "分流", "负载均衡", "流量", "路由", "切换"],
    "安全策略": ["安全", "防火墙", "ACL", "访问控制", "过滤", "策略"],
    "链路保护": ["链路", "保护", "冗余", "备份", "主备"],
}


# ──────────────────────── 文本处理器 ────────────────────────


class TextProcessor:
    """文本模态处理器"""

    def __init__(self, config: MultimodalProcessorConfig):
        self.config = config

    def process(self, text: str) -> ModalityOutput:
        """处理文本输入"""
        start_time = datetime.now(timezone.utc)

        extracted_entities: List[DetectedEntity] = []
        intent_hints: List[str] = []
        device_references: List[str] = []

        # 1. 提取设备引用
        for pattern in DEVICE_NAME_PATTERNS:
            matches = pattern.findall(text)
            for match in matches:
                if isinstance(match, tuple):
                    device_ref = "-".join(match)
                else:
                    device_ref = match
                if device_ref not in device_references:
                    device_references.append(device_ref)
                    extracted_entities.append(
                        DetectedEntity(
                            entity_type="device",
                            label=device_ref,
                            confidence=0.85,
                        )
                    )

        # 2. 意图关键词匹配
        for intent, keywords in INTENT_KEYWORD_MAP.items():
            for keyword in keywords:
                if keyword.lower() in text.lower():
                    if intent not in intent_hints:
                        intent_hints.append(intent)
                    break

        # 3. 提取数字指标
        metric_pattern = re.compile(r"(\d+(?:\.\d+)?)\s*(Mbps|Gbps|KB|MB|GB|ms|%)")
        for match in metric_pattern.finditer(text):
            value, unit = match.groups()
            extracted_entities.append(
                DetectedEntity(
                    entity_type="metric",
                    label=f"{value}{unit}",
                    attributes={"value": float(value), "unit": unit},
                    confidence=0.9,
                )
            )

        duration_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        return ModalityOutput(
            input_modality=ModalityType.TEXT,
            status=ProcessingStatus.COMPLETED,
            extracted_text=text,
            extracted_entities=extracted_entities,
            intent_hints=intent_hints,
            device_references=device_references,
            confidence=0.9,
            processing_time_ms=duration_ms,
        )


# ──────────────────────── 图像处理器 ────────────────────────


class ImageProcessor:
    """图像模态处理器（模拟实现）

    实际实现应集成视觉模型（如智谱GLM-4V）进行图像理解。
    此处为模拟实现，基于图像元数据和文件名推断内容。
    """

    def __init__(self, config: MultimodalProcessorConfig):
        self.config = config

    def process(self, image_data: Dict[str, Any]) -> ModalityOutput:
        """处理图像输入

        Args:
            image_data: 包含 image_url / image_base64 / filename / metadata 的字典
        """
        start_time = datetime.now(timezone.utc)

        filename = image_data.get("filename", "")
        metadata = image_data.get("metadata", {})

        # 1. 推断图像内容类型
        content_type = self._infer_content_type(filename, metadata)

        # 2. 模拟实体检测
        detected_entities = self._detect_entities(content_type, metadata)

        # 3. 模拟OCR文本提取
        ocr_text = self._simulate_ocr(content_type, filename, metadata)

        # 4. 提取设备引用
        device_refs = [e.label for e in detected_entities if e.entity_type == "device"]

        # 5. 意图推断
        intent_hints = self._infer_intent_from_image(content_type, detected_entities)

        duration_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        return ModalityOutput(
            input_modality=ModalityType.IMAGE,
            status=ProcessingStatus.COMPLETED,
            extracted_text=ocr_text,
            extracted_entities=detected_entities,
            intent_hints=intent_hints,
            device_references=device_refs,
            confidence=0.7,  # 图像识别置信度通常低于文本
            processing_time_ms=duration_ms,
        )

    def _infer_content_type(
        self, filename: str, metadata: Dict[str, Any]
    ) -> ImageContentType:
        """根据文件名和元数据推断图像内容类型"""
        filename_lower = filename.lower()

        if any(kw in filename_lower for kw in ["topo", "拓扑", "架构", "network"]):
            return ImageContentType.NETWORK_TOPOLOGY
        if any(kw in filename_lower for kw in ["panel", "面板", "dashboard"]):
            return ImageContentType.DEVICE_PANEL
        if any(kw in filename_lower for kw in ["config", "配置", "setting"]):
            return ImageContentType.CONFIGURATION_SCREEN
        if any(kw in filename_lower for kw in ["chart", "graph", "曲线", "图表", "监控"]):
            return ImageContentType.CHART_GRAPH
        if any(kw in filename_lower for kw in ["log", "日志", "output"]):
            return ImageContentType.LOG_OUTPUT
        if any(kw in filename_lower for kw in ["photo", "现场", "机房"]):
            return ImageContentType.PHOTO

        # 根据元数据推断
        content_hint = metadata.get("content_type_hint", "")
        if content_hint:
            try:
                return ImageContentType(content_hint)
            except ValueError:
                pass

        return ImageContentType.UNKNOWN

    def _detect_entities(
        self, content_type: ImageContentType, metadata: Dict[str, Any]
    ) -> List[DetectedEntity]:
        """模拟实体检测"""
        entities: List[DetectedEntity] = []

        if content_type == ImageContentType.NETWORK_TOPOLOGY:
            # 拓扑图中检测到的设备节点
            devices_in_metadata = metadata.get("detected_devices", [])
            for dev in devices_in_metadata[:10]:
                entities.append(
                    DetectedEntity(
                        entity_type="device",
                        label=dev,
                        confidence=0.75,
                    )
                )
            # 如果元数据中没有设备信息，添加模拟数据
            if not entities:
                entities = [
                    DetectedEntity(entity_type="device", label="Core-Router-01", confidence=0.7),
                    DetectedEntity(entity_type="device", label="Switch-A1", confidence=0.7),
                    DetectedEntity(entity_type="link", label="10G-Fiber-Link", confidence=0.65),
                ]

        elif content_type == ImageContentType.CHART_GRAPH:
            # 图表中检测到的指标
            metrics_in_metadata = metadata.get("detected_metrics", [])
            for metric in metrics_in_metadata[:5]:
                entities.append(
                    DetectedEntity(
                        entity_type="metric",
                        label=metric.get("name", ""),
                        attributes={
                            "value": metric.get("value"),
                            "unit": metric.get("unit", ""),
                        },
                        confidence=0.8,
                    )
                )
            if not entities:
                entities = [
                    DetectedEntity(
                        entity_type="metric",
                        label="CPU利用率",
                        attributes={"value": 85.3, "unit": "%"},
                        confidence=0.75,
                    ),
                ]

        elif content_type == ImageContentType.DEVICE_PANEL:
            port_info = metadata.get("port_info", [])
            for port in port_info[:8]:
                entities.append(
                    DetectedEntity(
                        entity_type="port",
                        label=port,
                        confidence=0.7,
                    )
                )

        return entities

    def _simulate_ocr(
        self, content_type: ImageContentType, filename: str, metadata: Dict[str, Any]
    ) -> str:
        """模拟OCR文本提取"""
        # 优先使用元数据中提供的文本
        ocr_text = metadata.get("ocr_text", "")
        if ocr_text:
            return ocr_text

        # 根据内容类型生成模拟文本
        if content_type == ImageContentType.NETWORK_TOPOLOGY:
            return "[拓扑图] 核心层: Core-Router-01, Core-Router-02; 汇聚层: Switch-A1, Switch-A2"
        if content_type == ImageContentType.CHART_GRAPH:
            return "[监控图表] CPU利用率: 85.3%, 内存使用率: 72.1%, 流量: 2.4Gbps"
        if content_type == ImageContentType.LOG_OUTPUT:
            return "[日志] Error: Interface GigabitEthernet0/0/1 link down; BFD session failed"
        if content_type == ImageContentType.CONFIGURATION_SCREEN:
            return "[配置界面] 设备: Switch-A1, 接口: GE0/0/1-24, VLAN: 100,200,300"
        return f"[图像] 文件: {filename}"

    def _infer_intent_from_image(
        self, content_type: ImageContentType, entities: List[DetectedEntity]
    ) -> List[str]:
        """从图像内容推断意图"""
        hints: List[str] = []

        if content_type == ImageContentType.NETWORK_TOPOLOGY:
            hints.extend(["流量调度", "链路保护"])
        elif content_type == ImageContentType.CHART_GRAPH:
            hints.extend(["故障自愈", "QoS优化"])
        elif content_type == ImageContentType.LOG_OUTPUT:
            hints.append("故障自愈")
        elif content_type == ImageContentType.CONFIGURATION_SCREEN:
            hints.extend(["安全策略", "带宽保障"])

        # 基于检测到的实体补充意图
        for entity in entities:
            if entity.entity_type == "metric":
                label = entity.label.lower() if entity.label else ""
                if any(kw in label for kw in ["cpu", "内存", "利用率", "usage"]):
                    if "故障自愈" not in hints:
                        hints.append("故障自愈")
                if any(kw in label for kw in ["流量", "带宽", "traffic", "bandwidth"]):
                    if "带宽保障" not in hints:
                        hints.append("带宽保障")

        return hints


# ──────────────────────── 表格处理器 ────────────────────────


class TableProcessor:
    """表格模态处理器"""

    def __init__(self, config: MultimodalProcessorConfig):
        self.config = config

    def process(self, table_data: Dict[str, Any]) -> ModalityOutput:
        """处理表格输入

        Args:
            table_data: 包含 headers / rows / raw_text / format 的字典
        """
        start_time = datetime.now(timezone.utc)

        parsed_tables: List[ParsedTable] = []
        extracted_entities: List[DetectedEntity] = []
        device_references: List[str] = []
        intent_hints: List[str] = []

        # 1. 解析表格
        if "headers" in table_data and "rows" in table_data:
            parsed_table = ParsedTable(
                headers=table_data["headers"],
                rows=table_data["rows"],
                row_count=len(table_data["rows"]),
                col_count=len(table_data["headers"]),
                confidence=0.95,
            )
            parsed_tables.append(parsed_table)
        elif "raw_text" in table_data:
            # 从原始文本解析表格
            parsed_table = self._parse_raw_table(table_data["raw_text"])
            if parsed_table:
                parsed_tables.append(parsed_table)

        # 2. 从表格中提取实体
        for table in parsed_tables:
            self._extract_entities_from_table(
                table, extracted_entities, device_references, intent_hints
            )

        duration_ms = int(
            (datetime.now(timezone.utc) - start_time).total_seconds() * 1000
        )

        return ModalityOutput(
            input_modality=ModalityType.TABLE,
            status=ProcessingStatus.COMPLETED,
            extracted_text=self._table_to_text(parsed_tables),
            extracted_entities=extracted_entities,
            parsed_tables=parsed_tables,
            intent_hints=intent_hints,
            device_references=device_references,
            confidence=0.85,
            processing_time_ms=duration_ms,
        )

    def _parse_raw_table(self, raw_text: str) -> Optional[ParsedTable]:
        """从原始文本解析表格（支持CSV/TSV/Markdown表格）"""
        lines = [line.strip() for line in raw_text.strip().split("\n") if line.strip()]
        if len(lines) < 2:
            return None

        # 检测分隔符
        delimiter = "\t"
        if "," in lines[0] and lines[0].count(",") >= lines[0].count("\t"):
            delimiter = ","
        elif "|" in lines[0] and lines[0].count("|") >= 2:
            delimiter = "|"

        # 解析表头
        headers = [h.strip() for h in lines[0].split(delimiter) if h.strip()]

        # 跳过分隔行（Markdown表格的 --- 行）
        data_start = 1
        if delimiter == "|" and len(lines) > 1 and set(lines[1].strip()) <= {"-", "|", ":", " "}:
            data_start = 2

        # 解析数据行
        rows = []
        for line in lines[data_start:]:
            cells = [c.strip() for c in line.split(delimiter) if c.strip()]
            if cells:
                # 补齐列数
                while len(cells) < len(headers):
                    cells.append("")
                rows.append(cells[: len(headers)])

        if not headers or not rows:
            return None

        return ParsedTable(
            headers=headers,
            rows=rows,
            row_count=len(rows),
            col_count=len(headers),
            confidence=0.8,
        )

    def _extract_entities_from_table(
        self,
        table: ParsedTable,
        entities: List[DetectedEntity],
        device_refs: List[str],
        intent_hints: List[str],
    ) -> None:
        """从表格中提取实体"""
        # 查找设备名列
        device_col = -1
        for i, header in enumerate(table.headers):
            if any(kw in header.lower() for kw in ["设备", "device", "名称", "name", "节点"]):
                device_col = i
                break

        if device_col >= 0:
            for row in table.rows:
                if device_col < len(row) and row[device_col]:
                    device_name = row[device_col]
                    if device_name not in device_refs:
                        device_refs.append(device_name)
                        entities.append(
                            DetectedEntity(
                                entity_type="device",
                                label=device_name,
                                confidence=0.9,
                            )
                        )

        # 查找指标列
        metric_cols = []
        for i, header in enumerate(table.headers):
            if any(kw in header.lower() for kw in ["利用率", "usage", "流量", "traffic", "延迟", "latency", "带宽"]):
                metric_cols.append((i, header))

        for col_idx, col_name in metric_cols:
            for row in table.rows:
                if col_idx < len(row) and row[col_idx]:
                    entities.append(
                        DetectedEntity(
                            entity_type="metric",
                            label=f"{col_name}: {row[col_idx]}",
                            attributes={"column": col_name, "value": row[col_idx]},
                            confidence=0.85,
                        )
                    )

        # 基于表头推断意图
        header_text = " ".join(table.headers).lower()
        if any(kw in header_text for kw in ["故障", "告警", "异常"]):
            intent_hints.append("故障自愈")
        if any(kw in header_text for kw in ["带宽", "qos", "流量"]):
            intent_hints.append("带宽保障")
        if any(kw in header_text for kw in ["安全", "acl", "策略"]):
            intent_hints.append("安全策略")

    def _table_to_text(self, tables: List[ParsedTable]) -> str:
        """将表格转换为文本描述"""
        parts = []
        for i, table in enumerate(tables):
            parts.append(f"表格{i + 1}（{table.row_count}行×{table.col_count}列）:")
            parts.append(" | ".join(table.headers))
            for row in table.rows[:5]:  # 最多5行
                parts.append(" | ".join(row))
            if table.row_count > 5:
                parts.append(f"... 省略 {table.row_count - 5} 行")
        return "\n".join(parts)


# ──────────────────────── 多模态融合器 ────────────────────────


class MultimodalFusion:
    """多模态融合器

    将不同模态的处理结果融合为统一的意图理解。
    """

    def __init__(self, config: MultimodalProcessorConfig):
        self.config = config

    def fuse(self, outputs: List[ModalityOutput]) -> FusionResult:
        """融合多个模态的处理结果"""
        if not outputs:
            return FusionResult()

        # 1. 收集所有意图提示，加权投票
        intent_scores: Dict[str, float] = {}
        for output in outputs:
            weight = self._get_modality_weight(output.input_modality)
            for hint in output.intent_hints:
                intent_scores[hint] = intent_scores.get(hint, 0.0) + weight * output.confidence

        # 2. 确定主意图
        primary_intent = None
        max_score = 0.0
        for intent, score in intent_scores.items():
            if score > max_score:
                max_score = score
                primary_intent = intent

        # 3. 合并实体
        combined_entities: List[DetectedEntity] = []
        seen_labels: Dict[str, float] = {}
        for output in outputs:
            for entity in output.extracted_entities:
                key = f"{entity.entity_type}:{entity.label}"
                if key not in seen_labels or entity.confidence > seen_labels[key]:
                    seen_labels[key] = entity.confidence
                    # 去重：替换低置信度的
                    combined_entities = [
                        e for e in combined_entities
                        if f"{e.entity_type}:{e.label}" != key
                    ]
                    combined_entities.append(entity)

        # 4. 合并设备引用
        combined_device_refs: List[str] = []
        for output in outputs:
            for ref in output.device_references:
                if ref not in combined_device_refs:
                    combined_device_refs.append(ref)

        # 5. 合并意图提示
        combined_intent_hints = []
        seen_hints = set()
        for output in outputs:
            for hint in output.intent_hints:
                if hint not in seen_hints:
                    seen_hints.add(hint)
                    combined_intent_hints.append(hint)

        # 6. 检测矛盾
        contradictions = self._detect_contradictions(outputs)

        # 7. 计算各模态贡献度
        total_weight = sum(self._get_modality_weight(o.input_modality) * o.confidence for o in outputs)
        text_contrib = 0.0
        image_contrib = 0.0
        table_contrib = 0.0
        if total_weight > 0:
            for output in outputs:
                contrib = self._get_modality_weight(output.input_modality) * output.confidence / total_weight
                if output.input_modality == ModalityType.TEXT:
                    text_contrib += contrib
                elif output.input_modality == ModalityType.IMAGE:
                    image_contrib += contrib
                elif output.input_modality == ModalityType.TABLE:
                    table_contrib += contrib

        # 8. 综合置信度
        overall_confidence = max_score / sum(
            self._get_modality_weight(o.input_modality) for o in outputs
        ) if outputs else 0.0
        overall_confidence = min(overall_confidence, 1.0)

        return FusionResult(
            primary_intent=primary_intent,
            confidence=round(overall_confidence, 3),
            text_contribution=round(text_contrib, 3),
            image_contribution=round(image_contrib, 3),
            table_contribution=round(table_contrib, 3),
            combined_entities=combined_entities,
            combined_device_refs=combined_device_refs,
            combined_intent_hints=combined_intent_hints,
            contradictions=contradictions,
        )

    def _get_modality_weight(self, modality: ModalityType) -> float:
        """获取模态权重"""
        weights = {
            ModalityType.TEXT: self.config.fusion_text_weight,
            ModalityType.IMAGE: self.config.fusion_image_weight,
            ModalityType.TABLE: self.config.fusion_table_weight,
            ModalityType.STRUCTURED_DATA: 0.4,
            ModalityType.MIXED: 0.3,
        }
        return weights.get(modality, 0.1)

    def _detect_contradictions(self, outputs: List[ModalityOutput]) -> List[str]:
        """检测模态间的矛盾"""
        contradictions: List[str] = []

        # 收集各模态的设备引用
        device_sets: Dict[ModalityType, set] = {}
        for output in outputs:
            if output.device_references:
                device_sets[output.input_modality] = set(output.device_references)

        # 检查设备引用冲突
        modalities = list(device_sets.keys())
        for i in range(len(modalities)):
            for j in range(i + 1, len(modalities)):
                set_a = device_sets[modalities[i]]
                set_b = device_sets[modalities[j]]
                if set_a and set_b and not set_a.intersection(set_b):
                    contradictions.append(
                        f"{modalities[i].value}和{modalities[j].value}引用的设备完全不同"
                    )

        return contradictions


# ──────────────────────── 多模态处理器主类 ────────────────────────


class MultimodalProcessor:
    """多模态处理器

    核心职责：
    1. 接收多种模态输入（文本/图像/表格）
    2. 分发给对应模态处理器
    3. 融合多模态结果
    4. 输出统一的意图理解和实体提取结果
    """

    def __init__(self, config: Optional[MultimodalProcessorConfig] = None):
        self.config = config or MultimodalProcessorConfig()
        self.logger = logging.getLogger(f"{__name__}.{self.__class__.__name__}")

        # 初始化子处理器
        self._text_processor = TextProcessor(self.config)
        self._image_processor = ImageProcessor(self.config)
        self._table_processor = TableProcessor(self.config)
        self._fusion = MultimodalFusion(self.config)

        # 处理统计
        self._processing_stats = {
            "text_count": 0,
            "image_count": 0,
            "table_count": 0,
            "mixed_count": 0,
            "total_count": 0,
            "avg_processing_time_ms": 0,
        }

    def _determine_modality(self, inputs: List[ModalityInput]) -> ModalityType:
        """确定输入的主要模态类型"""
        if len(inputs) == 1:
            return inputs[0].modality

        modalities = {inp.modality for inp in inputs}
        if len(modalities) > 1:
            return ModalityType.MIXED
        return inputs[0].modality

    def _process_single(self, modality_input: ModalityInput) -> ModalityOutput:
        """处理单个模态输入"""
        if modality_input.modality == ModalityType.TEXT:
            return self._text_processor.process(modality_input.content)
        elif modality_input.modality == ModalityType.IMAGE:
            return self._image_processor.process(
                modality_input.content
                if isinstance(modality_input.content, dict)
                else {"metadata": modality_input.metadata}
            )
        elif modality_input.modality == ModalityType.TABLE:
            return self._table_processor.process(
                modality_input.content
                if isinstance(modality_input.content, dict)
                else {"raw_text": str(modality_input.content)}
            )
        elif modality_input.modality == ModalityType.STRUCTURED_DATA:
            # 结构化数据转为文本处理
            text = json.dumps(modality_input.content, ensure_ascii=False) if not isinstance(
                modality_input.content, str
            ) else modality_input.content
            return self._text_processor.process(text)
        else:
            return ModalityOutput(
                input_modality=modality_input.modality,
                status=ProcessingStatus.FAILED,
                error=f"不支持的模态类型: {modality_input.modality.value}",
            )

    async def process(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """处理多模态任务

        支持的 action:
        - process: 处理多模态输入
        - process_text: 仅处理文本
        - process_image: 仅处理图像
        - process_table: 仅处理表格
        - fuse: 融合已有的处理结果
        - stats: 获取处理统计
        """
        action = task.get("action", "process")

        if action == "process":
            inputs_data = task.get("inputs", [])
            modality_inputs: List[ModalityInput] = []

            for inp_data in inputs_data:
                modality = ModalityType(inp_data.get("modality", "text"))
                modality_inputs.append(
                    ModalityInput(
                        modality=modality,
                        content=inp_data.get("content", ""),
                        metadata=inp_data.get("metadata", {}),
                        source=inp_data.get("source", "user"),
                    )
                )

            if not modality_inputs:
                return {"error": "未提供输入数据"}

            # 处理各模态
            outputs: List[ModalityOutput] = []
            for m_input in modality_inputs:
                output = self._process_single(m_input)
                outputs.append(output)

            # 融合结果
            fusion_result = self._fusion.fuse(outputs) if len(outputs) > 1 else None

            # 更新统计
            primary_modality = self._determine_modality(modality_inputs)
            self._update_stats(primary_modality, outputs)

            result: Dict[str, Any] = {
                "action": "process",
                "primary_modality": primary_modality.value,
                "modality_outputs": [
                    {
                        "modality": o.input_modality.value,
                        "status": o.status.value,
                        "extracted_text": o.extracted_text[:500] if o.extracted_text else "",
                        "entities_count": len(o.extracted_entities),
                        "device_references": o.device_references,
                        "intent_hints": o.intent_hints,
                        "confidence": o.confidence,
                        "processing_time_ms": o.processing_time_ms,
                    }
                    for o in outputs
                ],
            }

            if fusion_result:
                result["fusion"] = {
                    "primary_intent": fusion_result.primary_intent,
                    "confidence": fusion_result.confidence,
                    "text_contribution": fusion_result.text_contribution,
                    "image_contribution": fusion_result.image_contribution,
                    "table_contribution": fusion_result.table_contribution,
                    "combined_device_refs": fusion_result.combined_device_refs,
                    "combined_intent_hints": fusion_result.combined_intent_hints,
                    "contradictions": fusion_result.contradictions,
                }

            return result

        if action == "process_text":
            text = task.get("content", "")
            output = self._text_processor.process(text)
            self._update_stats(ModalityType.TEXT, [output])
            return {
                "action": "process_text",
                "status": output.status.value,
                "entities": [
                    {"type": e.entity_type, "label": e.label, "confidence": e.confidence}
                    for e in output.extracted_entities
                ],
                "device_references": output.device_references,
                "intent_hints": output.intent_hints,
                "confidence": output.confidence,
            }

        if action == "process_image":
            image_data = task.get("image_data", {})
            output = self._image_processor.process(image_data)
            self._update_stats(ModalityType.IMAGE, [output])
            return {
                "action": "process_image",
                "status": output.status.value,
                "content_type": image_data.get("content_type_hint", "unknown"),
                "entities": [
                    {"type": e.entity_type, "label": e.label, "confidence": e.confidence}
                    for e in output.extracted_entities
                ],
                "ocr_text": output.extracted_text[:500] if output.extracted_text else "",
                "device_references": output.device_references,
                "intent_hints": output.intent_hints,
                "confidence": output.confidence,
            }

        if action == "process_table":
            table_data = task.get("table_data", {})
            output = self._table_processor.process(table_data)
            self._update_stats(ModalityType.TABLE, [output])
            return {
                "action": "process_table",
                "status": output.status.value,
                "tables": [
                    {
                        "headers": t.headers,
                        "row_count": t.row_count,
                        "col_count": t.col_count,
                        "confidence": t.confidence,
                    }
                    for t in output.parsed_tables
                ],
                "device_references": output.device_references,
                "intent_hints": output.intent_hints,
                "confidence": output.confidence,
            }

        if action == "stats":
            return {"action": "stats", "statistics": self._processing_stats}

        return {"error": f"未知 action: {action}"}

    def _update_stats(
        self, primary_modality: ModalityType, outputs: List[ModalityOutput]
    ) -> None:
        """更新处理统计"""
        self._processing_stats["total_count"] += 1

        if primary_modality == ModalityType.TEXT:
            self._processing_stats["text_count"] += 1
        elif primary_modality == ModalityType.IMAGE:
            self._processing_stats["image_count"] += 1
        elif primary_modality == ModalityType.TABLE:
            self._processing_stats["table_count"] += 1
        elif primary_modality == ModalityType.MIXED:
            self._processing_stats["mixed_count"] += 1

        avg_time = sum(o.processing_time_ms for o in outputs) / max(len(outputs), 1)
        total = self._processing_stats["total_count"]
        old_avg = self._processing_stats["avg_processing_time_ms"]
        self._processing_stats["avg_processing_time_ms"] = int(
            (old_avg * (total - 1) + avg_time) / total
        )

    async def health_check(self) -> Dict[str, Any]:
        """健康检查"""
        stats = self._processing_stats
        is_healthy = stats["total_count"] < 100000  # 防止内存溢出

        return {
            "status": "healthy" if is_healthy else "degraded",
            "total_processed": stats["total_count"],
            "text_processed": stats["text_count"],
            "image_processed": stats["image_count"],
            "table_processed": stats["table_count"],
            "mixed_processed": stats["mixed_count"],
            "avg_processing_time_ms": stats["avg_processing_time_ms"],
            "ocr_enabled": self.config.enable_ocr,
            "entity_detection_enabled": self.config.enable_entity_detection,
            "table_parsing_enabled": self.config.enable_table_parsing,
        }
