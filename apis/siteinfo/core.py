import re
import requests
from typing import Optional, Dict, Any
from urllib.parse import urljoin, urlparse
import logging

logger = logging.getLogger(__name__)

API_ID = 2


def validate_url(url: str) -> str:
    """验证和标准化URL"""
    if not url:
        return None
    
    # 如果没有协议前缀，默认添加http://
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    
    # 验证URL格式
    try:
        parsed = urlparse(url)
        if not parsed.netloc:
            return None
        return url
    except Exception:
        return None


def fetch_page_content(url: str, max_redirects: int = 5) -> Dict[str, Any]:
    """
    获取网页内容，处理重定向
    
    Args:
        url: 目标URL
        max_redirects: 最大重定向次数
        
    Returns:
        包含状态码、内容和最终URL的字典
    """
    session = requests.Session()
    session.headers.update({
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    })
    
    try:
        response = session.get(
            url,
            timeout=30,
            allow_redirects=True,
            verify=False  # 不验证SSL证书，类似PHP代码
        )
        
        return {
            'httpcode': response.status_code,
            'content': response.text,
            'final_url': response.url,
            'encoding': response.encoding or 'utf-8'
        }
        
    except requests.exceptions.Timeout:
        return {
            'httpcode': 408,
            'content': '',
            'final_url': url,
            'error': '请求超时'
        }
    except requests.exceptions.ConnectionError:
        return {
            'httpcode': 0,
            'content': '',
            'final_url': url,
            'error': '连接失败'
        }
    except Exception as e:
        logger.error(f"获取网页内容失败: {e}")
        return {
            'httpcode': 500,
            'content': '',
            'final_url': url,
            'error': str(e)
        }


def extract_meta_info(html_content: str) -> Dict[str, Optional[str]]:
    """
    从HTML内容中提取meta信息
    
    Args:
        html_content: HTML内容
        
    Returns:
        包含title、description、keywords的字典
    """
    result = {
        'title': None,
        'description': None,
        'keywords': None
    }
    
    if not html_content:
        return result
    
    try:
        # 提取title
        title_match = re.search(r'<title[^>]*>(.*?)</title>', html_content, re.IGNORECASE | re.DOTALL)
        if title_match:
            result['title'] = title_match.group(1).strip()
        
        # 提取description
        desc_patterns = [
            r'<meta\s+name=["\']description["\']\s+content=["\']([^"\']*)["\']',
            r'<meta\s+content=["\']([^"\']*)["\'][^>]*name=["\']description["\']'
        ]
        for pattern in desc_patterns:
            desc_match = re.search(pattern, html_content, re.IGNORECASE)
            if desc_match:
                result['description'] = desc_match.group(1).strip()
                break
        
        # 提取keywords
        keywords_patterns = [
            r'<meta\s+name=["\']keywords["\']\s+content=["\']([^"\']*)["\']',
            r'<meta\s+content=["\']([^"\']*)["\'][^>]*name=["\']keywords["\']'
        ]
        for pattern in keywords_patterns:
            keywords_match = re.search(pattern, html_content, re.IGNORECASE)
            if keywords_match:
                result['keywords'] = keywords_match.group(1).strip()
                break
                
    except Exception as e:
        logger.error(f"解析HTML meta信息失败: {e}")
    
    return result


def get_site_info(url: str) -> Dict[str, Any]:
    """
    获取网站信息的主函数
    
    Args:
        url: 目标网站URL
        
    Returns:
        包含网站信息的字典
    """
    # 验证URL
    validated_url = validate_url(url)
    if not validated_url:
        return {
            'code': 201,
            'msg': '无效的URL格式'
        }
    
    # 获取网页内容
    page_data = fetch_page_content(validated_url)
    
    # 检查HTTP状态码
    if page_data['httpcode'] == 0:
        return {
            'code': 202,
            'msg': page_data.get('error', '连接失败')
        }
    elif page_data['httpcode'] >= 400:
        return {
            'code': 202,
            'msg': f'HTTP错误: {page_data["httpcode"]}'
        }
    
    # 提取meta信息
    meta_info = extract_meta_info(page_data['content'])
    
    # 检查是否成功获取到信息
    if not meta_info['title']:
        return {
            'code': 202,
            'msg': '获取失败'
        }
    
    return {
        'code': 200,
        'data': {
            'title': meta_info['title'],
            'description': meta_info['description'],
            'keywords': meta_info['keywords'],
            # 'final_url': page_data['final_url']
        }
    }
