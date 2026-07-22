import hashlib
import random
import secrets
import threading
import time
import requests
import json
import uuid
import logging
from fake_useragent import UserAgent

from src.utils.sanitize import log_safe_exception

logger = logging.getLogger(__name__)

original_request = requests.Session.request

ua = UserAgent()


class AuthCache:
    def __init__(self):
        self.data = None
        self.expire_at = 0
        self.lock = threading.Lock()
        self.ttl = 20


_cache = AuthCache()


class PatchSign:
    def __init__(self):
        self.patched = False

    def set_patch(self, patched):
        self.patched = patched

    def is_patched(self):
        return self.patched


_patch_sign = PatchSign()


def _get_nid(user_agent):
    """
    获取东方财富的 NID 授权令牌

    Args:
        user_agent (str): 用户代理字符串，用于模拟不同的浏览器访问

    Returns:
        str: 返回获取到的 NID 授权令牌，如果获取失败则返回 None

    功能说明:
        该函数通过向东方财富的授权接口发送请求来获取 NID 令牌，
        用于后续的数据访问授权。函数实现了缓存机制来避免频繁请求。
    """
    now = time.time()
    # Check if the cache is valid, to avoid repeated requests
    if _cache.data and now < _cache.expire_at:
        return _cache.data
    # Use thread lock to ensure concurrency safety
    with _cache.lock:
        try:
            def generate_uuid_md5():
                """
                生成 UUID 并对其进行 MD5 哈希处理
                :return: MD5 哈希值（32位十六进制字符串）
                """
                # Generate UUID
                unique_id = str(uuid.uuid4())
                # Perform MD5 hash on UUIDs
                md5_hash = hashlib.md5(unique_id.encode('utf-8')).hexdigest()
                return md5_hash

            def generate_st_nvi():
                """
                生成 st_nvi 值的方法
                :return: 返回生成的 st_nvi 值
                """
                HASH_LENGTH = 4  # Extract the first few digits of the hash value

                def generate_random_string(length=21):
                    """
                    生成指定长度的随机字符串
                    :param length: 字符串长度，默认为 21
                    :return: 随机字符串
                    """
                    charset = "useandom-26T198340PX75pxJACKVERYMINDBUSHWOLF_GQZbfghjklqvwyzrict"
                    return ''.join(secrets.choice(charset) for _ in range(length))

                def sha256(input_str):
                    """
                    计算 SHA-256 哈希值
                    :param input_str: 输入字符串
                    :return: 哈希值（十六进制）
                    """
                    return hashlib.sha256(input_str.encode('utf-8')).hexdigest()

                random_str = generate_random_string()
                hash_prefix = sha256(random_str)[:HASH_LENGTH]
                return random_str + hash_prefix

            url = "https://anonflow2.eastmoney.com/backend/api/webreport"
            # Randomly select screen resolution to increase request realism
            screen_resolution = random.choice(['1920X1080', '2560X1440', '3840X2160'])
            payload = json.dumps({
                "osPlatform": "Windows",
                "sourceType": "WEB",
                "osversion": "Windows 10.0",
                "language": "zh-CN",
                "timezone": "Asia/Shanghai",
                "webDeviceInfo": {
                    "screenResolution": screen_resolution,
                    "userAgent": user_agent,
                    "canvasKey": generate_uuid_md5(),
                    "webglKey": generate_uuid_md5(),
                    "fontKey": generate_uuid_md5(),
                    "audioKey": generate_uuid_md5()
                }
            })
            headers = {
                'Cookie': f'st_nvi={generate_st_nvi()}',
                'Content-Type': 'application/json'
            }
            # Increase timeout to prevent indefinite waiting
            response = requests.request("POST", url, headers=headers, data=payload, timeout=30)
            response.raise_for_status()  # Raise HTTPError for 4xx/5xx responses

            data = response.json()
            nid = data['data']['nid']

            _cache.data = nid
            _cache.expire_at = now + _cache.ttl
            return nid
        except requests.exceptions.RequestException as exc:
            log_safe_exception(
                logger,
                "Eastmoney authorization request failed",
                exc,
                error_code="eastmoney_authorization_request_failed",
                level=logging.WARNING,
            )
            _cache.data = None
            # If this interface request fails, the scheme may be invalid. Subsequent failures are likely to continue, as it cannot successfully obtain the token, it will continue to request next time, set a longer expiration time to avoid frequent requests.
            _cache.expire_at = now + 5 * 60
            return None
        except (KeyError, json.JSONDecodeError) as exc:
            log_safe_exception(
                logger,
                "Eastmoney authorization response parsing failed",
                exc,
                error_code="eastmoney_authorization_response_parse_failed",
                level=logging.WARNING,
            )
            _cache.data = None
            # If this interface request fails, the scheme may be invalid. Subsequent failures are likely to continue, as it cannot successfully obtain the token, it will continue to request next time, set a longer expiration time to avoid frequent requests.
            _cache.expire_at = now + 5 * 60
            return None


def eastmoney_patch():
    if _patch_sign.is_patched():
        return

    def patched_request(self, method, url, **kwargs):
        # Exclude non-target domains
        is_target = any(
            d in (url or "")
            for d in [
                "fund.eastmoney.com",
                "push2.eastmoney.com",
                "push2his.eastmoney.com",
            ]
        )
        if not is_target:
            return original_request(self, method, url, **kwargs)
        # Get a random User-Agent
        user_agent = ua.random
        # Handle Headers: Ensure they don't break business code-passed headers
        headers = kwargs.get("headers", {})
        headers["User-Agent"] = user_agent
        nid = _get_nid(user_agent)
        if nid:
            headers["Cookie"] = f"nid18={nid}"
        kwargs["headers"] = headers
        # Random sleep, reduce risk of being blocked
        sleep_time = random.uniform(1, 4)
        time.sleep(sleep_time)
        return original_request(self, method, url, **kwargs)

    # Replaces Session request entry globally
    requests.Session.request = patched_request
    _patch_sign.set_patch(True)
