"""
YiYan API - 一言API（仅路由层）
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import PlainTextResponse, JSONResponse
from typing import Optional
import logging
from app.utils.api_recorder import verify_and_record_api_call
from .core import format_hitokoto_response, API_ID

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/yiyan", tags=["YiYan API"])

@router.get("/")
async def get_hitokoto(
    request: Request,
    type: Optional[str] = Query(None, description="返回类型: text(纯文本) 或 js(JS函数) 或 json(JSON格式，默认)")
):
    """
    获取一言
    
    参数:
    - type: 返回类型
      - text: 返回纯文本
      - js: 返回JavaScript函数
      - json或空: 返回JSON格式（默认）
    """
    
    try:
        # 验证API密钥并记录调用 - 从请求中自动提取，验证失败直接抛出异常，不统计
        subscription = verify_and_record_api_call(api_id=API_ID, request=request)
        
        # 获取一言数据
        hitokoto_data = format_hitokoto_response(type or 'json')
        
        if not hitokoto_data or hitokoto_data.get('code') == 500:
            raise HTTPException(
                status_code=500,
                detail="获取一言失败"
            )
        
        # 根据type参数返回不同格式
        if type == 'text':
            return PlainTextResponse(
                content=hitokoto_data['content'],
                status_code=200
            )
        elif type == 'js':
            return PlainTextResponse(
                content=hitokoto_data['content'],
                status_code=200,
                media_type="application/javascript"
            )
        else:
            # 默认返回JSON格式
            return JSONResponse(
                status_code=200,
                content=hitokoto_data
            )
            
    except HTTPException as e:
        # API密钥验证失败不统计，直接抛出异常
        raise
    except Exception as e:
        logger.error(f"YiYan API调用失败: {e}")
        raise HTTPException(
            status_code=500,
            detail="获取一言失败"
        )
