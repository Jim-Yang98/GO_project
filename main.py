import os
import sys
from config import BASE_DIR, DATA_DIR, test_connection
from config import TARGET_GAMES, DATA_DIR
from crawlers.base_crawler import BaseCrawler
from crawlers.ptt_crawler import pttcrawler, PttParseError
from crawlers.dcard_crawler import dcardcrawler, DcardParseError
from crawlers.baha_crawler import bahacrawler, BahaParseError
from utils.data_cleaner import DataCleaner
from utils.data_converter import DataConverter

def run(game_keyword, platform_name, output_type="postgres"):
    """
    爬取--清洗--轉換，output_type 可選："csv", "postgres", "both"
    """
    print(f"\n***")
    print(f"開始處理：【{game_keyword}】的【{platform_name}】資料")
    print(f"***")

    game_cfg = TARGET_GAMES.get(game_keyword, {}).get(platform_name)
    if not game_cfg:
        print(f"找不到 {game_keyword} 在 {platform_name} 的設定，跳過。")
        return

    # 設定該次爬取的資料夾路徑
    raw_folder = os.path.join(DATA_DIR, game_keyword, platform_name)

    print(f"--- 階段 1: 開始爬取資料 ---")

    crawl_status = "ok"
    raw_file_path = None

    if platform_name == "ptt":
        crawler = pttcrawler.create(board=game_cfg["board"], save_folder=raw_folder)
        try:
            crawl_result = crawler.run(
                board=game_cfg["board"],
                safety_pages=game_cfg["safety_pages"],
                article_miss_limit=game_cfg.get("article_miss_limit", 10)
            )
        except PttParseError as e:
            print(f"[PTT] 爬蟲解析失敗，終止流程：{e}")
            raise

        crawl_status = crawl_result["status"]
        raw_file_path = crawl_result.get("raw_file_path")
        if crawl_status == "no_data":
            print(f"[PTT] {crawl_result['message']}")

    elif platform_name == "dcard":
        crawler = dcardcrawler.create(save_folder=raw_folder)
        try:
            crawl_result = crawler.run(
                mode=game_cfg["mode"], 
                query=game_cfg["query"], 
                safety_pages=game_cfg["safety_pages"], 
                comment_limit=game_cfg["comment_limit"]
            )
        except DcardParseError as e:
            print(f"[Dcard] 爬蟲失敗，終止流程：{e}")
            raise
        crawl_status = crawl_result["status"]
        raw_file_path = crawl_result.get("raw_file_path")
        if crawl_status == "no_data":
            print(f"[Dcard] {crawl_result['message']}")

    elif platform_name == "baha":
        crawler = bahacrawler.create(board=game_cfg["board_id"], save_folder=raw_folder)
        try:
            crawl_result = crawler.run(
                board_id=game_cfg["board_id"],
                safety_pages=game_cfg["safety_pages"],
                article_miss_limit=game_cfg.get("article_miss_limit", 10),
                floor_miss_limit=game_cfg.get("floor_miss_limit", 2)
            )
        except BahaParseError as e:
            print(f"[BAHA] 爬蟲解析失敗，終止流程：{e}")
            raise
        crawl_status = crawl_result["status"]
        raw_file_path = crawl_result.get("raw_file_path")
        if crawl_status == "no_data":
            print(f"[BAHA] {crawl_result['message']}")

    # 統一判斷：不管哪個平台，只要沒有新資料就跳過清洗/轉換/寫入DB
    if crawl_status == "no_data":
        print(f"[{platform_name.upper()}] 今天沒有新資料，跳過後續清洗與轉換階段。")
        return
    
    cleaner = DataCleaner()
    converter = DataConverter()

    print(f"--- 階段 2: 讀取原始 JSON 資料 ---")
    if platform_name in ("ptt", "dcard", "baha"):
        raw_data = converter.load_json_file(raw_file_path)
    else:
        raw_data = converter.load_json_folder(raw_folder)

    print(f"--- 階段 3: 進入 DataCleaner 進行數據清洗 ---")
    cleaned_data = cleaner.clean(platform=platform_name, data=raw_data)

    print(f"--- 階段 4: 進入 DataConverter 匯出結構化資料 ---")

    if output_type in ["csv", "both"]:
        df_result = converter.merge_and_explode_platforms(data_list=cleaned_data)
        if not df_result.empty:
            output_csv = os.path.join(DATA_DIR, f"{game_keyword}_{platform_name}_cleaned.csv")
            df_result.to_csv(output_csv, index=False, encoding="utf-8-sig")
            print(f" 成功存檔為 CSV: {output_csv}")
        else:
            print(" DataFrame 為空，取消 CSV 存檔。")

    if output_type in ["postgres", "both"]:
        print("\n 正在測試資料庫連線")
        try:
            test_connection()
        except Exception as e:
            print(f"\n 資料庫連線失敗，終止流程。請檢查 config.py 設定。錯誤: {e}")
            return
        print(f"開始將 [{platform_name}] 資料寫入 PostgreSQL...")
        converter.json_to_postgres(data=cleaned_data, platform=platform_name)

if __name__ == "__main__":
    run(game_keyword="PokemonGO", platform_name="dcard", output_type="postgres")

    print("\n 全流程執行完畢！")