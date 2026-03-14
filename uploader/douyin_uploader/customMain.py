# -*- coding: utf-8 -*-
from datetime import datetime
import random

# 尝试使用 patchright，如果不存在则回退到 playwright
try:
    from patchright.async_api import Playwright, async_playwright, Page
    douyin_logger_patchright = True
except ImportError:
    from playwright.async_api import Playwright, async_playwright, Page
    douyin_logger_patchright = False

import os
import asyncio
from pathlib import Path
import json

from conf import LOCAL_CHROME_PATH, BASE_DIR
from utils.base_social_media import set_init_script
from utils.log import douyin_logger


def random_sleep(min_sec=0.5, max_sec=2.0):
    """随机延迟，模拟人类操作"""
    return asyncio.sleep(random.uniform(min_sec, max_sec))


class DouYinImage(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, description='', productLink='', productTitle='', music_name='', music_type='search', comment=''):
        self.title = title  # 作品标题（最多30字）
        self.description = description  # 作品描述
        self.file_path = file_path  # 支持单张图片或图片列表
        self.tags = tags  # 标签列表
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH
        self.productLink = productLink
        self.productTitle = productTitle
        self.music_name = music_name  # 背景音乐名称
        self.music_type = music_type  # 音乐类型: search(搜索) 或 fav(收藏)
        self.comment = comment  # 发布后要评论的内容
        douyin_logger.info(f'评论内容: {self.comment}')
        self.work_url = None  # 发布成功后保存作品URL
        self.comment_result = False  # 评论检测结果：True-成功，False-失败

    async def set_schedule_time_douyin(self, page, publish_date):
        # 选择包含特定文本内容的 label 元素
        label_element = page.locator("[class^='radio']:has-text('定时发布')")
        # 在选中的 label 元素下点击 checkbox
        await label_element.click()
        await asyncio.sleep(1)
        publish_date_hour = publish_date.strftime("%Y-%m-%d %H:%M")

        await asyncio.sleep(1)
        await page.locator('.semi-input[placeholder="日期和时间"]').click()
        await page.keyboard.press("Control+KeyA")
        await page.keyboard.type(str(publish_date_hour))
        await page.keyboard.press("Enter")

        await asyncio.sleep(1)

    async def get_work_url_from_manage_page(self, page):
        """从作品管理页面获取刚发布的作品URL"""
        try:
            douyin_logger.info('[-] 正在获取刚发布的作品URL...')

            # 等待10秒后刷新页面
            await asyncio.sleep(10)
            douyin_logger.info('[-] 刷新页面...')
            await page.reload()
            await asyncio.sleep(3)

            # 循环等待并点击第一个作品封面区域，最多等待20秒
            video_cover_found = False
            for i in range(20):
                video_cover = page.locator('div.video-card-cover-xx9wyS').first
                if await video_cover.count() > 0:
                    await video_cover.click()
                    douyin_logger.info(f'[+] 第{i+1}次尝试，成功点击第一个作品封面')
                    video_cover_found = True
                    break
                else:
                    douyin_logger.info(f'[-] 第{i+1}/20次尝试，未找到作品封面，1秒后重试...')
                    await asyncio.sleep(1)

            if video_cover_found:
                await asyncio.sleep(2)

                # 循环等待iframe加载，最多等待20秒
                for i in range(20):
                    # 获取iframe_wrapper的HTML内容
                    iframe_wrapper = page.locator('div.iframe-wrapper-Y9kFxO').first
                    if await iframe_wrapper.count() > 0:
                        wrapper_html = await iframe_wrapper.inner_html()
                        douyin_logger.info(f'[DEBUG] 第{i+1}次尝试 - iframe_wrapper HTML: {wrapper_html[:500]}')

                        # 从HTML内容中直接提取作品ID
                        import re
                        match = re.search(r'creatorvideo/(\d+)', wrapper_html)
                        if match:
                            work_id = match.group(1)
                            self.work_url = f"https://www.douyin.com/note/{work_id}"
                            douyin_logger.success(f'[+] 成功获取作品URL: {self.work_url}')

                            # 如果有评论内容，跳转到创作者中心评论管理页面发布评论
                            if self.comment:
                                douyin_logger.info('[-] 正在跳转到创作者中心评论管理页面...')
                                await page.goto("https://creator.douyin.com/creator-micro/interactive/comment")
                                await asyncio.sleep(3)

                                # 查找评论输入框 - 15秒检测时长，每秒检测一次
                                douyin_logger.info('[-] 正在查找评论输入框...')
                                comment_input_found = False
                                for i in range(15):
                                    try:
                                        comment_input = page.locator('div.input-d24X73[contenteditable="true"]').first
                                        if await comment_input.count() > 0:
                                            # 点击输入框获取焦点
                                            await comment_input.click()
                                            await asyncio.sleep(0.5)
                                            douyin_logger.info(f'[+] 第{i+1}次尝试，成功点击评论输入框')
                                            comment_input_found = True
                                            break
                                    except Exception as e:
                                        douyin_logger.debug(f'[-] 第{i+1}次点击评论输入框失败: {e}')
                                    await asyncio.sleep(1)

                                if comment_input_found:
                                    # 输入评论内容
                                    await page.keyboard.type(self.comment)
                                    douyin_logger.info(f'[+] 已输入评论内容: {self.comment}')
                                    await asyncio.sleep(0.5)

                                    # 点击发送按钮 - 15秒检测时长，每秒检测一次
                                    douyin_logger.info('[-] 正在查找发送按钮...')
                                    send_btn_found = False
                                    for i in range(15):
                                        try:
                                            send_btn = page.locator('button.douyin-creator-interactive-button:has-text("发送")').first
                                            if await send_btn.count() > 0:
                                                await send_btn.click()
                                                douyin_logger.info(f'[+] 第{i+1}次尝试，成功点击发送按钮')
                                                send_btn_found = True
                                                break
                                        except Exception as e:
                                            douyin_logger.debug(f'[-] 第{i+1}次点击发送按钮失败: {e}')
                                        await asyncio.sleep(1)

                                    if send_btn_found:
                                        await asyncio.sleep(2)
                                        douyin_logger.success('[+] 评论发布成功')
                                    else:
                                        douyin_logger.warning('[-] 15秒内未找到发送按钮')
                                else:
                                    douyin_logger.warning('[-] 15秒内未找到评论输入框')

                            return self.work_url
                        else:
                            douyin_logger.warning('[-] 未从iframe中提取到作品ID')

                        return self.work_url

                    douyin_logger.info(f'[-] 第{i+1}/20次尝试，未找到iframe_wrapper，1秒后重试...')
                    await asyncio.sleep(1)

                douyin_logger.error('[-] 20秒内未能从iframe中提取作品ID')
            else:
                douyin_logger.error('[-] 20秒内未找到作品封面')

            return None

        except Exception as e:
            douyin_logger.error(f'[-] 获取作品URL失败: {e}')
            return None

    async def check_comment_with_another_account(self, playwright, work_url, comment_text):
        """使用另一个非异常账号检查评论是否存在"""
        import random
        import sqlite3
        import uuid
        import shutil

        try:
            douyin_logger.info('[-] 正在准备使用另一个账号检查评论...')

            # 从数据库获取所有非异常的抖音账号（status=1 表示正常）
            db_path = Path(BASE_DIR) / "db" / "database.db"
            if not db_path.exists():
                douyin_logger.warning('[-] 数据库文件不存在，跳过评论检查')
                return False

            with sqlite3.connect(db_path) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                # type=3 表示抖音，status=1 表示正常（非异常）
                cursor.execute('SELECT id, filePath, userName FROM user_info WHERE type = 3 AND status = 1')
                rows = cursor.fetchall()

            if not rows:
                douyin_logger.warning('[-] 未找到任何正常的抖音账号，跳过评论检查')
                return False

            # 排除当前账号（通过 filePath 匹配）
            current_cookie_path = str(Path(self.account_file).resolve())
            other_accounts = [row for row in rows if str(Path(BASE_DIR) / "cookiesFile" / row['filePath']).replace('\\', '/') != current_cookie_path.replace('\\', '/')]

            if not other_accounts:
                douyin_logger.warning('[-] 未找到其他正常的抖音账号，跳过评论检查')
                return False

            # 随机选择一个账号
            selected_account = random.choice(other_accounts)
            douyin_logger.info(f'[-] 随机选择账号: {selected_account["userName"]} (ID: {selected_account["id"]})')

            # 获取 cookie 文件路径
            cookie_file = Path(BASE_DIR) / "cookiesFile" / selected_account['filePath']
            if not cookie_file.exists():
                douyin_logger.warning(f'[-] Cookie文件不存在: {cookie_file}')
                return False

            # 使用唯一的临时目录，避免旧数据干扰
            unique_id = str(uuid.uuid4())[:8]
            user_data_dir = Path(BASE_DIR) / "browser_data" / f"douyin_check_{unique_id}"
            user_data_dir.mkdir(parents=True, exist_ok=True)

            # 用户是否手动关闭了浏览器的标志
            user_closed_browser = False

            context = None
            page = None
            try:
                launch_kwargs = {
                    "user_data_dir": str(user_data_dir),
                    "headless": False
                }
                if self.local_executable_path:
                    launch_kwargs["executable_path"] = self.local_executable_path

                context = await playwright.chromium.launch_persistent_context(**launch_kwargs)
                context = await set_init_script(context)

                # 监听浏览器关闭事件
                async def on_context_close():
                    nonlocal user_closed_browser
                    user_closed_browser = True
                    douyin_logger.warning('[-] 检测到用户手动关闭了浏览器')

                context.on("close", lambda: asyncio.create_task(on_context_close()))

                # 先清除可能存在的旧 cookie，再加载新账号的 cookie
                await context.clear_cookies()

                # 加载选中账号的 cookie
                with open(cookie_file, 'r', encoding='utf-8') as f:
                    state = json.load(f)
                if 'cookies' not in state:
                    douyin_logger.warning(f'[-] Cookie 文件中没有 cookies 数据')
                    await context.close()
                    return False

                await context.add_cookies(state['cookies'])
                douyin_logger.info(f'[-] 已加载账号 {selected_account["userName"]} 的 Cookie')

                page = await context.new_page()

                # 打开作品页面
                douyin_logger.info(f'[-] 正在打开作品页面: {work_url}')
                await page.goto(work_url, wait_until="domcontentloaded", timeout=60000)
                await asyncio.sleep(3)

                # 检测登录状态 - 10秒检测时长，每秒检测一次
                douyin_logger.info('[-] 正在检测登录状态...')
                login_required = False
                for i in range(10):
                    # 检查用户是否关闭了浏览器
                    if user_closed_browser:
                        douyin_logger.warning('[-] 用户已手动关闭浏览器，终止评论检测')
                        return False
                    try:
                        login_prompt = page.locator('div.mV5mWhEp:has-text("登录后免费畅享高清视频")').first
                        if await login_prompt.count() > 0:
                            douyin_logger.warning(f'[-] 第{i+1}次检测，发现登录提示，该 Cookie 已失效')
                            login_required = True
                            break
                    except Exception as e:
                        douyin_logger.debug(f'[-] 第{i+1}次检测登录状态失败: {e}')
                    await asyncio.sleep(1)

                if login_required:
                    douyin_logger.warning(f'[-] 账号 {selected_account["userName"]} Cookie 已失效')
                    await context.close()
                    return False

                douyin_logger.info('[+] 登录状态正常，继续评论检测')

                # 评论检测循环 - 最多6次刷新重试
                comment_found = False
                max_retry_times = 6
                comment_prefix = comment_text[:2] if len(comment_text) >= 2 else comment_text
                douyin_logger.info(f'[-] 开始评论检测，最多{max_retry_times}轮，匹配前缀: {comment_prefix}')

                for retry in range(max_retry_times):
                    # 检查用户是否关闭了浏览器
                    if user_closed_browser:
                        douyin_logger.warning('[-] 用户已手动关闭浏览器，终止评论检测')
                        return False

                    douyin_logger.info(f'[-] ===== 第 {retry + 1}/{max_retry_times} 轮评论检测 =====')

                    # 点击评论按钮 - 15秒检测时长，每秒检测一次
                    douyin_logger.info('[-] 正在查找评论按钮...')
                    comment_btn_found = False
                    for i in range(15):
                        # 检查用户是否关闭了浏览器
                        if user_closed_browser:
                            douyin_logger.warning('[-] 用户已手动关闭浏览器，终止评论检测')
                            return False
                        try:
                            comment_btn = page.locator('div.cxpsBymd.kNtvycrk').first
                            if await comment_btn.count() > 0:
                                await comment_btn.click()
                                douyin_logger.info(f'[+] 第{i+1}次尝试，成功点击评论按钮')
                                comment_btn_found = True
                                break
                        except Exception as e:
                            douyin_logger.debug(f'[-] 第{i+1}次点击评论按钮失败: {e}')
                        await asyncio.sleep(1)

                    if not comment_btn_found:
                        douyin_logger.warning(f'[-] 第 {retry + 1} 轮：15秒内未找到评论按钮')
                        # 刷新页面继续下一轮
                        if retry < max_retry_times - 1:
                            douyin_logger.info(f'[-] 刷新页面，准备第 {retry + 2} 轮检测...')
                            await page.reload(wait_until="domcontentloaded", timeout=60000)
                            await asyncio.sleep(3)
                        continue

                    await asyncio.sleep(2)

                    # 查找评论 - 10秒检测时长，每秒检测一次
                    for i in range(10):
                        # 检查用户是否关闭了浏览器
                        if user_closed_browser:
                            douyin_logger.warning('[-] 用户已手动关闭浏览器，终止评论检测')
                            return False

                        try:
                            # 查找所有评论项
                            comment_items = page.locator('div.Vrj4Q3zT.fiDvPS80')
                            count = await comment_items.count()

                            if count > 0:
                                douyin_logger.info(f'[-] 第{i+1}次尝试，找到 {count} 条评论')

                                for j in range(count):
                                    try:
                                        item = comment_items.nth(j)
                                        # 获取评论文本内容 - 排除作者名称（有 xtTwhlGw class 的是作者名）
                                        comment_content = item.locator('span.arnSiSbK:not(.xtTwhlGw)').first
                                        if await comment_content.count() > 0:
                                            text = await comment_content.inner_text()
                                            if len(text) > 50:
                                                douyin_logger.info(f'[-] 评论 {j+1}: {text[:50]}...')
                                            else:
                                                douyin_logger.info(f'[-] 评论 {j+1}: {text}')

                                            # 检查是否匹配 - 只匹配前两个字符
                                            if comment_prefix in text:
                                                douyin_logger.success(f'[+] ✅ 找到匹配的评论！内容: {text}')
                                                comment_found = True
                                                break
                                    except Exception as e:
                                        douyin_logger.debug(f'[-] 解析评论 {j+1} 失败: {e}')
                                        continue

                                if comment_found:
                                    break
                            else:
                                douyin_logger.info(f'[-] 第{i+1}/15次尝试，暂未找到评论，等待1秒后重试...')

                        except Exception as e:
                            douyin_logger.debug(f'[-] 第 {i+1} 次查找评论失败: {e}')

                        await asyncio.sleep(1)

                    if comment_found:
                        break

                    # 本轮未找到评论，刷新页面继续下一轮
                    if retry < max_retry_times - 1:
                        douyin_logger.warning(f'[-] 第 {retry + 1} 轮未找到评论，刷新页面重试...')
                        await page.reload(wait_until="domcontentloaded", timeout=60000)
                        await asyncio.sleep(3)

                if comment_found:
                    douyin_logger.success('[+] 评论检测完成，评论已成功发布！')
                    await context.close()
                    return True
                else:
                    douyin_logger.warning(f'[-] {max_retry_times} 轮检测后仍未找到匹配的评论: {comment_text}')
                    await context.close()
                    return False

            except Exception as e:
                douyin_logger.error(f'[-] 使用账号 {selected_account["userName"]} 检测失败: {e}')
                # 检查是否是用户手动关闭导致的错误
                if user_closed_browser:
                    douyin_logger.warning('[-] 用户已手动关闭浏览器，终止评论检测')
                    return False
                if context:
                    try:
                        await context.close()
                    except:
                        pass
                return False
            finally:
                # 清理临时目录
                try:
                    if user_data_dir.exists():
                        shutil.rmtree(user_data_dir, ignore_errors=True)
                except:
                    pass

        except Exception as e:
            douyin_logger.error(f'[-] 检查评论失败: {e}')
            return False

    async def handle_upload_error(self, page):
        douyin_logger.info('图片出错了，重新上传中')
        # 图片上传错误处理，重新选择文件
        if isinstance(self.file_path, list):
            await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files(self.file_path)
        else:
            await page.locator('div.progress-div [class^="upload-btn-input"]').set_input_files([self.file_path])

    async def set_background_music(self, page, music_name, music_type='search'):
        """设置背景音乐"""
        try:
            douyin_logger.info(f"[-] 正在设置背景音乐: {music_name}, 类型: {music_type}")
            
            # 点击"选择音乐"按钮
            music_selectors = [
                'span.action-Q1y01k:has-text("选择音乐")',
                'text="选择音乐"',
                '[class*="action"]:has-text("选择音乐")',
                'button:has-text("选择音乐")'
            ]
            
            music_button_clicked = False
            for selector in music_selectors:
                try:
                    music_button = page.locator(selector)
                    if await music_button.count() > 0:
                        await music_button.click()
                        await asyncio.sleep(2)
                        douyin_logger.info(f"[+] 成功点击选择音乐按钮 (选择器: {selector})")
                        music_button_clicked = True
                        break
                except Exception as e:
                    douyin_logger.debug(f"[-] 音乐按钮选择器 {selector} 失败: {e}")
                    continue
            
            if not music_button_clicked:
                douyin_logger.warning("[-] 未找到选择音乐按钮")
                return False

            # 如果是收藏音乐模式
            if music_type == 'fav':
                # 点击收藏标签
                try:
                    fav_tab = page.locator('div[data-scrollkey="fav-1-bar"]')
                    if await fav_tab.count() > 0:
                        await fav_tab.click()
                        await asyncio.sleep(2)
                        douyin_logger.info("[+] 成功点击收藏标签")
                        
                        # 等待音乐列表加载
                        await asyncio.sleep(2)
                        
                        # 获取要选择的第几个音乐 (music_name 应该是数字字符串)
                        try:
                            index = int(music_name)
                            if index < 1:
                                index = 1
                        except ValueError:
                            index = 1
                            douyin_logger.warning(f"[-] 收藏音乐序号格式错误: {music_name}，默认使用第1个")
                        
                        douyin_logger.info(f"[-] 正在选择第 {index} 个收藏音乐...")
                        
                        # 等待音乐列表容器出现
                        music_container = page.locator('div.music-collection-container-cTsB7J')
                        if await music_container.count() > 0:
                            # 找到所有音乐项
                            music_items = await music_container.locator('div.card-container-tmocjc').all()
                            
                            if len(music_items) >= index:
                                target_item = music_items[index-1]  # 0-indexed
                                
                                # 先悬停在目标音乐项上
                                await target_item.hover()
                                await asyncio.sleep(1)
                                
                                # 寻找并点击使用按钮
                                use_button = target_item.locator('button.apply-btn-LUPP0D:has-text("使用")')
                                if await use_button.count() > 0:
                                    await use_button.click()
                                    await asyncio.sleep(2)
                                    douyin_logger.info(f"[+] 成功选择第 {index} 个收藏音乐")
                                    return True
                                else:
                                    douyin_logger.warning(f"[-] 第 {index} 个音乐项的使用按钮未找到")
                            else:
                                douyin_logger.warning(f"[-] 收藏音乐数量不足，只有 {len(music_items)} 个，无法选择第 {index} 个")
                        else:
                            douyin_logger.warning("[-] 音乐列表容器未找到")
                            
                        return False
                    else:
                        douyin_logger.warning("[-] 未找到收藏标签")
                        return False
                except Exception as e:
                    douyin_logger.error(f"[-] 选择收藏音乐失败: {e}")
                    return False
            
            # 在搜索框中输入音乐名称
            search_input = page.locator('input.semi-input[placeholder="搜索音乐"]')
            if await search_input.count() > 0:
                await search_input.click()
                await search_input.fill(music_name)
                await asyncio.sleep(3)  # 等待搜索结果加载
                douyin_logger.info(f"[+] 已输入音乐名称: {music_name}")
            else:
                douyin_logger.warning("[-] 未找到音乐搜索框")
                return False
            
            # 等待音乐列表加载并点击第一个音乐项的"使用"按钮
            max_wait_attempts = 50
            wait_attempt = 0
            use_button_clicked = False
            
            while not use_button_clicked and wait_attempt < max_wait_attempts:
                wait_attempt += 1
                douyin_logger.info(f"[DEBUG] 第 {wait_attempt} 次尝试寻找音乐使用按钮...")
                
                # 等待音乐列表容器出现
                music_container = page.locator('div.music-collection-container-cTsB7J')
                if await music_container.count() > 0:
                    # 找到第一个音乐项的使用按钮
                    first_use_button = music_container.locator('div.card-container-tmocjc').first.locator('button.apply-btn-LUPP0D:has-text("使用")')
                    
                    if await first_use_button.count() > 0:
                        # 先悬停在第一个音乐项上
                        first_music_item = music_container.locator('div.card-container-tmocjc').first
                        await first_music_item.hover()
                        await asyncio.sleep(1)
                        douyin_logger.info("[+] 已悬停在第一个音乐项上")
                        
                        # 点击使用按钮
                        await first_use_button.click()
                        await asyncio.sleep(2)
                        douyin_logger.info("[+] 成功选择背景音乐")
                        use_button_clicked = True
                        break
                    else:
                        douyin_logger.debug("[-] 第一个音乐项的使用按钮未找到")
                else:
                    douyin_logger.debug("[-] 音乐列表容器未找到")
                
                await asyncio.sleep(0.5)  # 等待后重试
            
            if use_button_clicked:
                return True
            else:
                douyin_logger.warning("[-] 未找到使用按钮")
                return False
                
        except Exception as e:
            douyin_logger.error(f"[-] 设置背景音乐失败: {e}")
            return False

    async def upload(self, playwright: Playwright) -> None:
        try:
            # 使用 Chromium 浏览器启动一个浏览器实例
            # 使用固定的用户数据目录，避免每次被认为是新设备
            # 从 account_file 中提取账号名作为目录名
            account_name = Path(self.account_file).stem  # 获取文件名（不含扩展名）
            user_data_dir = Path(BASE_DIR) / "browser_data" / f"douyin_{account_name}"
            user_data_dir.mkdir(parents=True, exist_ok=True)

            douyin_logger.info(f'[-] 使用浏览器数据目录: {user_data_dir}')
            if douyin_logger_patchright:
                douyin_logger.info('[-] 使用 patchright 模式（反检测增强）')
            else:
                douyin_logger.warning('[-] 未安装 patchright，使用普通 playwright 模式')

            context = None
            if self.local_executable_path:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    headless=False,
                    executable_path=self.local_executable_path
                )
            else:
                context = await playwright.chromium.launch_persistent_context(
                    user_data_dir=str(user_data_dir),
                    headless=False
                )

            # 加载cookie
            if os.path.exists(self.account_file):
                with open(self.account_file, 'r', encoding='utf-8') as f:
                    cookies = json.load(f)
                    if 'cookies' in cookies:
                        await context.add_cookies(cookies['cookies'])

            context = await set_init_script(context)

            # 创建一个新的页面
            page = await context.new_page()
            # 访问指定的 URL
            await page.goto("https://creator.douyin.com/creator-micro/content/upload")

            # 检查是否登录（页面渲染延迟时加两级兜底）
            try:
                # 1. 增加等待，确保登录组件渲染
                await page.wait_for_load_state("networkidle")

                # 2. 定位“登录/注册”按钮
                # 使用 class 包含匹配，这样即使后面的后缀变了也能搜到
                login_btn_selector = 'div[class*="douyin_login_comp_btn"]:has-text("登录/注册")'
                login_btn = page.locator(login_btn_selector)

                # 3. 兜底定位：如果上面的失效，尝试直接匹配文字
                fallback_text = page.get_by_text("登录/注册")

                # 只要这两个定位器有一个被发现，且是可见的，就判定为未登录
                if await login_btn.count() > 0 or await fallback_text.is_visible():
                    douyin_logger.error('[+] 检测到“登录/注册”按钮，账号未登录')
                    raise Exception("未登录，请先登录账号")

            except Exception as e:
                if "未登录" in str(e):
                    raise
                douyin_logger.debug(f"[-] 登录检测过程中捕获到异常: {e}")
        
            # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
            douyin_logger.info(f'[-] 正在打开主页...')
            await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload")
        
            # 点击"发布图文"选项卡
            douyin_logger.info("[-] 正在寻找发布图文选项卡...")
            
            # 多种可能的选择器来定位"发布图文"
            image_text_selectors = [
                'text="发布图文"',
                ':text("发布图文")',
                '[role="tab"]:has-text("发布图文")',
                '.tab:has-text("发布图文")',
                'div:has-text("发布图文")',
                'span:has-text("发布图文")'
            ]
            
            tab_found = False
            for attempt in range(60):  # 最多尝试60次，每次间隔0.5秒
                for selector in image_text_selectors:
                    try:
                        tab_element = page.locator(selector)
                        if await tab_element.count() > 0:
                            await tab_element.click()
                            await asyncio.sleep(2)
                            douyin_logger.info(f"[+] 成功点击发布图文选项卡 (选择器: {selector})")
                            tab_found = True
                            break
                    except Exception as e:
                        douyin_logger.debug(f"[-] 发布图文选择器 {selector} 失败: {e}")
                        continue
                
                if tab_found:
                    break
                
                douyin_logger.debug(f"[-] 第 {attempt + 1} 次尝试未找到发布图文选项卡，等待0.5秒后重试...")
                await asyncio.sleep(0.5)
            
            if not tab_found:
                douyin_logger.error("[-] 未找到发布图文选项卡")
                raise Exception("未找到发布图文选项卡")
            
            douyin_logger.info("[-] 成功进入发布图文流程")
            
            # 等待上传区域出现并上传图片
            douyin_logger.info("[-] 正在寻找图片上传区域...")
            
            # 寻找图片input元素
            for attempt in range(20):  # 最多尝试20次，每次间隔0.5秒
                try:
                    # 优先寻找accept属性包含image的input
                    image_inputs = await page.locator('input[type="file"]').all()
                    target_input = None
                    
                    for input_elem in image_inputs:
                        accept_attr = await input_elem.get_attribute('accept')
                        if accept_attr and 'image' in accept_attr:
                            target_input = input_elem
                            break
                    
                    # 如果没找到专门的图片input，使用第一个文件input
                    if not target_input and image_inputs:
                        target_input = image_inputs[0]
                    
                    if target_input:
                        # 上传图片文件
                        if isinstance(self.file_path, list):
                            await target_input.set_input_files(self.file_path)
                        else:
                            await target_input.set_input_files([self.file_path])
                        
                        douyin_logger.info("[+] 成功上传图片文件")
                        break
                    else:
                        douyin_logger.debug(f"[-] 第 {attempt + 1} 次尝试未找到图片input，等待0.5秒后重试...")
                        await asyncio.sleep(0.5)
                        
                except Exception as e:
                    douyin_logger.debug(f"[-] 第 {attempt + 1} 次上传尝试失败: {e}")
                    await asyncio.sleep(0.5)
            else:
                raise Exception("未找到图片上传input元素")

            # 等待页面跳转到发布页面
            while True:
                try:
                    # 尝试等待图文发布页面URL
                    current_url = page.url
                    if "publish" in current_url or "post" in current_url:
                        if "media_type=image" in current_url or "type=new" in current_url:
                            douyin_logger.info("[+] 成功进入图文发布页面!")
                            break
                        else:
                            # 通用发布页面检查
                            await page.wait_for_url("**/publish**", timeout=3000)
                            douyin_logger.info("[+] 成功进入发布页面!")
                            break
                    else:
                        await asyncio.sleep(0.5)
                except Exception:
                    douyin_logger.debug("[-] 等待进入发布页面...")
                    await asyncio.sleep(0.5)

            # 填充标题、描述和话题
            await asyncio.sleep(1)
            douyin_logger.info(f'[-] 正在填充标题、描述和话题...')
        
            # 填充标题（最多20字）- 等待标题输入框加载
            title_input = page.locator('input[placeholder="添加作品标题"]')
            for attempt in range(20):
                if await title_input.count():
                    await title_input.fill(self.title[:20])
                    douyin_logger.info(f'[+] 已填充标题: {self.title[:20]}')
                    break
                douyin_logger.debug(f"[-] 第 {attempt + 1} 次等待标题输入框...")
                await asyncio.sleep(0.5)
            else:
                douyin_logger.warning('[-] 未找到标题输入框')
        
            # 填充描述和话题标签（zone-container）
            css_selector = ".zone-container"
            # 等待描述容器出现
            description_container = page.locator(css_selector)
            for attempt in range(20):
                if await description_container.count():
                    break
                douyin_logger.debug(f"[-] 第 {attempt + 1} 次等待描述容器...")
                await asyncio.sleep(0.5)
        
            if await description_container.count():
                await description_container.click()
                await asyncio.sleep(0.5)
            
                # 先填充描述内容
                if self.description:
                    await page.keyboard.type(self.description)
                    await page.keyboard.press("Enter")
                    douyin_logger.info(f'[+] 已填充描述: {self.description[:50]}...' if len(self.description) > 50 else f'[+] 已填充描述: {self.description}')
                    await asyncio.sleep(0.5)
            
                # 再填充话题标签
                for index, tag in enumerate(self.tags, start=1):
                    await page.type(css_selector, "#" + tag)
                    await page.press(css_selector, "Space")
                    await asyncio.sleep(1)
                douyin_logger.info(f'[+] 已填充标签: {self.tags}')
            else:
                douyin_logger.warning('[-] 未找到描述输入容器')

            # 设置商品链接
            if self.productLink:
                douyin_logger.info('[-] 正在设置商品链接...')
                await page.locator('text="添加商品"').click()
                await page.locator('input[placeholder="请输入商品链接"]').fill(self.productLink)
                await page.locator('input[placeholder="请输入商品标题"]').fill(self.productTitle)
                await page.locator('text="确认"').click()
                await asyncio.sleep(2)

            # 设置第三方平台同步
            third_part_element = '[class^="info"] > [class^="semi-switch"]'
            if await page.locator(third_part_element).count():
                if 'semi-switch-checked' not in await page.eval_on_selector(third_part_element, 'div => div.className'):
                    await page.locator(third_part_element).locator('input.semi-switch-native-control').click()

            # 先点击"不允许"单选按钮
            try:
                douyin_logger.info("[-] 正在点击不允许选项...")
                
                # 多种可能的选择器来定位"不允许"
                not_allow_selectors = [
                    'label:has-text("不允许")',
                    'label.radio-d4zkru:has-text("不允许")',
                    'label:has(span:text("不允许"))',
                    'input[value="0"] + svg + span:text("不允许")'
                ]
                
                not_allow_clicked = False
                for selector in not_allow_selectors:
                    try:
                        not_allow_element = page.locator(selector)
                        if await not_allow_element.count() > 0:
                            await not_allow_element.click()
                            await asyncio.sleep(1)
                            douyin_logger.info(f"[+] 成功点击不允许选项 (选择器: {selector})")
                            not_allow_clicked = True
                            break
                    except Exception as e:
                        douyin_logger.debug(f"[-] 不允许选项选择器 {selector} 失败: {e}")
                        continue
            
                if not not_allow_clicked:
                    douyin_logger.warning("[-] 未找到不允许选项，继续执行...")
            except Exception as e:
                douyin_logger.warning(f"[-] 点击不允许选项失败: {e}")

            # 设置背景音乐
            if self.music_name:
                music_success = await self.set_background_music(page, self.music_name, self.music_type)
                if not music_success:
                    raise Exception("设置背景音乐失败：未找到可用的音乐元素")

            # 设置定时发布
            if self.publish_date != 0:
                await self.set_schedule_time_douyin(page, self.publish_date)

            # 等待图片上传完成
            for i in range(60):  # 60 次
                try:
                    # 查找 div，而不是 button
                    if await page.locator('div.container-eAvaPv:has-text("预览图文")').count() > 0:
                        douyin_logger.success("[-] 图片上传成功")
                        break
                except Exception as e:
                    douyin_logger.info(f"[-] 检查失败，第 {i + 1}/60 次，错误: {e}")

                douyin_logger.info(f"[-] 第 {i + 1}/60 次检查：未检测到“预览图文”；0.5 秒后重试...")
                await asyncio.sleep(0.5)  # 每次睡眠 0.5 秒

            else:
                # 循环正常结束（60 次都没 break）→ 抛异常
                raise Exception("等待 60 次仍未检测到“预览图文”按钮，图片可能未成功发布或页面结构已变化")

            # 发布图片
            douyin_logger.info('[-] 正在发布...')
            try:
                # 优先尝试点击定时发布按钮
                if await page.locator('button:has-text("定时发布")').count() > 0:
                    await page.locator('button:has-text("定时发布")').click()
                    douyin_logger.info('[-] 点击了定时发布按钮')
                else:
                    publish_button = page.locator('button.button-dhlUZE:has-text("发布")')
                    if await publish_button.count() > 0:
                        await publish_button.click()
                        douyin_logger.info('[-] 点击了立即发布按钮')
                    else:
                        await page.locator('button:has-text("发布")').last.click()
                        douyin_logger.info('[-] 使用通用选择器点击了发布按钮')
            except Exception as e:
                douyin_logger.error(f'[-] 点击发布按钮失败: {str(e)}')
                raise
        
            # 持续监听发布成功
            douyin_logger.info('[-] 正在等待发布结果...')
            success = False
            for _ in range(100):  # 10秒，每0.2秒检查一次
                try:
                    # 检查发布成功提示
                    toast = page.locator('span.semi-toast-content-text:has-text("发布成功")')
                    if await toast.count() > 0:
                        douyin_logger.success('[+] 检测到发布成功提示！')
                        success = True
                        break
                except Exception:
                    pass
                await asyncio.sleep(0.2)
        
            if not success:
                douyin_logger.error('[-] 10秒内未检测到发布成功提示')
                raise Exception("发布失败：10秒内未检测到成功提示")

            # 如果有评论内容，使用另一个账号检查评论是否存在
            if self.comment:
                # 发布成功后获取作品URL
                work_url = await self.get_work_url_from_manage_page(page)
                if work_url:
                    douyin_logger.success(f'[+] 作品发布成功，作品链接: {work_url}')

                    # 评论成功后等待10秒再打开新页面检测
                    douyin_logger.info('[-] 评论发布成功，等待10秒后再检测评论...')
                    await asyncio.sleep(10)

                    douyin_logger.info('[-] 开始使用另一个账号检查评论...')
                    self.comment_result = await self.check_comment_with_another_account(playwright, work_url, self.comment)
                    if self.comment_result:
                        douyin_logger.success('[+] 评论检测成功，评论已发布！')
                    else:
                        douyin_logger.warning('[-] 评论检测失败，评论可能未成功发布')
                else:
                    douyin_logger.warning('[-] 未能获取作品URL，保持页面打开以便调试...')
                    # 保持页面打开，等待用户手动查看
                    douyin_logger.info('[-] 页面保持打开状态，请手动查看元素，按Ctrl+C退出')
                    await asyncio.sleep(3600)  # 等待1小时，保持页面打开

            await context.storage_state(path=self.account_file)  # 保存cookie
            douyin_logger.success('[-] cookie更新完毕！')
            await asyncio.sleep(2)
        finally:
            if context:
                await context.close()
            # 不再删除用户数据目录，保持浏览器状态以便下次使用

    async def set_location(self, page: Page, location: str = ""):
        if not location:
            return
        await page.locator('div.semi-select span:has-text("输入地理位置")').click()
        await page.keyboard.press("Backspace")
        await page.wait_for_timeout(2000)
        await page.keyboard.type(location)
        await page.wait_for_selector('div[role="listbox"] [role="option"]', timeout=5000)
        await page.locator('div[role="listbox"] [role="option"]').first.click()

    async def main(self):
        async with async_playwright() as playwright:
            await self.upload(playwright)