import hashlib
import json
import os
import pandas as pd
import numpy as np
import psycopg2
from datetime import datetime
from config import get_db_connection

class DataConverter:
    def __init__(self):
        pass

    def merge_and_explode_platforms(self, folder_paths: list = None, data_list: list = None) -> pd.DataFrame:

        all_platform_data = []

        # 優先使用直接傳入的資料列表
        if data_list is not None:
            all_platform_data = data_list
        elif folder_paths is not None:
            for folder_path in folder_paths:
                if not os.path.exists(folder_path):
                    print(f"警告：找不到資料夾路徑 {folder_path}")
                    continue
                for filename in os.listdir(folder_path):
                    if not filename.endswith(".json"):
                        continue
                    file_path = os.path.join(folder_path, filename)
                    try:
                        with open(file_path, "r", encoding="utf-8") as f:
                            file_data = json.load(f)
                            if isinstance(file_data, list):
                                all_platform_data.extend(
                                    file_data
                                )

                    except Exception as e:
                        print(f"讀取失敗: {file_path}")
                        print(e)

        if not all_platform_data:
            print("未讀取到任何資料")
            return pd.DataFrame()

        base_df = pd.DataFrame(
            all_platform_data
        )

        required_fields = [
            "platform", "post_time", "author", "title", "content", "total_reac", "comment_count", "comments_data"
        ]

        for field in required_fields:
            if field not in base_df.columns:
                base_df[field] = None

        # comments_data 統一格式
        base_df["comments_data"] = (
            base_df["comments_data"].apply(lambda x: x if isinstance(x, list) else [])
        )

        exploded_df = (
            base_df.explode("comments_data").reset_index(drop=True)
        )

        # 只保留 dict 型態
        valid_comments = exploded_df[
            exploded_df["comments_data"].apply(lambda x:isinstance(x, dict)
            )
        ]

        if not valid_comments.empty:
            comments_normalized = (
                pd.json_normalize(
                    valid_comments[
                        "comments_data"
                    ]
                )
            )

            comments_normalized.index = (
                valid_comments.index
            )
        else:
            comments_normalized = (
                pd.DataFrame(
                    index=exploded_df.index
                )
            )

        exploded_df = exploded_df.drop(
            columns=["comments_data"]
        )

        final_df = pd.concat(
            [exploded_df, comments_normalized
            ],axis=1
        )
        if "comment_author" not in final_df.columns:
            final_df["comment_author"] = np.nan

        if "comment" not in final_df.columns:
            final_df["comment"] = np.nan
        print(
            f"總列數：{len(final_df)}"
        )

        return final_df

    def generate_md5_id(self, platform, post_time, author, title):
        """組合主要欄位計算 MD5"""
        short_title = str(title)[:10] if title else ""
        unique_str = f"{platform}_{post_time}_{author}_{short_title}"
        return hashlib.md5(unique_str.encode('utf-8')).hexdigest()

    def load_json_file(self, file_path: str):
        all_data = []
        if not file_path or not os.path.exists(file_path):
            print(f"警告：找不到檔案路徑 {file_path}")
            return all_data
        try:
            with open(file_path, 'r', encoding='utf-8') as f:
                file_data = json.load(f)
                if isinstance(file_data, list):
                    all_data.extend(file_data)
        except Exception as e:
            print(f"讀取失敗: {file_path}，原因: {e}")
        return all_data

    def load_json_folder(self, folder_path: str):
        all_data = []
        if not os.path.exists(folder_path):
            print(f"警告：找不到資料夾路徑 {folder_path}")
            return all_data
            
        for filename in os.listdir(folder_path):
            if not filename.endswith(".json"):
                continue
            file_path = os.path.join(folder_path, filename)
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    file_data = json.load(f)
                    if isinstance(file_data, list):
                        all_data.extend(file_data)
            except Exception as e:
                print(f"讀取失敗: {file_path}，原因: {e}")
        return all_data

    # 建立資料表架構 (移除 comment_tag)
    def _create_tables(self, cursor, table_prefix):
        # 貼文主表（不變）
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_prefix}_posts (
                post_id CHAR(32) PRIMARY KEY,
                platform VARCHAR(50),
                post_time TIMESTAMPTZ,
                author VARCHAR(255),
                total_reac INTEGER DEFAULT 0,
                title TEXT NOT NULL,
                content TEXT,
                comment_count INTEGER DEFAULT 0,
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
        ''')
        # 留言副表：comment_id 是內容 hash（跟 posts 表設計一致）
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_prefix}_comments (
                comment_id CHAR(32) PRIMARY KEY,
                post_id CHAR(32) REFERENCES {table_prefix}_posts(post_id) ON DELETE CASCADE,
                comment_author VARCHAR(255),
                comment TEXT,
                like_count INTEGER DEFAULT 0,
                comment_floor INTEGER,       -- 留言樓層
                source_platform VARCHAR(50),
                created_at TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
            );
        ''')

    # 檢查函式
    def _is_valid_post(self, post):
        title = post.get("title")
        content = post.get("content", "") or ""
        post_time_str = post.get("post_time")

        # 標題驗證：空標題或全空白過濾掉
        if not title or not str(title).strip():
            return False

        # 過濾刪除文
        if "[文章已刪除]" in content or "[已刪除]" in str(title):
            return False

        # 發文時間驗證：若解析成功且晚於當前時間則過濾
        if post_time_str:
            try:
                post_dt = pd.to_datetime(post_time_str)
                if post_dt > datetime.now(post_dt.tz):
                    return False
            except Exception:
                pass
        return True

    # 統一中央處理器
    def _insert_generic_data(self, cursor, data, table_prefix):
        self._create_tables(cursor, table_prefix)

        inserted_posts_count = 0
        skipped_posts_count = 0

        for post in data:
            if not self._is_valid_post(post):
                skipped_posts_count += 1
                continue

            post_id = self.generate_md5_id(
                post.get("platform"),
                post.get("post_time"),
                post.get("author"),
                post.get("title")
            )

            cursor.execute(f'''
                INSERT INTO {table_prefix}_posts (
                    post_id, platform, post_time, author, total_reac, title, content, comment_count
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT (post_id) DO NOTHING;
            ''', (
                post_id,
                post.get("platform"),
                post.get("post_time"),
                post.get("author"),
                post.get("total_reac"),
                post.get("title"),
                post.get("content"),
                post.get("comment_count")
            ))

            inserted_posts_count += 1

            comments_data = post.get("comments_data", [])
            if isinstance(comments_data, list):
                for c in comments_data:
                    if not isinstance(c, dict):
                        continue

                    comment_author = c.get("comment_author") or c.get("author") or "Unknown"
                    comment_text = c.get("comment") or c.get("content") or ""
                    like_count = c.get("like_count") or c.get("likes") or 0

                    # comment_id：內容 hash，跟 posts 表設計一致
                    raw_comment_id_str = f"{post_id}_{comment_author}_{comment_text}"
                    comment_id = hashlib.md5(raw_comment_id_str.encode("utf-8")).hexdigest()

                    cursor.execute(f'''
                        INSERT INTO {table_prefix}_comments (
                            comment_id, post_id, comment_author, comment, like_count, source_platform
                        ) VALUES (%s, %s, %s, %s, %s, %s)
                        ON CONFLICT (comment_id) DO NOTHING;
                    ''', (
                        comment_id,
                        post_id,
                        comment_author,
                        comment_text,
                        like_count,
                        post.get("platform")
                    ))


    
    # 各平台對應分流
    def _postgres_ptt(self, cursor, data):
        self._insert_generic_data(cursor, data, "ptt")

    def _postgres_baha(self, cursor, data):
        self._insert_generic_data(cursor, data, "baha")

    def _postgres_dcard(self, cursor, data):
        self._insert_generic_data(cursor, data, "dcard")

    # 主流程
    def json_to_postgres(self, data, platform):
        """
        :param data: 已清洗的資料（list of dict），而非檔案路徑
        """
        if not data:
            print(f"[{platform}] 錯誤: 沒有資料可寫入")
            return

        process_map = {
            "ptt": self._postgres_ptt,
            "baha": self._postgres_baha,
            "dcard": self._postgres_dcard
        }

        process_func = process_map.get(platform.lower())
        if not process_func:
            raise ValueError(f"未支援該類型平台: {platform}")

        conn = None
        try:
            conn = get_db_connection()
            cursor = conn.cursor()

            process_func(cursor, data)

            conn.commit()
            cursor.close()
            print(f"成功將 [{platform}] 轉入 PostgreSQL 資料庫！")
        except Exception as e:
            if conn:
                conn.rollback()
            print(f"PostgreSQL 匯入失敗: {e}")
        finally:
            if conn:
                conn.close()