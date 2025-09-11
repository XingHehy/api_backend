import requests
from typing import Optional, Dict
import logging

logger = logging.getLogger(__name__)

API_ID = 6


def resolve_music_direct_url(song_id: str) -> Dict[str, Optional[str]]:
    """根据网易云音乐song id解析直链。
    - 输入: song_id 字符串
    - 输出: { code, music_id, src, msg }
    规则：
    - 请求 https://music.163.com/song/media/outer/url?id={id}.mp3
    - 跟随/解析重定向，得到最终直链
    - 若直链为 https://music.163.com/404 视为失败（付费或错误ID）
    """
    if not song_id or not str(song_id).strip():
        return {
            'code': 202,
            'music_id': None,
            'src': None,
            'msg': 'id不能为空'
        }

    try:
        url = f"https://music.163.com/song/media/outer/url?id={song_id}.mp3"
        # 只获取最终跳转地址，不下载内容
        resp = requests.get(url, allow_redirects=True, timeout=15)
        final_url = resp.url

        if final_url == "https://music.163.com/404":
            return {
                'code': 201,
                'music_id': song_id,
                'src': None,
                'msg': '获取失败 歌曲id错误或为付费歌曲'
            }

        return {
            'code': 200,
            'music_id': song_id,
            'src': final_url,
            'msg': '获取成功'
        }
    except requests.exceptions.Timeout:
        return {
            'code': 500,
            'music_id': song_id,
            'src': None,
            'msg': '请求超时'
        }
    except Exception as e:
        logger.error(f"解析网易云直链失败: {e}")
        return {
            'code': 500,
            'music_id': song_id,
            'src': None,
            'msg': '解析失败'
        }
