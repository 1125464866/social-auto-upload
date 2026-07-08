# -*- coding: utf-8 -*-
"""测试抖音作品页面评论按钮点击"""
import asyncio
import json
from pathlib import Path

try:
    from patchright.async_api import async_playwright
except ImportError:
    from playwright.async_api import async_playwright

from conf import LOCAL_CHROME_PATH, BASE_DIR
from utils.base_social_media import set_init_script
from utils.log import douyin_logger


TEST_URL = "https://www.douyin.com/note/7650166325662272809"


async def test_comment_btn():
    # 从数据库随机取一个正常抖音账号
    import sqlite3
    db_path = Path(BASE_DIR) / "db" / "database.db"
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        cursor.execute('SELECT id, filePath, userName FROM user_info WHERE type = 3 AND status = 1')
        rows = cursor.fetchall()

    if not rows:
        douyin_logger.error('[-] 未找到任何正常抖音账号')
        return

    import random
    account = random.choice(rows)
    cookie_file = Path(BASE_DIR) / "cookiesFile" / account['filePath']
    if not cookie_file.exists():
        douyin_logger.error(f'[-] Cookie文件不存在: {cookie_file}')
        return

    async with async_playwright() as playwright:
        user_data_dir = Path(BASE_DIR) / "browser_data" / "douyin_test_comment"
        user_data_dir.mkdir(parents=True, exist_ok=True)

        launch_kwargs = {
            "user_data_dir": str(user_data_dir),
            "headless": False
        }
        if LOCAL_CHROME_PATH:
            launch_kwargs["executable_path"] = LOCAL_CHROME_PATH

        context = await playwright.chromium.launch_persistent_context(**launch_kwargs)
        context = await set_init_script(context)

        await context.clear_cookies()
        with open(cookie_file, 'r', encoding='utf-8') as f:
            state = json.load(f)
        if 'cookies' in state:
            await context.add_cookies(state['cookies'])
        douyin_logger.info(f'[-] 已加载账号 {account["userName"]} 的Cookie')

        page = await context.new_page()
        douyin_logger.info(f'[-] 正在打开: {TEST_URL}')
        await page.goto(TEST_URL, wait_until="domcontentloaded", timeout=60000)

        # 等待页面充分加载
        douyin_logger.info('[-] 等待10秒让页面充分加载...')
        await asyncio.sleep(10)

        # 截图保存
        screenshot_path = Path(BASE_DIR) / "test_screenshot.png"
        await page.screenshot(path=str(screenshot_path), full_page=False)
        douyin_logger.info(f'[-] 截图已保存: {screenshot_path}')

        # ========== 第一步：用JS搜索页面所有含"评论"文字的元素 ==========
        douyin_logger.info('=' * 50)
        douyin_logger.info('用JS搜索页面所有含"评论"文字的元素...')

        all_elements = await page.evaluate('''() => {
            const results = [];
            const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT, null);
            while (walker.nextNode()) {
                const text = walker.currentNode.textContent.trim();
                if (text.includes("评论")) {
                    const el = walker.currentNode.parentElement;
                    if (el) {
                        results.push({
                            tag: el.tagName,
                            text: text.substring(0, 60),
                            className: (el.className || '').toString().substring(0, 80),
                            visible: el.offsetWidth > 0 && el.offsetHeight > 0,
                            rect: el.getBoundingClientRect().toString()
                        });
                    }
                }
            }
            return results;
        }''')

        douyin_logger.info(f'找到 {len(all_elements)} 个含"评论"文字的元素:')
        for i, el in enumerate(all_elements):
            douyin_logger.info(f'  [{i+1}] <{el["tag"]} class="{el["className"]}"> text="{el["text"]}" visible={el["visible"]}')

        # ========== 第二步：测试各种选择器 ==========
        douyin_logger.info('=' * 50)
        douyin_logger.info('测试选择器...')

        selectors = [
            'xpath=//div[contains(text(), "评论(")]',
            'xpath=//*[contains(text(), "评论(")]',
            'xpath=//*[starts-with(text(), "评论")]',
            'text=评论(',
            ':text("评论(")',
            'div:has-text("评论(")',
        ]

        for selector in selectors:
            try:
                count = await page.locator(selector).count()
                douyin_logger.info(f'  [{selector}] 匹配: {count}')
                for i in range(min(count, 3)):
                    el = page.locator(selector).nth(i)
                    text = await el.inner_text()
                    visible = await el.is_visible()
                    tag = await el.evaluate('e => e.tagName')
                    douyin_logger.info(f'    #{i+1}: <{tag}> text="{text[:40]}" visible={visible}')
            except Exception as e:
                douyin_logger.info(f'  [{selector}] 失败: {e}')

        # ========== 第三步：尝试点击 ==========
        douyin_logger.info('=' * 50)
        douyin_logger.info('尝试点击...')

        # 先等2秒再试
        await asyncio.sleep(2)

        # 用最宽泛的选择器
        comment_btn = page.locator('xpath=//*[contains(text(), "评论(")]')
        count = await comment_btn.count()
        douyin_logger.info(f'[//*[contains(text(), "评论(")]] 匹配: {count}')

        if count > 0:
            for i in range(count):
                el = comment_btn.nth(i)
                try:
                    text = await el.inner_text()
                    visible = await el.is_visible()
                    douyin_logger.info(f'  候选{i+1}: text="{text}" visible={visible}')
                    if visible:
                        await el.click(force=True)
                        douyin_logger.success(f'[+] 成功点击第{i+1}个元素!')
                        break
                except Exception as e:
                    douyin_logger.info(f'  候选{i+1} 操作失败: {e}')
            else:
                # 全不可见，尝试 force click 第一个
                douyin_logger.warning('[-] 所有元素不可见，尝试force click第1个...')
                try:
                    await comment_btn.first.click(force=True)
                    douyin_logger.success('[+] force click成功!')
                except Exception as e:
                    douyin_logger.error(f'[-] force click也失败: {e}')
        else:
            douyin_logger.warning('[-] 未找到任何匹配元素，可能Cookie失效或页面未加载')

        # 等待观察
        douyin_logger.info('[-] 测试完成，30秒后关闭浏览器...')
        await asyncio.sleep(30)
        await context.close()


if __name__ == '__main__':
    asyncio.run(test_comment_btn())
