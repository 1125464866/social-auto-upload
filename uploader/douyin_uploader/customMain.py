# -*- coding: utf-8 -*-
from datetime import datetime

from playwright.async_api import Playwright, async_playwright, Page
import os
import asyncio
from pathlib import Path
import tempfile
import json
import shutil

from conf import LOCAL_CHROME_PATH
from utils.base_social_media import set_init_script
from utils.log import douyin_logger


class DouYinImage(object):
    def __init__(self, title, file_path, tags, publish_date: datetime, account_file, productLink='', productTitle='', music_name='', music_type='search'):
        self.title = title  # 图片标题
        self.file_path = file_path  # 支持单张图片或图片列表
        self.tags = tags
        self.publish_date = publish_date
        self.account_file = account_file
        self.date_format = '%Y年%m月%d日 %H:%M'
        self.local_executable_path = LOCAL_CHROME_PATH
        self.productLink = productLink
        self.productTitle = productTitle
        self.music_name = music_name  # 背景音乐名称
        self.music_type = music_type  # 音乐类型: search(搜索) 或 fav(收藏)

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
        # 使用 Chromium 浏览器启动一个浏览器实例
        # 为每个实例创建独立的用户数据目录
        temp_dir = tempfile.mkdtemp(prefix="douyin_image_browser_")
        
        # 使用 launch_persistent_context 来指定用户数据目录
        if self.local_executable_path:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=temp_dir,
                headless=False,
                executable_path=self.local_executable_path
            )
        else:
            context = await playwright.chromium.launch_persistent_context(
                user_data_dir=temp_dir,
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
        douyin_logger.info(f'[+]正在上传图片-------{self.title}')
        # 等待页面跳转到指定的 URL，没进入，则自动等待到超时
        douyin_logger.info(f'[-] 正在打开主页...')
        await page.wait_for_url("https://creator.douyin.com/creator-micro/content/upload")
        
        # 点击"发布图文"选项卡
        try:
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
                douyin_logger.warning("[-] 未找到发布图文选项卡，继续尝试上传...")
        except Exception as e:
            douyin_logger.warning(f"[-] 点击发布图文选项卡失败: {e}")

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

        # 填充标题和话题
        await asyncio.sleep(1)
        douyin_logger.info(f'[-] 正在填充标题和话题...')
        
        # 填充标题
        title_container = page.get_by_text('作品标题').locator("..").locator("xpath=following-sibling::div[1]").locator("input")
        if await title_container.count():
            await title_container.fill(self.title[:30])
        else:
            titlecontainer = page.locator(".notranslate")
            await titlecontainer.click()
            await page.keyboard.press("Backspace")
            await page.keyboard.press("Control+KeyA")
            await page.keyboard.press("Delete")
            await page.keyboard.type(self.title)
            await page.keyboard.press("Enter")
        
        # 填充话题标签
        css_selector = ".zone-container"
        for index, tag in enumerate(self.tags, start=1):
            await page.type(css_selector, "#" + tag)
            await page.press(css_selector, "Space")
            await asyncio.sleep(1)

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

        # 设置定时发布
        if self.publish_date != 0:
            await self.set_schedule_time_douyin(page, self.publish_date)

        # 设置背景音乐
        if self.music_name:
            await self.set_background_music(page, self.music_name, self.music_type)

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
        # 更精确地定位发布按钮，避免匹配到页面头部的"高清发布"按钮
        # 使用 class 属性来区分，弹窗中的发布按钮有特定的 class
        try:
            # 优先尝试点击定时发布按钮
            if await page.locator('button:has-text("定时发布")').count() > 0:
                await page.locator('button:has-text("定时发布")').click()
                douyin_logger.info('[-] 点击了定时发布按钮')
            else:
                # 如果没有定时发布按钮，点击立即发布按钮
                # 使用更精确的选择器，排除头部的"高清发布"按钮
                publish_button = page.locator('button.button-dhlUZE:has-text("发布")')
                if await publish_button.count() > 0:
                    await publish_button.click()
                    douyin_logger.info('[-] 点击了立即发布按钮')
                else:
                    # 如果上面的选择器也找不到，尝试使用更通用的方式
                    await page.locator('button:has-text("发布")').last.click()
                    douyin_logger.info('[-] 使用通用选择器点击了发布按钮')
        except Exception as e:
            douyin_logger.error(f'[-] 点击发布按钮失败: {str(e)}')
            raise
        
        await asyncio.sleep(2)

        await context.storage_state(path=self.account_file)  # 保存cookie
        douyin_logger.success('[-] cookie更新完毕！')
        await asyncio.sleep(2)  # 这里延迟是为了方便眼睛直观的观看
        # 关闭浏览器上下文
        await context.close()
        
        # 清理临时目录
        try:
            if 'temp_dir' in locals() and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)
        except:
            pass

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