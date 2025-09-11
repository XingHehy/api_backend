import re
import requests
import random
from typing import Optional, Dict, Any
from urllib.parse import quote
import logging

logger = logging.getLogger(__name__)

API_ID = 5  # 腾讯验证码API的ID


def parse_jsonp_response(jsonp_text: str) -> Dict[str, Any]:
    """
    解析JSONP响应
    
    Args:
        jsonp_text: JSONP格式的响应文本
        
    Returns:
        解析后的字典
    """
    if not jsonp_text:
        return {}
    
    try:
        jsonp_text = jsonp_text.strip()
        
        # 如果不是以 [ 或 { 开头，可能是JSONP格式
        if jsonp_text and jsonp_text[0] not in '[{':
            # 找到括号内的JSON部分
            begin = jsonp_text.find('(')
            if begin != -1:
                end = jsonp_text.rfind(')')
                if end != -1:
                    jsonp_text = jsonp_text[begin + 1:end]
        
        # 解析JSON
        import json
        return json.loads(jsonp_text)
        
    except Exception as e:
        logger.error(f"解析JSONP响应失败: {e}")
        return {}


def verify_captcha_ticket(ticket: str, randstr: str) -> int:
    """
    验证腾讯验证码票据
    
    Args:
        ticket: 验证票据
        randstr: 随机字符串
        
    Returns:
        验证结果：1=验证通过，0=验证不通过，-1=接口已失效
    """
    if not ticket or not randstr:
        return 0
    
    try:
        # 构建验证URL（模拟原PHP代码的逻辑）
        random_num = random.randint(111111, 999999)
        url = (
            f"https://cgi.urlsec.qq.com/index.php"
            f"?m=check&a=gw_check&callback=url_query"
            f"&url={quote('https://www.qq.com/')}{random_num}"
            f"&ticket={quote(ticket)}"
            f"&randstr={quote(randstr)}"
        )
        
        # 设置请求头（模拟原PHP代码）
        headers = {
            'Accept': 'application/json',
            'Accept-Language': 'zh-CN,zh;q=0.8',
            'Connection': 'close',
            'Referer': 'https://urlsec.qq.com/check.html',
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/86.0.4240.198 Safari/537.36'
        }
        
        # 发送请求
        response = requests.get(
            url,
            headers=headers,
            timeout=30,
            verify=False  # 不验证SSL证书
        )
        
        if response.status_code != 200:
            logger.error(f"验证码验证请求失败，状态码: {response.status_code}")
            return -1
        
        # 解析响应
        result_data = parse_jsonp_response(response.text)
        
        if not result_data:
            logger.error("解析验证码响应失败")
            return -1
        
        # 根据reCode判断结果
        re_code = result_data.get('reCode')
        
        if re_code == 0:
            # 验证通过
            return 1
        elif re_code == -109:
            # 验证码错误
            return 0
        else:
            # 接口已失效或其他错误
            logger.warning(f"验证码验证失败，reCode: {re_code}")
            return -1
            
    except requests.exceptions.Timeout:
        logger.error("验证码验证请求超时")
        return -1
    except requests.exceptions.RequestException as e:
        logger.error(f"验证码验证请求异常: {e}")
        return -1
    except Exception as e:
        logger.error(f"验证码验证失败: {e}")
        return -1


def check_tencent_captcha(ticket: str, randstr: str) -> Dict[str, Any]:
    """
    检查腾讯验证码的主函数
    
    Args:
        ticket: 验证票据
        randstr: 随机字符串
        
    Returns:
        包含验证结果的字典
    """
    # 检查参数
    if not ticket or not randstr:
        return {
            'code': 400,
            'msg': '参数不能为空',
            'success': False
        }
    
    # 验证票据
    result = verify_captcha_ticket(ticket, randstr)
    
    if result == 1:
        return {
            'code': 200,
            'msg': '验证通过',
            'success': True
        }
    elif result == 0:
        return {
            'code': 400,
            'msg': '验证不通过',
            'success': False
        }
    else:  # result == -1
        return {
            'code': 500,
            'msg': '接口已失效',
            'success': False
        }
