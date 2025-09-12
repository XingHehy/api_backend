import requests
from typing import Any, Dict, Optional

API_ID = 7


def query_unipus_word(name: str, timeout: float = 10.0) -> Optional[Dict[str, Any]]:
    """调用 Unipus 词典检索接口。

    参考 PHP 实现，POST JSON 到
    https://dict.unipus.cn/dict/lexicon/1.1/word-search/search

    返回结构按原接口的 rs.list 字段转换为统一格式：
    - 成功：{"code":200, "list": <list>, "msg":"查询成功"}
    - 失败/无结果：{"code":201, "list": null, "msg":"查询失败"}
    - 异常：{"code":500, "list": null, "msg":"服务异常"}
    """
    if not name or not name.strip():
        return {
            "code": 201,
            "list": None,
            "msg": "查询的单词不能为空"
        }

    url = "https://dict.unipus.cn/dict/lexicon/1.1/word-search/search"
    payload = {"name": name.strip()}

    headers = {
        "accept": "application/json, text/plain, */*",
        "accept-language": "zh-CN,zh;q=0.9,en;q=0.8",
        "cache-control": "no-cache",
        "content-type": "application/json",
        "dnt": "1",
        "origin": "https://u.unipus.cn",
        "pragma": "no-cache",
        "referer": "https://u.unipus.cn/",
        "sec-ch-ua": '"Chromium";v="106", "Google Chrome";v="106", "Not;A=Brand";v="99"',
        "sec-ch-ua-mobile": "?0",
        "sec-ch-ua-platform": '"Windows"',
        "sec-fetch-dest": "empty",
        "sec-fetch-mode": "cors",
        "sec-fetch-site": "same-site",
        "terminal": "pc",
        "user-agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/106.0.0.0 Safari/537.36"
        ),
    }

    try:
        resp = requests.post(url, json=payload, headers=headers, timeout=timeout, verify=True)
        if resp.status_code != 200:
            return {"code": 201, "list": None, "msg": "查询失败"}
        data = resp.json()
        rs = data.get("rs") or {}
        lst = rs.get("list")
        if not lst:
            return {"code": 201, "list": None, "msg": "查询失败"}
        return {"code": 200, "list": lst, "msg": "查询成功"}
    except Exception:
        return {"code": 500, "list": None, "msg": "服务异常"}


