import hashlib
import json
import os
import pandas as pd
import numpy as np
import sqlite3

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

    # 建立資料表架構 (徹底拔除 comment_tag)
    def _create_tables(self, cursor, table_prefix):
        # 貼文主表
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_prefix}_posts (
                post_id CHAR(32) PRIMARY KEY,
                platform TEXT,
                post_time TEXT,
                author TEXT,
                total_reac INTEGER,
                title TEXT,
                content TEXT,
                comment_count INTEGER
            )
        ''')
        # 留言副表 (拔除 comment_tag 欄位)
        cursor.execute(f'''
            CREATE TABLE IF NOT EXISTS {table_prefix}_comments (
                comment_id INTEGER PRIMARY KEY AUTOINCREMENT,
                post_id CHAR(32),
                comment_author TEXT,
                comment TEXT,
                FOREIGN KEY (post_id) REFERENCES {table_prefix}_posts (post_id)
            )
        ''')


    # 統一中央處理器 (四個平台共用此邏輯)
    def _insert_generic_data(self, cursor, data, table_prefix):
        self._create_tables(cursor, table_prefix)
        
        for post in data:
            # 計算貼文唯一 ID (用於資料庫防重複)
            post_id = self.generate_md5_id(
                post.get("platform"), 
                post.get("post_time"), 
                post.get("author"), 
                post.get("title")
            )
            
            # 寫入貼文主表
            cursor.execute(f'''
                INSERT OR IGNORE INTO {table_prefix}_posts (
                    post_id, platform, post_time, author, total_reac, title, content, comment_count
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
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
            
            # 展開並寫入留言副表
            comments_data = post.get("comments_data", [])
            for c in comments_data:
                if not isinstance(c, dict):
                    continue
                cursor.execute(f'''
                    INSERT INTO {table_prefix}_comments (
                        post_id, comment_author, comment
                    ) VALUES (?, ?, ?)
                ''', (
                    post_id,
                    c.get("comment_author"),
                    c.get("comment")
                ))


    # 各平台對應分流 (PTT 現在也整合進來了)
    def _sqlite_ptt(self, cursor, data):
        self._insert_generic_data(cursor, data, "ptt")

    def _sqlite_fb(self, cursor, data):
        self._insert_generic_data(cursor, data, "fb")

    def _sqlite_baha(self, cursor, data):
        self._insert_generic_data(cursor, data, "baha")

    def _sqlite_dcard(self, cursor, data):
        self._insert_generic_data(cursor, data, "dcard")


    # 主進入點流程
    def json_to_sqlite(self, folder_path, db_name, platform):
        data = self.load_json_folder(folder_path)
        if not data:
            print(f"[{platform}] 錯誤: 資料夾內無資料或路徑錯誤")
            return
        
        sqlite_process_map = {
            "ptt": self._sqlite_ptt,
            "fb": self._sqlite_fb,
            "baha": self._sqlite_baha,
            "dcard": self._sqlite_dcard
        }

        process_func = sqlite_process_map.get(platform.lower())
        if not process_func:
            raise ValueError(f"未支援該類型平台: {platform}")
            
        try:
            con = sqlite3.connect(db_name)
            cursor = con.cursor()
            cursor.execute("PRAGMA foreign_keys = ON;")
            
            process_func(cursor, data)
            
            con.commit()
            con.close()
            print(f" 成功將 [{platform}] 轉入 SQLite 資料庫: {db_name} (共 {len(data)} 篇貼文)")
        except Exception as e:
            print(f" SQLite 匯入失敗: {e}")