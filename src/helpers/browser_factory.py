"""
浏览器工厂模块
支持 Chrome 和 Edge 浏览器，以及多种 WebDriver 获取策略
"""

import os
import sys
import random
from pathlib import Path

# 将 src 目录添加到路径
sys.path.insert(0, str(Path(__file__).parent.parent))

from config import HEADLESS, BROWSER_TYPE, DRIVER_STRATEGY
from helpers.utils import build_request_user_agent


class BrowserFactory:
    """
    浏览器工厂类
    支持 Chrome 和 Edge 浏览器的创建
    """
    
    def __init__(self):
        self.browser_type = BROWSER_TYPE.lower()
        self.driver_strategy = DRIVER_STRATEGY.lower()
        self.headless = HEADLESS
        self.driver = None
    
    def create_driver(self, proxy_url=None, user_agent=None, locale=None, accept_language=None):
        """
        创建并返回配置好的 WebDriver 实例
        
        Args:
            proxy_url: 代理地址 (可选)
            user_agent: User-Agent 字符串 (可选)
            locale: 语言设置 (可选)
            accept_language: Accept-Language 头 (可选)
        
        Returns:
            WebDriver 实例
        """
        browser_name = "Edge" if self.browser_type == "edge" else "Chrome"
        print(f"🌐 正在配置 {browser_name} 浏览器...")
        
        # 根据浏览器类型创建 options
        if self.browser_type == "edge":
            from selenium.webdriver.edge.options import Options
            options = Options()
        else:
            # 优先使用 undetected-chromedriver
            try:
                import undetected_chromedriver as uc
                return self._create_undetected_chrome(proxy_url, user_agent, locale, accept_language)
            except ImportError:
                print("⚠️  undetected-chromedriver 未安装，使用标准 Selenium")
                from selenium.webdriver.chrome.options import Options
                options = Options()
        
        # 配置通用选项
        self._configure_options(options, proxy_url, user_agent, locale, accept_language)
        
        # 根据策略创建 driver
        driver = self._create_driver_with_strategy(options)
        
        if driver:
            self._inject_stealth_scripts(driver)
        
        return driver
    
    def _create_undetected_chrome(self, proxy_url=None, user_agent=None, locale=None, accept_language=None):
        """
        使用 undetected-chromedriver 创建 Chrome 实例
        """
        import undetected_chromedriver as uc
        import tempfile
        
        options = uc.ChromeOptions()
        
        # 基本设置
        if self.headless:
            options.add_argument('--headless=new')
        
        # 窗口大小
        common_resolutions = ["1920,1080", "1366,768", "1536,864", "1440,900", "1280,720"]
        chosen_res = random.choice(common_resolutions)
        options.add_argument(f'--window-size={chosen_res}')
        options.add_argument('--start-maximized')
        
        # 语言设置
        if locale:
            options.add_argument(f'--lang={locale}')
        if accept_language:
            options.add_argument(f'--accept-lang={accept_language}')
        
        # 反检测参数
        options.add_argument('--disable-blink-features=AutomationControlled')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-web-security')
        options.add_argument('--disable-features=IsolateOrigins,site-per-process')
        options.add_argument('--disable-site-isolation-trials')
        options.add_argument('--enable-webgl')
        options.add_argument('--enable-features=NetworkService,NetworkServiceInProcess')
        options.add_argument('--autoplay-policy=no-user-gesture-required')
        
        # WebRTC 防泄露
        options.add_argument('--force-webrtc-ip-handling-policy=default_public_interface_only')
        options.add_argument('--disable-features=WebRtcHideLocalIpsWithMdns')
        
        # User-Agent
        if user_agent:
            options.add_argument(f'--user-agent={user_agent}')
        
        # 代理
        if proxy_url:
            options.add_argument(f'--proxy-server={proxy_url}')
            print(f"✅ 代理已应用: {proxy_url}")
        
        # 创建临时用户目录
        user_data_dir = tempfile.mkdtemp(prefix=f"browser_{random.randint(1000, 9999)}_")
        options.add_argument(f"--user-data-dir={user_data_dir}")
        print(f"📁 创建临时用户目录: {user_data_dir}")
        
        print("🚀 正在启动 undetected-chromedriver...")
        driver = uc.Chrome(options=options, user_data_dir=user_data_dir)
        
        # 注入硬件指纹混淆
        self._inject_hardware_fingerprint(driver)
        
        print("✅ Chrome 浏览器启动成功 (反检测模式)")
        
        # 保存临时目录路径供后续清理
        driver._temp_user_data_dir = user_data_dir
        
        return driver
    
    def _configure_options(self, options, proxy_url=None, user_agent=None, locale=None, accept_language=None):
        """
        配置浏览器选项
        """
        # 无头模式
        if self.headless:
            options.add_argument('--headless')
            options.add_argument('--disable-gpu')
        
        # 窗口大小
        common_resolutions = ["1920,1080", "1366,768", "1536,864", "1440,900"]
        chosen_res = random.choice(common_resolutions)
        options.add_argument(f'--window-size={chosen_res}')
        
        # 通用设置
        options.add_argument('--no-sandbox')
        options.add_argument('--disable-dev-shm-usage')
        options.add_argument('--disable-blink-features=AutomationControlled')
        
        # User-Agent
        if user_agent:
            options.add_argument(f'--user-agent={user_agent}')
        else:
            default_ua = build_request_user_agent()
            options.add_argument(f'--user-agent={default_ua}')
        
        # 语言设置
        if locale:
            options.add_argument(f'--lang={locale}')
        if accept_language:
            options.add_argument(f'--accept-lang={accept_language}')
        
        # 代理
        if proxy_url:
            options.add_argument(f'--proxy-server={proxy_url}')
            print(f"✅ 代理已应用: {proxy_url}")
        
        # 排除自动化开关
        options.add_experimental_option('excludeSwitches', ['enable-automation'])
        options.add_experimental_option('useAutomationExtension', False)
        
        # 禁用图片加载（可选，提高速度）
        # options.add_experimental_option("prefs", {"profile.managed_default_content_settings.images": 2})
    
    def _create_driver_with_strategy(self, options):
        """
        根据策略创建 WebDriver
        """
        browser_name = "Edge" if self.browser_type == "edge" else "Chrome"
        driver = None
        
        # ============ 策略1: webdriver-manager ============
        if self.driver_strategy in ['auto', 'manager']:
            driver = self._try_webdriver_manager(options)
            if driver:
                return driver
        
        # ============ 策略2: 系统 PATH ============
        if self.driver_strategy in ['auto', 'system']:
            driver = self._try_system_driver(options)
            if driver:
                return driver
        
        # ============ 策略3: 本地文件 ============
        if self.driver_strategy in ['auto', 'local']:
            driver = self._try_local_driver(options)
            if driver:
                return driver
        
        # ============ 全部失败 ============
        self._print_driver_help()
        raise Exception(f"无法创建 {browser_name} WebDriver，请按照上述方案解决")
    
    def _try_webdriver_manager(self, options):
        """
        尝试使用 webdriver-manager
        """
        browser_name = "Edge" if self.browser_type == "edge" else "Chrome"
        
        try:
            if self.browser_type == "edge":
                from selenium import webdriver
                from selenium.webdriver.edge.service import Service
                
                try:
                    from webdriver_manager.microsoft import EdgeChromiumDriverManager
                except ImportError:
                    print("  ⚠️ webdriver-manager 未安装")
                    print("  提示: 运行 'pip install webdriver-manager' 可自动管理驱动")
                    return None
                
                print("  尝试使用 webdriver-manager 自动管理 EdgeDriver...")
                try:
                    driver_path = EdgeChromiumDriverManager().install()
                    print(f"  EdgeDriver 路径: {driver_path}")
                    service = Service(driver_path)
                    driver = webdriver.Edge(service=service, options=options)
                    print("  ✓ 使用 webdriver-manager 成功")
                    return driver
                except Exception as e:
                    print(f"  ⚠️ EdgeDriver 安装/启动失败: {e}")
                    return None
            else:
                from selenium import webdriver
                from selenium.webdriver.chrome.service import Service
                
                try:
                    from webdriver_manager.chrome import ChromeDriverManager
                except ImportError:
                    print("  ⚠️ webdriver-manager 未安装")
                    print("  提示: 运行 'pip install webdriver-manager' 可自动管理驱动")
                    return None
                
                print("  尝试使用 webdriver-manager 自动管理 ChromeDriver...")
                try:
                    driver_path = ChromeDriverManager().install()
                    print(f"  ChromeDriver 路径: {driver_path}")
                    service = Service(driver_path)
                    driver = webdriver.Chrome(service=service, options=options)
                    print("  ✓ 使用 webdriver-manager 成功")
                    return driver
                except Exception as e:
                    print(f"  ⚠️ ChromeDriver 安装/启动失败: {e}")
                    return None
                
        except Exception as e:
            print(f"  ⚠️ webdriver-manager 失败: {e}")
        
        return None
    
    def _try_system_driver(self, options):
        """
        尝试使用系统 PATH 中的驱动
        """
        try:
            if self.browser_type == "edge":
                from selenium import webdriver
                from selenium.webdriver.edge.service import Service as EdgeService
                
                print("  尝试使用系统内置的 EdgeDriver...")
                
                # 尝试多种可能的 EdgeDriver 位置
                possible_paths = [
                    None,  # 系统 PATH
                    r"C:\Windows\System32\msedgedriver.exe",
                    r"C:\Program Files\Microsoft\Edge\Application\msedgedriver.exe",
                    r"C:\Program Files (x86)\Microsoft\Edge\Application\msedgedriver.exe",
                ]
                
                for path in possible_paths:
                    try:
                        if path:
                            if os.path.exists(path):
                                print(f"    尝试路径: {path}")
                                service = EdgeService(executable_path=path)
                                driver = webdriver.Edge(service=service, options=options)
                            else:
                                continue
                        else:
                            driver = webdriver.Edge(options=options)
                        print("  ✓ 使用系统 EdgeDriver 成功")
                        return driver
                    except Exception as e:
                        continue
                
                print(f"  ⚠️ 系统 EdgeDriver 未找到")
                return None
            else:
                from selenium import webdriver
                print("  尝试使用系统 PATH 中的 ChromeDriver...")
                driver = webdriver.Chrome(options=options)
                print("  ✓ 使用系统 ChromeDriver 成功")
                return driver
                
        except Exception as e:
            print(f"  ⚠️ 系统驱动失败: {e}")
        
        return None
    
    def _try_local_driver(self, options):
        """
        尝试使用本地目录的驱动文件
        """
        script_dir = Path(__file__).parent.parent.parent  # 项目根目录
        
        if self.browser_type == "edge":
            driver_name = "msedgedriver.exe" if os.name == 'nt' else "msedgedriver"
        else:
            driver_name = "chromedriver.exe" if os.name == 'nt' else "chromedriver"
        
        local_driver_path = script_dir / driver_name
        
        if local_driver_path.exists():
            try:
                if self.browser_type == "edge":
                    from selenium import webdriver
                    from selenium.webdriver.edge.service import Service
                    print(f"  尝试使用本地 EdgeDriver: {local_driver_path}")
                    service = Service(str(local_driver_path))
                    driver = webdriver.Edge(service=service, options=options)
                    print("  ✓ 使用本地 EdgeDriver 成功")
                    return driver
                else:
                    from selenium import webdriver
                    from selenium.webdriver.chrome.service import Service
                    print(f"  尝试使用本地 ChromeDriver: {local_driver_path}")
                    service = Service(str(local_driver_path))
                    driver = webdriver.Chrome(service=service, options=options)
                    print("  ✓ 使用本地 ChromeDriver 成功")
                    return driver
                    
            except Exception as e:
                print(f"  ⚠️ 本地驱动失败: {e}")
        else:
            if self.driver_strategy == 'local':
                print(f"  ⚠️ 本地未找到 {driver_name}")
        
        return None
    
    def _inject_stealth_scripts(self, driver):
        """
        注入反检测脚本
        """
        try:
            driver.execute_cdp_cmd('Page.addScriptToEvaluateOnNewDocument', {
                'source': 'Object.defineProperty(navigator, "webdriver", {get: () => undefined})'
            })
            print("  ✓ 反检测脚本已注入")
        except Exception as e:
            print(f"  ⚠️ 注入反检测脚本失败: {e}")
    
    def _inject_hardware_fingerprint(self, driver):
        """
        注入硬件指纹混淆
        """
        cores = random.choice([4, 8, 12, 16])
        memory = random.choice([4, 8, 16, 32])
        
        try:
            driver.execute_cdp_cmd("Page.addScriptToEvaluateOnNewDocument", {
                "source": f"""
                    Object.defineProperty(navigator, 'hardwareConcurrency', {{
                        get: () => {cores}
                    }});
                    Object.defineProperty(navigator, 'deviceMemory', {{
                        get: () => {memory}
                    }});
                    const getParameter = WebGLRenderingContext.prototype.getParameter;
                    WebGLRenderingContext.prototype.getParameter = function(parameter) {{
                        if (parameter === 37445) {{
                            return 'Intel Inc.';
                        }}
                        if (parameter === 37446) {{
                            return 'Intel Iris OpenGL Engine';
                        }}
                        return getParameter(parameter);
                    }};
                """
            })
            print(f"  ✓ 硬件指纹已混淆 (CPU: {cores}核, 内存: {memory}GB)")
        except Exception as e:
            print(f"  ⚠️ 硬件指纹混淆失败: {e}")
    
    def _print_driver_help(self):
        """
        打印驱动配置帮助信息
        """
        browser_name = "Edge" if self.browser_type == "edge" else "Chrome"
        
        print("\n" + "=" * 70)
        print(f"❌ 无法启动 {browser_name} 浏览器！")
        print("=" * 70)
        
        if self.browser_type == "edge":
            print("\n请选择以下解决方案之一:\n")
            print("方案 1 (推荐): 安装 webdriver-manager")
            print("  pip install webdriver-manager")
            print()
            print("方案 2: 确认 Edge 浏览器已安装")
            print("  Edge 浏览器路径通常在:")
            print("  C:\\Program Files (x86)\\Microsoft\\Edge\\Application\\msedge.exe")
            print()
            print("方案 3: 手动下载 EdgeDriver")
            print("  1. 查看 Edge 版本: edge://version/")
            print("  2. 下载匹配版本: https://developer.microsoft.com/en-us/microsoft-edge/tools/webdriver/")
            print(f"  3. 解压 msedgedriver.exe 到项目根目录")
            print()
            print("方案 4: 改用 Chrome 浏览器")
            print("  在 config/config.yaml 中设置: browser.type: 'chrome'")
        else:
            print("\n请选择以下解决方案之一:\n")
            print("方案 1 (推荐): 安装 webdriver-manager")
            print("  pip install webdriver-manager")
            print()
            print("方案 2: 安装 undetected-chromedriver (反检测)")
            print("  pip install undetected-chromedriver")
            print()
            print("方案 3: 手动下载 ChromeDriver")
            print("  1. 查看 Chrome 版本: chrome://version/")
            print("  2. 下载匹配版本: https://chromedriver.chromium.org/downloads")
            print("     或: https://googlechromelabs.github.io/chrome-for-testing/")
            print(f"  3. 解压 chromedriver.exe 到项目根目录")
            print()
            print("方案 4: 使用国内镜像下载")
            print("  https://registry.npmmirror.com/binary.html?path=chromedriver/")
            print()
            print("方案 5: 改用 Edge 浏览器")
            print("  在 config/config.yaml 中设置: browser.type: 'edge'")
        
        print("=" * 70)
    
    @staticmethod
    def cleanup_driver(driver):
        """
        安全地清理 WebDriver 和临时文件
        """
        if not driver:
            return
        
        try:
            # 正常退出
            driver.quit()
        except:
            pass
        
        # 清理临时用户目录
        if hasattr(driver, '_temp_user_data_dir'):
            import shutil
            import time
            try:
                time.sleep(1)  # 等待进程释放文件锁
                shutil.rmtree(driver._temp_user_data_dir, ignore_errors=True)
                print("🧹 已清理临时目录")
            except:
                pass
        
        # 防止垃圾回收时再次调用 quit
        try:
            driver.quit = lambda: None
        except:
            pass


# 创建全局实例
browser_factory = BrowserFactory()


def create_driver(proxy_url=None, user_agent=None, locale=None, accept_language=None):
    """
    便捷函数：创建浏览器驱动
    """
    return browser_factory.create_driver(proxy_url, user_agent, locale, accept_language)


def cleanup_driver(driver):
    """
    便捷函数：清理浏览器驱动
    """
    BrowserFactory.cleanup_driver(driver)
