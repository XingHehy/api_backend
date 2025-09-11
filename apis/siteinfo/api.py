"""
SiteInfo API - 网站信息获取API（仅路由层）
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from typing import Optional
import logging
from app.utils.api_recorder import verify_and_record_api_call
from .core import get_site_info, API_ID

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/siteinfo", tags=["SiteInfo API"])

@router.get("/")
async def get_site_information(
    request: Request,
    url: str = Query(..., description="要获取信息的网站URL")
):
    """
    获取网站信息
    
    参数:
    - url: 目标网站的URL（必填）
    
    返回信息:
    - title: 网站标题
    - description: 网站描述
    - keywords: 网站关键词
    - final_url: 最终URL（处理重定向后）
    
    状态码:
    - 200: 成功获取网站信息
    - 201: 缺少参数
    - 202: 获取失败（无效URL、连接失败等）
    """
    
    try:
        # 验证API密钥并记录调用（支持免费API）
        subscription = verify_and_record_api_call(api_id=API_ID, request=request)
        
        # 检查URL参数
        if not url or not url.strip():
            return JSONResponse(
                status_code=200,
                content={
                    "code": 201,
                    "msg": "缺少参数"
                }
            )
        
        # 获取网站信息
        site_data = get_site_info(url.strip())
        
        return JSONResponse(
            status_code=200,
            content=site_data
        )
            
    except HTTPException as e:
        # API密钥验证失败不统计，直接抛出异常
        raise
    except Exception as e:
        logger.error(f"SiteInfo API调用失败: {e}")
        return JSONResponse(
            status_code=200,
            content={
                "code": 202,
                "msg": "获取失败"
            }
        )
