from typing import Dict, List, Optional
from datetime import datetime, timezone
from sqlalchemy import select, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from backend.database.connection import async_session_maker
from backend.database.models import IntentTemplate
import uuid
import re
import logging

logger = logging.getLogger(__name__)


def _generate_template_id() -> str:
    return f"tmpl_{uuid.uuid4().hex[:8]}"


def _template_to_dict(t: IntentTemplate) -> dict:
    return {
        "id": t.id,
        "template_id": t.template_id,
        "name": t.name,
        "description": t.description,
        "category": t.category,
        "intent_type": t.intent_type,
        "template_content": t.template_content,
        "parameters_schema": t.parameters_schema,
        "example_values": t.example_values,
        "sla_template": t.sla_template,
        "priority": t.priority,
        "is_public": t.is_public,
        "author": t.author,
        "usage_count": t.usage_count,
        "rating": t.rating,
        "rating_count": t.rating_count,
        "tags": t.tags,
        "version": t.version,
        "created_at": t.created_at.isoformat() if t.created_at else None,
        "updated_at": t.updated_at.isoformat() if t.updated_at else None,
    }


class IntentTemplateManager:
    async def create_template(
        self,
        name: str,
        description: str,
        category: str,
        intent_type: str,
        template_content: str,
        parameters_schema: list,
        author: str,
        **kwargs,
    ) -> IntentTemplate:
        template_id = _generate_template_id()
        async with async_session_maker() as session:
            template = IntentTemplate(
                template_id=template_id,
                name=name,
                description=description,
                category=category,
                intent_type=intent_type,
                template_content=template_content,
                parameters_schema=parameters_schema,
                example_values=kwargs.get("example_values"),
                sla_template=kwargs.get("sla_template"),
                priority=kwargs.get("priority", "medium"),
                is_public=kwargs.get("is_public", True),
                author=author,
                tags=kwargs.get("tags", []),
                version=1,
            )
            session.add(template)
            await session.commit()
            await session.refresh(template)
            logger.info(f"Created intent template {template_id}: {name}")
            return template

    async def instantiate_template(self, template_id: str, parameter_values: dict) -> dict:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentTemplate).where(IntentTemplate.template_id == template_id)
            )
            template = result.scalar_one_or_none()
            if not template:
                return None

            content = template.template_content
            placeholders = re.findall(r"\{(\w+)\}", content)
            filled_content = content
            missing = []
            for ph in placeholders:
                if ph in parameter_values:
                    filled_content = filled_content.replace(f"{{{ph}}}", str(parameter_values[ph]))
                else:
                    missing.append(ph)

            if missing:
                schema_names = [p.get("name") for p in (template.parameters_schema or [])]
                required_missing = [m for m in missing if m in schema_names]
                if required_missing:
                    return {
                        "error": f"Missing required parameters: {', '.join(required_missing)}",
                        "missing_parameters": required_missing,
                    }

            template.usage_count = (template.usage_count or 0) + 1
            await session.commit()

            return {
                "template_id": template.template_id,
                "name": template.name,
                "intent_type": template.intent_type,
                "filled_content": filled_content,
                "parameter_values": parameter_values,
                "missing_parameters": missing if missing else None,
                "sla_template": template.sla_template,
                "priority": template.priority,
            }

    async def list_templates(
        self,
        category: Optional[str] = None,
        intent_type: Optional[str] = None,
        is_public: Optional[bool] = None,
        author: Optional[str] = None,
        search: Optional[str] = None,
        limit: int = 20,
        offset: int = 0,
    ) -> List[dict]:
        async with async_session_maker() as session:
            query = select(IntentTemplate)
            conditions = []
            if category is not None:
                conditions.append(IntentTemplate.category == category)
            if intent_type is not None:
                conditions.append(IntentTemplate.intent_type == intent_type)
            if is_public is not None:
                conditions.append(IntentTemplate.is_public == is_public)
            if author is not None:
                conditions.append(IntentTemplate.author == author)
            if search is not None:
                conditions.append(
                    or_(
                        IntentTemplate.name.contains(search),
                        IntentTemplate.description.contains(search),
                    )
                )
            if conditions:
                query = query.where(*conditions)
            query = query.order_by(IntentTemplate.usage_count.desc(), IntentTemplate.created_at.desc())
            query = query.offset(offset).limit(limit)
            result = await session.execute(query)
            templates = result.scalars().all()
            return [_template_to_dict(t) for t in templates]

    async def get_template(self, template_id: str) -> Optional[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentTemplate).where(IntentTemplate.template_id == template_id)
            )
            template = result.scalar_one_or_none()
            if not template:
                return None
            return _template_to_dict(template)

    async def update_template(self, template_id: str, **kwargs) -> Optional[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentTemplate).where(IntentTemplate.template_id == template_id)
            )
            template = result.scalar_one_or_none()
            if not template:
                return None
            allowed_fields = [
                "name", "description", "category", "intent_type",
                "template_content", "parameters_schema", "example_values",
                "sla_template", "priority", "is_public", "tags",
            ]
            for field in allowed_fields:
                if field in kwargs:
                    setattr(template, field, kwargs[field])
            if any(f in kwargs for f in allowed_fields):
                template.version = (template.version or 1) + 1
            template.updated_at = datetime.now(timezone.utc)
            await session.commit()
            await session.refresh(template)
            logger.info(f"Updated intent template {template_id}")
            return _template_to_dict(template)

    async def delete_template(self, template_id: str) -> bool:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentTemplate).where(IntentTemplate.template_id == template_id)
            )
            template = result.scalar_one_or_none()
            if not template:
                return False
            await session.delete(template)
            await session.commit()
            logger.info(f"Deleted intent template {template_id}")
            return True

    async def rate_template(self, template_id: str, rating: float) -> Optional[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentTemplate).where(IntentTemplate.template_id == template_id)
            )
            template = result.scalar_one_or_none()
            if not template:
                return None
            old_rating = template.rating or 0.0
            old_count = template.rating_count or 0
            new_count = old_count + 1
            new_rating = (old_rating * old_count + rating) / new_count
            template.rating = round(new_rating, 2)
            template.rating_count = new_count
            await session.commit()
            await session.refresh(template)
            return _template_to_dict(template)

    async def increment_usage(self, template_id: str) -> None:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentTemplate).where(IntentTemplate.template_id == template_id)
            )
            template = result.scalar_one_or_none()
            if template:
                template.usage_count = (template.usage_count or 0) + 1
                await session.commit()

    async def get_popular_templates(self, limit: int = 10) -> List[dict]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentTemplate)
                .where(IntentTemplate.is_public == True)
                .order_by(IntentTemplate.usage_count.desc(), IntentTemplate.rating.desc())
                .limit(limit)
            )
            templates = result.scalars().all()
            return [_template_to_dict(t) for t in templates]

    async def get_categories(self) -> List[str]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentTemplate.category).distinct()
            )
            return [row[0] for row in result.all()]

    async def clone_template(self, template_id: str, new_author: str) -> Optional[IntentTemplate]:
        async with async_session_maker() as session:
            result = await session.execute(
                select(IntentTemplate).where(IntentTemplate.template_id == template_id)
            )
            original = result.scalar_one_or_none()
            if not original:
                return None
            new_template_id = _generate_template_id()
            cloned = IntentTemplate(
                template_id=new_template_id,
                name=original.name,
                description=original.description,
                category=original.category,
                intent_type=original.intent_type,
                template_content=original.template_content,
                parameters_schema=original.parameters_schema,
                example_values=original.example_values,
                sla_template=original.sla_template,
                priority=original.priority,
                is_public=False,
                author=new_author,
                usage_count=0,
                rating=0.0,
                rating_count=0,
                tags=original.tags,
                version=1,
            )
            session.add(cloned)
            await session.commit()
            await session.refresh(cloned)
            logger.info(f"Cloned template {template_id} -> {new_template_id} by {new_author}")
            return cloned


_intent_template_manager: Optional[IntentTemplateManager] = None


def get_intent_template_manager() -> IntentTemplateManager:
    global _intent_template_manager
    if _intent_template_manager is None:
        _intent_template_manager = IntentTemplateManager()
    return _intent_template_manager
