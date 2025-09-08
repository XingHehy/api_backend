import re
import requests
from typing import Optional

API_ID = 1


def get_bing_wallpaper_url() -> Optional[str]:
    """获取必应每日壁纸URL"""
    try:
        url = "http://cn.bing.com/HPImageArchive.aspx?idx=0&n=1"
        response = requests.get(url, timeout=10)
        response.raise_for_status()

        content = response.text
        pattern = r"<url>(.+?)</url>"
        match = re.search(pattern, content, re.IGNORECASE | re.DOTALL)

        if match:
            img_path = match.group(1)
            return f"http://cn.bing.com{img_path}"

        return None
    except Exception:
        return None


