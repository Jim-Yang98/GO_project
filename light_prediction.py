import os
import time
import json
import pandas as pd
from datetime import datetime
from sqlalchemy import create_engine, text
from config import DB_CONFIG, GEMINI_MODEL
from google.genai import types
from google import genai
from sqlalchemy.exc import ProgrammingError

BASE_DIR = os.getcwd()

VALID_LABELS = {"positive", "neutral", "negative"}
DB_PLATFORMS = ["ptt", "baha", "dcard"]


def get_pg_engine():
    """建立並回傳 PostgreSQL 的 SQLAlchemy Engine"""
    user = DB_CONFIG.get("user", "postgres")
    password = DB_CONFIG.get("password", "your_password")
    host = DB_CONFIG.get("host", "localhost")
    port = DB_CONFIG.get("port", 5432)
    dbname = DB_CONFIG.get("dbname", "go_project_db")

    connection_string = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{dbname}"
    return create_engine(connection_string)


def fetch_unlabeled_comments(engine):
    all_rows = []

    with engine.connect() as conn:
        for platform in DB_PLATFORMS:
            comments_table = f"{platform}_comments"
            posts_table = f"{platform}_posts"

            query = f"""
                SELECT
                    c.comment_id,
                    '{platform}' AS platform,
                    p.title AS title,
                    c.comment AS comment
                FROM {comments_table} c
                JOIN {posts_table} p ON c.post_id = p.post_id
                WHERE c.predict_label IS NULL OR c.predict_label = ''
            """
            try:
                result = conn.execute(text(query))
                rows = result.mappings().all()
                print(f"[{platform}] 撈取到 {len(rows)} 筆尚未預測的留言")
                all_rows.extend(rows)
            except ProgrammingError as e:
                if "does not exist" in str(e):
                    print(f"[WARN] {platform} 相關資料表尚不存在，跳過")
                    conn.rollback()
                    continue
                raise

    if not all_rows:
        return pd.DataFrame(columns=["comment_id", "platform", "title", "comment"])

    return pd.DataFrame(all_rows)


def build_batch_prompt(batch_df):
    """
    組成批次情緒分類的 prompt，要求 Gemini 回傳 JSON array
    每筆帶入 comment_id，確保回應能準確對應回原始留言
    """
    items = []
    for _, row in batch_df.iterrows():
        items.append({
            "comment_id": row["comment_id"],
            "title": row["title"] or "",
            "comment": row["comment"] or ""
        })

    items_json = json.dumps(items, ensure_ascii=False)

    prompt = f"""你是一個情緒分析助手，任務是判斷社群留言的情緒傾向。

請針對以下每一則留言，參考其所屬文章標題提供的情境，判斷該留言的情緒屬於以下三類之一：
- "positive"（正向）
- "neutral"（中性）
- "negative"（負向）

輸入資料（JSON array，每筆包含 comment_id, title, comment）：
{items_json}

請只回傳一個 JSON array，每個元素格式為：
{{"comment_id": "<原樣照抄輸入的 comment_id>", "predict_label": "positive/neutral/negative 三選一"}}

不要加入任何其他文字或說明，只回傳 JSON array 本身。"""

    return prompt


def call_gemini(prompt, retries=3, delay=1):
    client = genai.Client(api_key=os.getenv("GEMINI_API_KEY"))

    for attempt in range(retries):
        try:
            res = client.models.generate_content(
                model=GEMINI_MODEL,
                contents=prompt,
                config=types.GenerateContentConfig(response_mime_type='application/json')
            )
            return res
        except Exception as e:
            error_str = str(e)
            if "404" in error_str and "NOT_FOUND" in error_str:
                print(f"[FATAL] 模型 {GEMINI_MODEL} 已下架或不存在，停止重試。錯誤內容：{e}")
                raise 

            wait = 2 ** attempt
            print(f"[ERROR] Gemini 嘗試第 {attempt+1} 次，{wait}s 後重試: {e}")
            time.sleep(wait)
    return None


def parse_and_validate_response(response, batch_df):
    """
    解析 Gemini 回應，驗證每筆 comment_id 都能對應回原始輸入、label
    回傳: (成功結果 list of dict, 失敗的 comment_id list)
    """
    if not response or not response.text:
        print("[ERROR] Gemini 未回傳內容，整批視為失敗")
        return [], batch_df["comment_id"].tolist()

    try:
        parsed = json.loads(response.text)
    except json.JSONDecodeError as e:
        print(f"[ERROR] JSON 解析失敗: {e}，整批視為失敗")
        return [], batch_df["comment_id"].tolist()

    if not isinstance(parsed, list):
        print("[ERROR] 回應不是 JSON array，整批視為失敗")
        return [], batch_df["comment_id"].tolist()

    expected_ids = set(batch_df["comment_id"].tolist())
    results = []
    matched_ids = set()

    for item in parsed:
        if not isinstance(item, dict):
            continue
        cid = item.get("comment_id")
        label = item.get("predict_label")

        if cid not in expected_ids:
            print(f"[WARN] 回應中出現非本批次的 comment_id: {cid}，忽略")
            continue

        if label not in VALID_LABELS:
            print(f"[WARN] comment_id={cid} 回傳標籤不合法: {label}，視為失敗")
            continue

        results.append({"comment_id": cid, "predict_label": label})
        matched_ids.add(cid)

    failed_ids = list(expected_ids - matched_ids)
    if failed_ids:
        print(f"[WARN] 本批次有 {len(failed_ids)} 筆未成功取得有效標籤")

    return results, failed_ids


def run_sentiment_prediction(df, batch_size=25):
    """
    對整份待預測 DataFrame 分批呼叫 Gemini，回傳所有成功結果與失敗清單
    """
    all_results = []
    all_failed_ids = []

    for start in range(0, len(df), batch_size):
        batch_df = df.iloc[start:start + batch_size]
        print(f"處理批次 {start // batch_size + 1}（{len(batch_df)} 筆）...")

        prompt = build_batch_prompt(batch_df)
        response = call_gemini(prompt)
        results, failed_ids = parse_and_validate_response(response, batch_df)

        all_results.extend(results)
        all_failed_ids.extend(failed_ids)

        time.sleep(1)  # 批次間稍作間隔，避免過於密集請求

    return all_results, all_failed_ids


def save_audit_csv(df, results, output_dir=BASE_DIR):
    """
    合併原始資料與預測結果，輸出一份檢查用 CSV
    """
    result_df = pd.DataFrame(results)
    merged = df.merge(result_df, on="comment_id", how="left")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    output_path = os.path.join(output_dir, f"predict_audit_{timestamp}.csv")
    merged.to_csv(output_path, index=False, encoding="utf-8-sig")
    print(f"檢查用 CSV 已輸出: {output_path}")
    return output_path


def update_predictions_to_db(engine, results):
    if not results:
        print("沒有可回寫的預測結果")
        return

    result_df = pd.DataFrame(results)
    records = result_df.to_dict(orient="records")

    total_updated = 0
    for platform in DB_PLATFORMS:
        table_name = f"{platform}_comments"

        update_sql = f"""
            UPDATE {table_name}
            SET predict_label = :predict_label
            WHERE comment_id = :comment_id;
        """
        try:
            with engine.begin() as conn:
                result = conn.execute(text(update_sql), records)
                total_updated += result.rowcount
        except ProgrammingError as e:
            if "does not exist" in str(e):
                print(f"[WARN] 資料表 {table_name} 尚不存在，跳過")
                continue
            raise

    print(f"全部更新完成！成功更新 {total_updated} 筆資料庫留言記錄。")

def ensure_predict_label_column(engine):
    """
    確保各平台 comments 表已具備 predict_label 欄位（若不存在則新增）
    若該平台的表尚未建立（例如該平台還沒跑過任何一次成功寫入），則跳過並提示
    """
    for platform in DB_PLATFORMS:
        table_name = f"{platform}_comments"
        alter_query = f"""
            ALTER TABLE {table_name}
            ADD COLUMN IF NOT EXISTS predict_label VARCHAR(50);
        """
        try:
            with engine.begin() as conn:
                conn.execute(text(alter_query))
        except ProgrammingError as e:
            if "UndefinedTable" in str(e.orig.__class__.__name__) or "does not exist" in str(e):
                print(f"[WARN] 資料表 {table_name} 尚不存在，跳過（該平台可能尚未執行過寫入）")
                continue
            raise  # 其他非預期的 DB 錯誤，不要吞掉，繼續往上拋讓你看到

    print("資料庫欄位檢查/擴充完成 (predict_label)")

def run_predict():
    engine = get_pg_engine()

    print("確認資料庫是否存在")
    ensure_predict_label_column(engine)

    print("Step 1: 撈取尚未預測的留言")
    df = fetch_unlabeled_comments(engine)

    if df.empty:
        print("沒有需要預測的新留言，結束。")
        return

    print(f"共 {len(df)} 筆待預測留言")

    print("Step 2: 呼叫 Gemini 進行情緒分類")
    results, failed_ids = run_sentiment_prediction(df)

    print(f"成功: {len(results)} 筆，失敗: {len(failed_ids)} 筆")

    print("Step 3a: 輸出檢查用 CSV...")
    save_audit_csv(df, results)

    print("Step 3b: 回寫預測結果至資料庫...")
    update_predictions_to_db(engine, results)

    engine.dispose()

    if failed_ids:
        print(f"注意：以下 comment_id 未能成功取得預測結果，需人工複查或重跑：{failed_ids}")


if __name__ == "__main__":
    run_predict()