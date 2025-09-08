import ipaddress

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.utils.api_recorder import verify_and_record_api_call  # 复用API密钥验证逻辑
from .core import get_ip_info, API_ID

# -------------------------- 核心API路由 --------------------------
router = APIRouter(prefix="/ip", tags=["IP API"])


@router.get("/")  # 最终请求路径：/ip
async def query_ip(
        request: Request
):
    try:
        # 1. 验证API密钥（从请求中自动提取，失败直接抛出HTTPException）
        verify_and_record_api_call(api_id=API_ID, request=request)

        # 2. 确定查询IP（优先query参数ip，无传参则取访问者IP）
        client_ip = request.headers.get("x-forwarded-for") or \
                    request.headers.get("x-real-ip") or \
                    request.client.host
        ip_param = request.query_params.get("ip")
        query_ip_val = ip_param.strip() if ip_param else client_ip

        # 3. 校验IP格式合法性
        try:
            ipaddress.ip_address(query_ip_val)
        except ValueError:
            raise HTTPException(status_code=400, detail=f"无效IP地址：{query_ip_val}")

        # 4. 解析IP信息并返回结果
        ip_info = get_ip_info(query_ip_val)
        return JSONResponse(
            status_code=200,
            content={
                "code": 200,
                "msg": "IP查询成功（欢迎使用九天API）",
                "data": ip_info
            }
        )

    except HTTPException as e:
        # 已知错误（密钥无效/IP格式错误）直接抛出
        raise
    except Exception as e:
        # 未知错误返回500
        raise HTTPException(
            status_code=500,
            detail=f"IP查询失败：{str(e)}"
        )

 