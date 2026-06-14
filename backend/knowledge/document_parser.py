import re
import os
import logging
from typing import List, Dict, Any, Optional
from dataclasses import dataclass, field

logger = logging.getLogger(__name__)


@dataclass
class ParsedDocument:
    title: str
    content: str
    sections: List[Dict[str, str]] = field(default_factory=list)
    metadata: Dict[str, Any] = field(default_factory=dict)
    source_file: str = ""


class DocumentParser:
    def parse_text(self, content: str, title: str = "") -> ParsedDocument:
        sections = []
        paragraphs = re.split(r'\n\s*\n', content.strip())
        for i, para in enumerate(paragraphs):
            para = para.strip()
            if para:
                first_line = para.split('\n')[0].strip()
                heading = first_line[:50] if first_line else f"段落 {i + 1}"
                sections.append({"heading": heading, "content": para})

        return ParsedDocument(
            title=title or "未命名文档",
            content=content,
            sections=sections,
            metadata={"format": "text", "char_count": len(content)},
            source_file="",
        )

    def parse_markdown(self, content: str, title: str = "") -> ParsedDocument:
        sections = []
        current_heading = ""
        current_content_lines = []

        for line in content.split('\n'):
            header_match = re.match(r'^(#{1,6})\s+(.+)$', line)
            if header_match:
                if current_heading or current_content_lines:
                    section_content = '\n'.join(current_content_lines).strip()
                    if section_content:
                        sections.append({
                            "heading": current_heading,
                            "content": section_content,
                        })
                current_heading = header_match.group(2).strip()
                current_content_lines = []
            else:
                current_content_lines.append(line)

        if current_heading or current_content_lines:
            section_content = '\n'.join(current_content_lines).strip()
            if section_content:
                sections.append({
                    "heading": current_heading,
                    "content": section_content,
                })

        if not title:
            for line in content.split('\n'):
                match = re.match(r'^#\s+(.+)$', line)
                if match:
                    title = match.group(1).strip()
                    break
            if not title:
                title = "未命名Markdown文档"

        return ParsedDocument(
            title=title,
            content=content,
            sections=sections,
            metadata={"format": "markdown", "char_count": len(content), "section_count": len(sections)},
            source_file="",
        )

    def parse_pdf(self, file_path: str) -> ParsedDocument:
        try:
            from PyPDF2 import PdfReader
            reader = PdfReader(file_path)
            pages = []
            sections = []

            for i, page in enumerate(reader.pages):
                text = page.extract_text()
                if text and text.strip():
                    pages.append(text.strip())
                    sections.append({
                        "heading": f"第 {i + 1} 页",
                        "content": text.strip(),
                    })

            content = '\n\n'.join(pages)
            title = os.path.splitext(os.path.basename(file_path))[0]

            metadata = {
                "format": "pdf",
                "char_count": len(content),
                "page_count": len(reader.pages),
            }

            try:
                pdf_info = reader.metadata
                if pdf_info:
                    if pdf_info.title:
                        title = pdf_info.title
                    if pdf_info.author:
                        metadata["author"] = pdf_info.author
            except Exception:
                pass

            return ParsedDocument(
                title=title,
                content=content,
                sections=sections,
                metadata=metadata,
                source_file=file_path,
            )
        except ImportError:
            logger.warning("PyPDF2 not installed, attempting basic PDF parsing")
            return self._parse_pdf_fallback(file_path)
        except Exception as e:
            logger.error(f"PDF parsing failed for {file_path}: {e}")
            return ParsedDocument(
                title=os.path.splitext(os.path.basename(file_path))[0],
                content="",
                sections=[],
                metadata={"format": "pdf", "error": str(e)},
                source_file=file_path,
            )

    def _parse_pdf_fallback(self, file_path: str) -> ParsedDocument:
        try:
            with open(file_path, 'rb') as f:
                raw = f.read()
            text = raw.decode('utf-8', errors='ignore')
            text = re.sub(r'[^\u4e00-\u9fff\u3000-\u303f\uff00-\uffefa-zA-Z0-9\s.,;:!?()（）、。，；：！？]', '', text)
            text = re.sub(r'\s+', ' ', text).strip()

            title = os.path.splitext(os.path.basename(file_path))[0]
            return ParsedDocument(
                title=title,
                content=text,
                sections=[{"heading": "全文", "content": text}] if text else [],
                metadata={"format": "pdf_fallback", "char_count": len(text)},
                source_file=file_path,
            )
        except Exception as e:
            logger.error(f"PDF fallback parsing failed for {file_path}: {e}")
            return ParsedDocument(
                title=os.path.splitext(os.path.basename(file_path))[0],
                content="",
                sections=[],
                metadata={"format": "pdf_fallback", "error": str(e)},
                source_file=file_path,
            )

    def parse_file(self, file_path: str) -> ParsedDocument:
        ext = os.path.splitext(file_path)[1].lower()
        title = os.path.splitext(os.path.basename(file_path))[0]

        if ext == '.pdf':
            return self.parse_pdf(file_path)
        elif ext in ('.md', '.markdown'):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse_markdown(content, title)
        elif ext in ('.txt', '.text', '.log', '.cfg', '.conf'):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse_text(content, title)
        elif ext in ('.json', '.yaml', '.yml', '.xml', '.csv'):
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            return self.parse_text(content, title)
        else:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                return self.parse_text(content, title)
            except UnicodeDecodeError:
                with open(file_path, 'r', encoding='gbk', errors='ignore') as f:
                    content = f.read()
                return self.parse_text(content, title)


document_parser = DocumentParser()
