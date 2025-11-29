import asyncio
from pathlib import Path
import re
from datetime import datetime

from conf import BASE_DIR
from uploader.douyin_uploader.main import douyin_setup
from uploader.douyin_uploader.customMain import DouYinImage
from utils.files_times import generate_schedule_time_next_day


def read_txt_file(file_path):
    """读取txt文件内容"""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read().strip()
    except Exception as e:
        print(f"读取文件失败: {file_path}, 错误: {e}")
        return None


def parse_copywriter_content(content):
    """解析文案内容：提取描述和标签"""
    if not content:
        return "", []
    
    lines = content.split('\n')
    description_lines = []
    hashtag_lines = []
    collecting_hashtags = False
    
    for line in lines:
        line = line.strip()
        if not line:
            continue
        
        # 如果行全部都是#开头的词（标签行）
        if re.match(r'^#\w+(\s+#\w+)*\s*$', line):
            collecting_hashtags = True
            hashtag_lines.append(line)
        # 如果已经在收集hashtag但遇到非hashtag行，停止收集
        elif collecting_hashtags and not line.startswith('#'):
            break
        # 还没开始收集hashtag，这是描述内容
        elif not collecting_hashtags:
            description_lines.append(line)
    
    # 合并描述内容
    description = '\n'.join(description_lines)
    
    # 提取所有hashtag
    hashtag_text = ' '.join(hashtag_lines)
    hashtag_pattern = r'#(\w+)'
    hashtags = re.findall(hashtag_pattern, hashtag_text)
    
    return description, hashtags


def get_title_description_tags(folder_path, override_title=None, override_copywriter=None):
    """
    从文件夹获取标题、描述和标签
    优先级：传入的参数 > 文件夹中的txt文件
    
    Args:
        folder_path: 文件夹路径
        override_title: 传入的标题，如果有则优先使用
        override_copywriter: 传入的文案，如果有则优先使用
    
    Returns:
        tuple: (title, description, tags)
    """
    folder = Path(folder_path)
    title = "图文发布"
    description = ""
    tags = ["图文", "抖音"]
    
    # 处理标题
    if override_title:
        title = override_title
        print(f"使用传入的标题: {title}")
    else:
        # 从文件夹读取title.txt
        title_file = folder / "title.txt"
        if title_file.exists():
            title_content = read_txt_file(title_file)
            if title_content:
                title = title_content[:20]  # 标题最多20字
                print(f"从 title.txt 读取标题: {title}")
        else:
            print(f"未找到 title.txt，使用默认标题: {title}")
    
    # 处理文案和标签
    if override_copywriter:
        description, tags = parse_copywriter_content(override_copywriter)
        print(f"使用传入的文案")
        if not tags:
            tags = ["图文", "抖音"]
    else:
        # 从文件夹读取copywriter.txt
        copywriter_file = folder / "copywriter.txt"
        if copywriter_file.exists():
            copywriter_content = read_txt_file(copywriter_file)
            if copywriter_content:
                description, tags = parse_copywriter_content(copywriter_content)
                print(f"从 copywriter.txt 读取文案")
                if not tags:
                    tags = ["图文", "抖音"]
        else:
            print(f"未找到 copywriter.txt，使用默认文案")
    
    print(f"最终标题: {title[:50]}..." if len(title) > 50 else f"最终标题: {title}")
    print(f"最终描述: {description[:50]}..." if len(description) > 50 else f"最终描述: {description}")
    print(f"最终标签: {tags}")
    
    return title, description, tags


def get_all_images(folder_path):
    """获取文件夹中的所有图片文件"""
    folder = Path(folder_path)
    
    # 获取所有图片文件
    image_extensions = ['.jpg', '.jpeg', '.png', '.bmp', '.webp']
    image_files = []
    for ext in image_extensions:
        image_files.extend(folder.glob(f"*{ext}"))
    
    # 自定义排序函数，封面文件排在最前面，其他按数字排序
    def sort_key(file_path):
        name = file_path.stem
        # 如果是封面文件，返回一个很小的数字让它排在最前面
        if '封面' in name:
            return -1
        
        # 提取文件名中的数字
        import re
        numbers = re.findall(r'\d+', name)
        if numbers:
            # 使用最后一个数字作为排序键
            return int(numbers[-1])
        else:
            # 如果没有数字，返回0
            return 0
    
    # 按自定义规则排序
    image_files.sort(key=sort_key)
    
    return image_files


async def main():
    # 配置参数
    folder_path = Path("D:\C盘转移\新言初小红书_言初咨询_17-05-47")  # 图片文件夹路径
    account_file = Path(BASE_DIR / "cookies" / "douyin_uploader" / "account.json")
    
    # 检查cookie是否有效
    if not await douyin_setup(account_file, handle=True):
        print("Cookie设置失败，请重新登录")
        return
    
    print("开始上传图片到抖音...")
    
    # 获取文件夹中的所有图片文件
    image_files = get_all_images(folder_path)
    
    if not image_files:
        print(f"错误: 在 {folder_path} 中未找到图片文件")
        return
    
    print(f"找到 {len(image_files)} 张图片")
    print(f"图片文件: {[f.name for f in image_files]}")
    
    # 获取标题、描述、标签（可通过参数覆盖）
    title, description, tags = get_title_description_tags(folder_path)
    
    # 检查图片文件是否存在
    valid_images = []
    for image_file in image_files:
        if image_file.exists():
            valid_images.append(str(image_file))
        else:
            print(f"警告: 图片文件不存在: {image_file}")
    
    if not valid_images:
        print("错误: 没有有效的图片文件")
        return
    
    # 限制最多9张图片（抖音限制）
    if len(valid_images) > 9:
        valid_images = valid_images[:9]
        print(f"警告: 图片数量超过9张，只上传前9张")
    
    # 生成发布时间
    # publish_datetimes = generate_schedule_time_next_day(1, 1, daily_times=[16])
    publish_datetimes = [0]
    
    # 创建DouYinImage实例
    douyin_image = DouYinImage(
        title=title,
        description=description,
        file_path=valid_images,
        tags=tags,
        publish_date=publish_datetimes[0],
        account_file=account_file,
        productLink="",
        productTitle="",
        music_name="唯一"  # 可以在这里设置背景音乐名称，如"轻音乐"、"钢琴曲"等
    )
    
    try:
        # 执行上传
        await douyin_image.main()
        print("✅ 图片上传完成！")
    except Exception as e:
        print(f"❌ 图片上传失败: {e}")
    
    print("\n上传任务完成！")


if __name__ == '__main__':
    # 运行批量上传
    asyncio.run(main())
