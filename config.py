import os
import psycopg2
from psycopg2.extras import RealDictCursor

# 基本路徑設定
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DATA_DIR = os.path.join(BASE_DIR, "game_data")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.6-flash")

DB_CONFIG = {
    "dbname": os.getenv("DB_NAME", "go_project_db"),
    "user": os.getenv("DB_USER", "go_user"),
    "password": os.getenv("DB_PASSWORD", ""), # 剛建好的專用帳號密碼
    "host": os.getenv("DB_HOST", "localhost"),
    "port": os.getenv("DB_PORT", "5432")
}

def get_db_connection():
    """
    建立並回傳 PostgreSQL 連線物件，可以在需要操作 DB 的地方呼叫 get_db_connection()
    """
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except psycopg2.Error as e:
        print(f"PostgreSQL 連線失敗: {e}")
        raise e

def test_connection():
    """連線測試工具函式"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT version();")
        db_version = cursor.fetchone()
        print(f"成功連線至 PostgreSQL!")
        print(f"資料庫版本: {db_version[0]}")
        cursor.close()
        conn.close()
    except Exception as e:
        print(f"連線測試失敗: {e}")

TARGET_GAMES = {
    "PokemonGO": {
        "ptt": {"board": "PokemonGO",
                "safety_pages": 2,
                "article_miss_limit": 10 },
        "dcard": {"mode": "topic", # 需事先確定好網址結構
                "query": "PokemonGo",
                "safety_pages": 2, # 安全頁數，爬蟲機制失敗才會發現
                "comment_limit": 5},
        "baha": {"board_id": 29659, 
                "safety_pages": 2,
                "article_miss_limit": 20,
                "floor_miss_limit": 2 }
    }
}

if __name__ == "__main__":
    test_connection()
