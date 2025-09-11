import random
import os
from typing import Optional, Dict, Any

API_ID = 3


def get_hitokoto_text() -> Optional[Dict[str, Any]]:
    """获取一言文本"""
    try:
        # 获取hitokoto.txt文件路径
        current_dir = os.path.dirname(os.path.abspath(__file__))
        filename = os.path.join(current_dir, 'hitokoto.txt')
        
        if not os.path.exists(filename):
            raise FileNotFoundError(f'{filename} 数据文件不存在')
        
        # 读取整个数据文件
        with open(filename, 'r', encoding='utf-8') as f:
            content = f.read()
        
        # 按换行符分割成数组，过滤空行
        lines = [line.strip() for line in content.split('\n') if line.strip()]
        
        if not lines:
            raise ValueError('数据文件为空')
        
        # 随机获取一行
        hitokoto = random.choice(lines)
        
        return {
            'code': 200,
            'text': hitokoto,
            'msg': '欢迎使用九天API'
        }
        
    except Exception as e:
        print(f"获取一言失败: {e}")
        return None


def format_hitokoto_response(response_type: str = 'json') -> Dict[str, Any]:
    """格式化一言响应"""
    hitokoto_data = get_hitokoto_text()
    
    if not hitokoto_data:
        return {
            'code': 500,
            'text': '',
            'msg': '获取一言失败'
        }
    
    if response_type == 'text':
        return {'type': 'text', 'content': hitokoto_data['text']}
    elif response_type == 'js':
        js_content = f'function hitokoto(){{document.write("{hitokoto_data["text"]}");}}'
        return {'type': 'js', 'content': js_content}
    else:
        return hitokoto_data
