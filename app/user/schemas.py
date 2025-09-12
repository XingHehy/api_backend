from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List, Dict, Any, Union
from datetime import datetime
from enum import Enum

# 枚举类型
class HTTPMethod(str, Enum):
    GET = "GET"
    POST = "POST"
    PUT = "PUT"
    DELETE = "DELETE"
    PATCH = "PATCH"

class ReturnFormat(str, Enum):
    JSON = "JSON"
    XML = "XML"
    TEXT = "TEXT"
    HTML = "HTML"

class PriceType(str, Enum):
    """价格类型枚举"""
    PER_CALL = "per_call"      # 按次付费
    MONTHLY = "monthly"         # 月付
    QUARTERLY = "quarterly"     # 季付
    YEARLY = "yearly"           # 年付
    LIFETIME = "lifetime"       # 终身付费

# 用户相关模式
class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str
    ticket: Optional[str] = None
    randstr: Optional[str] = None

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    password: Optional[str] = None

# 修改密码（需要提供原密码与新密码）
class ChangePassword(BaseModel):
    current_password: str
    new_password: str

class User(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# API相关模式（前台用户可见）
class APIBrief(BaseModel):
    """API简要信息（前台展示）"""
    id: int
    title: str
    alias: str
    description: Optional[str] = None
    endpoint: str
    method: HTTPMethod
    return_format: ReturnFormat
    is_free: bool
    price_type: PriceType
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    call_count: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class APIDetail(BaseModel):
    """API详细信息（前台展示）"""
    id: int
    title: str
    alias: str
    description: Optional[str] = None
    endpoint: str
    method: HTTPMethod
    return_format: ReturnFormat
    
    # 请求参数配置
    parameters: Optional[List[Dict[str, Any]]] = None
    request_example: Optional[str] = None
    request_headers: Optional[Dict[str, str]] = None
    
    # 响应信息
    response_example: Optional[str] = None
    response_schema: Optional[Dict[str, Any]] = None
    
    # 代码示例
    code_examples: Optional[Dict[str, str]] = None
    
    # 错误处理
    error_codes: Optional[Dict[str, str]] = None
    
    # 接口状态
    is_free: bool
    price_type: PriceType
    
    # 分类标签
    category: Optional[str] = None
    tags: Optional[List[str]] = None
    
    # 版本信息
    version: str
    deprecated: bool
    
    # 统计信息
    call_count: int
    
    # 价格选项
    pricing_options: Optional[List[Dict[str, Any]]] = None
    
    class Config:
        from_attributes = True

# 订阅相关模式
class SubscriptionBase(BaseModel):
    api_id: int
    pricing_id: int
    auto_renew: bool = Field(False, description="是否自动续费")

class SubscriptionCreate(SubscriptionBase):
    pass

class Subscription(SubscriptionBase):
    id: int
    user_id: int
    api_key: str
    start_date: datetime
    end_date: datetime
    status: str
    used_calls: int = 0
    remaining_calls: Optional[int] = None
    next_billing_date: Optional[datetime] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# 订单相关模式
class OrderBase(BaseModel):
    api_id: int
    pricing_id: int
    quantity: int = Field(1, ge=1, description="购买数量")

class OrderCreate(OrderBase):
    pass

class OrderUpdate(BaseModel):
    status: Optional[str] = None
    payment_status: Optional[str] = None

class Order(OrderBase):
    id: int
    user_id: int
    order_no: str
    amount: float
    status: str
    payment_method: Optional[str] = None
    payment_status: str
    remark: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    paid_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# 认证相关模式
class Token(BaseModel):
    access_token: str
    token_type: str

class TokenData(BaseModel):
    username: Optional[str] = None

class Login(BaseModel):
    username: str
    password: str
    ticket: Optional[str] = None
    randstr: Optional[str] = None

# 响应模式
class ResponseModel(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

class ErrorResponseModel(BaseModel):
    success: bool = False
    message: str
    error_code: str
    status_code: int
    data: Optional[dict] = None

class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    skip: int
    limit: int

# API搜索和过滤模式
class APISearch(BaseModel):
    keyword: Optional[str] = Field(None, description="搜索关键词")
    category: Optional[str] = Field(None, description="分类筛选")
    tags: Optional[List[str]] = Field(None, description="标签筛选")
    method: Optional[HTTPMethod] = Field(None, description="请求方式筛选")
    is_free: Optional[bool] = Field(None, description="是否免费")
    price_type: Optional[PriceType] = Field(None, description="价格类型筛选")
    price_min: Optional[float] = Field(None, description="最低价格")
    price_max: Optional[float] = Field(None, description="最高价格")
    sort_by: str = Field("created_at", description="排序字段")
    sort_order: str = Field("desc", description="排序方向")

# 价格计算模式
class PriceCalculation(BaseModel):
    api_id: int
    pricing_id: int
    quantity: int = 1
    total_price: float
    discount_amount: float = 0.0
    final_price: float
    currency: str = "CNY"
    billing_cycle: Optional[str] = None
    call_limit: Optional[int] = None
    time_limit: Optional[int] = None

# 用户个人资料
class UserProfile(BaseModel):
    id: int
    username: str
    email: EmailStr
    is_active: bool
    balance: float = 0.0  # 账户余额
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    # 统计信息
    total_apis: int = 0
    total_orders: int = 0
    total_subscriptions: int = 0
    
    class Config:
        from_attributes = True

# 用户API调用统计
class UserAPIStats(BaseModel):
    api_id: int
    api_title: str
    total_calls: int
    success_calls: int
    error_calls: int
    success_rate: float
    last_called: Optional[datetime] = None
