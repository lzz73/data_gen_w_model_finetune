"""
Evaluation Dataset Schemas
"""
import json
from datetime import datetime
from typing import Optional, Any, Dict, List
from uuid import UUID
from pydantic import BaseModel, ConfigDict, Field, field_validator


class EvalDatasetBase(BaseModel):
    """Base eval dataset schema"""
    name: str = Field(..., min_length=1, max_length=255)
    question_type: Optional[str] = Field("mixed", max_length=50)
    extra_data: Optional[dict] = None


class EvalDatasetCreate(EvalDatasetBase):
    """Eval dataset create schema"""
    pass


class EvalDatasetUpdate(BaseModel):
    """Eval dataset update schema"""
    name: Optional[str] = Field(None, min_length=1, max_length=255)
    question_type: Optional[str] = Field(None, max_length=50)
    extra_data: Optional[dict] = None


class EvalDatasetResponse(EvalDatasetBase):
    """Eval dataset response schema"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: UUID
    status: Optional[str] = "pending"
    question_count: Optional[int] = 0
    created_at: datetime
    updated_at: datetime


class ModelInfo(BaseModel):
    """Model information schema"""
    modelId: Optional[UUID] = None
    modelName: Optional[str] = None
    providerId: Optional[UUID] = None
    providerName: Optional[str] = None


class TaskDetail(BaseModel):
    """Task detail schema"""
    evalDatasetIds: Optional[List[str]] = None
    judgeModelId: Optional[str] = None
    judgeProviderId: Optional[str] = None
    filterOptions: Optional[Dict[str, Any]] = None
    hasSubjectiveQuestions: Optional[bool] = None
    customScoreAnchors: Optional[Dict[str, Any]] = None


class TaskBase(BaseModel):
    """Base task schema"""
    task_type: str = Field(..., max_length=50)
    status: Optional[Any] = "pending"
    language: Optional[str] = "zh-CN"
    total_count: Optional[int] = 0
    completed_count: Optional[int] = 0
    progress: Optional[int] = 0
    note: Optional[str] = None
    model_info: Optional[Dict[str, Any]] = None
    detail: Optional[Dict[str, Any]] = None
    result: Optional[Dict[str, Any]] = None


class TaskResponse(TaskBase):
    """Task response schema"""
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    project_id: Optional[UUID] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    end_time: Optional[str] = None
    error: Optional[str] = None

    @field_validator("detail", "result", "model_info", mode="before")
    @classmethod
    def parse_json_string(cls, v: Any) -> Any:
        """Auto-parse JSON string fields to dict/list.

        ORM model stores detail/result/model_info as Text/JSON,
        but Pydantic v2 from_attributes does NOT auto-parse JSON strings.
        Without this validator, these fields remain as raw strings,
        causing frontend code like `task.result?.created_questions` to
        always return undefined — which is why progress stays at 0.
        """
        if isinstance(v, str):
            try:
                return json.loads(v)
            except (json.JSONDecodeError, ValueError):
                return v
        return v


# Alias for CRUD
EvalDatasetCreateSchema = EvalDatasetCreate
EvalDatasetUpdateSchema = EvalDatasetUpdate


# ============ Helper Methods ============

def validate_task_status(status: Any) -> str:
    if isinstance(status, int):
        status_map = {
            0: "pending",
            1: "running",
            2: "completed",
            3: "stopped",
            4: "failed"
        }
        return status_map.get(status, "unknown")
    elif isinstance(status, str):
        return status.lower()
    else:
        return "unknown"


def parse_task_response(task_dict: Dict[str, Any]) -> Dict[str, Any]:
    import json

    result = {
        "id": task_dict.get("id"),
        "project_id": task_dict.get("project_id"),
        "task_type": task_dict.get("task_type"),
        "status": validate_task_status(task_dict.get("status")),
        "language": task_dict.get("language", "zh-CN"),
        "total_count": task_dict.get("total_count", 0),
        "completed_count": task_dict.get("completed_count", 0),
        "note": task_dict.get("note"),
        "create_at": task_dict.get("create_at"),
        "update_at": task_dict.get("update_at"),
        "end_time": task_dict.get("end_time")
    }

    model_info = task_dict.get("model_info", {})
    if isinstance(model_info, str):
        try:
            model_info = json.loads(model_info)
        except Exception:
            model_info = {}
    result["model_info"] = model_info

    detail = task_dict.get("detail", {})
    if isinstance(detail, str):
        try:
            detail = json.loads(detail)
        except Exception:
            detail = {}
    result["detail"] = detail

    return result


def format_task_response(task_dict: Dict[str, Any]) -> Dict[str, Any]:
    parsed = parse_task_response(task_dict)

    return {
        "id": str(parsed["id"]) if parsed["id"] else None,
        "projectId": str(parsed["project_id"]) if parsed["project_id"] else None,
        "taskType": parsed["task_type"],
        "status": parsed["status"],
        "language": parsed["language"],
        "totalCount": parsed["total_count"],
        "completedCount": parsed["completed_count"],
        "note": parsed["note"],
        "modelInfo": parsed["model_info"],
        "detail": parsed["detail"],
        "createAt": parsed["create_at"].isoformat() if parsed["create_at"] else None,
        "updateAt": parsed["update_at"].isoformat() if parsed["update_at"] else None,
        "endTime": parsed["end_time"].isoformat() if parsed["end_time"] else None
    }
