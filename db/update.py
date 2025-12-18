import sqlite3
import os

# 数据库文件路径
db_file = './database.db'

def update_all_types_to_douyin():
    print(f"Connecting to database at: {os.path.abspath(db_file)}")
    
    if not os.path.exists(db_file):
        print("❌ Database file not found!")
        return

    conn = sqlite3.connect(db_file)
    cursor = conn.cursor()

    try:
        # 将 user_info 表中所有记录的 type 字段更新为 3 (快手)
        cursor.execute("UPDATE user_info SET type = 3")
        conn.commit()
        print(f"✅ 更新成功: 已将 {cursor.rowcount} 条记录的 type 更新为 3")
        
        # 验证更新结果
        print("\n📋 更新后的数据表内容：")
        cursor.execute("SELECT * FROM user_info")
        rows = cursor.fetchall()
        for row in rows:
            print(row)
            
    except Exception as e:
        print(f"❌ 更新失败: {str(e)}")
    finally:
        conn.close()

if __name__ == "__main__":
    update_all_types_to_douyin()
