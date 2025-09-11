"""
WyyMusic API - 网易云音乐直链解析
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional
import logging
from app.utils.api_recorder import verify_and_record_api_call
from .core import resolve_music_direct_url, API_ID

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/wyy_music", tags=["WyyMusic API"])

@router.get("/")
async def get_music_url(
    request: Request,
    id: str = Query(None, description="网易云歌曲ID")
):
    """
    根据网易云歌曲ID解析直链
    - 成功: { code:200, music_id, src, msg }
    - 失败: { code:201/202/500, music_id, src:null, msg }
    """
    try:
        # 支持免费API：内部函数会判断是否免费，免费则不需要apiKey
        verify_and_record_api_call(api_id=API_ID, request=request)

        result = resolve_music_direct_url(id)
        return JSONResponse(status_code=200, content=result)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"WyyMusic API调用失败: {e}")
        return JSONResponse(status_code=200, content={
            'code': 500,
            'music_id': id,
            'src': None,
            'msg': '解析失败'
        })
