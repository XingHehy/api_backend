import ipaddress
import maxminddb
from pathlib import Path
from typing import Optional, Dict, Any


# -------------------------- MMDB 数据库加载 --------------------------
try:
    BASE_DIR = Path(__file__).parent.resolve()
    DATA_DIR = BASE_DIR / 'GeoLite2'
    city_path = DATA_DIR / 'City.mmdb'
    asn_path = DATA_DIR / 'ASN.mmdb'
    country_path = DATA_DIR / 'Country.mmdb'

    city_reader = maxminddb.open_database(str(city_path))
    asn_reader = maxminddb.open_database(str(asn_path))
    cn_reader = maxminddb.open_database(str(country_path))
except Exception as e:
    raise RuntimeError(f"MMDB数据库加载失败: {e} | 路径: {DATA_DIR}")


# -------------------------- 常量与工具函数 --------------------------
API_ID = 5  # 与其他API区分的唯一ID（确保与订阅配置一致）
lang = ["zh-CN", "en"]

# ASN运营商映射表
asn_map = {
    9812: "东方有线", 9389: "中国长城", 17962: "天威视讯", 17429: "歌华有线", 7497: "科技网",
    24139: "华数", 9801: "中关村", 4538: "教育网", 24151: "CNNIC",
    38019: "中国移动", 139080: "中国移动", 9808: "中国移动", 24400: "中国移动", 134810: "中国移动", 24547: "中国移动",
    56040: "中国移动", 56041: "中国移动", 56042: "中国移动", 56044: "中国移动", 132525: "中国移动", 56046: "中国移动",
    56047: "中国移动", 56048: "中国移动", 59257: "中国移动", 24444: "中国移动", 24445: "中国移动", 137872: "中国移动",
    9231: "中国移动", 58453: "中国移动", 4134: "中国电信", 4812: "中国电信", 23724: "中国电信", 136188: "中国电信",
    137693: "中国电信", 17638: "中国电信", 140553: "中国电信", 4847: "中国电信", 140061: "中国电信", 136195: "中国电信",
    17799: "中国电信", 139018: "中国电信", 134764: "中国电信", 4837: "中国联通", 4808: "中国联通", 134542: "中国联通",
    134543: "中国联通", 59019: "金山云", 135377: "优刻云", 45062: "网易云", 37963: "阿里云", 45102: "阿里云国际",
    45090: "腾讯云", 132203: "腾讯云国际", 55967: "百度云", 38365: "百度云", 58519: "华为云", 55990: "华为云",
    136907: "华为云", 4609: "澳門電訊", 13335: "Cloudflare", 55960: "亚马逊云", 14618: "亚马逊云", 16509: "亚马逊云",
    15169: "谷歌云", 396982: "谷歌云", 36492: "谷歌云",
    137718: "火山引擎"
}


def get_as_info(number: int) -> Optional[str]:
    return asn_map.get(number)


def derive_isp_from_org(org_name: str) -> Optional[str]:
    if not org_name:
        return None
    name = org_name.lower()
    if "volcano" in name or "byte" in name:
        return "火山引擎"
    if "alibaba" in name or "aliyun" in name or "alicloud" in name:
        return "阿里云"
    if "tencent" in name or "qcloud" in name:
        return "腾讯云"
    if "huawei" in name:
        return "华为云"
    if "baidu" in name:
        return "百度云"
    if "amazon" in name or "aws" in name:
        return "亚马逊云"
    if "google" in name or "gcp" in name:
        return "谷歌云"
    if "cloudflare" in name:
        return "Cloudflare"
    return None


def get_des(d: Dict[str, Any]) -> str:
    for i in lang:
        if i in d.get('names', {}):
            return d['names'][i]
    return d.get('names', {}).get('en', '')


def get_country(d: Dict[str, Any]) -> str:
    country_name = get_des(d)
    if country_name in ["香港", "澳门", "台湾"]:
        return "中国" + country_name
    return country_name


def de_duplicate(regions):
    regions = filter(bool, regions)
    ret = []
    [ret.append(i) for i in regions if i not in ret]
    return ret


def get_addr(ip: str, mask: int) -> str:
    network = ipaddress.ip_network(f"{ip}/{mask}", strict=False)
    first_ip = network.network_address
    return f"{first_ip}/{mask}"


def get_maxmind(ip: str) -> Dict[str, Any]:
    ret: Dict[str, Any] = {"ip": ip}

    # ASN
    asn_info = asn_reader.get(ip)
    if asn_info:
        as_data = {
            "number": asn_info["autonomous_system_number"],
            "name": asn_info["autonomous_system_organization"]
        }
        as_extra = get_as_info(as_data["number"]) or derive_isp_from_org(as_data["name"])
        if as_extra:
            as_data["info"] = as_extra
        ret["as"] = as_data

    # City/Geo
    city_info, prefix = city_reader.get_with_prefix_len(ip)
    ret["addr"] = get_addr(ip, prefix)
    if not city_info:
        return ret

    if "location" in city_info:
        ret["location"] = {
            "latitude": city_info["location"].get("latitude"),
            "longitude": city_info["location"].get("longitude")
        }

    if "country" in city_info:
        ret["country"] = {
            "code": city_info["country"]["iso_code"],
            "name": get_country(city_info["country"])
        }

    if "registered_country" in city_info:
        ret["registered_country"] = {
            "code": city_info["registered_country"]["iso_code"],
            "name": get_country(city_info["registered_country"])
        }

    regions = [get_des(sub) for sub in city_info.get('subdivisions', [])]
    if "city" in city_info:
        city = get_des(city_info["city"])
        country_name = ret["country"]["name"] if "country" in ret else ""
        if (not regions or city not in regions[-1]) and city not in country_name:
            regions.append(city)
    ret["regions"] = de_duplicate(regions) if regions else []

    if ret["regions"]:
        # 始终设置省/市，避免未定义键访问
        ret["province"] = ret["regions"][0]
        if len(ret["regions"]) > 1:
            ret["city"] = ret["regions"][-1]

    return ret


def get_cn(ip: str, info: Dict[str, Any]):
    cn_info, prefix = cn_reader.get_with_prefix_len(ip)
    if not cn_info:
        return
    info["addr"] = get_addr(ip, prefix)
    # 使用 .get 安全读取，避免缺键
    province = cn_info.get("province", "") or ""
    city = cn_info.get("city", "") or ""
    districts = cn_info.get("districts", "") or ""
    regions = de_duplicate([province, city, districts])
    if regions:
        info["regions"] = regions
        # 若省/市未设置，依据 regions 进行补全
        if "province" not in info or not info.get("province"):
            info["province"] = regions[0]
        if len(regions) > 1 and ("city" not in info or not info.get("city")):
            info["city"] = regions[-1]
    if "as" not in info:
        info["as"] = {}
    # 运营商信息（可能不存在）
    isp = cn_info.get('isp')
    if isp:
        info["as"]["info"] = isp
    net_val = cn_info.get('net')
    if net_val:
        info["type"] = net_val


def build_uniform_result(info: Dict[str, Any]) -> Dict[str, Any]:
    def get_nested(dct, keys, default=""):
        cur = dct
        try:
            for k in keys:
                if cur is None:
                    return default
                cur = cur.get(k)
            return default if cur is None else cur
        except Exception:
            return default

    result = {
        "ip": info.get("ip", ""),
        "addr": info.get("addr", ""),
        "as_number": get_nested(info, ["as", "number"], ""),
        "as_name": get_nested(info, ["as", "name"], ""),
        "as_info": get_nested(info, ["as", "info"], ""),
        "country_code": get_nested(info, ["country", "code"], ""),
        "country_name": get_nested(info, ["country", "name"], ""),
        "registered_country_code": get_nested(info, ["registered_country", "code"], ""),
        "registered_country_name": get_nested(info, ["registered_country", "name"], ""),
        "latitude": get_nested(info, ["location", "latitude"], ""),
        "longitude": get_nested(info, ["location", "longitude"], ""),
        "province": info.get("province", ""),
        "city": info.get("city", ""),
        "regions": ",".join(info.get("regions", [])) if info.get("regions") else "",
        "type": info.get("type", ""),
    }

    for k, v in list(result.items()):
        if v is None:
            result[k] = ""

    return result


def get_ip_info(ip: str) -> Dict[str, Any]:
    info = get_maxmind(ip)
    if ("country" in info and info["country"]["code"] == "CN") and \
       ("registered_country" not in info or info["registered_country"]["code"] == "CN"):
        get_cn(ip, info)
    return build_uniform_result(info)


 