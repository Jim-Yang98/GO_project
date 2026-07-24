from random import random
from datetime import datetime
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import parse_qs, urlparse
import random
from crawlers.base_crawler import BaseCrawler



class bahacrawler(BaseCrawler):
    
    default_pages = 1
    BASE_URL = "https://forum.gamer.com.tw"

    def __init__(self, board, save_folder="baha_data"):
        super().__init__(topic_name=board, save_folder=save_folder)
        self.board = board
        self.headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/122.0.0.0 Safari/537.36"
    }
    @classmethod
    def create(cls, board, save_folder="baha_data"):
        return cls(board=board, save_folder=save_folder)
    
    # 建立看板型url
    def build_board_url(self, board_id, page=1):
        return f"{self.BASE_URL}/B.php?page={page}&bsn={board_id}"

    # 建立文章型url
    def build_article_url(self, board_id, article_id, page=1):
        return f"{self.BASE_URL}/C.php?page={page}&bsn={board_id}&snA={article_id}"
    
    def crawl_board(self, board_id, max_pages):
        return self.parse_article(board_id, article_id=max_pages, page=1)

    def crawl_article(self, board_id, article_id):
        return self.parse_article(board_id, article_id, page=1)
    
    def fetch_article_ids(self, board_id, page=1):
        url = self.build_board_url(board_id, page)
        max_retries = 3  # 最大嘗試次數
        
        for attempt in range(1, max_retries + 1):
            try:
                res = requests.get(url, headers=self.headers, timeout=10)
                
                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    # 放寬選擇器，直接抓取文章標題連結
                    links = soup.select(".b-list__main__title")
                    return links # 或你原本後續處理 links 的 logic（註：若下方還有處理邏輯，請看下方說明）
                    
                else:
                    print(f" 看板列表請求失敗，狀態碼: {res.status_code} (第 {attempt}/{max_retries} 次嘗試)")
                    
            except requests.RequestException as e:
                # 捕捉連線超時、斷線等異常
                print(f" 網路請求異常: {e} (第 {attempt}/{max_retries} 次嘗試)")
            
            # 如果還沒到最後一次嘗試，就等待幾秒後再重試
            if attempt < max_retries:
                sleep_time = random.uniform(2, 5) # 隨機等待 2~5 秒，模擬真人行為
                print(f" 將於 {sleep_time:.1f} 秒後重新嘗試...")
                time.sleep(sleep_time)
                
        # 若 3 次都失敗，最終返回空列表
        print(f" 錯誤：已重試 {max_retries} 次均失敗，放棄此頁面。")
        return []
    
    def get_total_pages(self, board_id, article_id):
        url = self.build_article_url(board_id, article_id, page=1)
        try:
            res = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(res.text, "html.parser")
            
            # 尋找分頁元件
            pagination = soup.select_one(".BH-pagebtnA")
            if not pagination:
                return 1
            max_page = 1
            for a_tag in pagination.select("a"):
                href = a_tag.get("href", "")
                parsed_url = urlparse(href)
                query_params = parse_qs(parsed_url.query)
                page_val = query_params.get('page', [None])[0]
                if page_val and page_val.isdigit():
                    max_page = max(max_page, int(page_val))
                
            return max_page
        except Exception as e:
            print(f" 抓取文章總頁數失敗 ({e})，預設為 1 頁")
            return 1
        
        # # 抓取最後一頁的數字
        # last_page_btn = pagination.select("a")[-1]
        # if last_page_btn:
        #     try:
        #         return int(last_page_btn.text)
        #     except:
        #         return 1
        # return 1

    def format_data(self, post, main_title):
        # 標題
        try:
            title_ele = post.select_one("h1.c-post__header__title")
            title = title_ele.text.strip() if title_ele else main_title
        except:
            title = main_title

        # 作者
        try:
            author_ele = post.select_one("a.username")
            author = author_ele.text.strip() if author_ele else "Anonymous"
        except:
            author = "Anonymous"

        # 時間
        try:
            time_ele = post.select_one('.c-post__header__info a.edittime')

            if time_ele and time_ele.has_attr("data-mtime"):
                raw_time = time_ele["data-mtime"]
                
                dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
                post_time = dt.strftime("%Y-%m-%d")
            else:
                post_time = "未成功抓取時間"
        except Exception as e:
            post_time = f"解析失敗: {e}"

        # 互動數(任何)
        try:
            like_tag = post.select_one("a.count.tippy-gpbp-list")
            total_reac = int(like_tag.text.strip()) if like_tag else 0
        except:
            total_reac = 0

        # 內文
        try:
            content = post.select_one("div.c-article__content").text.strip()
        except:
            content = ""
        
        # 留言
        formatted_comments = []
        for c in post.select(".c-reply__item"):
            try:
                # 巴哈留言作者
                c_author_ele = c.select_one(".reply-content__user")
                c_author = c_author_ele.text.strip().replace("：", "") if c_author_ele else "Anonymous"
                
                c_text = c.select_one(".reply-content__article").text.strip()
                
                formatted_comments.append({
                    "comment_author": c_author,
                    "comment": c_text
                })
            except:
                continue

        return {
            "platform": "Bahamut",
            "post_time": post_time,
            "author": author,
            "title": title,
            "content": content,
            "total_reac": total_reac,
            "comment_count": len(formatted_comments),
            "comments_data": formatted_comments
        }

    def parse_article(self, board_id, article_id, page=1):
        url = self.build_article_url(board_id, article_id, page)

        try:
            res = requests.get(url, headers=self.headers)
            soup = BeautifulSoup(res.text, "html.parser")
        except Exception as e:
            print(f"網路請求失敗: {e}")
            return []
        
        all_floor_data = []
        
        posts = soup.select(".c-section")

        main_title_ele = soup.select_one("h1.c-post__header__title")
        main_title = main_title_ele.text.strip() if main_title_ele else "巴哈討論串"
        for post in posts:
            # 呼叫 format_data
            floor_data = self.format_data(post, main_title)
            all_floor_data.append(floor_data)
            
        return all_floor_data

    def run(self, board_id, start_board_page=1, end_board_page=1, reply_pages=2):
        """
        執行動態分頁爬取
        :param board_id: 看板代號 (bsn)
        :param start_board_page: 開始爬取的看板頁碼
        :param end_board_page: 結束爬取的看板頁碼
        :param reply_pages: 預計爬取的文章內回覆頁數
        """
        # 參數檢查
        if start_board_page < 1 or end_board_page < start_board_page:
            print("錯誤：頁碼設定不合法。請確保 start_board_page >= 1 且 end_board_page >= start_board_page")
            return []
        
        all_data = []

        for p in range(start_board_page, end_board_page + 1):
            print(f"正在掃描看板第 {p} 頁列表...")
            aids = self.fetch_article_ids(board_id, p)

            for aid in aids:
                print(f"  -> 處理文章 ID: {aid}")

                # 判斷回覆頁數
                total_pages = self.get_total_pages(board_id, aid)
                print(f"     共 {total_pages} 頁回覆")

                if total_pages > 3:
                    start_page = total_pages
                    end_page = max(total_pages - reply_pages + 1, 1)
                    target_pages = list(range(start_page, end_page - 1, -1  ))
                else:
                    target_pages = list(range(1, min(total_pages, reply_pages) + 1))

                for page in target_pages:
                    print(f"     -> 抓取第 {page} 頁回覆...")
                    page_data = self.parse_article(board_id, aid, page=page)
                    all_data.extend(page_data)
                    time.sleep(random.uniform(2, 4))

        self.save_data(all_data, f"baha_{board_id}")
        return all_data