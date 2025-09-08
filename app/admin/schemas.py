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

class ParameterType(str, Enum):
    """参数类型枚举"""
    STRING = "string"
    INTEGER = "integer"
    FLOAT = "float"
    BOOLEAN = "boolean"
    ARRAY = "array"
    OBJECT = "object"
    FILE = "file"

# 用户相关模式
class UserBase(BaseModel):
    username: str
    email: EmailStr

class UserCreate(UserBase):
    password: str

class UserUpdate(BaseModel):
    username: Optional[str] = None
    email: Optional[EmailStr] = None
    is_active: Optional[bool] = None

class User(UserBase):
    id: int
    is_active: bool
    is_admin: bool
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# 管理端用户创建请求
class AdminUserCreate(UserCreate):
    is_admin: Optional[bool] = None
    is_active: Optional[bool] = None
    balance: Optional[float] = None

# API参数相关模式
class APIParameterBase(BaseModel):
    name: str = Field(..., description="参数名")
    required: bool = Field(False, description="是否必填")
    param_type: ParameterType = Field(..., description="参数类型")
    description: Optional[str] = Field(None, description="参数说明")
    
    # 验证规则
    min_length: Optional[int] = Field(None, description="最小长度")
    max_length: Optional[int] = Field(None, description="最大长度")
    min_value: Optional[float] = Field(None, description="最小值")
    max_value: Optional[float] = Field(None, description="最大值")
    pattern: Optional[str] = Field(None, description="正则表达式")
    enum_values: Optional[List[Any]] = Field(None, description="枚举值列表")
    default_value: Optional[str] = Field(None, description="默认值")
    
    # 示例
    example: Optional[str] = Field(None, description="参数示例")
    sort_order: int = Field(0, description="排序顺序")

class APIParameterCreate(APIParameterBase):
    pass

class APIParameter(APIParameterBase):
    id: int
    api_id: int
    
    class Config:
        from_attributes = True

# API价格相关模式已删除，价格信息现在直接存储在 API 模型中

# API相关模式
class APIBase(BaseModel):
    title: str = Field(..., description="接口标题（中文）")
    alias: str = Field(..., description="别名（英文标识，唯一）")
    description: Optional[str] = Field(None, description="简介说明")
    
    # 接口配置
    endpoint: str = Field(..., description="接口地址")
    method: HTTPMethod = Field(..., description="请求方式")
    return_format: ReturnFormat = Field(ReturnFormat.JSON, description="返回格式")
    
    # 请求参数配置
    request_params: Optional[str] = Field(None, description="请求参数列表（JSON字符串）")
    request_example: Optional[str] = Field(None, description="请求示例")
    request_headers: Optional[str] = Field(None, description="请求头配置（JSON字符串）")
    
    # 响应信息
    response_example: Optional[str] = Field(None, description="返回示例")
    
    # 代码示例
    code_examples: Optional[str] = Field(None, description="代码示例（JSON字符串）")
    
    # 错误处理
    error_codes: Optional[str] = Field(None, description="错误代码及说明（JSON字符串）")
    
    # 接口状态
    is_active: bool = Field(True, description="是否启用")
    is_public: bool = Field(True, description="是否公开")
    is_free: bool = Field(True, description="是否免费")
    
    
    # 分类标签
    category_id: Optional[int] = Field(None, description="接口分类ID")
    tags: Optional[str] = Field(None, description="标签列表（JSON字符串）")
    
    # 价格配置 - 支持多种付费模式
    price_config: Optional[str] = Field(None, description="价格配置（JSON字符串）")
    price_type: PriceType = Field(PriceType.PER_CALL, description="主要价格类型")
    
    # 版本信息
    version: str = Field("1.0.0", description="接口版本")
    deprecated: bool = Field(False, description="是否已废弃")

class APICreate(APIBase):
    pass

class APIUpdate(BaseModel):
    title: Optional[str] = None
    alias: Optional[str] = None
    description: Optional[str] = None
    endpoint: Optional[str] = None
    method: Optional[HTTPMethod] = None
    return_format: Optional[ReturnFormat] = None
    request_params: Optional[str] = None
    request_example: Optional[str] = None
    request_headers: Optional[str] = None
    response_example: Optional[str] = None
    code_examples: Optional[str] = None
    error_codes: Optional[str] = None
    is_active: Optional[bool] = None
    is_public: Optional[bool] = None
    is_free: Optional[bool] = None
    category_id: Optional[int] = None
    tags: Optional[str] = None
    price_config: Optional[str] = None
    price_type: Optional[PriceType] = None
    version: Optional[str] = None
    deprecated: Optional[bool] = None

class API(APIBase):
    id: int
    call_count: int = 0
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

# 响应模式
class ResponseModel(BaseModel):
    success: bool
    message: str
    data: Optional[dict] = None

class PaginatedResponse(BaseModel):
    items: List[dict]
    total: int
    page: int
    size: int
    pages: int

# 统计信息模式
class APIStats(BaseModel):
    total_apis: int
    active_apis: int
    total_calls: int
    total_users: int
    total_orders: int
    total_revenue: float
    popular_categories: List[Dict[str, Any]]
    recent_activities: List[Dict[str, Any]]

# 系统日志模式
class SystemLog(BaseModel):
    id: int
    actor_id: Optional[int] = None
    actor_type: str = "system"
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None
    created_at: datetime

    class Config:
        from_attributes = True

class SystemLogCreate(BaseModel):
    actor_id: Optional[int] = None
    actor_type: str = "system"
    action: str
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    description: Optional[str] = None
    metadata: Optional[Dict[str, Any]] = None
    ip: Optional[str] = None
    user_agent: Optional[str] = None

class SystemLogQuery(BaseModel):
    actor_id: Optional[int] = None
    actor_type: Optional[str] = None
    action: Optional[str] = None
    resource_type: Optional[str] = None
    resource_id: Optional[int] = None
    keyword: Optional[str] = None

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

# 分类相关模式
class CategoryBase(BaseModel):
    name: str = Field(..., description="分类名称")
    description: Optional[str] = Field(None, description="分类描述")
    sort_order: int = Field(0, description="排序顺序")
    is_active: bool = Field(True, description="是否激活")

class CategoryCreate(CategoryBase):
    pass

class CategoryUpdate(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    sort_order: Optional[int] = None
    is_active: Optional[bool] = None

class Category(CategoryBase):
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True

class CategoryWithCount(Category):
    api_count: int = 0
    
    class Config:
        from_attributes = True

# 订单相关模式
class OrderDetail(BaseModel):
    id: int
    order_no: str
    user_id: int
    user_username: str
    user_email: str
    api_id: int
    api_title: str
    api_alias: str
    amount: float
    quantity: Optional[int] = 1
    status: str
    payment_method: Optional[str] = None
    payment_status: Optional[str] = None
    paid_at: Optional[datetime] = None
    remark: Optional[str] = None
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True

class OrderStatusUpdate(BaseModel):
    status: str = Field(..., description="订单状态")

class OrderExportParams(BaseModel):
    status: Optional[str] = Field(None, description="订单状态筛选")
    start_date: Optional[str] = Field(None, description="开始日期")
    end_date: Optional[str] = Field(None, description="结束日期")

# 网站配置相关模式
class WebConfigBase(BaseModel):
    k: str = Field(..., description="配置键")
    v: str = Field(..., description="配置值")

class WebConfigCreate(WebConfigBase):
    pass

class WebConfigUpdate(BaseModel):
    v: Optional[str] = Field(None, description="配置值")

class WebConfig(WebConfigBase):
    id: int
    created_at: datetime
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True