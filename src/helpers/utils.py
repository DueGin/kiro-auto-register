import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import os
import re
import random
import shutil
import subprocess
import requests
from functools import lru_cache
from config import REGION_CURRENT, REGION_PROFILES, DEVICE_TYPE, BROWSER_TYPE, USER_AGENT_MODE

# 创建 HTTP 会话
http_session = requests.Session()


def _normalize_version(version: str) -> str:
    """Normalize browser version to four segments."""
    nums = re.findall(r"\d+", version or "")
    if not nums:
        return ""
    nums = nums[:4]
    while len(nums) < 4:
        nums.append("0")
    return ".".join(nums)


def _extract_version(text: str) -> str:
    """Extract version string from command output."""
    if not text:
        return ""
    match = re.search(r"(\d+(?:\.\d+){1,3})", text)
    return _normalize_version(match.group(1) if match else "")


def _version_from_command(command):
    """Run a version command safely and parse browser version."""
    try:
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            timeout=2,
            check=False,
        )
        output = (result.stdout or "") + " " + (result.stderr or "")
        return _extract_version(output)
    except Exception:
        return ""


@lru_cache(maxsize=1)
def get_local_browser_user_agent():
    """
    Try to build UA from local installed browser.
    Priority:
    1) LOCAL_BROWSER_UA environment variable
    2) Browser executable --version
    """
    env_ua = os.getenv("LOCAL_BROWSER_UA", "").strip()
    if env_ua:
        return env_ua

    candidates = []
    browser = (BROWSER_TYPE or "chrome").lower()
    if browser == "edge":
        candidates.extend([
            ("edge", "msedge.exe"),
            ("edge", "msedge"),
            ("edge", "microsoft-edge"),
        ])
    else:
        candidates.extend([
            ("chrome", "chrome.exe"),
            ("chrome", "chrome"),
            ("chrome", "google-chrome"),
            ("chrome", "google-chrome-stable"),
            ("chrome", "chromium"),
        ])

    # Fallback: also probe the other browser family.
    candidates.extend([
        ("edge", "msedge.exe"),
        ("chrome", "chrome.exe"),
    ])

    for browser_kind, cmd in candidates:
        path = shutil.which(cmd)
        if not path:
            continue
        version = _version_from_command([path, "--version"])
        if not version:
            continue

        if browser_kind == "edge":
            return (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36 Edg/{version}"
            )

        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
        )

    return ""


def build_random_user_agent():
    """Generate random UA when local browser UA is unavailable."""
    if DEVICE_TYPE == "mobile":
        ios_major = random.randint(16, 18)
        ios_minor = random.randint(0, 6)
        return (
            "Mozilla/5.0 (iPhone; CPU iPhone OS "
            f"{ios_major}_{ios_minor} like Mac OS X) AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        )

    browser = (BROWSER_TYPE or "chrome").lower()
    major = random.randint(122, 136)
    build = random.randint(6200, 7999)
    patch = random.randint(50, 220)
    version = f"{major}.0.{build}.{patch}"

    if browser == "edge":
        return (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36 Edg/{version}"
        )

    return (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        f"AppleWebKit/537.36 (KHTML, like Gecko) Chrome/{version} Safari/537.36"
    )


def build_request_user_agent():
    """UA for HTTP request headers with configurable mode."""
    env_mode = os.getenv("USER_AGENT_MODE", "").strip().lower()
    mode = env_mode or str(USER_AGENT_MODE or "auto").strip().lower()
    if mode not in {"auto", "local", "random"}:
        mode = "auto"

    if mode == "random":
        return build_random_user_agent()

    local_ua = get_local_browser_user_agent()
    if local_ua:
        return local_ua

    # local mode falls back to random when local browser UA is unavailable.
    return build_random_user_agent()


def get_region_config():
    """获取当前地区配置"""
    return REGION_PROFILES.get(REGION_CURRENT, REGION_PROFILES.get("usa"))


def get_user_agent():
    """获取当前地区和设备类型的随机 User-Agent"""
    return build_request_user_agent()


def is_mobile():
    """判断当前是否为移动设备模式"""
    return DEVICE_TYPE == "mobile"


def get_locale():
    """获取当前地区的语言设置"""
    region_config = get_region_config()
    return region_config.get("locale", "en-US")


def get_timezone():
    """获取当前地区的时区"""
    region_config = get_region_config()
    return region_config.get("timezone", "America/New_York")


def get_accept_language():
    """获取当前地区的 Accept-Language"""
    region_config = get_region_config()
    return region_config.get("accept_language", "en-US,en;q=0.9")



def extract_verification_code(text: str):
    """
    从文本中提取验证码（6位数字）
    """
    if not text:
        return None
    
    # 匹配6位数字验证码
    patterns = [
        r'\b(\d{6})\b',  # 独立的6位数字
        r'code[:\s]+(\d{6})',  # code: 123456
        r'验证码[：:\s]+(\d{6})',  # 验证码：123456
    ]
    
    for pattern in patterns:
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            return match.group(1)
    
    return None


# === 动态地区配置支持 ===

def get_region_config_by_name(region_name):
    """根据地区名称获取配置"""
    return REGION_PROFILES.get(region_name, REGION_PROFILES.get("usa"))


def get_user_agent_for_region(region_name):
    """获取指定地区的 User-Agent (强制 Windows + 动态版本号)"""
    return build_request_user_agent()


def get_locale_for_region(region_name):
    """获取指定地区的语言设置"""
    region_config = get_region_config_by_name(region_name)
    return region_config.get("locale", "en-US")


def get_timezone_for_region(region_name):
    """获取指定地区的时区"""
    region_config = get_region_config_by_name(region_name)
    return region_config.get("timezone", "America/New_York")


def get_accept_language_for_region(region_name):
    """获取指定地区的 Accept-Language"""
    region_config = get_region_config_by_name(region_name)
    return region_config.get("accept_language", "en-US,en;q=0.9")
