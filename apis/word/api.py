"""
Word API - 词典查询（仅路由层）
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional
import logging
from app.utils.api_recorder import verify_and_record_api_call
from .core import query_unipus_word, API_ID

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/word", tags=["Word API"])


@router.get("/")
async def search_word(
    request: Request,
    word: Optional[str] = Query(None, description="要查询的单词")
):
    try:
        # 验证API密钥并记录调用（若为免费API则只统计，不校验密钥）
        verify_and_record_api_call(api_id=API_ID, request=request)

        result = query_unipus_word(word or "")
        code = (result or {}).get("code", 500)
        status = 200 if code in (200, 201) else 500
        return JSONResponse(status_code=status, content=result or {"code":500, "list":None, "msg":"服务异常"})

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Word API 调用失败: {e}")
        raise HTTPException(status_code=500, detail="查询失败")


