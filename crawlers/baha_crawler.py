from random import random
from datetime import datetime, timedelta
import re
import time
import requests
from bs4 import BeautifulSoup
from urllib.parse import parse_qs, urlparse
import random
from crawlers.base_crawler import BaseCrawler

class BahaParseError(Exception):
    pass


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
    
    def _extract_query_param(self, href, param):
        parsed = urlparse(href)
        qs = parse_qs(parsed.query)
        return qs.get(param, [None])[0]

    def parse_latest_reply_date(self, raw_text):
        """
        確認"最新回覆"欄位文字，回傳 date ；無法辨識回傳 None
        已知格式：剛剛 / X 分鐘前 / X 小時前 / 昨天 HH:MM / 前天 HH:MM / MM-DD HH:MM
        （一週以前格式不考慮，safety_pages 限制在近期範圍內）
        """
        raw_text = raw_text.strip()
        now = datetime.now()
        today = now.date()

        if raw_text == "剛剛":
            return today

        m = re.match(r'^(\d+)\s*分鐘前$', raw_text)
        if m:
            return (now - timedelta(minutes=int(m.group(1)))).date()

        m = re.match(r'^(\d+)\s*小時前$', raw_text)
        if m:
            return (now - timedelta(hours=int(m.group(1)))).date()

        if raw_text.startswith("昨天"):
            return today - timedelta(days=1)

        if raw_text.startswith("前天"):
            return today - timedelta(days=2)

        m = re.match(r'^(\d{2})-(\d{2})\s+\d{2}:\d{2}$', raw_text)
        if m:
            month, day = int(m.group(1)), int(m.group(2))
            try:
                dt = datetime(now.year, month, day).date()
            except ValueError:
                return None
            if dt > today:  # 跨年邊界防呆：日期不應晚於今天
                dt = datetime(now.year - 1, month, day).date()
            return dt

        return None
    
    def fetch_article_list(self, board_id, page=1):
        """
        回傳當頁文章列表
        網路請求重試3次仍失敗，回傳 None（傳 raise BahaParseError）
        """
        url = self.build_board_url(board_id, page)
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                res = requests.get(url, headers=self.headers, timeout=10)

                if res.status_code == 200:
                    soup = BeautifulSoup(res.text, "html.parser")
                    rows = soup.select("tr.b-list__row")
                    results = []

                    for row in rows:
                        title_ele = row.select_one(".b-list__main__title")
                        time_ele = row.select_one(".b-list__time__edittime a")
                        if not title_ele or not time_ele:
                            continue  # 缺少必要欄位（例如廣告列），跳過

                        # 從標題連結取得 article_id（snA 參數）
                        title_link = title_ele if title_ele.name == "a" else title_ele.find_parent("a")
                        href = title_link.get("href", "") if title_link else ""
                        article_id = self._extract_query_param(href, "snA")

                        if not article_id:
                            # 備用：從「最新回覆」連結取得（同一列必為同一篇文章）
                            article_id = self._extract_query_param(time_ele.get("href", ""), "snA")

                        if not article_id:
                            continue  # 兩邊都拿不到 id，跳過

                        results.append({
                            "article_id": article_id,
                            "title": title_ele.text.strip(),
                            "time_text": time_ele.text.strip()
                        })
                    return results
                else:
                    print(f" 看板列表請求失敗，狀態碼: {res.status_code} (第 {attempt}/{max_retries} 次嘗試)")

            except requests.RequestException as e:
                print(f" 網路請求異常: {e} (第 {attempt}/{max_retries} 次嘗試)")

            if attempt < max_retries:
                sleep_time = random.uniform(2, 5)
                print(f" 將於 {sleep_time:.1f} 秒後重新嘗試...")
                time.sleep(sleep_time)

        print(f" 錯誤：已重試 {max_retries} 次均失敗，放棄此頁面。")
        return None
    
    def get_total_pages(self, board_id, article_id):
        url = self.build_article_url(board_id, article_id, page=1)
        max_retries = 3

        for attempt in range(1, max_retries + 1):
            try:
                res = requests.get(url, headers=self.headers, timeout=10)
                soup = BeautifulSoup(res.text, "html.parser")

                pagination = soup.select_one(".BH-pagebtnA")
                if not pagination:
                    return 1

                max_page = 1
                for a_tag in pagination.select("a"):
                    page_val = self._extract_query_param(a_tag.get("href", ""), "page")
                    if page_val and page_val.isdigit():
                        max_page = max(max_page, int(page_val))
                return max_page

            except requests.RequestException as e:
                print(f" 抓取文章總頁數失敗: {e} (第 {attempt}/{max_retries} 次嘗試)")
                if attempt < max_retries:
                    time.sleep(random.uniform(2, 5))

        # 重試用盡仍失敗
        raise BahaParseError(f"抓取文章總頁數失敗（article_id={article_id}），已重試 {max_retries} 次")


    def format_data(self, post, main_title):
            # 優先檢查內文
            try:
                content_ele = post.select_one("div.c-article__content")
                content = content_ele.text.strip() if content_ele else ""
                if not content:  # 內文為空直接放棄
                    return None
            except:
                return None

            # 時間解析
            try:
                time_ele = post.select_one('.c-post__header__info a.edittime')
                if time_ele and time_ele.has_attr("data-mtime"):
                    raw_time = time_ele["data-mtime"]
                    dt = datetime.strptime(raw_time, "%Y-%m-%d %H:%M:%S")
                    post_time = dt.strftime("%Y-%m-%d")
                else:
                    return None  # 抓不到時間直接放棄
            except Exception:
                return None

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

            # 互動數
            try:
                like_tag = post.select_one("a.count.tippy-gpbp-list")
                total_reac = int(like_tag.text.strip()) if like_tag else 0
            except:
                total_reac = 0
            
            # 留言
            formatted_comments = []
            for c in post.select(".c-reply__item"):
                try:
                    c_author_ele = c.select_one(".reply-content__user")
                    c_author = c_author_ele.text.strip().replace("：", "") if c_author_ele else "Anonymous"
                    c_text = c.select_one(".reply-content__article").text.strip()
                    if c_text:
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
        max_retries = 3
        soup = None

        for attempt in range(1, max_retries + 1):
            try:
                res = requests.get(url, headers=self.headers, timeout=10)
                soup = BeautifulSoup(res.text, "html.parser")
                break
            except requests.RequestException as e:
                print(f" 網路請求失敗: {e} (第 {attempt}/{max_retries} 次嘗試)")
                if attempt < max_retries:
                    time.sleep(random.uniform(2, 5))

        if soup is None:
            raise BahaParseError(f"抓取文章內容失敗（article_id={article_id}, page={page}），已重試 {max_retries} 次")

        posts = soup.select(".c-section")
        main_title_ele = soup.select_one("h1.c-post__header__title")
        main_title = main_title_ele.text.strip() if main_title_ele else "巴哈討論串"

        all_floor_data = []
        for post in posts:
            floor_data = self.format_data(post, main_title)
            if floor_data is not None:  # 過濾單一樓層分析失敗/內文為空的情況
                all_floor_data.append(floor_data)
        return all_floor_data

    def crawl_today_floors(self, board_id, article_id, floor_miss_limit=2):
        """
        從文章最後一頁往前掃描樓層，只保留當天樓層；
        往回連續遇到 floor_miss_limit 個非當天樓層就停止（換下一篇文章）
        不設回抓頁數上限。
        """
        today_str = datetime.now().strftime("%Y-%m-%d")
        total_pages = self.get_total_pages(board_id, article_id)  # 可能 raise BahaParseError

        collected = []
        consecutive_miss = 0

        for page_num in range(total_pages, 0, -1):
            page_floors = self.parse_article(board_id, article_id, page=page_num)  # 可能 raise BahaParseError

            for floor in reversed(page_floors):
                if floor["post_time"] == today_str:
                    consecutive_miss = 0
                    collected.append(floor)
                else:
                    consecutive_miss += 1
                    if consecutive_miss >= floor_miss_limit:
                        return collected

            time.sleep(random.uniform(2, 4))

        return collected

    def _finalize_result(self, all_data, board_id, today_display):
        if not all_data:
            return {
                "status": "no_data",
                "message": f"日期 {today_display} 平台 BAHA 沒有相關文章",
                "data": []
            }
        today_str = datetime.now().strftime("%Y%m%d")
        raw_file_path = self.save_data(all_data, f"{board_id}_{today_str}_result")
        return {
            "status": "ok",
            "message": None,
            "data": all_data,
            "raw_file_path": raw_file_path
        }


    def run(self, board_id, safety_pages=2, article_miss_limit=10, floor_miss_limit=2):
        """
        每日模式：從看板第1頁（最新）開始，只抓「最新回覆為今天」的文章的當天樓層
        :param board_id: 看板代號 (bsn)
        :param safety_pages: 看板列表安全上限頁數（防呆用，非目標抓取量）
        :param article_miss_limit: 連續幾篇文章「最新回覆非當天」就停止整個爬取
        :param floor_miss_limit: 單篇文章內，往回抓樓層連續幾個非當天就換下一篇文章
        """
        today_display = datetime.now().strftime("%y/%m/%d")
        today_date = datetime.now().date()
        all_data = []
        miss_streak = 0

        for page in range(1, safety_pages + 1):
            print(f"正在掃描看板第 {page} 頁列表...")
            articles = self.fetch_article_list(board_id, page)

            if articles is None:
                raise BahaParseError(f"看板列表解析失敗（board_id={board_id}, page={page}）")

            if not articles:
                print("此頁沒有任何文章，結束掃描")
                break

            for art in articles:
                latest_date = self.parse_latest_reply_date(art["time_text"])

                if latest_date != today_date:
                    miss_streak += 1
                    print(f"  -> 文章 {art['article_id']} 最新回覆非當天（{art['time_text']}），連續未命中 {miss_streak}/{article_miss_limit}")
                    if miss_streak >= article_miss_limit:
                        print(f"已連續 {article_miss_limit} 篇文章非當天，停止抓取")
                        return self._finalize_result(all_data, board_id, today_display)
                    continue

                miss_streak = 0
                print(f"  -> 文章 {art['article_id']} 命中當天，開始抓取當天樓層")

                floor_data = self.crawl_today_floors(board_id, art["article_id"], floor_miss_limit)
                all_data.extend(floor_data)
                time.sleep(random.uniform(2, 4))

        return self._finalize_result(all_data, board_id, today_display)