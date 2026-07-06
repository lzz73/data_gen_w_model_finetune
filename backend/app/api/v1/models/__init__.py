"""
Model API Router
"""
import uuid
import logging
import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update

from app.core.database import get_db
from app.api.response import ApiResponse
from app.models.models import ModelConfig
from app.schemas.model import ModelCreate, ModelUpdate, ModelResponse

router = APIRouter()
logger = logging.getLogger(__name__)

VALID_MODEL_TYPES = {"chat", "vlm", "embedding", "rerank"}


def normalize_model_type(model_type: str | None, model_name: str | None) -> str:
    """Normalize model type, with keyword fallback for legacy records."""
    if model_type in VALID_MODEL_TYPES and model_type != "chat":
        return model_type

    normalized_name = (model_name or "").strip().lower()

    rerank_keywords = ("rerank", "bce-reranker", "gte-rerank")
    embedding_keywords = (
        "embedding",
        "embed",
        "text-embedding",
        "bge-",
        "bge_m3",
        "gte-",
        "m3e",
        "e5-",
        "jina-embeddings",
    )
    vlm_keywords = ("vl", "vision", "visual", "multimodal", "qwen-vl", "gpt-4o")

    if any(keyword in normalized_name for keyword in rerank_keywords):
        return "rerank"
    if any(keyword in normalized_name for keyword in embedding_keywords):
        return "embedding"
    if any(keyword in normalized_name for keyword in vlm_keywords):
        return "vlm"
    return model_type if model_type in VALID_MODEL_TYPES else "chat"


async def test_model_connection(model: ModelConfig) -> dict:
    """Test model connection by calling the API"""
    if not model.api_key:
        return {"success": False, "message": "API Key is missing"}

    api_base = model.api_base or ""
    provider = model.provider
    model_name = model.model_name
    model_type = normalize_model_type(model.model_type, model_name)
    api_key = model.api_key

    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient(timeout=60.0, trust_env=False) as client:
            if model_type in {"chat", "vlm"} and provider in {"openai", "ali"}:
                # OpenAI compatible API test
                url = f"{api_base.rstrip('/')}/chat/completions"
                logger.info(f"[模型连接测试] provider={provider}, model={model_name}, type={model_type}, url={url}")
                response = await client.post(
                    url,
                    headers=headers,
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": "Hi"}],
                        "max_tokens": 5
                    }
                )
            elif model_type in {"chat", "vlm"} and provider == "minimax":
                # MiniMax API test
                url = f"{api_base.rstrip('/')}/chat/completions_v2"
                logger.info(f"[模型连接测试] provider={provider}, model={model_name}, type={model_type}, url={url}")
                response = await client.post(
                    url,
                    headers={
                        **headers,
                        "Authorization": f"Bearer {api_key}"
                    },
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": "Hi"}]
                    }
                )
            elif model_type in {"chat", "vlm"} and provider == "glm":
                # GLM API test
                url = f"{api_base.rstrip('/')}/chat/completions"
                logger.info(f"[模型连接测试] provider={provider}, model={model_name}, type={model_type}, url={url}")
                response = await client.post(
                    url,
                    headers=headers,
                    json={
                        "model": model_name,
                        "messages": [{"role": "user", "content": "Hi"}]
                    }
                )
            elif model_type == "embedding" and provider in {"openai", "ali", "glm"}:
                url = f"{api_base.rstrip('/')}/embeddings"
                logger.info(f"[模型连接测试] provider={provider}, model={model_name}, type={model_type}, url={url}")
                response = await client.post(
                    url,
                    headers=headers,
                    json={
                        "model": model_name,
                        "input": "test"
                    }
                )
            elif model_type == "embedding" and provider == "minimax":
                return {"success": False, "message": "MiniMax embedding 自动测试暂未接入，请手动确认端点与模型"}
            elif model_type == "rerank":
                return {"success": False, "message": "Rerank 自动测试暂未接入，请先保存配置并在实际流程中验证"}
            else:
                return {"success": False, "message": f"Unsupported provider/type: {provider}/{model_type}"}

            logger.info(f"[模型连接测试] response.status_code={response.status_code}")
            if response.status_code == 200:
                return {"success": True, "message": "Connection successful"}
            else:
                return {"success": False, "message": f"API error: {response.status_code} - {response.text[:100]}"}

    except httpx.TimeoutException:
        logger.error(f"[模型连接测试] Timeout - provider={provider}, model={model_name}, url={api_base}")
        return {"success": False, "message": "Connection timeout"}
    except Exception as e:
        logger.error(f"[模型连接测试] Exception - provider={provider}, model={model_name}, error={str(e)}")
        return {"success": False, "message": f"Connection failed: {str(e)}"}


# Helper to convert string to UUID
def parse_uuid(id_str: str) -> uuid.UUID:
    """Parse string to UUID"""
    try:
        return uuid.UUID(id_str)
    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid UUID format")


@router.get("", response_model=ApiResponse)
async def list_models(db: AsyncSession = Depends(get_db)):
    """Get all models"""
    result = await db.execute(
        select(ModelConfig).where(ModelConfig.project_id == None)  # noqa: E711
    )
    models = result.scalars().all()
    # Convert to Pydantic schema
    model_responses = [ModelResponse.model_validate(m) for m in models]
    return ApiResponse(data=model_responses)


@router.post("", response_model=ApiResponse)
async def create_model(model: ModelCreate, db: AsyncSession = Depends(get_db)):
    """Create a new model"""
    # If setting as default, unset other defaults first
    if model.is_default == "true":
        await db.execute(
            update(ModelConfig)
            .where(ModelConfig.project_id == None)  # noqa: E711
            .values(is_default="false")
        )

    # 自动补全 api_base 协议
    api_base = model.api_base or ""
    if api_base and not api_base.startswith(("http://", "https://")):
        api_base = f"https://{api_base}"

    db_model = ModelConfig(
        provider=model.provider,
        model_type=model.model_type,
        model_name=model.model_name,
        api_key=model.api_key,
        api_base=api_base,
        is_default=model.is_default,
        project_id=None  # Global model config
    )
    db.add(db_model)
    await db.commit()
    await db.refresh(db_model)
    # Convert to Pydantic schema
    response = ModelResponse.model_validate(db_model)
    return ApiResponse(data=response)


@router.get("/{model_id}", response_model=ApiResponse)
async def get_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """Get a model by ID"""
    model_uuid = parse_uuid(model_id)
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_uuid,
            ModelConfig.project_id == None  # noqa: E711
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")
    response = ModelResponse.model_validate(model)
    return ApiResponse(data=response)


@router.put("/{model_id}", response_model=ApiResponse)
async def update_model(model_id: str, model_update: ModelUpdate, db: AsyncSession = Depends(get_db)):
    """Update a model"""
    model_uuid = parse_uuid(model_id)
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_uuid,
            ModelConfig.project_id == None  # noqa: E711
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # If setting as default, unset other defaults first
    if model_update.is_default == "true":
        await db.execute(
            update(ModelConfig)
            .where(
                ModelConfig.project_id == None,  # noqa: E711
                ModelConfig.id != model_uuid
            )
            .values(is_default="false")
        )

    update_data = model_update.model_dump(exclude_unset=True)

    # 自动补全 api_base 协议
    if "api_base" in update_data and update_data["api_base"]:
        if not update_data["api_base"].startswith(("http://", "https://")):
            update_data["api_base"] = f"https://{update_data['api_base']}"

    for key, value in update_data.items():
        setattr(model, key, value)

    await db.commit()
    await db.refresh(model)
    response = ModelResponse.model_validate(model)
    return ApiResponse(data=response)


@router.delete("/{model_id}", response_model=ApiResponse)
async def delete_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """Delete a model"""
    model_uuid = parse_uuid(model_id)
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_uuid,
            ModelConfig.project_id == None  # noqa: E711
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    await db.delete(model)
    await db.commit()
    return ApiResponse(message="Model deleted successfully")


@router.post("/{model_id}/set-default", response_model=ApiResponse)
async def set_default_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """Set a model as default"""
    model_uuid = parse_uuid(model_id)
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_uuid,
            ModelConfig.project_id == None  # noqa: E711
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # Unset all other defaults
    await db.execute(
        update(ModelConfig)
        .where(
            ModelConfig.project_id == None,  # noqa: E711
            ModelConfig.id != model_uuid
        )
        .values(is_default="false")
    )

    model.is_default = "true"
    await db.commit()
    await db.refresh(model)
    response = ModelResponse.model_validate(model)
    return ApiResponse(data=response)


@router.post("/{model_id}/test", response_model=ApiResponse)
async def test_model(model_id: str, db: AsyncSession = Depends(get_db)):
    """Test model connection"""
    model_uuid = parse_uuid(model_id)
    result = await db.execute(
        select(ModelConfig).where(
            ModelConfig.id == model_uuid,
            ModelConfig.project_id == None  # noqa: E711
        )
    )
    model = result.scalar_one_or_none()
    if not model:
        raise HTTPException(status_code=404, detail="Model not found")

    # Test the connection
    test_result = await test_model_connection(model)

    # Save connection status to database
    model.model_type = normalize_model_type(model.model_type, model.model_name)
    model.connection_status = "connected" if test_result["success"] else "disconnected"
    await db.commit()
    await db.refresh(model)

    # Return updated model
    response = ModelResponse.model_validate(model)
    return ApiResponse(data={"test_result": test_result, "model": response})
