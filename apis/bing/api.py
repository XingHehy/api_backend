"""
Bing API - 获取必应每日壁纸（仅路由层）
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import RedirectResponse, JSONResponse
from typing import Optional
import logging
from app.utils.api_recorder import verify_and_record_api_call
from .core import get_bing_wallpaper_url, API_ID

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/bing", tags=["Bing API"])

@router.get("/")
async def get_bing_wallpaper(
    request: Request,
    type: Optional[str] = Query(None, description="返回类型: img(重定向到图片) 或 json(返回JSON)")
):

    try:
        # 验证API密钥并记录调用 - 从请求中自动提取，验证失败直接抛出异常，不统计
        subscription = verify_and_record_api_call(api_id=API_ID, request=request)
        

        img_url = get_bing_wallpaper_url()

        if type == 'img':
            return RedirectResponse(url=img_url, status_code=302)
        else:
            return JSONResponse(
                status_code=200,
                content={
                    "code": 200,
                    "url": img_url,
                    "msg": "欢迎使用九天API"
                }
            )
            
    except HTTPException as e:
        # API密钥验证失败不统计，直接抛出异常
        raise
    except Exception as e:
        logger.error(f"Bing API调用失败: {e}")
        raise HTTPException(
            status_code=500,
            detail="获取壁纸失败"
        )

