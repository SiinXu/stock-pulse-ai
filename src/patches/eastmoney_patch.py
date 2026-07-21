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
    Get the NID authorization token from Eastmoney.

    Args:
        user_agent (str): User agent string, used to simulate different browser access

    Returns:
        str: Returns the obtained NID authorization token, if retrieval fails, return None

    Function description:
        This function obtains the NID token by sending requests to Eastmoney's authorized interface.
        Used for subsequent data access authorization. The function implements a caching mechanism to avoid frequent requests.
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
                Generate UUID and perform MD5 hashing on it
                :return: MD5 hash value (32-bit hexadecimal string)
                """
                # Generate UUID
                unique_id = str(uuid.uuid4())
                # Perform MD5 hash on UUIDs
                md5_hash = hashlib.md5(unique_id.encode('utf-8')).hexdigest()
                return md5_hash

            def generate_st_nvi():
                """
                Method for generating st_nvi value
                :return: Returns the generated st_nvi value
                """
                HASH_LENGTH = 4  # Extract the first few digits of the hash value

                def generate_random_string(length=21):
                    """
                    Generate a random string of the specified length
                    :param length: String length, default is 21
                    :return: Random string
                    """
                    charset = "useandom-26T198340PX75pxJACKVERYMINDBUSHWOLF_GQZbfghjklqvwyzrict"
                    return ''.join(secrets.choice(charset) for _ in range(length))

                def sha256(input_str):
                    """
                    Calculate SHA-256 hash value
                    :param input_str: Input string
                    :return: Hash value (hexadecimal)
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
