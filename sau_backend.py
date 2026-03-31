import asyncio
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
import uuid
import requests
from pathlib import Path
from queue import Queue
from flask_cors import CORS
from datetime import datetime
import logging

# 尝试使用 patchright，如果不存在则回退到 playwright
try:
    from patchright.async_api import async_playwright
    USE_PATCHRIGHT = True
    print("[INFO] 使用 patchright 模式（反检测增强）")
except ImportError:
    from playwright.async_api import async_playwright
    USE_PATCHRIGHT = False
    print("[WARNING] 未安装 patchright，使用普通 playwright 模式")

from myUtils.auth import check_cookie
from flask import Flask, request, jsonify, Response, render_template, send_from_directory
from conf import BASE_DIR, LOCAL_CHROME_PATH
from myUtils.login import get_tencent_cookie, douyin_cookie_gen, get_ks_cookie, xiaohongshu_cookie_gen
from myUtils.postVideo import post_video_tencent, post_video_DouYin, post_video_ks, post_video_xhs, post_image_DouYin
from utils.base_social_media import set_init_script

active_queues = {}
app = Flask(__name__)

#允许所有来源跨域访问
CORS(app)

# 限制上传文件大小为160MB
app.config['MAX_CONTENT_LENGTH'] = 160 * 1024 * 1024


def setup_publish_error_logger():
    """设置发布错误日志记录器，每天生成一个日志文件"""
    log_dir = Path(BASE_DIR) / "log"
    log_dir.mkdir(parents=True, exist_ok=True)

    # 日志文件名格式：publish_error_YYYY-MM-DD.log
    log_filename = log_dir / f"publish_error_{datetime.now().strftime('%Y-%m-%d')}.log"

    # 创建 logger
    logger = logging.getLogger('publish_error_logger')
    logger.setLevel(logging.ERROR)

    # 避免重复添加 handler
    if not logger.handlers:
        # 创建文件 handler
        file_handler = logging.FileHandler(log_filename, encoding='utf-8')
        file_handler.setLevel(logging.ERROR)

        # 设置日志格式：时间 - 账号：失败原因
        formatter = logging.Formatter('%(asctime)s - %(message)s', datefmt='%Y-%m-%d %H:%M:%S')
        file_handler.setFormatter(formatter)

        logger.addHandler(file_handler)

    return logger


def log_publish_error(account_name: str, error_msg: str):
    """记录发布错误日志

    Args:
        account_name: 账号名称
        error_msg: 失败原因
    """
    try:
        logger = setup_publish_error_logger()
        logger.error(f"{account_name}：{error_msg}")
    except Exception as e:
        print(f"记录日志失败: {str(e)}")


async def open_douyin_creator_center(cookie_file_path: str):
    """打开抖音创作者中心，使用固定的用户数据目录"""
    # 从 cookie 文件路径提取账号名
    cookie_filename = Path(cookie_file_path).stem  # 获取文件名（不含扩展名）
    # 使用固定的用户数据目录
    user_data_dir = Path(BASE_DIR) / "browser_data" / f"douyin_{cookie_filename}"
    user_data_dir.mkdir(parents=True, exist_ok=True)

    print(f"[INFO] 使用浏览器数据目录: {user_data_dir}")

    context = None
    try:
        async with async_playwright() as playwright:
            launch_kwargs = {
                "user_data_dir": str(user_data_dir),
                "headless": False
            }
            if LOCAL_CHROME_PATH:
                launch_kwargs["executable_path"] = LOCAL_CHROME_PATH

            context = await playwright.chromium.launch_persistent_context(**launch_kwargs)
            context = await set_init_script(context)

            # 加载 cookie
            if os.path.exists(cookie_file_path):
                try:
                    with open(cookie_file_path, 'r', encoding='utf-8') as f:
                        state = json.load(f)
                    if 'cookies' in state:
                        await context.add_cookies(state['cookies'])
                        print(f"[INFO] 已加载 Cookie 文件: {cookie_file_path}")
                except Exception as cookie_error:
                    print(f"[ERROR] 加载Cookie失败: {cookie_error}")

            page = await context.new_page()

            # 定义页面关闭时的处理函数
            async def on_page_close():
                """页面关闭时保存 Cookie"""
                try:
                    await context.storage_state(path=cookie_file_path)
                    print(f"[INFO] Cookie 已自动保存到: {cookie_file_path}")
                except Exception as e:
                    # persistent_context 会自动保存到 user_data_dir，所以这里只是补充保存
                    print(f"[INFO] 浏览器数据已自动保存到目录: {user_data_dir}")

            # 监听页面关闭事件
            page.on("close", lambda: asyncio.create_task(on_page_close()))

            try:
                await page.goto(
                    "https://creator.douyin.com/creator-micro/interactive/comment",
                    wait_until="domcontentloaded",
                    timeout=60000
                )
            except Exception as nav_error:
                print(f"[ERROR] 打开抖音创作者中心页面导航失败: {nav_error}")

            print("[INFO] 抖音创作者中心页面已打开")
            print(f"[INFO] 浏览器数据会自动保存到: {user_data_dir}")
            print("[INFO] 关闭窗口后请等待几秒让数据保存完成...")

            # 等待页面关闭
            await page.wait_for_event("close", timeout=0)
            print("[INFO] 用户已关闭抖音创作者中心窗口")

            # 给一点时间让数据保存完成
            await asyncio.sleep(1)

    except Exception as e:
        print(f"[ERROR] 打开抖音创作者中心失败: {e}")
    finally:
        if context:
            try:
                await context.close()
            except Exception as close_error:
                pass  # context 可能已关闭，忽略错误
        print(f"[INFO] 浏览器状态已保存，下次打开将自动恢复登录状态")


def launch_open_douyin_creator_center(cookie_file_path: str):
    def _target():
        try:
            asyncio.run(open_douyin_creator_center(cookie_file_path))
        except Exception as e:
            print(f"打开创作者中心任务执行失败: {e}")

    threading.Thread(target=_target, daemon=True).start()


@app.route('/openDouyinCreatorCenter', methods=['POST'])
def open_douyin_creator_center_api():
    try:
        payload = request.get_json(silent=True) or {}
        account_id = payload.get('id')
        if not account_id:
            return jsonify({
                "code": 400,
                "msg": "缺少账号ID",
                "data": None
            }), 400

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT filePath, type FROM user_info WHERE id = ?', (account_id,))
            row = cursor.fetchone()

        if not row:
            return jsonify({
                "code": 404,
                "msg": "账号不存在",
                "data": None
            }), 404

        if row[1] != 3:
            return jsonify({
                "code": 400,
                "msg": "仅支持抖音账号打开创作者中心",
                "data": None
            }), 400

        cookie_file_path = Path(BASE_DIR / "cookiesFile" / row[0])
        if not cookie_file_path.exists():
            return jsonify({
                "code": 404,
                "msg": "Cookie文件不存在，请先登录账号",
                "data": None
            }), 404

        launch_open_douyin_creator_center(str(cookie_file_path))
        return jsonify({
            "code": 200,
            "msg": "已启动浏览器并尝试打开抖音创作者中心",
            "data": None
        }), 200

    except Exception as e:
        print(f"openDouyinCreatorCenter 接口异常: {e}")
        return jsonify({
            "code": 500,
            "msg": f"打开创作者中心失败: {e}",
            "data": None
        }), 500

# 获取当前目录（假设 index.html 和 assets 在这里）
current_dir = os.path.dirname(os.path.abspath(__file__))

# 处理所有静态资源请求（未来打包用）
@app.route('/assets/<filename>')
def custom_static(filename):
    return send_from_directory(os.path.join(current_dir, 'assets'), filename)

# 处理 favicon.ico 静态资源（未来打包用）
@app.route('/favicon.ico')
def favicon():
    return send_from_directory(os.path.join(current_dir, 'assets'), 'vite.svg')

@app.route('/vite.svg')
def vite_svg():
    return send_from_directory(os.path.join(current_dir, 'assets'), 'vite.svg')

# （未来打包用）
@app.route('/')
def index():  # put application's code here
    return send_from_directory(current_dir, 'index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({
            "code": 200,
            "data": None,
            "msg": "No file part in the request"
        }), 400
    file = request.files['file']
    if file.filename == '':
        return jsonify({
            "code": 200,
            "data": None,
            "msg": "No selected file"
        }), 400
    try:
        # 保存文件到指定位置
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")
        filepath = Path(BASE_DIR / "videoFile" / f"{uuid_v1}_{file.filename}")
        file.save(filepath)
        return jsonify({"code":200,"msg": "File uploaded successfully", "data": f"{uuid_v1}_{file.filename}"}), 200
    except Exception as e:
        return jsonify({"code":200,"msg": str(e),"data":None}), 500

@app.route('/getFile', methods=['GET'])
def get_file():
    # 获取 filename 参数
    filename = request.args.get('filename')

    if not filename:
        return {"error": "filename is required"}, 400

    # 防止路径穿越攻击
    if '..' in filename or filename.startswith('/'):
        return {"error": "Invalid filename"}, 400

    # 拼接完整路径
    file_path = str(Path(BASE_DIR / "videoFile"))

    # 返回文件
    return send_from_directory(file_path,filename)


@app.route('/uploadSave', methods=['POST'])
def upload_save():
    if 'file' not in request.files:
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No file part in the request"
        }), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({
            "code": 400,
            "data": None,
            "msg": "No selected file"
        }), 400

    # 获取表单中的自定义文件名（可选）
    custom_filename = request.form.get('filename', None)
    if custom_filename:
        filename = custom_filename + "." + file.filename.split('.')[-1]
    else:
        filename = file.filename

    try:
        # 生成 UUID v1
        uuid_v1 = uuid.uuid1()
        print(f"UUID v1: {uuid_v1}")

        # 构造文件名和路径
        final_filename = f"{uuid_v1}_{filename}"
        filepath = Path(BASE_DIR / "videoFile" / f"{uuid_v1}_{filename}")

        # 保存文件
        file.save(filepath)

        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            cursor.execute('''
                                INSERT INTO file_records (filename, filesize, file_path)
            VALUES (?, ?, ?)
                                ''', (filename, round(float(os.path.getsize(filepath)) / (1024 * 1024),2), final_filename))
            conn.commit()
            print("✅ 上传文件已记录")

        return jsonify({
            "code": 200,
            "msg": "File uploaded and saved successfully",
            "data": {
                "filename": filename,
                "filepath": final_filename
            }
        }), 200

    except Exception as e:
        print(f"Upload failed: {e}")
        return jsonify({
            "code": 500,
            "msg": f"upload failed: {e}",
            "data": None
        }), 500

@app.route('/getFiles', methods=['GET'])
def get_all_files():
    try:
        # 使用 with 自动管理数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row  # 允许通过列名访问结果
            cursor = conn.cursor()

            # 查询所有记录
            cursor.execute("SELECT * FROM file_records")
            rows = cursor.fetchall()

            # 将结果转为字典列表，并提取UUID
            data = []
            for row in rows:
                row_dict = dict(row)
                # 从 file_path 中提取 UUID (文件名的第一部分，下划线前)
                if row_dict.get('file_path'):
                    file_path_parts = row_dict['file_path'].split('_', 1)  # 只分割第一个下划线
                    if len(file_path_parts) > 0:
                        row_dict['uuid'] = file_path_parts[0]  # UUID 部分
                    else:
                        row_dict['uuid'] = ''
                else:
                    row_dict['uuid'] = ''
                data.append(row_dict)

            return jsonify({
                "code": 200,
                "msg": "success",
                "data": data
            }), 200
    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("get file failed!"),
            "data": None
        }), 500


@app.route("/checkAccountStatus", methods=['GET'])
async def checkAccountStatus():
    account_id = request.args.get('id')
    if not account_id:
        return jsonify({"code": 400, "msg": "缺少账号ID", "data": None}), 400

    try:
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT * FROM user_info WHERE id = ?', (account_id,))
            row = cursor.fetchone()

            if not row:
                return jsonify({"code": 404, "msg": "账号不存在", "data": None}), 404

            # row 结构: [id, type, filePath, userName, status]
            row_list = list(row)
            flag = await check_cookie(row_list[1], row_list[2])
            
            # cookie 有效 -> status 应为 1，失效 -> 0
            new_status = 1 if flag else 0
            
            if row_list[4] != new_status:
                cursor.execute('''
                UPDATE user_info 
                SET status = ? 
                WHERE id = ?
                ''', (new_status, account_id))
                conn.commit()
                print(f"✅ 用户 {row_list[3]} 状态已更新为 {new_status}")
            
            # 返回更新后的账号信息
            cursor.execute('SELECT * FROM user_info WHERE id = ?', (account_id,))
            updated_row = cursor.fetchone()
            return jsonify({
                "code": 200,
                "msg": "验证成功",
                "data": list(updated_row)
            }), 200
    except Exception as e:
        print(f"验证账号状态时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"验证失败: {str(e)}",
            "data": None
        }), 500


@app.route("/getAccounts", methods=['GET'])
def getAccounts():
    """快速获取所有账号信息，不进行cookie验证"""
    try:
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('''
            SELECT * FROM user_info''')
            rows = cursor.fetchall()
            rows_list = [list(row) for row in rows]

            print("\n📋 当前数据表内容（快速获取）：")
            for row in rows:
                print(row)

            return jsonify(
                {
                    "code": 200,
                    "msg": None,
                    "data": rows_list
                }), 200
    except Exception as e:
        print(f"获取账号列表时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"获取账号列表失败: {str(e)}",
            "data": None
        }), 500


@app.route("/getValidAccounts",methods=['GET'])
async def getValidAccounts():
    with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
        cursor = conn.cursor()
        cursor.execute('''
        SELECT * FROM user_info''')
        rows = cursor.fetchall()
        rows_list = [list(row) for row in rows]
        print("\n📋 当前数据表内容：")
        for row in rows:
            print(row)
        # rows_list 结构: [id, type, filePath, userName, status]
        for row in rows_list:
            flag = await check_cookie(row[1], row[2])
            # cookie 有效 -> status 应为 1，失效 -> 0
            new_status = 1 if flag else 0
            if row[4] != new_status:
                row[4] = new_status
                cursor.execute('''
                UPDATE user_info 
                SET status = ? 
                WHERE id = ?
                ''', (new_status, row[0]))
                conn.commit()
                print(f"✅ 用户 {row[3]} 状态已更新为 {new_status}")
        # 为了打印最新结果，再查一次
        cursor.execute('''
        SELECT * FROM user_info''')
        updated_rows = cursor.fetchall()
        print("\n📋 更新后的数据表内容：")
        for row in updated_rows:
            print(row)
        return jsonify(
                        {
                            "code": 200,
                            "msg": None,
                            "data": rows_list
                        }),200

@app.route('/deleteFile', methods=['GET'])
def delete_file():
    file_id = request.args.get('id')

    if not file_id or not file_id.isdigit():
        return jsonify({
            "code": 400,
            "msg": "Invalid or missing file ID",
            "data": None
        }), 400

    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 查询要删除的记录
            cursor.execute("SELECT * FROM file_records WHERE id = ?", (file_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({
                    "code": 404,
                    "msg": "File not found",
                    "data": None
                }), 404

            record = dict(record)

            # 获取文件路径并删除实际文件
            file_path = Path(BASE_DIR / "videoFile" / record['file_path'])
            if file_path.exists():
                try:
                    file_path.unlink()  # 删除文件
                    print(f"✅ 实际文件已删除: {file_path}")
                except Exception as e:
                    print(f"⚠️ 删除实际文件失败: {e}")
                    # 即使删除文件失败，也要继续删除数据库记录，避免数据不一致
            else:
                print(f"⚠️ 实际文件不存在: {file_path}")

            # 删除数据库记录
            cursor.execute("DELETE FROM file_records WHERE id = ?", (file_id,))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "File deleted successfully",
            "data": {
                "id": record['id'],
                "filename": record['filename']
            }
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("delete failed!"),
            "data": None
        }), 500

@app.route('/deleteAccount', methods=['GET'])
def delete_account():
    account_id = int(request.args.get('id'))

    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 查询要删除的记录
            cursor.execute("SELECT * FROM user_info WHERE id = ?", (account_id,))
            record = cursor.fetchone()

            if not record:
                return jsonify({
                    "code": 404,
                    "msg": "account not found",
                    "data": None
                }), 404

            record = dict(record)

            # 删除数据库记录
            cursor.execute("DELETE FROM user_info WHERE id = ?", (account_id,))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "account deleted successfully",
            "data": None
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("delete failed!"),
            "data": None
        }), 500


# SSE 登录接口
@app.route('/login')
def login():
    # 1 小红书 2 视频号 3 抖音 4 快手
    type = request.args.get('type')
    # 账号名
    id = request.args.get('id')
    # 数据库ID (用于重新绑定)
    account_id = request.args.get('account_id')

    # 模拟一个用于异步通信的队列
    status_queue = Queue()
    active_queues[id] = status_queue

    def on_close():
        print(f"清理队列: {id}")
        del active_queues[id]
    # 启动异步任务线程
    thread = threading.Thread(target=run_async_function, args=(type,id,status_queue,account_id), daemon=True)
    thread.start()
    response = Response(sse_stream(status_queue,), mimetype='text/event-stream')
    response.headers['Cache-Control'] = 'no-cache'
    response.headers['X-Accel-Buffering'] = 'no'  # 关键：禁用 Nginx 缓冲
    response.headers['Content-Type'] = 'text/event-stream'
    response.headers['Connection'] = 'keep-alive'
    return response

@app.route('/postVideo', methods=['POST'])
def postVideo():
    # 获取JSON数据
    data = request.get_json()

    # 从JSON数据中提取fileList和accountList
    file_list = data.get('fileList', [])
    account_list = data.get('accountList', [])
    type = data.get('type')
    title = data.get('title')
    tags = data.get('tags')
    category = data.get('category')
    enableTimer = data.get('enableTimer')
    if category == 0:
        category = None
    productLink = data.get('productLink', '')
    productTitle = data.get('productTitle', '')
    thumbnail_path = data.get('thumbnail', '')
    is_draft = data.get('isDraft', False)  # 新增参数：是否保存为草稿

    videos_per_day = data.get('videosPerDay')
    daily_times = data.get('dailyTimes')
    start_days = data.get('startDays')
    # 打印获取到的数据（仅作为示例）
    print("File List:", file_list)
    print("Account List:", account_list)
    match type:
        case 1:
            post_video_xhs(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                               start_days)
        case 2:
            post_video_tencent(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                               start_days, is_draft)
        case 3:
            post_video_DouYin(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                      start_days, thumbnail_path, productLink, productTitle)
        case 4:
            post_video_ks(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                      start_days)
    # 返回响应给客户端
    return jsonify(
        {
            "code": 200,
            "msg": None,
            "data": None
        }), 200


@app.route('/updateUserinfo', methods=['POST'])
def updateUserinfo():
    # 获取JSON数据
    data = request.get_json()

    # 从JSON数据中提取 type 和 userName
    user_id = data.get('id')
    type = data.get('type')
    userName = data.get('userName')
    try:
        # 获取数据库连接
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # 更新数据库记录
            cursor.execute('''
                           UPDATE user_info
                           SET type     = ?,
                               userName = ?
                           WHERE id = ?;
                           ''', (type, userName, user_id))
            conn.commit()

        return jsonify({
            "code": 200,
            "msg": "account update successfully",
            "data": None
        }), 200

    except Exception as e:
        return jsonify({
            "code": 500,
            "msg": str("update failed!"),
            "data": None
        }), 500

@app.route('/postVideoBatch', methods=['POST'])
def postVideoBatch():
    data_list = request.get_json()

    if not isinstance(data_list, list):
        return jsonify({"error": "Expected a JSON array"}), 400
    for data in data_list:
        # 从JSON数据中提取fileList和accountList
        file_list = data.get('fileList', [])
        account_list = data.get('accountList', [])
        type = data.get('type')
        title = data.get('title')
        tags = data.get('tags')
        category = data.get('category')
        enableTimer = data.get('enableTimer')
        if category == 0:
            category = None
        productLink = data.get('productLink', '')
        productTitle = data.get('productTitle', '')

        videos_per_day = data.get('videosPerDay')
        daily_times = data.get('dailyTimes')
        start_days = data.get('startDays')
        # 打印获取到的数据（仅作为示例）
        print("File List:", file_list)
        print("Account List:", account_list)
        match type:
            case 1:
                return
            case 2:
                post_video_tencent(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                                   start_days)
            case 3:
                post_video_DouYin(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days, productLink, productTitle)
            case 4:
                post_video_ks(title, file_list, tags, account_list, category, enableTimer, videos_per_day, daily_times,
                          start_days)
    # 返回响应给客户端
    return jsonify(
        {
            "code": 200,
            "msg": None,
            "data": None
        }), 200

# Cookie文件上传API
@app.route('/uploadCookie', methods=['POST'])
def upload_cookie():
    try:
        if 'file' not in request.files:
            return jsonify({
                "code": 500,
                "msg": "没有找到Cookie文件",
                "data": None
            }), 400

        file = request.files['file']
        if file.filename == '':
            return jsonify({
                "code": 500,
                "msg": "Cookie文件名不能为空",
                "data": None
            }), 400

        if not file.filename.endswith('.json'):
            return jsonify({
                "code": 500,
                "msg": "Cookie文件必须是JSON格式",
                "data": None
            }), 400

        # 获取账号信息
        account_id = request.form.get('id')
        platform = request.form.get('platform')

        if not account_id or not platform:
            return jsonify({
                "code": 500,
                "msg": "缺少账号ID或平台信息",
                "data": None
            }), 400

        # 从数据库获取账号的文件路径
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute('SELECT filePath FROM user_info WHERE id = ?', (account_id,))
            result = cursor.fetchone()

        if not result:
            return jsonify({
                "code": 500,
                "msg": "账号不存在",
                "data": None
            }), 404

        # 保存上传的Cookie文件到对应路径
        cookie_file_path = Path(BASE_DIR / "cookiesFile" / result['filePath'])
        cookie_file_path.parent.mkdir(parents=True, exist_ok=True)

        file.save(str(cookie_file_path))

        # 更新数据库中的账号信息（可选，比如更新更新时间）
        # 这里可以根据需要添加额外的处理逻辑

        return jsonify({
            "code": 200,
            "msg": "Cookie文件上传成功",
            "data": None
        }), 200

    except Exception as e:
        print(f"上传Cookie文件时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"上传Cookie文件失败: {str(e)}",
            "data": None
        }), 500


# Cookie文件下载API
@app.route('/downloadCookie', methods=['GET'])
def download_cookie():
    try:
        file_path = request.args.get('filePath')
        if not file_path:
            return jsonify({
                "code": 500,
                "msg": "缺少文件路径参数",
                "data": None
            }), 400

        # 验证文件路径的安全性，防止路径遍历攻击
        cookie_file_path = Path(BASE_DIR / "cookiesFile" / file_path).resolve()
        base_path = Path(BASE_DIR / "cookiesFile").resolve()

        if not cookie_file_path.is_relative_to(base_path):
            return jsonify({
                "code": 500,
                "msg": "非法文件路径",
                "data": None
            }), 400

        if not cookie_file_path.exists():
            return jsonify({
                "code": 500,
                "msg": "Cookie文件不存在",
                "data": None
            }), 404

        # 返回文件
        return send_from_directory(
            directory=str(cookie_file_path.parent),
            path=cookie_file_path.name,
            as_attachment=True
        )

    except Exception as e:
        print(f"下载Cookie文件时出错: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"下载Cookie文件失败: {str(e)}",
            "data": None
        }), 500

@app.route("/custom/api/douyin/getAccounts", methods=['GET'])
def get_douyin_accounts():
    """
    获取抖音账号列表（专门给Java后端调用）
    返回格式：{"code": 200, "data": {"data": [[id, platform, filePath, name, status], ...]}}
    """
    try:
        with sqlite3.connect(Path(BASE_DIR / "db" / "database.db")) as conn:
            cursor = conn.cursor()
            # 先查询所有账号，然后在 Python 中过滤
            cursor.execute('SELECT * FROM user_info')
            rows = cursor.fetchall()
            
            # 过滤出抖音账号（platform = 3，索引为 1）
            douyin_rows = [list(row) for row in rows if len(row) > 1 and row[1] == 3]
            
            print(f"\n📋 获取到 {len(douyin_rows)} 个抖音账号")
            for row in douyin_rows:
                print(f"  - ID: {row[0]}, Platform: {row[1]}, 名称: {row[3] if len(row) > 3 else 'N/A'}, 文件: {row[2] if len(row) > 2 else 'N/A'}")
            
            return jsonify({
                "code": 200,
                "msg": None,
                "data": {
                    "data": douyin_rows
                }
            }), 200
    except Exception as e:
        print(f"❌ 获取抖音账号列表失败: {str(e)}")
        import traceback
        traceback.print_exc()
        return jsonify({
            "code": 500,
            "msg": f"获取账号列表失败: {str(e)}",
            "data": None
        }), 500

# 抖音图文发布接口
@app.route('/custom/api/douyin/publishImage', methods=['POST'])
def publish_douyin_image():
    """
    抖音图文发布接口
    接收参数：
    - account_file: 账号cookie文件名（不含路径）
    - folder_path: 图片文件夹绝对路径
    - music_name: 背景音乐名称（可选）
    - publish_type: 发布类型 'immediate'立即发布 或 'scheduled'定时发布
    - publish_time: 定时发布时间（格式：yyyy-mm-dd hh:mm:ss）
    - task_id: 任务ID（用于回调更新状态）
    - callback_url: 回调地址
    """
    try:
        data = request.get_json()
        
        # 必填参数验证
        account_file = data.get('account_file')
        folder_path = data.get('folder_path')
        task_id = data.get('task_id')
        callback_url = data.get('callback_url')
        
        if not all([account_file, folder_path, task_id, callback_url]):
            return jsonify({
                "code": 400,
                "msg": "缺少必填参数",
                "data": None
            }), 400
        
        # 可选参数
        title = data.get('title', '')  # 标题（可选，留空则从文件夹读取）
        copywriter = data.get('copywriter', '')  # 文案/作品描述（可选，留空则从文件夹读取）
        comment = data.get('comment', '')  # 评论内容（可选，发布后在评论区发布）
        music_name = data.get('music_name', '')
        music_type = data.get('music_type', 'search')  # search或fav
        publish_type = data.get('publish_type', 'immediate')
        publish_time_str = data.get('publish_time', '')
        
        # 验证文件夹路径
        folder = Path(folder_path)
        if not folder.exists() or not folder.is_dir():
            return jsonify({
                "code": 400,
                "msg": "文件夹路径不存在",
                "data": None
            }), 400
        
        # 处理发布时间
        publish_date = 0  # 默认立即发布
        if publish_type == 'scheduled' and publish_time_str:
            try:
                publish_date = datetime.strptime(publish_time_str, '%Y-%m-%d %H:%M:%S')
            except ValueError:
                return jsonify({
                    "code": 400,
                    "msg": "时间格式错误，应为 yyyy-mm-dd hh:mm:ss",
                    "data": None
                }), 400
        
        # 生成任务ID
        job_id = str(uuid.uuid4())
        
        # 在后台线程中执行发布任务
        def publish_task():
            # 预先计算发布时间，确保在所有回调中都能使用
            if publish_type == 'scheduled' and publish_time_str:
                dy_push_time = publish_time_str
            else:
                # 立即发布，使用当前时间
                dy_push_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            try:
                # 调用发布函数（需要修改 post_image_DouYin 以支持直接传入文件夹路径）
                from uploader.douyin_uploader.customMain import DouYinImage
                from uploader.douyin_uploader.main import douyin_setup
                from examples.upload_image_to_douyin import get_title_description_tags, get_all_images
                
                # 获取图片文件
                image_files = get_all_images(folder)
                if not image_files:
                    raise Exception("文件夹中未找到图片文件")
                
                # 获取标题、描述、标签（优先使用传入参数，否则从文件夹读取）
                final_title, description, tags = get_title_description_tags(
                    folder, 
                    override_title=title if title else None,
                    override_copywriter=copywriter if copywriter else None
                )
                
                # 准备图片路径列表
                valid_images = [str(img) for img in image_files if img.exists()]
                if len(valid_images) > 9:
                    valid_images = valid_images[:9]
                
                # 账号文件路径
                account_file_path = Path(BASE_DIR / "cookiesFile" / account_file)
                
                # 创建上传实例
                douyin_image = DouYinImage(
                    title=final_title,
                    description=description,  # 作品描述（文案）
                    file_path=valid_images,
                    tags=tags,
                    publish_date=publish_date,
                    account_file=account_file_path,
                    productLink="",
                    productTitle="",
                    music_name=music_name,
                    music_type=music_type,
                    comment=comment if comment else ""  # 评论内容（发布后在评论区发布）
                )

                # 执行上传
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                loop.run_until_complete(douyin_image.main())
                loop.close()

                print("抖音图文发布成功，准备回调 Java 服务...")

                # 获取评论状态
                dy_comment_status = "成功" if douyin_image.comment_result else "失败"
                print(f"评论状态: {dy_comment_status}")

                # 发布成功，回调通知 Java 服务
                try:
                    callback_response = requests.post(callback_url, json={
                        "task_id": task_id,
                        "status": 1,
                        "message": "发布成功",
                        "dyPushTime": dy_push_time,
                        "dyCommentStatus": dy_comment_status
                    }, timeout=10)
                    print(f"回调成功: {callback_response.status_code}, {callback_response.text}")
                except Exception as callback_error:
                    print(f"回调 Java 服务失败: {str(callback_error)}")
                    print(f"回调 URL: {callback_url}")
                    print(f"回调数据: task_id={task_id}, status=1, dyCommentStatus={dy_comment_status}")

            except Exception as e:
                print(f"抖音图文发布失败: {str(e)}")
                import traceback
                traceback.print_exc()

                # 记录发布错误日志
                account_name = Path(account_file).stem  # 从账号文件名提取账号名
                log_publish_error(account_name, str(e))

                # 发布失败，回调通知 Java 服务
                try:
                    callback_response = requests.post(callback_url, json={
                        "task_id": task_id,
                        "status": 2,
                        "message": f"发布失败: {str(e)}",
                        "dyPushTime": dy_push_time,
                        "dyCommentStatus": "失败"  # 发布失败时评论状态也是失败
                    }, timeout=10)
                    print(f"失败回调成功: {callback_response.status_code}, {callback_response.text}")
                except Exception as callback_error:
                    print(f"失败回调 Java 服务失败: {str(callback_error)}")
                    print(f"回调 URL: {callback_url}")
                    print(f"回调数据: task_id={task_id}, status=2, dyCommentStatus=失败")
        
        # 启动后台线程
        thread = threading.Thread(target=publish_task, daemon=True)
        thread.start()
        
        return jsonify({
            "code": 200,
            "msg": "发布任务已提交",
            "data": {
                "job_id": job_id,
                "task_id": task_id
            }
        }), 200
        
    except Exception as e:
        print(f"提交发布任务失败: {str(e)}")
        return jsonify({
            "code": 500,
            "msg": f"提交发布任务失败: {str(e)}",
            "data": None
        }), 500


# 包装函数：在线程中运行异步函数
def run_async_function(type,id,status_queue,account_id=None):
    match type:
        case '1':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(xiaohongshu_cookie_gen(id, status_queue, account_id))
            loop.close()
        case '2':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(get_tencent_cookie(id,status_queue, account_id))
            loop.close()
        case '3':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(douyin_cookie_gen(id,status_queue, account_id))
            loop.close()
        case '4':
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(get_ks_cookie(id,status_queue, account_id))
            loop.close()

# SSE 流生成器函数
def sse_stream(status_queue):
    while True:
        if not status_queue.empty():
            msg = status_queue.get()
            yield f"data: {msg}\n\n"
        else:
            # 避免 CPU 占满
            time.sleep(0.1)

if __name__ == '__main__':
    app.run(host='0.0.0.0' ,port=5409)
