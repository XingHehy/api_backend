from fastapi import FastAPI, Depends, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from app.database import init_db, health_check as db_health_check
from app.admin.api import router as admin_router
from app.user.api import router as user_router
from app.index.api import router as index_router
from apis.bing.api import router as bing_router
from apis.ip.api import router as ip_router
from apis.yiyan.api import router as yiyan_router
from apis.siteinfo.api import router as siteinfo_router
from apis.tcaptcha.api import router as tcaptcha_router
from apis.wyy_music.api import router as wyy_music_router
from app.config import config
import logging
import os
from datetime import datetime

# 配置日志
app_config = config.get_app_config()
log_config = config.get('app.logging', {})
log_level = log_config.get('level', 'INFO')
log_file = log_config.get('file', 'logs/app.log')
log_dir = os.path.dirname(log_file)

# 确保日志目录存在
os.makedirs(log_dir, exist_ok=True)

logging.basicConfig(
    level=getattr(logging, log_level.upper()),
    format=log_config.get('format', '%(asctime)s - %(name)s - %(levelname)s - %(message)s'),
    handlers=[
        logging.FileHandler(log_file, encoding='utf-8'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期管理"""
    # 启动事件
    try:
        # 初始化数据库
        init_db()
        logger.info("应用启动成功")
    except Exception as e:
        logger.error(f"应用启动失败: {e}")
        raise
    
    yield
    
    # 关闭事件
    logger.info("应用正在关闭...")

# 创建FastAPI应用
app = FastAPI(
    title=app_config.get('name', 'API管理系统'),
    description="前后端分离的API接口管理系统，支持多种付费模式",
    version=app_config.get('version', '1.0.0'),
    # docs_url="/docs",
    # redoc_url="/redoc",
    lifespan=lifespan
)

# 配置CORS
cors_origins = config.get('app.security.cors_origins', ["*"])
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
upload_dir = config.get('app.upload.upload_dir', 'uploads')
if os.path.exists(upload_dir):
    app.mount("/uploads", StaticFiles(directory=upload_dir), name="uploads")

# 注册路由
# 系统接口使用 /v/xxx
app.include_router(admin_router, prefix="/v/admin", tags=["后台管理"])
app.include_router(user_router, prefix="/v/user", tags=["前台用户"])
app.include_router(index_router, prefix="/v/index", tags=["首页"])

# 第三方/对外开放 API 使用 /api/xxx
app.include_router(bing_router, prefix="/api", tags=["API"])
app.include_router(ip_router, prefix="/api", tags=["API"])
app.include_router(yiyan_router, prefix="/api", tags=["API"])
app.include_router(siteinfo_router, prefix="/api", tags=["API"])
app.include_router(tcaptcha_router, prefix="/api", tags=["API"])
app.include_router(wyy_music_router, prefix="/api", tags=["API"])

# 全局异常处理器
@app.exception_handler(HTTPException)
async def http_exception_handler(request: Request, exc: HTTPException):
    """HTTP异常处理器"""
    error_code = "HTTP_ERROR"
    if exc.status_code == 401:
        error_code = "UNAUTHORIZED"
    elif exc.status_code == 403:
        error_code = "FORBIDDEN"
    elif exc.status_code == 404:
        error_code = "NOT_FOUND"
    elif exc.status_code == 422:
        error_code = "VALIDATION_ERROR"
    
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "success": False,
            "error_code": error_code,
            "message": exc.detail,
            "status_code": exc.status_code
        }
    )

@app.exception_handler(Exception)
async def general_exception_handler(request: Request, exc: Exception):
    """通用异常处理器"""
    logger.error(f"未处理的异常: {exc}")
    return JSONResponse(
        status_code=500,
        content={
            "success": False,
            "error_code": "INTERNAL_SERVER_ERROR",
            "message": "内部服务器错误",
            "status_code": 500
        }
    )

@app.get("/")
async def root():
    """根路径"""
    return {
        "message": app_config.get('name', 'API管理系统'),
        "version": app_config.get('version', '1.0.0'),
        "description": "专业的API接口管理平台",
        "docs": "/docs",
        "admin": "/v/admin",
        "user": "/v/user",
        "index": "/v/index",
        "features": [
            "支持多种付费模式：按次付费、月付、季付、年付、终身付费",
            "详细的API参数配置和验证",
            "完整的用户管理和权限控制",
            "Redis缓存支持",
            "前后端分离架构"
        ]
    }

if __name__ == "__main__":
    import uvicorn
    
    host = app_config.get('host', '0.0.0.0')
    port = app_config.get('port', 8000)
    debug = app_config.get('debug', False)
    
    uvicorn.run(
        "web:app",
        host=host,
        port=port,
        reload=debug,
        log_level=log_level.lower()
    )
