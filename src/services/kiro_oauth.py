"""
Kiro OAuth Service - 通过 AWS Builder ID 获取 Kiro Token
基于 kiro-account-manager-main 的 web_oauth.rs 流程实现

流程:
1. InitiateLogin - 生成 PKCE，获取 Cognito 授权 URL
2. 浏览器登录 AWS Builder ID
3. ExchangeToken - 用 code 换取 Kiro access_token
"""

import os
import hashlib
import base64
import secrets
import json
import time
import re
import cbor2
import requests
from urllib.parse import urlparse, parse_qs
from typing import Optional, Dict, Tuple
from helpers.utils import build_request_user_agent

# Kiro Web Portal 配置
KIRO_WEB_PORTAL = "https://app.kiro.dev"
KIRO_REDIRECT_URI = "https://app.kiro.dev/signin/oauth"

class KiroOAuthClient:
    """Kiro OAuth 客户端 - 使用 CBOR 协议"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            "Content-Type": "application/cbor",
            "Accept": "application/cbor",
            "smithy-protocol": "rpc-v2-cbor",
            "User-Agent": build_request_user_agent(),
        })
    
    @staticmethod
    def generate_code_verifier() -> str:
        """生成 PKCE code_verifier (43-128 字符的随机字符串)"""
        random_bytes = secrets.token_bytes(32)
        return base64.urlsafe_b64encode(random_bytes).decode('utf-8').rstrip('=')
    
    @staticmethod
    def generate_code_challenge(verifier: str) -> str:
        """生成 code_challenge = Base64URL(SHA256(code_verifier))"""
        digest = hashlib.sha256(verifier.encode('utf-8')).digest()
        return base64.urlsafe_b64encode(digest).decode('utf-8').rstrip('=')
    
    @staticmethod
    def generate_state() -> str:
        """生成随机 state"""
        import uuid
        return str(uuid.uuid4())
    
    def initiate_login(self, idp: str = "BuilderId") -> Dict:
        """
        调用 InitiateLogin 接口 - 获取 OAuth 重定向 URL
        
        Args:
            idp: 身份提供者，可选值: Github, AWSIdC, BuilderId, Google, Internal
        
        Returns:
            Dict 包含 authorize_url, state, code_verifier, redirect_uri, idp
        """
        state = self.generate_state()
        code_verifier = self.generate_code_verifier()
        code_challenge = self.generate_code_challenge(code_verifier)
        
        url = f"{KIRO_WEB_PORTAL}/service/KiroWebPortalService/operation/InitiateLogin"
        
        request_data = {
            "idp": idp,
            "redirectUri": KIRO_REDIRECT_URI,
            "codeChallenge": code_challenge,
            "codeChallengeMethod": "S256",
            "state": state,
        }
        
        print(f"[KiroOAuth] InitiateLogin Request:")
        print(f"  idp: {idp}")
        print(f"  redirectUri: {KIRO_REDIRECT_URI}")
        print(f"  state: {state[:20]}...")
        
        body = cbor2.dumps(request_data)
        response = self.session.post(url, data=body)
        
        if not response.ok:
            raise Exception(f"InitiateLogin failed ({response.status_code}): {response.text}")
        
        resp_data = cbor2.loads(response.content)
        redirect_url = resp_data.get("redirectUrl")
        
        if not redirect_url:
            raise Exception("No redirectUrl in InitiateLogin response")
        
        print(f"[KiroOAuth] InitiateLogin Response:")
        print(f"  redirectUrl: {redirect_url[:80]}...")
        
        return {
            "authorize_url": redirect_url,
            "state": state,
            "code_verifier": code_verifier,
            "redirect_uri": KIRO_REDIRECT_URI,
            "idp": idp,
        }
    
    def exchange_token(self, idp: str, code: str, code_verifier: str, 
                       redirect_uri: str, state: str) -> Dict:
        """
        调用 ExchangeToken 接口 - 用 code 换取 token
        
        Args:
            idp: 身份提供者
            code: OAuth 授权码
            code_verifier: PKCE code_verifier
            redirect_uri: 重定向 URI
            state: 返回的 state 值
        
        Returns:
            Dict 包含 access_token, csrf_token, refresh_token, expires_in, profile_arn
        """
        url = f"{KIRO_WEB_PORTAL}/service/KiroWebPortalService/operation/ExchangeToken"
        
        request_data = {
            "idp": idp,
            "code": code,
            "codeVerifier": code_verifier,
            "redirectUri": redirect_uri,
            "state": state,
        }
        
        print(f"[KiroOAuth] ExchangeToken Request:")
        print(f"  idp: {idp}")
        print(f"  code: {code[:30]}...")
        print(f"  state: {state[:30]}...")
        
        body = cbor2.dumps(request_data)
        response = self.session.post(url, data=body)
        
        # 解析 Set-Cookie 头
        cookies = {}
        for cookie_header in response.headers.get('Set-Cookie', '').split(','):
            # 简单解析 cookie
            if '=' in cookie_header:
                parts = cookie_header.strip().split(';')[0]
                if '=' in parts:
                    name, value = parts.split('=', 1)
                    cookies[name.strip()] = value.strip()
        
        # 也解析 response.cookies
        for c in response.cookies:
            cookies[c.name] = c.value
        
        print(f"[KiroOAuth] ExchangeToken Cookies: {list(cookies.keys())}")
        
        if not response.ok:
            error_msg = response.text
            try:
                error_data = cbor2.loads(response.content)
                error_msg = json.dumps(error_data)
            except:
                pass
            raise Exception(f"ExchangeToken failed ({response.status_code}): {error_msg}")
        
        resp_data = cbor2.loads(response.content)
        
        print(f"[KiroOAuth] ExchangeToken Response:")
        print(f"  accessToken: {resp_data.get('accessToken', '')[:30]}...")
        print(f"  csrfToken: {resp_data.get('csrfToken')}")
        print(f"  expiresIn: {resp_data.get('expiresIn')}")
        print(f"  profileArn: {resp_data.get('profileArn')}")
        
        # RefreshToken 可能叫 RefreshToken 或 SessionToken
        refresh_token = cookies.get("RefreshToken") or cookies.get("SessionToken")
        
        return {
            "access_token": resp_data.get("accessToken") or cookies.get("AccessToken"),
            "csrf_token": resp_data.get("csrfToken"),
            "refresh_token": refresh_token,  # 从 Set-Cookie 获取
            "session_token": cookies.get("SessionToken"),  # 额外保存 SessionToken
            "expires_in": resp_data.get("expiresIn", 3600),
            "profile_arn": resp_data.get("profileArn"),
            "idp": cookies.get("Idp", idp),
        }
    
    def get_user_info(self, access_token: str, idp: str) -> Dict:
        """
        获取用户信息
        
        Args:
            access_token: 访问令牌
            idp: 身份提供者
        
        Returns:
            Dict 包含 email, userId, status 等
        """
        url = f"{KIRO_WEB_PORTAL}/service/KiroWebPortalService/operation/GetUserInfo"
        
        request_data = {
            "origin": "KIRO_IDE"
        }
        
        headers = {
            "Content-Type": "application/cbor",
            "Accept": "application/cbor",
            "smithy-protocol": "rpc-v2-cbor",
            "authorization": f"Bearer {access_token}",
            "Cookie": f"Idp={idp}; AccessToken={access_token}"
        }
        
        body = cbor2.dumps(request_data)
        response = self.session.post(url, data=body, headers=headers)
        
        if not response.ok:
            raise Exception(f"GetUserInfo failed ({response.status_code})")
        
        return cbor2.loads(response.content)


def perform_kiro_oauth_in_browser(driver, aws_email: str, aws_password: str) -> Optional[Dict]:
    """
    在浏览器中执行 Kiro OAuth 流程
    
    Args:
        driver: Selenium WebDriver
        aws_email: AWS Builder ID 邮箱
        aws_password: AWS Builder ID 密码
    
    Returns:
        Dict 包含 Kiro token 信息，或 None 如果失败
    """
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
    
    print("\n" + "=" * 50)
    print("🔐 开始 Kiro OAuth 登录流程...")
    print("=" * 50)
    
    try:
        # Step 1: 初始化登录
        client = KiroOAuthClient()
        init_result = client.initiate_login("BuilderId")
        
        authorize_url = init_result["authorize_url"]
        code_verifier = init_result["code_verifier"]
        expected_state = init_result["state"]
        idp = init_result["idp"]
        
        print(f"\n📌 授权 URL: {authorize_url[:80]}...")
        
        # Step 2: 打开授权页面 (如果浏览器已登录 AWS，会自动重定向)
        driver.get(authorize_url)
        time.sleep(3)
        
        current_url = driver.current_url
        print(f"当前页面: {current_url}")
        
        # 🔍 快速检查：如果 URL 已经包含 code，直接交换 Token
        if "app.kiro.dev/signin/oauth" in current_url and "code=" in current_url:
            print("✅ 检测到已有授权码，直接交换 Token...")
            
            parsed = urlparse(current_url)
            params = parse_qs(parsed.query)
            code = params.get("code", [None])[0]
            returned_state = params.get("state", [None])[0]
            
            if code:
                print(f"   code: {code[:30]}...")
                print(f"   state: {returned_state[:30]}..." if returned_state else "   state: None")
                
                print("\n🔄 正在交换 Token...")
                token_result = client.exchange_token(
                    idp=idp,
                    code=code,
                    code_verifier=code_verifier,
                    redirect_uri=KIRO_REDIRECT_URI,
                    state=returned_state or expected_state
                )
                
                print("\n✅ Kiro Token 获取成功!")
                print(f"   access_token: {token_result['access_token'][:50]}...")
                print(f"   csrf_token: {token_result['csrf_token']}")
                print(f"   expires_in: {token_result['expires_in']} 秒")
                
                return token_result
        
        # Step 3: 等待并填写邮箱 (AWS 登录页面)
        try:
            # 等待页面加载
            time.sleep(3)
            
            # AWS 登录页面使用多种不同的选择器
            email_selectors = [
                "input[placeholder*='username@example']",
                "input[placeholder*='example.com']",
                "input[name='email']",
                "input[type='email']",
                "input[type='text']",  # AWS 可能使用 text 类型
                "#awsui-input-0",
                "input[data-testid='username-input']",
                "input[placeholder*='mail']",
                "input[placeholder*='Email']",
                "//input[@name='email']",
                "//input[@type='email']",
                "//input[contains(@placeholder, 'example')]",
            ]
            
            email_input = None
            for selector in email_selectors:
                try:
                    if selector.startswith("//"):
                        email_input = driver.find_element(By.XPATH, selector)
                    else:
                        email_input = driver.find_element(By.CSS_SELECTOR, selector)
                    if email_input and email_input.is_displayed():
                        break
                except:
                    continue
            
            if email_input:
                email_input.clear()
                email_input.send_keys(aws_email)
                print(f"✅ 已填写邮箱: {aws_email}")
                time.sleep(1)
                
                # 点击继续按钮 (注意不要点击 "Continue with Google")
                continue_selectors = [
                    "button[type='submit']",  # 优先使用 submit 按钮
                    "//button[contains(., '继续') and not(contains(., 'Google'))]",
                    "//button[contains(., 'Continue') and not(contains(., 'Google'))]",
                    "//button[contains(., 'Next') and not(contains(., 'Google'))]",
                    "//button[@type='submit' and not(contains(., 'Google'))]",
                ]
                
                for selector in continue_selectors:
                    try:
                        if selector.startswith("//"):
                            btn = driver.find_element(By.XPATH, selector)
                        else:
                            btn = driver.find_element(By.CSS_SELECTOR, selector)
                        if btn and btn.is_displayed():
                            btn.click()
                            print("✅ 已点击继续按钮")
                            break
                    except:
                        continue
                        
                time.sleep(3)
            else:
                print("⚠️  未找到邮箱输入框")
        except Exception as e:
            print(f"⚠️  邮箱填写异常 (可能已登录): {e}")
        
        # Step 4: 填写密码 (如果需要)
        try:
            time.sleep(2)
            
            password_selectors = [
                "input[type='password']",
                "input[name='password']",
                "#awsui-input-1",
                "//input[@type='password']",
            ]
            
            password_input = None
            for selector in password_selectors:
                try:
                    if selector.startswith("//"):
                        password_input = driver.find_element(By.XPATH, selector)
                    else:
                        password_input = driver.find_element(By.CSS_SELECTOR, selector)
                    if password_input and password_input.is_displayed():
                        break
                except:
                    continue
            
            if password_input:
                password_input.clear()
                password_input.send_keys(aws_password)
                print("✅ 已填写密码")
                time.sleep(1)
                
                # 点击登录/继续按钮
                login_selectors = [
                    "//button[contains(., '继续')]",  # 中文
                    "//button[contains(., 'Continue')]",
                    "//button[contains(., 'Sign in')]",
                    "//button[contains(., 'Login')]",
                    "button[type='submit']",
                    "//button[@type='submit']",
                ]
                
                clicked = False
                for selector in login_selectors:
                    try:
                        if selector.startswith("//"):
                            btn = driver.find_element(By.XPATH, selector)
                        else:
                            btn = driver.find_element(By.CSS_SELECTOR, selector)
                        if btn and btn.is_displayed():
                            btn.click()
                            print(f"✅ 已点击登录按钮: {selector}")
                            clicked = True
                            break
                    except:
                        continue
                
                if not clicked:
                    print("⚠️ 未找到登录按钮")
                        
                time.sleep(5)
            else:
                print("⚠️  未找到密码输入框，可能已登录或不需要密码")
        except Exception as e:
            print(f"⚠️  密码填写异常: {e}")
        
        # Step 5: 处理登录验证码 (如果需要)
        try:
            time.sleep(3)
            # 检查是否有验证码输入框 (Verify your identity 页面)
            verify_indicators = [
                "Verify your identity",
                "验证码",
                "verification code",
            ]
            
            page_source = driver.page_source
            needs_verification = any(indicator in page_source for indicator in verify_indicators)
            
            if needs_verification:
                print("📧 检测到需要邮箱验证码...")
                
                # 导入邮箱服务
                from services.email_service import ChatGPTMailClient
                
                # 创建邮箱客户端并获取验证码
                mail_client = ChatGPTMailClient()
                mail_client.current_email = aws_email  # 设置当前邮箱
                
                # 等待验证码邮件
                print(f"⏳ 等待验证码邮件发送到 {aws_email}...")
                verification_code = mail_client.wait_for_code(aws_email, timeout=120)
                
                if verification_code:
                    print(f"✅ 收到验证码: {verification_code}")
                    
                    # 填写验证码
                    code_selectors = [
                        "input[placeholder*='digit']",
                        "input[placeholder*='6-digit']",
                        "input[type='text']",
                        "//input[contains(@placeholder, 'digit')]",
                        "//input[@type='text']",
                    ]
                    
                    code_input = None
                    for selector in code_selectors:
                        try:
                            if selector.startswith("//"):
                                code_input = driver.find_element(By.XPATH, selector)
                            else:
                                code_input = driver.find_element(By.CSS_SELECTOR, selector)
                            if code_input and code_input.is_displayed():
                                break
                        except:
                            continue
                    
                    if code_input:
                        code_input.clear()
                        code_input.send_keys(verification_code)
                        print("✅ 已填写验证码")
                        time.sleep(1)
                        
                        # 点击继续
                        try:
                            continue_btn = driver.find_element(By.XPATH, "//button[contains(., '继续') or contains(., 'Continue')]")
                            continue_btn.click()
                            print("✅ 已点击继续按钮")
                            time.sleep(5)
                        except Exception as e:
                            print(f"⚠️ 点击继续失败: {e}")
                    else:
                        print("⚠️ 未找到验证码输入框")
                else:
                    print("❌ 未能获取验证码")
        except Exception as e:
            print(f"⚠️  验证码处理异常: {e}")
        
        # Step 6: 等待重定向到 Kiro
        print("⏳ 等待重定向到 Kiro...")
        max_wait = 60
        start_time = time.time()
        builder_id_clicked = False
        
        while time.time() - start_time < max_wait:
            current_url = driver.current_url
            
            # 🔍 优先检查：如果 URL 已经包含 code，直接交换 Token
            if "app.kiro.dev/signin/oauth" in current_url and "code=" in current_url:
                print(f"✅ 成功重定向到 Kiro!")
                print(f"   URL: {current_url[:100]}...")
                
                # 解析 code 和 state
                parsed = urlparse(current_url)
                params = parse_qs(parsed.query)
                
                code = params.get("code", [None])[0]
                returned_state = params.get("state", [None])[0]
                
                if not code:
                    print("❌ 未找到 code 参数")
                    return None
                
                print(f"   code: {code[:30]}...")
                print(f"   state: {returned_state[:30]}..." if returned_state else "   state: None")
                
                # 交换 Token
                print("\n🔄 正在交换 Token...")
                token_result = client.exchange_token(
                    idp=idp,
                    code=code,
                    code_verifier=code_verifier,
                    redirect_uri=KIRO_REDIRECT_URI,
                    state=returned_state or expected_state
                )
                
                print("\n✅ Kiro Token 获取成功!")
                print(f"   access_token: {token_result['access_token'][:50]}...")
                print(f"   csrf_token: {token_result['csrf_token']}")
                print(f"   expires_in: {token_result['expires_in']} 秒")
                
                return token_result
            
            # 检查是否在 Kiro 登录选择页面 (需要点击 Builder ID)
            if "app.kiro.dev/signin" in current_url and "oauth" not in current_url and "code=" not in current_url and not builder_id_clicked:
                print("📌 检测到 Kiro 登录选择页面，尝试点击 Builder ID...")
                try:
                    time.sleep(2)
                    # 尝试多种方式找到 Builder ID 按钮
                    builder_id_selectors = [
                        "//button[contains(., 'Builder ID')]",
                        "//button[contains(@class, 'signInButton')][contains(., 'Builder')]",
                        "//span[contains(., 'Builder ID')]/ancestor::button",
                        "//div[contains(., 'Builder ID')]/ancestor::button",
                    ]
                    
                    for selector in builder_id_selectors:
                        try:
                            btn = driver.find_element(By.XPATH, selector)
                            if btn.is_displayed():
                                btn.click()
                                print("✅ 已点击 Builder ID 按钮")
                                builder_id_clicked = True
                                time.sleep(3)
                                break
                        except:
                            continue
                    
                    if not builder_id_clicked:
                        # 尝试使用 CSS 选择器
                        try:
                            btn = driver.find_element(By.CSS_SELECTOR, "button[data-variant='secondary']")
                            # 检查按钮文本是否包含 Builder
                            if "Builder" in btn.text:
                                btn.click()
                                print("✅ 已点击 Builder ID 按钮 (CSS)")
                                builder_id_clicked = True
                                time.sleep(3)
                        except:
                            pass
                except Exception as e:
                    print(f"⚠️  点击 Builder ID 失败: {e}")
            
            # 检查是否需要授权同意
            if "consent" in current_url.lower() or "authorize" in current_url.lower():
                try:
                    allow_btn = driver.find_element(By.XPATH, "//button[contains(., 'Allow') or contains(., 'Authorize')]")
                    allow_btn.click()
                    print("✅ 已点击授权按钮")
                    time.sleep(3)
                except:
                    pass
            
            time.sleep(2)
        
        print("❌ 等待重定向超时")
        return None
        
    except Exception as e:
        print(f"❌ Kiro OAuth 失败: {e}")
        import traceback
        traceback.print_exc()
        return None


def perform_kiro_oauth_direct(aws_email: str, aws_password: str) -> Optional[Dict]:
    """
    直接使用 requests 执行 Kiro OAuth 流程（无浏览器）
    注意：这个方法需要先完成 AWS 登录获取 session
    
    对于刚注册的账号，建议使用 perform_kiro_oauth_in_browser
    """
    # TODO: 实现纯 HTTP 流程（复杂，需要处理 AWS Cognito 登录）
    pass


# 测试代码
if __name__ == "__main__":
    client = KiroOAuthClient()
    
    # 测试 InitiateLogin
    print("测试 InitiateLogin...")
    result = client.initiate_login("BuilderId")
    print(f"授权 URL: {result['authorize_url'][:100]}...")
    print(f"State: {result['state']}")
    print(f"Code Verifier: {result['code_verifier']}")
