import asyncio
import configparser
import os

from playwright.async_api import async_playwright
from xhs import XhsClient

from conf import BASE_DIR, LOCAL_CHROME_HEADLESS
from utils.base_social_media import set_init_script
from utils.log import tencent_logger, kuaishou_logger, douyin_logger
from pathlib import Path
from uploader.xhs_uploader.main import sign_local


async def cookie_auth_douyin(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=LOCAL_CHROME_HEADLESS)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        page = await context.new_page()

        try:
            await page.goto("https://creator.douyin.com/creator-micro/content/upload",
                            timeout=60000, wait_until="domcontentloaded")
            # 等网络空闲，确保登录浮层/内容都已渲染
            try:
                await page.wait_for_load_state("networkidle", timeout=15000)
            except:
                pass

            # 未登录指示器：登录/注册按钮 或 扫码登录
            login_btn = page.locator('div[class*="douyin_login_comp_btn"]').or_(
                page.get_by_text("登录/注册")).or_(page.get_by_text("扫码登录"))
            # 已登录指示器：发布图文/发布视频 选项卡 或 文件上传框
            logged_in = page.get_by_text("发布视频").or_(
                page.get_by_text("发布图文")).or_(page.locator('input[type="file"]'))

            async def wait_not_logged():
                await login_btn.first.wait_for(state="visible", timeout=55000)
                return False  # 出现登录按钮 → 失效

            async def wait_logged():
                await logged_in.first.wait_for(state="visible", timeout=55000)
                return True  # 出现上传界面 → 有效

            # 竞态：两种信号谁先出现谁赢，不再依赖固定超时，最多等1分钟
            done, pending = await asyncio.wait(
                [asyncio.create_task(wait_not_logged()),
                 asyncio.create_task(wait_logged())],
                return_when=asyncio.FIRST_COMPLETED,
                timeout=60
            )
            for t in pending:
                t.cancel()

            if not done:
                # 1分钟都没出现明确信号，按失效处理（保守判断）
                douyin_logger.error("[-] 1分钟内未确定登录状态，按失效处理")
                return False

            result = done.pop().result()
            if result:
                douyin_logger.success("[+]  cookie 有效")
            else:
                douyin_logger.error("[+] cookie 失效，需要扫码登录")
            return result
        except Exception as e:
            douyin_logger.error(f"[+] cookie 检测异常: {e}")
            return False
        finally:
            await context.close()
            await browser.close()


async def cookie_auth_tencent(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=LOCAL_CHROME_HEADLESS)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://channels.weixin.qq.com/platform/post/create")
        try:
            await page.wait_for_selector('div.title-name:has-text("微信小店")', timeout=5000)  # 等待5秒
            tencent_logger.error("[+] 等待5秒 cookie 失效")
            return False
        except:
            tencent_logger.success("[+] cookie 有效")
            return True


async def cookie_auth_ks(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=LOCAL_CHROME_HEADLESS)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://cp.kuaishou.com/article/publish/video")
        try:
            await page.wait_for_selector("div.names div.container div.name:text('机构服务')", timeout=5000)  # 等待5秒

            kuaishou_logger.info("[+] 等待5秒 cookie 失效")
            return False
        except:
            kuaishou_logger.success("[+] cookie 有效")
            return True


async def cookie_auth_xhs(account_file):
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(headless=LOCAL_CHROME_HEADLESS)
        context = await browser.new_context(storage_state=account_file)
        context = await set_init_script(context)
        # 创建一个新的页面
        page = await context.new_page()
        # 访问指定的 URL
        await page.goto("https://creator.xiaohongshu.com/creator-micro/content/upload")
        try:
            await page.wait_for_url("https://creator.xiaohongshu.com/creator-micro/content/upload", timeout=5000)
        except:
            print("[+] 等待5秒 cookie 失效")
            await context.close()
            await browser.close()
            return False
        # 2024.06.17 抖音创作者中心改版
        if await page.get_by_text('手机号登录').count() or await page.get_by_text('扫码登录').count():
            print("[+] 等待5秒 cookie 失效")
            return False
        else:
            print("[+] cookie 有效")
            return True


async def check_cookie(type, file_path):
    match type:
        # 小红书
        case 1:
            return await cookie_auth_xhs(Path(BASE_DIR / "cookiesFile" / file_path))
        # 视频号
        case 2:
            return await cookie_auth_tencent(Path(BASE_DIR / "cookiesFile" / file_path))
        # 抖音
        case 3:
            return await cookie_auth_douyin(Path(BASE_DIR / "cookiesFile" / file_path))
        # 快手
        case 4:
            return await cookie_auth_ks(Path(BASE_DIR / "cookiesFile" / file_path))
        case _:
            return False

# a = asyncio.run(check_cookie(1,"3a6cfdc0-3d51-11f0-8507-44e51723d63c.json"))
# print(a)
