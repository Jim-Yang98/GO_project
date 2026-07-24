import time
from datetime import datetime
import requests
from bs4 import BeautifulSoup
from crawlers.base_crawler import BaseCrawler

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

    def parse_article(self, url, author, title):
        res = self.get_response(url)
        if not res:
            return None

        soup = BeautifulSoup(res.text, "lxml")
        main = soup.find("div", id="main-content")

        if not main:
            return None

        # 時間
        try:
            meta = soup.find_all("span", class_="article-meta-value")
            raw_time = meta[3].text.strip()
            # dt = datetime.strptime(raw_time, "%a %b %d %H:%M:%S %Y")
            # article_date = dt.strftime("%Y-%m-%d")
        except:
            raw_time = ""

        
        # 推不推
        like, unlike, arrow = 0, 0, 0
        push_list = []
        pushes = main.find_all("div", class_="push")
        
        # 先把推文取出並轉成標準結構
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

            except:
                continue
            p.extract()

        # 拆出 meta 資訊與看板標籤
        for meta_tag in main.find_all("div", class_="article-metaline"):
            meta_tag.extract()
        for meta_tag in main.find_all("div", class_="article-metaline-right"):
            meta_tag.extract()
        content = main.text.strip()

        return self.format_data(raw_time, author, title, content, like, unlike, push_list)

    def parse_board(self, board, index):
        url = self.build_board_url(board, index)
        res = self.get_response(url)

        if not res:
            return []

        soup = BeautifulSoup(res.text, "lxml")
        articles = soup.find_all("div", class_="r-ent")

        data = []

        for art in articles:
            title_tag = art.find("div", class_="title").find("a")
            if not title_tag:
                continue

            article_url = self.build_article_url(title_tag["href"])
            title = title_tag.text.strip()

            author = art.find("div", class_="author").text.strip()
            inside = self.parse_article(article_url, author, title)

            if inside:
                # 保留網址以方便未來對照原始網頁
                inside["post_url"] = article_url
                data.append(inside)

            time.sleep(1)
        return data
    
    def run(self, board=None, start_index=1, pages=None):

        if pages is None:
            pages = self.default_pages

        all_data = []

        for i in range(pages):
            index = start_index - i
            print(f"抓第 {i+1} 頁: index{index}")

            page_data = self.parse_board(board, index)
            all_data.extend(page_data)
            time.sleep(2)

        self.save_data(all_data, "result")
        print(f"總共抓取 {len(all_data)} 篇")

        return all_data