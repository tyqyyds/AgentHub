import uuid
import hashlib
import difflib
import logging
from typing import Optional, List, Dict, Any

from sqlalchemy import select, func, desc
from backend.database.connection import async_session_maker
from backend.database.models import KnowledgeDocumentVersion

logger = logging.getLogger(__name__)


def _generate_version_id() -> str:
    return f"kv_{uuid.uuid4().hex[:12]}"


def _compute_content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _version_to_dict(version: KnowledgeDocumentVersion) -> dict:
    if version is None:
        return {}
    result = {}
    for col in version.__table__.columns:
        val = getattr(version, col.name, None)
        if val is not None and hasattr(val, "isoformat"):
            val = val.isoformat()
        result[col.name] = val
    return result


class KnowledgeVersionControl:
    async def create_version(
        self,
        document_id: str,
        title: str,
        content: str,
        contributor: str,
        change_type: str = "created",
        change_summary: str = None,
    ) -> KnowledgeDocumentVersion:
        content_hash = _compute_content_hash(content)

        async with async_session_maker() as session:
            stmt = select(func.max(KnowledgeDocumentVersion.version_number)).where(
                KnowledgeDocumentVersion.document_id == document_id
            )
            result = await session.execute(stmt)
            max_version = result.scalar() or 0

            version = KnowledgeDocumentVersion(
                version_id=_generate_version_id(),
                document_id=document_id,
                title=title,
                content=content,
                version_number=max_version + 1,
                change_type=change_type,
                change_summary=change_summary,
                contributor=contributor,
                content_hash=content_hash,
            )
            session.add(version)
            try:
                await session.commit()
            except Exception as e:
                await session.rollback()
                raise e
            await session.refresh(version)
            return version

    async def get_version(self, version_id: str) -> dict:
        async with async_session_maker() as session:
            stmt = select(KnowledgeDocumentVersion).where(
                KnowledgeDocumentVersion.version_id == version_id
            )
            result = await session.execute(stmt)
            version = result.scalar_one_or_none()
            if version is None:
                raise ValueError(f"Version not found: {version_id}")
            return _version_to_dict(version)

    async def get_document_versions(self, document_id: str, limit: int = 20) -> List[dict]:
        async with async_session_maker() as session:
            stmt = (
                select(KnowledgeDocumentVersion)
                .where(KnowledgeDocumentVersion.document_id == document_id)
                .order_by(desc(KnowledgeDocumentVersion.version_number))
                .limit(limit)
            )
            result = await session.execute(stmt)
            versions = result.scalars().all()
            return [_version_to_dict(v) for v in versions]

    async def get_latest_version(self, document_id: str) -> dict:
        async with async_session_maker() as session:
            stmt = (
                select(KnowledgeDocumentVersion)
                .where(KnowledgeDocumentVersion.document_id == document_id)
                .order_by(desc(KnowledgeDocumentVersion.version_number))
                .limit(1)
            )
            result = await session.execute(stmt)
            version = result.scalar_one_or_none()
            if version is None:
                raise ValueError(f"No versions found for document: {document_id}")
            return _version_to_dict(version)

    async def compare_versions(self, document_id: str, version_a: str, version_b: str) -> dict:
        async with async_session_maker() as session:
            stmt_a = select(KnowledgeDocumentVersion).where(
                KnowledgeDocumentVersion.version_id == version_a
            )
            result_a = await session.execute(stmt_a)
            va = result_a.scalar_one_or_none()
            if va is None:
                raise ValueError(f"Version not found: {version_a}")

            stmt_b = select(KnowledgeDocumentVersion).where(
                KnowledgeDocumentVersion.version_id == version_b
            )
            result_b = await session.execute(stmt_b)
            vb = result_b.scalar_one_or_none()
            if vb is None:
                raise ValueError(f"Version not found: {version_b}")

            lines_a = va.content.splitlines(keepends=True)
            lines_b = vb.content.splitlines(keepends=True)
            diff = list(difflib.unified_diff(lines_a, lines_b, fromfile=version_a, tofile=version_b))

            content_changed = va.content_hash != vb.content_hash
            title_changed = va.title != vb.title

            return {
                "document_id": document_id,
                "version_a": _version_to_dict(va),
                "version_b": _version_to_dict(vb),
                "content_changed": content_changed,
                "title_changed": title_changed,
                "diff": "".join(diff) if diff else "",
                "summary": {
                    "content_changed": content_changed,
                    "title_changed": title_changed,
                    "lines_added": sum(1 for d in diff if d.startswith("+") and not d.startswith("+++")),
                    "lines_removed": sum(1 for d in diff if d.startswith("-") and not d.startswith("---")),
                },
            }

    async def rollback_to_version(self, document_id: str, version_id: str, contributor: str) -> dict:
        async with async_session_maker() as session:
            stmt = select(KnowledgeDocumentVersion).where(
                KnowledgeDocumentVersion.version_id == version_id
            )
            result = await session.execute(stmt)
            target = result.scalar_one_or_none()
            if target is None:
                raise ValueError(f"Version not found: {version_id}")
            if target.document_id != document_id:
                raise ValueError(f"Version {version_id} does not belong to document {document_id}")

        new_version = await self.create_version(
            document_id=document_id,
            title=target.title,
            content=target.content,
            contributor=contributor,
            change_type="updated",
            change_summary=f"Rollback to version {version_id}",
        )
        return _version_to_dict(new_version)

    async def get_contributor_history(self, contributor: str, limit: int = 50) -> List[dict]:
        async with async_session_maker() as session:
            stmt = (
                select(KnowledgeDocumentVersion)
                .where(KnowledgeDocumentVersion.contributor == contributor)
                .order_by(desc(KnowledgeDocumentVersion.created_at))
                .limit(limit)
            )
            result = await session.execute(stmt)
            versions = result.scalars().all()
            return [_version_to_dict(v) for v in versions]

    async def get_version_stats(self) -> dict:
        async with async_session_maker() as session:
            total_stmt = select(func.count(KnowledgeDocumentVersion.id))
            total_result = await session.execute(total_stmt)
            total_versions = total_result.scalar() or 0

            doc_stmt = select(func.count(func.distinct(KnowledgeDocumentVersion.document_id)))
            doc_result = await session.execute(doc_stmt)
            total_documents = doc_result.scalar() or 0

            contributor_stmt = select(func.count(func.distinct(KnowledgeDocumentVersion.contributor)))
            contributor_result = await session.execute(contributor_stmt)
            total_contributors = contributor_result.scalar() or 0

            change_type_stmt = (
                select(KnowledgeDocumentVersion.change_type, func.count(KnowledgeDocumentVersion.id))
                .group_by(KnowledgeDocumentVersion.change_type)
            )
            change_type_result = await session.execute(change_type_stmt)
            change_type_counts = {row[0]: row[1] for row in change_type_result}

            return {
                "total_versions": total_versions,
                "total_documents": total_documents,
                "total_contributors": total_contributors,
                "change_type_counts": change_type_counts,
            }


_knowledge_version_control: Optional[KnowledgeVersionControl] = None


def get_knowledge_version_control() -> KnowledgeVersionControl:
    global _knowledge_version_control
    if _knowledge_version_control is None:
        _knowledge_version_control = KnowledgeVersionControl()
    return _knowledge_version_control
