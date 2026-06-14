from typing import Optional
import os
import csv
import io
import re
import logging

logger = logging.getLogger(__name__)

IMAGE_EXTENSIONS = {".png", ".jpg", ".jpeg", ".gif", ".bmp", ".webp"}
LOG_EXTENSIONS = {".log", ".txt"}
CSV_EXTENSIONS = {".csv"}
PDF_EXTENSIONS = {".pdf"}

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
MAX_LOG_SIZE_BYTES = 50 * 1024 * 1024
ALLOWED_UPLOAD_DIR = os.environ.get("AGENTHUB_UPLOAD_DIR", "")


def _validate_file_path(file_path: str) -> Optional[str]:
    resolved = os.path.realpath(file_path)
    if ALLOWED_UPLOAD_DIR:
        allowed_root = os.path.realpath(ALLOWED_UPLOAD_DIR)
        if not resolved.startswith(allowed_root + os.sep) and resolved != allowed_root:
            return f"文件路径不在允许的目录内"
    if ".." in file_path:
        return "文件路径包含非法的路径遍历字符"
    return None


class MultimodalProcessor:
    async def process_topology_image(self, file_path: str) -> dict:
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}

        path_error = _validate_file_path(file_path)
        if path_error:
            return {"error": path_error}

        file_size = os.path.getsize(file_path)
        if file_size > MAX_IMAGE_SIZE_BYTES:
            return {"error": f"图片文件过大（{file_size}字节），最大允许{MAX_IMAGE_SIZE_BYTES}字节"}

        try:
            from backend.agents.llm_gateway import get_llm_gateway
            gateway = get_llm_gateway()

            import base64
            with open(file_path, "rb") as f:
                image_data = base64.b64encode(f.read()).decode("utf-8")

            ext = os.path.splitext(file_path)[1].lower()
            mime_map = {
                ".png": "image/png",
                ".jpg": "image/jpeg",
                ".jpeg": "image/jpeg",
                ".gif": "image/gif",
                ".bmp": "image/bmp",
                ".webp": "image/webp",
            }
            mime_type = mime_map.get(ext, "image/png")

            prompt = """请分析这张网络拓扑图，提取以下信息并以JSON格式返回：
1. devices: 设备列表，每个设备包含 name(名称), type(类型如路由器/交换机/防火墙), status(状态标识，如在线/离线)
2. connections: 连接列表，每个连接包含 source(源设备), target(目标设备), link_type(链路类型)
3. summary: 拓扑概要描述

请严格返回JSON格式，不要添加其他文字。"""

            messages = [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {
                                "url": f"data:{mime_type};base64,{image_data}"
                            },
                        },
                    ],
                }
            ]

            try:
                response = await gateway.chat(
                    messages,
                    temperature=0.1,
                    max_tokens=2048,
                )
                import json
                content = response.get("content", "") if isinstance(response, dict) else str(response)
                json_str = content.strip()
                if json_str.startswith("```"):
                    json_str = json_str.split("\n", 1)[1] if "\n" in json_str else json_str[3:]
                    json_str = json_str.rsplit("```", 1)[0]
                result = json.loads(json_str.strip())
                return {
                    "file_type": "topology_image",
                    "topology": result,
                }
            except Exception as llm_err:
                logger.warning(f"LLM vision analysis failed: {llm_err}, returning basic info")
                return {
                    "file_type": "topology_image",
                    "topology": {
                        "devices": [],
                        "connections": [],
                        "summary": f"已上传拓扑图 {os.path.basename(file_path)}，LLM视觉分析暂不可用",
                    },
                    "warning": "LLM视觉能力不可用，无法自动提取拓扑信息",
                }
        except Exception as e:
            logger.error(f"Process topology image error: {e}")
            return {"error": f"处理拓扑图失败: {str(e)}"}

    async def process_log_file(self, file_path: str, file_type: str = "text") -> dict:
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}

        path_error = _validate_file_path(file_path)
        if path_error:
            return {"error": path_error}

        file_size = os.path.getsize(file_path)
        if file_size > MAX_LOG_SIZE_BYTES:
            return {"error": f"日志文件过大（{file_size}字节），最大允许{MAX_LOG_SIZE_BYTES}字节"}

        try:
            ext = os.path.splitext(file_path)[1].lower()
            lines = []
            error_patterns = []
            severity_counts = {"critical": 0, "error": 0, "warning": 0, "info": 0, "debug": 0}
            timestamps = []

            if ext in CSV_EXTENSIONS:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    reader = csv.DictReader(f)
                    for row in reader:
                        lines.append(dict(row))
                        line_str = " ".join(str(v) for v in row.values()).lower()
                        for sev in severity_counts:
                            if sev in line_str:
                                severity_counts[sev] += 1
                        for k, v in row.items():
                            v_str = str(v)
                            ts_match = re.search(
                                r"\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}", v_str
                            )
                            if ts_match:
                                timestamps.append(ts_match.group())
                            if any(
                                kw in v_str.lower()
                                for kw in ["error", "fail", "exception", "timeout", "refused"]
                            ):
                                error_patterns.append(v_str)
            else:
                with open(file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        lines.append(line)
                        line_lower = line.lower()
                        for sev in severity_counts:
                            if sev in line_lower:
                                severity_counts[sev] += 1
                        ts_match = re.search(
                            r"\d{4}[-/]\d{2}[-/]\d{2}[T ]\d{2}:\d{2}:\d{2}", line
                        )
                        if ts_match:
                            timestamps.append(ts_match.group())
                        if any(
                            kw in line_lower
                            for kw in ["error", "fail", "exception", "timeout", "refused"]
                        ):
                            error_patterns.append(line)

            summary = await self._generate_log_summary(lines, error_patterns, severity_counts)

            return {
                "file_type": "log_file",
                "total_lines": len(lines),
                "severity_counts": severity_counts,
                "error_count": len(error_patterns),
                "error_patterns": error_patterns[:50],
                "timestamp_range": {
                    "earliest": timestamps[0] if timestamps else None,
                    "latest": timestamps[-1] if timestamps else None,
                },
                "summary": summary,
            }
        except Exception as e:
            logger.error(f"Process log file error: {e}")
            return {"error": f"处理日志文件失败: {str(e)}"}

    async def _generate_log_summary(
        self, lines: list, error_patterns: list, severity_counts: dict
    ) -> str:
        try:
            from backend.agents.llm_gateway import get_llm_gateway
            gateway = get_llm_gateway()

            sample = lines[:100] if len(lines) > 100 else lines
            error_sample = error_patterns[:20] if len(error_patterns) > 20 else error_patterns

            prompt = f"""请分析以下日志文件摘要，生成简洁的中文总结：

日志总行数：{len(lines)}
严重级别统计：{severity_counts}
错误模式样本：
{chr(10).join(str(e) for e in error_sample)}

日志样本（前100行）：
{chr(10).join(str(l) for l in sample)}

请用中文总结：1)主要问题 2)可能原因 3)建议操作"""

            messages = [{"role": "user", "content": prompt}]
            response = await gateway.chat(
                messages,
                temperature=0.3,
                max_tokens=1024,
            )
            return response.get("content", "") if isinstance(response, dict) else str(response)
        except Exception as e:
            logger.warning(f"LLM log summary generation failed: {e}")
            total_errors = severity_counts.get("error", 0) + severity_counts.get("critical", 0)
            return f"日志文件包含 {len(lines)} 行，其中 {total_errors} 条错误/严重记录"

    async def process_file_upload(self, file_path: str, file_name: str) -> dict:
        if not os.path.exists(file_path):
            return {"error": f"File not found: {file_path}"}

        path_error = _validate_file_path(file_path)
        if path_error:
            return {"error": path_error}

        ext = os.path.splitext(file_name)[1].lower()

        if ext in IMAGE_EXTENSIONS:
            return await self.process_topology_image(file_path)
        elif ext in LOG_EXTENSIONS:
            return await self.process_log_file(file_path, file_type="text")
        elif ext in CSV_EXTENSIONS:
            return await self.process_log_file(file_path, file_type="csv")
        elif ext in PDF_EXTENSIONS:
            return await self._process_pdf(file_path)
        else:
            return {
                "file_type": "unknown",
                "file_name": file_name,
                "message": f"不支持的文件类型: {ext}",
            }

    async def _process_pdf(self, file_path: str) -> dict:
        path_error = _validate_file_path(file_path)
        if path_error:
            return {"error": path_error}

        try:
            page_count = 0
            full_text = ""
            try:
                import PyPDF2
                with open(file_path, "rb") as f:
                    reader = PyPDF2.PdfReader(f)
                    page_count = len(reader.pages)
                    text_parts = []
                    for page in reader.pages[:20]:
                        text = page.extract_text()
                        if text:
                            text_parts.append(text)
                    full_text = "\n".join(text_parts)
            except ImportError:
                logger.warning("PyPDF2 not installed, cannot extract PDF text")

            if full_text:
                return {
                    "file_type": "pdf",
                    "page_count": page_count,
                    "extracted_text_length": len(full_text),
                    "summary": full_text[:2000],
                }
            return {
                "file_type": "pdf",
                "message": "PDF文本提取失败，可能为扫描件或加密文档",
            }
        except Exception as e:
            logger.error(f"Process PDF error: {e}")
            return {"error": f"处理PDF文件失败: {str(e)}"}


_multimodal_processor: Optional[MultimodalProcessor] = None


def get_multimodal_processor() -> MultimodalProcessor:
    global _multimodal_processor
    if _multimodal_processor is None:
        _multimodal_processor = MultimodalProcessor()
    return _multimodal_processor
