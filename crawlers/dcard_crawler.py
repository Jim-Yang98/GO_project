import json
import time
from datetime import datetime
from crawlers.base_crawler import BaseCrawler
import re
import random
from DrissionPage import ChromiumPage

class dcardcrawler(BaseCrawler):
    default_pages = 1

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
        elif mode == "forum":
            target_forum = forum if forum else query
            front_url = f"https://www.dcard.tw/f/{target_forum}?tab=latest"
            api_url = f"https://www.dcard.tw/service/api/v3/forums/{target_forum}/posts?sort=new"
                
        else:
            raise ValueError(f"未知的 Dcard 爬取模式: {mode}")

        return front_url, api_url
    
    def page_to_json(self, page):
        match = re.search(r'<pre>(.*?)</pre>', page.html, re.S)
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
    
    def format_data(self, post, comments):
        # 時間
        raw_time = post.get('createdAt', '')
        try:
            dt = datetime.fromisoformat(raw_time.replace('Z', '+00:00'))
            post_time = dt.strftime("%Y-%m-%d")
        except:
            post_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S") # 容錯處理

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
            if not isinstance(c, dict): continue
            # 抓取留言學校/卡稱，若匿名則給 Anonymous
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
                
                # 抓原始留言
                comments = self.fetch_comments(page, post_id, comment_limit)
                print(f"留言 ({len(comments)} 則):")

                for c in comments:
                    if not isinstance(c, dict):
                        continue
                    floor = c.get("floor", "?")
                    text = c.get("content", "")
                    print(f"  {floor}F: {text[:20]}...")
                    time.sleep(random.uniform(2, 4))
                    # comment_list.append({
                    #     "comment": text
                    # })

                formatted_post = self.format_data(post, comments)
                all_data.append(formatted_post)

                time.sleep(random.uniform(1, 2))

                    # if post_time < "2025-01-01": 
                    #     print("已到達目標日期，停止抓取")
                    #     return all_data

                # 取得下一頁密鑰
            if isinstance(data, dict):
                next_key = data.get("nextKey")
            elif isinstance(data, list) and data:
                # 純看板模式的分頁通常是用最後一篇文章的 id 當作 before 參數
                next_key = data[-1].get("id")
                base_url = base_url.split('&before=')[0] + f"&before={next_key}"
            else:
                next_key = None

            if not next_key:
                print("已經到達最後一頁")
                break
                
        return all_data

    def run(self, mode="topic", query=None, forum=None, pages=2, comment_limit=2, **kwargs):
        """
        泛用型
        param mode: 'topic' (話題) 或 'search' (搜尋) 或 'forum' (純看板)
        param query: 關鍵字或話題名稱 (例如 'PokemonGO')
        param forum: 限定看板名稱 (例如 'pokemon')
        """
        if not query and mode != "forum":
            raise ValueError("在當前模式下，必須提供 query 參數")
        
        # 透過建構器取得對應網址
        front_url, base_url = self._build_urls(mode, query, forum)

        print(f"開始執行 dcard 爬蟲 [模式: {mode}]")
        print(f"前端網址: {front_url}")

        page = ChromiumPage()
        page.get(front_url)

        input("過驗證出現正常畫面後回 VS code 按下 Enter")

        # 開始爬取
        data = self.crawl_all_pages(page, base_url, pages, comment_limit, mode)

        file_name = f"{mode}_{query or forum}"
        self.save_data(data, f"{file_name}_result")

        page.quit()