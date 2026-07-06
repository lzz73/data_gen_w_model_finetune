"""
Database CRUD Operations
数据库通用 CRUD 操作
"""
from typing import Any, Generic, List, Optional, Type, TypeVar
from uuid import UUID
from sqlalchemy import select, func, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload, joinedload

from app.core.exceptions import NotFoundException, DuplicateException
from app.core.logging import LoggerMixin

ModelType = TypeVar("ModelType")


class CRUDBase(Generic[ModelType], LoggerMixin):
    """Base CRUD class with common operations"""

    def __init__(self, model: Type[ModelType]):
        """Initialize CRUD with model"""
        self.model = model

    async def get(
        self,
        db: AsyncSession,
        id: UUID,
        load_relations: Optional[List[str]] = None
    ) -> Optional[ModelType]:
        """Get single record by ID"""
        query = select(self.model).where(self.model.id == id)

        # Load relationships if specified
        if load_relations:
            for relation in load_relations:
                if hasattr(self.model, relation):
                    query = query.options(selectinload(getattr(self.model, relation)))

        result = await db.execute(query)
        return result.scalar_one_or_none()

    async def get_or_raise(
        self,
        db: AsyncSession,
        id: UUID,
        resource_name: str = "Resource",
        load_relations: Optional[List[str]] = None
    ) -> ModelType:
        """Get single record by ID or raise NotFoundException"""
        obj = await self.get(db, id, load_relations)
        if not obj:
            raise NotFoundException(resource_name, id)
        return obj

    async def get_multi(
        self,
        db: AsyncSession,
        skip: int = 0,
        limit: int = 20,
        load_relations: Optional[List[str]] = None,
        filters: Optional[dict] = None,
        order_by: Optional[str] = "created_at",
        descending: bool = True
    ) -> tuple[List[ModelType], int]:
        """Get multiple records with pagination"""
        query = select(self.model)
        count_query = select(func.count()).select_from(self.model)

        # Apply filters
        if filters:
            conditions = []
            for key, value in filters.items():
                if hasattr(self.model, key):
                    conditions.append(getattr(self.model, key) == value)
            if conditions:
                query = query.where(and_(*conditions))
                count_query = count_query.where(and_(*conditions))

        # Load relationships if specified
        if load_relations:
            for relation in load_relations:
                if hasattr(self.model, relation):
                    query = query.options(selectinload(getattr(self.model, relation)))

        # Count total
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0

        # Apply ordering
        if order_by and hasattr(self.model, order_by):
            order_column = getattr(self.model, order_by)
            if descending:
                query = query.order_by(order_column.desc())
            else:
                query = query.order_by(order_column.asc())

        # Apply pagination
        query = query.offset(skip).limit(limit)

        result = await db.execute(query)
        items = result.scalars().all()

        return list(items), total

    async def create(
        self,
        db: AsyncSession,
        obj_in: Any,
        commit: bool = True
    ) -> ModelType:
        """Create new record"""
        obj_data = obj_in.model_dump() if hasattr(obj_in, 'model_dump') else obj_in.dict()
        db_obj = self.model(**obj_data)
        db.add(db_obj)

        if commit:
            await db.commit()
            await db.refresh(db_obj)
            self.log.debug(f"Created {self.model.__name__}: {db_obj.id}")

        return db_obj

    async def update(
        self,
        db: AsyncSession,
        db_obj: ModelType,
        obj_in: Any,
        commit: bool = True
    ) -> ModelType:
        """Update existing record"""
        if hasattr(obj_in, 'model_dump'):
            obj_data = obj_in.model_dump(exclude_unset=True)
        elif hasattr(obj_in, 'dict'):
            obj_data = obj_in.dict(exclude_unset=True)
        else:
            obj_data = obj_in

        for field, value in obj_data.items():
            if hasattr(db_obj, field):
                setattr(db_obj, field, value)

        if commit:
            await db.commit()
            await db.refresh(db_obj)
            self.log.debug(f"Updated {self.model.__name__}: {db_obj.id}")

        return db_obj

    async def delete(
        self,
        db: AsyncSession,
        id: UUID,
        commit: bool = True
    ) -> bool:
        """Delete record by ID"""
        obj = await self.get(db, id)
        if obj:
            await db.delete(obj)
            if commit:
                await db.commit()
            self.log.debug(f"Deleted {self.model.__name__}: {id}")
            return True
        return False

    async def exists(
        self,
        db: AsyncSession,
        filters: dict
    ) -> bool:
        """Check if record exists"""
        query = select(func.count()).select_from(self.model)
        for key, value in filters.items():
            if hasattr(self.model, key):
                query = query.where(getattr(self.model, key) == value)

        result = await db.execute(query)
        count = result.scalar() or 0
        return count > 0
