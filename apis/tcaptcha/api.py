"""
TCaptcha API - 腾讯验证码验证API（仅路由层）
"""
from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import JSONResponse
from fastapi.templating import Jinja2Templates
import os
from typing import Optional
import logging
from app.utils.api_recorder import verify_and_record_api_call
from .core import check_tencent_captcha, API_ID

logger = logging.getLogger(__name__)
templates = Jinja2Templates(directory=os.path.dirname(os.path.abspath(__file__)))

router = APIRouter(prefix="/tcaptcha", tags=["TCaptcha API"])

@router.get("/")
async def verify_tencent_captcha(
    request: Request,
    ticket: str = Query(..., description="腾讯验证码票据"),
    randstr: str = Query(..., description="验证随机字符串")
):
    """
    验证腾讯验证码
    
    参数:
    - ticket: 腾讯验证码票据（必填）
    - randstr: 验证随机字符串（必填）
    
    返回JSON格式：
    {
        "code": 200,
        "msg": "验证通过",
        "success": true
    }
    
    状态码说明:
    - code: 200=验证通过, 400=验证不通过/参数错误, 500=接口失效/系统错误
    - success: true=成功, false=失败
    """
    
    try:
        # 验证API密钥并记录调用（支持免费API）
        subscription = verify_and_record_api_call(api_id=API_ID, request=request)
        
        # 验证腾讯验证码
        result = check_tencent_captcha(ticket, randstr)
        
        return JSONResponse(
            status_code=200,
            content=result
        )
            
    except HTTPException as e:
        # API密钥验证失败不统计，直接抛出异常
        raise
    except Exception as e:
        logger.error(f"TCaptcha API调用失败: {e}")
        return JSONResponse(
            status_code=200,
            content={
                'code': 500,
                'msg': '系统错误',
                'success': False
            }
        )

@router.get("/examples")
async def get_tcaptcha_examples(request: Request):
    """
    腾讯验证码API示例页面（Jinja2模板渲染）
    """
    try:
        return templates.TemplateResponse("example.html", {"request": request, "api": "tcaptcha"})
    except Exception as e:
        logger.error(f"模板渲染失败: {e}")
        # 兜底：简单提示
        return JSONResponse(status_code=500, content={"code": 500, "msg": "示例页面加载失败", "success": False})
