import os
from config import TARGET_GAMES, DATA_DIR
from crawlers.base_crawler import BaseCrawler
from crawlers.ptt_crawler import pttcrawler
from crawlers.dcard_crawler import dcardcrawler
from crawlers.baha_crawler import bahacrawler
from utils.data_cleaner import DataCleaner
from utils.data_converter import DataConverter

def run(game_keyword, platform_name, output_type="csv"):
    """
    爬取--清洗--轉換
    """
    print(f"\n***")
    print(f"開始處理：【{game_keyword}】的【{platform_name.upper()}】資料")
    print(f"***")

    game_cfg = TARGET_GAMES.get(game_keyword, {}).get(platform_name)
    if not game_cfg:
        print(f"找不到 {game_keyword} 在 {platform_name} 的設定，跳過。")
        return

    # 設定該次爬取的資料夾路徑
    raw_folder = os.path.join(DATA_DIR, game_keyword, platform_name)

    # 執行爬蟲
    print(f"--- 階段 1: 開始爬取資料 ---")
    if platform_name == "ptt":
        crawler = pttcrawler.create(board=game_cfg["board"], save_folder=raw_folder)
        crawler.run(board=game_cfg["board"], start_index=game_cfg["start_index"], pages=game_cfg["pages"])
    elif platform_name == "dcard":
        crawler = dcardcrawler.create(save_folder=raw_folder)
        crawler.run(mode=game_cfg["mode"], query=game_cfg["query"], pages=game_cfg["pages"], comment_limit=game_cfg["comment_limit"])
    elif platform_name == "baha":
        crawler = bahacrawler.create(board=game_cfg["board_id"], save_folder=raw_folder)
        crawler.run(board_id=game_cfg["board_id"], start_board_page=game_cfg["start_board_page"], end_board_page=game_cfg["end_board_page"], reply_pages=game_cfg["reply_pages"])

    cleaner = DataCleaner()
    converter = DataConverter()

    print(f"--- 階段 2: 讀取原始 JSON 資料 ---")
    raw_data = converter.load_json_folder(raw_folder)

    print(f"--- 階段 3: 進入 DataCleaner 進行數據清洗 ---")
    cleaned_data = cleaner.clean(platform=platform_name, data=raw_data)

    print(f"--- 階段 4: 進入 DataConverter 匯出結構化資料 ---")
    
    # 輸出 CSV
    if output_type in ["csv", "both"]:
        df_result = converter.merge_and_explode_platforms(data_list=cleaned_data)
        if not df_result.empty:
            output_csv = os.path.join(DATA_DIR, f"{game_keyword}_{platform_name}_cleaned.csv")
            df_result.to_csv(output_csv, index=False, encoding="utf-8-sig")
            print(f" 成功存檔為 CSV: {output_csv}")
        else:
            print(" DataFrame 為空，取消 CSV 存檔。")

    # 輸出 SQLite
    if output_type in ["sqlite", "both"]:
        db_name = os.path.join(DATA_DIR, f"{game_keyword}_database.db")
        converter.json_to_sqlite(raw_folder, db_name=db_name, platform=platform_name)
        print(f" 成功寫入資料庫: {db_name}")

if __name__ == "__main__":
    run(game_keyword="tower_of_saviors", platform_name="baha", output_type="csv")
    
    print("\n 全流程執行完畢！")