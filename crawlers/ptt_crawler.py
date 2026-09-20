import re
import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from crawlers.base_crawler import BaseCrawler

class PttParseError(Exception):
    """PTT 看板列表或文章解析失敗：可能原因為被擋、網頁改版、或網路異常（已重試仍失敗）"""
    pass

class pttcrawler(BaseCrawler):

    BASE_URL = "https://www.ptt.cc"
    default_pages = 1

    def __init__(self, board, save_folder="ptt_data"):
        super().__init__(topic_name=board, save_folder=save_folder)
        self.board = board

    @classmethod
    def create(cls, board, save_folder="ptt_data"):
        return cls(board=board, save_folder=save_folder)

    def build_board_url(self, board, index=None):
            if index:
                return f"{self.BASE_URL}/bbs/{board}/index{index}.html"
            else:
                return f"{self.BASE_URL}/bbs/{board}/index.html"

    def build_article_url(self, href):
        return f"{self.BASE_URL}{href}"

    def get_response(self, url, retries=3):
        headers = {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko)",
            "Referer": self.BASE_URL
        }
        cookies = {"over18": "1"}

        for i in range(retries):
            try:
                res = requests.get(url, headers=headers, cookies=cookies, timeout=10)
                if res.status_code == 200:
                    return res
            except Exception as e:
                print(f"Retry {i+1}: {e}")
                time.sleep(2)
        return None

    def _extract_latest_index(self, soup):
        """從分頁按鈕的【上頁】連結反推目前最新頁的 index（上頁 index + 1）"""
        paging = soup.select_one(".btn-group-paging")
        if not paging:
            return None
        for a in paging.find_all("a"):
            if "上頁" in a.text:
                href = a.get("href", "")
                m = re.search(r'index(\d+)\.html', href)
                if m:
                    return int(m.group(1)) + 1
        return None

    def _parse_list_date(self, raw_date_text, today):
        """
        解析列表頁日期欄位（格式 'M/D'），回傳是否為今天
        僅用於初步篩選、決定要不要開內頁；精確日期仍以內頁完整時間為準
        """
        raw_date_text = raw_date_text.strip()
        try:
            month_str, day_str = raw_date_text.split("/")
            return (int(month_str), int(day_str)) == (today.month, today.day)
        except Exception:
            return False  # 日期欄位缺失/異常，不開內頁

    def parse_board(self, board, index):
        """
        抓取單一頁看板列表 HTML
        request 失敗（重試用盡)，raise PttParseError
        """
        url = self.build_board_url(board, index)
        res = self.get_response(url)

        if not res:
            raise PttParseError(f"看板列表請求失敗（board={board}, index={index}），已重試仍失敗")

        soup = BeautifulSoup(res.text, "lxml")
        articles = soup.find_all("div", class_="r-ent")
        return soup, articles

    def parse_article(self, url, author, title):
        res = self.get_response(url)
        if not res:
            raise PttParseError(f"文章內容請求失敗（url={url}），已重試仍失敗")

        soup = BeautifulSoup(res.text, "lxml")
        main = soup.find("div", id="main-content")

        if not main:
            return None  # 頁面存在但結構異常（例如文章被刪除），單篇跳過

        # 時間：供 run() 做精確日期確認
        try:
            meta = soup.find_all("span", class_="article-meta-value")
            raw_time = meta[3].text.strip()
            dt = datetime.strptime(raw_time, "%a %b %d %H:%M:%S %Y")
            article_date = dt.date()
        except Exception:
            raw_time = ""
            article_date = None

        # 推噓文（內容不變）
        like, unlike, arrow = 0, 0, 0
        push_list = []
        pushes = main.find_all("div", class_="push")

        for p in pushes:
            try:
                tag = p.find("span", class_="push-tag").text.strip()
                user = p.find("span", class_="push-userid").text.strip()
                comment = p.find("span", class_="push-content").text.strip().lstrip(":")

                if tag == "推":
                    like += 1
                elif tag == "噓":
                    unlike += 1
                else:
                    arrow += 1

                push_list.append({
                    "comment_tag": tag,
                    "comment_author": user,
                    "comment": comment
                })
            except Exception:
                continue
            p.extract()

        for meta_tag in main.find_all("div", class_="article-metaline"):
            meta_tag.extract()
        for meta_tag in main.find_all("div", class_="article-metaline-right"):
            meta_tag.extract()
        content = main.text.strip()

        formatted = self.format_data(raw_time, author, title, content, like, unlike, push_list)
        formatted["_article_date"] = article_date  # 內部欄位，run() 判斷用，存檔前會移除
        return formatted

    
    def format_data(self, raw_time, author, title, content, like, unlike, push_list):
        # 時間
        try:
            dt = datetime.strptime(raw_time, "%a %b %d %H:%M:%S %Y")
            post_time = dt.strftime("%Y-%m-%d")
        except:
            post_time = datetime.now().strftime("%Y-%m-%d")

        # 互動計算
        total_reac = like - unlike

        return {
            "platform": "PTT",
            "post_time": post_time,
            "author": author,
            "title": title,
            "content": content,
            "total_reac": total_reac,
            "comment_count": len(push_list),
            "comments_data": push_list
        }

    
    def run(self, board=None, safety_pages=2, article_miss_limit=10):
        """
        每日模式：從看板最新頁開始往回掃描，只保留今天發文的文章
        :param board: 看板代號
        :param safety_pages: 看板列表安全上限頁數（防呆用，非目標抓取量）
        :param article_miss_limit: 連續幾篇文章非今天就停止整個爬取
        """
        board = board or self.board
        today = datetime.now().date()
        today_display = datetime.now().strftime("%y/%m/%d")

        all_data = []
        miss_streak = 0
        stop = False

        # 先抓最新頁，順便反推目前最新 index
        soup, articles = self.parse_board(board, index=None)
        latest_index = self._extract_latest_index(soup)

        for page_count in range(safety_pages):
            if page_count > 0:
                if latest_index is None:
                    print("無法取得最新 index，停止翻頁")
                    break
                current_index = latest_index - page_count
                if current_index < 1:
                    print("已到達看板最舊頁，停止翻頁")
                    break
                print(f"正在掃描第 {page_count+1} 頁 (index{current_index})...")
                soup, articles = self.parse_board(board, current_index)

            # PTT 同一頁由上到下是舊到新，所以由下往上掃才是「新到舊」
            for art in reversed(articles):
                title_div = art.find("div", class_="title")
                title_tag = title_div.find("a") if title_div else None
                if not title_tag:
                    continue  # 已刪除文章沒有連結，跳過，不計入 miss

                date_div = art.find("div", class_="date")
                raw_date_text = date_div.text if date_div else ""
                is_today_coarse = self._parse_list_date(raw_date_text, today)

                if not is_today_coarse:
                    miss_streak += 1
                    print(f"  -> 列表日期非今天（{raw_date_text.strip()}），連續未命中 {miss_streak}/{article_miss_limit}")
                    if miss_streak >= article_miss_limit:
                        print(f"已連續 {article_miss_limit} 篇非今天，停止抓取")
                        stop = True
                        break
                    continue

                article_url = self.build_article_url(title_tag["href"])
                title = title_tag.text.strip()
                author_div = art.find("div", class_="author")
                author = author_div.text.strip() if author_div else "Anonymous"

                inside = self.parse_article(article_url, author, title)

                if inside is None or inside.get("_article_date") != today:
                    miss_streak += 1
                    print(f"  -> 日期確認非今天，連續未命中 {miss_streak}/{article_miss_limit}")
                    if miss_streak >= article_miss_limit:
                        print(f"已連續 {article_miss_limit} 篇非今天，停止抓取")
                        stop = True
                        break
                    continue

                miss_streak = 0
                print(f"  -> 文章「{title}」命中當天，開始抓取內容")
                inside.pop("_article_date", None)
                inside["post_url"] = article_url
                all_data.append(inside)
                time.sleep(1)

            if stop:
                break
            time.sleep(2)

        if not all_data:
            return {
                "status": "no_data",
                "message": f"日期 {today_display} 平台 PTT 沒有相關文章",
                "data": []
            }

        today_str = datetime.now().strftime("%Y%m%d")
        raw_file_path = self.save_data(all_data, f"{board}_{today_str}_result")
        return {
            "status": "ok",
            "message": None,
            "data": all_data,
            "raw_file_path": raw_file_path
        }