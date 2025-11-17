import asyncio
from pathlib import Path
import re
from datetime import datetime

from conf import BASE_DIR
from uploader.douyin_uploader.main import douyin_setup
from uploader.douyin_uploader.customMain import DouYinImage
from utils.files_times import generate_schedule_time_next_day


def parse_txt_content(txt_file_path):
    """解析txt文件内容：第一个#后面是标题，中间是文案描述，最后的#是标签"""
    try:
        with open(txt_file_path, 'r', encoding='utf-8') as f:
            content = f.read().strip()
        
        # 按行分割内容
        lines = content.split('\n')
        
        # 查找第一个以#开头的行作为标题
        title = "图文发布"
        description_lines = []
        hashtag_lines = []
        
        # 标记是否已经找到标题
        title_found = False
        # 标记是否开始收集hashtag
        collecting_hashtags = False
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
                
            # 如果行以#开头且还没找到标题，这就是标题
            if line.startswith('#') and not title_found:
                title = line[1:].strip()  # 去掉#号
                title_found = True
            # 如果行全部都是#开头的词（标签行）
            elif re.match(r'^#\w+(\s+#\w+)*\s*$', line):
                collecting_hashtags = True
                hashtag_lines.append(line)
            # 如果已经在收集hashtag但遇到非hashtag行，停止收集
            elif collecting_hashtags and not line.startswith('#'):
                break
            # 如果已经找到标题但还没开始收集hashtag，这是描述内容
            elif title_found and not collecting_hashtags:
                description_lines.append(line)
        
        # 合并描述内容
        description = '\n'.join(description_lines)
        
        # 提取所有hashtag
        hashtag_text = ' '.join(hashtag_lines)
        hashtag_pattern = r'#(\w+)'
        hashtags = re.findall(hashtag_pattern, hashtag_text)
        
        # 组合标题和描述作为完整标题
        if description:
            full_title = f"{title}\n{description}"
        else:
            full_title = title
            
        return full_title, hashtags
        
    except Exception as e:
        print(f"解析txt文件失败: {e}")
        return "图文发布", ["图文", "抖音"]


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
    
    # 查找txt文件
    txt_files = list(folder_path.glob("*.txt"))
    
    if txt_files:
        txt_file = txt_files[0]  # 使用第一个txt文件
        print(f"使用txt文件: {txt_file.name}")
        
        # 解析标题和hashtag
        title, tags = parse_txt_content(txt_file)
        print(f"解析到的标题: {title[:50]}..." if len(title) > 50 else f"解析到的标题: {title}")
        print(f"解析到的标签: {tags}")
    else:
        title = "图文发布"
        tags = ["图文", "抖音"]
        print(f"未找到txt文件，使用默认标题: {title}")
    
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
