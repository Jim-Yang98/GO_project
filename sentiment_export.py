import os
import pandas as pd
from sqlalchemy import create_engine
from config import DB_CONFIG

# 資料庫連線配置 (PostgreSQL)
def get_pg_engine():
    """建立並回傳 PostgreSQL 的 SQLAlchemy Engine"""
    # 也可以直接引用 config.py 的連線參數
    user = DB_CONFIG.get("user", "postgres")
    password = DB_CONFIG.get("password", "your_password")
    host = DB_CONFIG.get("host", "localhost")
    port = DB_CONFIG.get("port", 5432)
    dbname = DB_CONFIG.get("dbname", "go_project_db")

    # 組裝連線字串
    connection_string = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(connection_string)


# 關鍵字與查詢邏輯
PLATFORM_LIST = ["ptt", "baha", "dcard"]

POSITIVE_KEYWORDS = [
    "超讚", "很讚", "超強", "佛心", "真香", "畢業",
    "賺爛", "感謝N社", "感謝s社", "高興",
    "優質", "感動", "好看", "好玩"
]
NEGATIVE_KEYWORDS = [
    "爛活動", "超爛", "討厭", "垃圾",
    "愛錢", "騙錢", "坑錢", "機率低", "bug"
]
NEUTRAL_KEYWORDS = [
    "普通", "地點", "還好吧", "兌換"
]

def build_or_condition(keywords):
    """產生 SQL 的 LIKE 條件式"""
    return " OR ".join([f"c.comment LIKE '%%{kw}%%'" for kw in keywords])

def fetch_comments(engine, platform, or_condition, limit=None):
    """查詢單一平台留言，limit=None 表示取全部"""
    limit_clause = f"LIMIT {limit}" if limit else ""
    
    # 針對 PostgreSQL 優化 SQL 查詢
    query = f"""
    SELECT
        '{platform}'   AS platform,
        p.title        AS title,
        c.comment      AS comment,
        COALESCE(p.total_reac, 0) AS total_reac
    FROM {platform}_comments c
    LEFT JOIN {platform}_posts p ON c.post_id = p.post_id
    WHERE c.comment IS NOT NULL AND c.comment != ''
      AND ({or_condition})
    ORDER BY COALESCE(p.total_reac, 0) DESC
    {limit_clause};
    """

    return pd.read_sql_query(query, engine)

# 主執行流程
def run_sentiment_export():
    print("開始執行社群留言情緒標籤資料導出流程...")
    
    engine = get_pg_engine()
    all_frames = []

    try:
        for platform in PLATFORM_LIST:
            print(f"正在查詢 [{platform.upper()}] 平台留言...")
            
            # 正向
            pos_df = fetch_comments(engine, platform, build_or_condition(POSITIVE_KEYWORDS), limit=None)
            pos_df["sentiment"] = "positive"

            # 負向
            neg_df = fetch_comments(engine, platform, build_or_condition(NEGATIVE_KEYWORDS), limit=30)
            neg_df["sentiment"] = "negative"

            # 中立
            neu_df = fetch_comments(engine, platform, build_or_condition(NEUTRAL_KEYWORDS), limit=30)
            neu_df["sentiment"] = "neutral"

            all_frames.extend([pos_df, neg_df, neu_df])

    except Exception as e:
        print(f"讀取 PostgreSQL 資料庫時發生錯誤: {e}")
        return
    finally:
        engine.dispose()

    # 合併 DataFrame
    combined_df = pd.concat(all_frames, ignore_index=True)

    # 新增空欄位
    combined_df["label"] = ""
    combined_df["remark"] = ""

    output_path = os.path.join(BASE_DIR if 'BASE_DIR' in globals() else os.getcwd(), "comments_combined.xlsx")
    combined_df.to_excel(output_path, index=False)

    print(f"處理完畢！共 {len(combined_df)} 筆留言，已成功匯出至: {output_path}")

if __name__ == "__main__":
    run_sentiment_export()