import json
import time
from datetime import datetime
from crawlers.base_crawler import BaseCrawler
import re
import random
from DrissionPage import ChromiumOptions, ChromiumPage
from pyvirtualdisplay import Display

class DcardParseError(Exception):
    """page_to_json 解析失敗：可能原因有被擋、網頁改版、或需要重新登入驗證"""
    pass


class dcardcrawler(BaseCrawler):
    default_safety_pages = 1

    def __init__(self, save_folder="dcard_data"):
        super().__init__(topic_name="dcard", save_folder=save_folder)

    @classmethod
    def create(cls, save_folder="dcard_data"):
        return cls(save_folder=save_folder)
    
    # 網址建構
    def _build_urls(self, mode, query, forum=None):
        """
        依據模式生成前端過驗證網址與後端 api 網址
        """
        mode = mode.lower()

        if mode == "topic":
            # 話題追蹤
            front_url =f"https://www.dcard.tw/topics/{query}?tab=latest"
            api_url = (
                f"https://www.dcard.tw/service/api/v3/search/posts?"
                f"query={query}&field=topics&highlight=false&sort=latest&country=TW&nsfw=true&platform=web"
            )
        elif mode == "search":
            # 支援限定看板或全站搜尋
            front_url = f"https://www.dcard.tw/search/posts?query={query}&sort=latest"
            api_url = (
                f"https://www.dcard.tw/service/api/v3/search/posts?"
                f"query={query}&field=all&highlight=false&sort=latest&country=TW&nsfw=true&platform=web"
            )
        else:
            raise ValueError(f"未知的 Dcard 爬取模式: {mode}")

        return front_url, api_url
    
    def page_to_json(self, safety_pages):
        match = re.search(r'<pre>(.*?)</pre>', safety_pages.html, re.S)
        if not match:
            return None
        try:
            return json.loads(match.group(1))
        except:
            return None
        
    def extract_posts(self, data, mode):
        # 如果是純看板模式(forum)
        if not data:
            return []
        
        if isinstance(data, list):
            return data

        posts = []
        if isinstance(data, dict):
            if "widgets" in data:
                widgets = data.get("widgets", [])
                for widget in widgets:
                    if not isinstance(widget, dict):
                        continue
                    items = widget.get("forumlist", {}).get("items", [])
                    for item in items:
                        if isinstance(item, dict) and "post" in item:
                            posts.append(item.get("post"))
                return posts
            
        items = data.get("items", [])
        for item in items:
            if "searchPost" in item:
                posts.append(item.get("searchPost", {}).get("post", {}))
            elif "post" in item:
                posts.append(item.get("post", {}))
            elif isinstance(item, dict) and "id" in item:
                posts.append(item)
        return posts
            
    def fetch_comments(self, page, post_id, comment_limit):
        comment_url = f"https://www.dcard.tw/service/api/v3/posts/{post_id}/comments?limit={comment_limit}&sort=oldest"
        page.get(comment_url)
        time.sleep(random.uniform(1, 2))

        data = self.page_to_json(page)
        if not data:
            return []
        if isinstance(data, dict):
            return data.get("items", data.get("comments", []))
        elif isinstance(data, list):
            return data
        return []
    
    def _parse_post_date(self, post):
        """回傳 'YYYY-MM-DD'；解析失敗回傳 None（不算命中）"""
        raw_time = post.get('createdAt', '')
        try:
            dt = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
            return dt.strftime("%Y-%m-%d")
        except Exception:
            return None
    
    def format_data(self, post, comments):
        # 時間（解析失敗時 fallback 為今天，不影響停止判斷）
        post_time = self._parse_post_date(post) or datetime.now().strftime("%Y-%m-%d")

        # 作者
        author = post.get('school') or post.get('department')
        if post.get('anonymous', True) or not author:
            author = "Anonymous"

        # 內文
        content = post.get("meta", {}).get("annotation")
        if not content:
            content = post.get("excerpt", "")

        # 留言
        formatted_comments = []
        for c in comments:
            if not isinstance(c, dict):
                continue
            c_author = c.get("school") or c.get("department")
            if c.get("anonymous", True) or not c_author:
                c_author = "Anonymous"
            formatted_comments.append({
                "comment_author": c_author,
                "comment": c.get("content", "")
            })

        return {
            "platform": "Dcard",
            "post_time": post_time,
            "author": author,
            "title": post.get("title", "無標題"),
            "content": content,
            "total_reac": post.get('likeCount', 0),
            "comment_count": post.get('commentCount', 0),
            "comments_data": formatted_comments
        }
        
        
    def crawl_all_pages(self, page, base_url, max_pages, comment_limit, mode):
        next_key = None
        all_data = []
        today_str = datetime.now().strftime("%Y-%m-%d")
        miss_streak = 0
        MAX_MISS = 3

        def _no_data_result():
            today_display = datetime.now().strftime("%y/%m/%d")
            return {
                "status": "no_data",
                "message": f"日期 {today_display} 平台 Dcard 沒有相關文章",
                "data": []
            }

        for page_num in range(max_pages):
            print(f"\n 第 {page_num+1} 頁 ")

            if next_key:
                url = f"{base_url}&nextKey={next_key}" if "nextKey" not in base_url else base_url
            else:
                url = base_url

            page.get(url)
            time.sleep(random.uniform(2, 4))

            data = self.page_to_json(page)
            if not data:
                print("解析失敗")
                break
            posts = self.extract_posts(data, mode)
            print(f"抓到 {len(posts)} 篇文章")

            for i, post in enumerate(posts, 1):
                post_id = post.get("id")
                if not post_id:
                    continue

                post_date = self._parse_post_date(post)

                if post_date is None:
                    print(f"文章 {post_id} 日期解析失敗，跳過")
                    continue

                if post_date != today_str:
                    miss_streak += 1
                    print(f"非當天文章（{post_date}），連續未命中 {miss_streak}/{MAX_MISS}")
                    if miss_streak >= MAX_MISS:
                        print(f"已連續 {MAX_MISS} 篇非當天文章，停止抓取")
                        if not all_data:
                            return _no_data_result()
                        return {"status": "ok", "message": None, "data": all_data}
                    continue

                miss_streak = 0

                comments = self.fetch_comments(page, post_id, comment_limit)
                print(f"留言 ({len(comments)} 則):")
                for c in comments:
                    if not isinstance(c, dict):
                        continue
                    floor = c.get("floor", "?")
                    text = c.get("content", "")
                    print(f"  {floor}F: {text[:10]}...")
                    time.sleep(random.uniform(2, 4))

                formatted_post = self.format_data(post, comments)
                all_data.append(formatted_post)
                time.sleep(random.uniform(1, 2))

            # 取得下一頁密鑰
            if isinstance(data, dict):
                next_key = data.get("nextKey")
            elif isinstance(data, list) and data:
                next_key = data[-1].get("id")
                base_url = base_url.split('&before=')[0] + f"&before={next_key}"
            else:
                next_key = None

            if not next_key:
                print("已經到達最後一頁")
                break

        if not all_data:
            return _no_data_result()
        return {"status": "ok", "message": None, "data": all_data}

    def run(self, mode="topic", query=None, forum=None, safety_pages=2, comment_limit=5, **kwargs):
        """
        泛用型
        param query: 關鍵字或話題名稱 (例如 'PokemonGO')
        param forum: 限定看板名稱 (例如 'pokemon')
        """
        if not query and mode != "forum":
            raise ValueError("在當前模式下，必須提供 query 參數")
        
        # 建立前端網址與後端 api網址
        front_url, base_url = self._build_urls(mode, query, forum)

        print(f"開始執行 dcard 爬蟲 [模式: {mode}]")
        print(f"前端網址: {front_url}")

        co = ChromiumOptions()
        co.set_browser_path('/usr/bin/chromium')
        co.headless(True)
        co.set_argument('--no-sandbox')
        co.set_argument('--disable-dev-shm-usage')
        page = ChromiumPage(addr_or_opts=co)

        try:
            page.get(front_url)
            page.get_screenshot(path='/opt/airflow/dags/debug_dcard.png')  # 暫時加入，用來檢查實際載入的畫面
            result = self.crawl_all_pages(page, base_url, safety_pages, comment_limit, mode)


            if result["status"] == "no_data":
                result["raw_file_path"] = None
                return result

            today_str = datetime.now().strftime("%Y%m%d")
            file_name = f"{mode}_{query or forum}_{today_str}"
            raw_file_path = self.save_data(result["data"], f"{file_name}_result")
            result["raw_file_path"] = raw_file_path
            return result
        finally:
            page.quit()