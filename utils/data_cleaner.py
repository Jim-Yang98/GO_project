import unicodedata
import re
import pandas as pd
import emoji

class DataCleaner:
    def __init__(self):
        pass

    def clean(self, platform, data):
        platform_map = {
            "ptt": self.clean_ptt,
            "fb": self.clean_fb,
            "baha": self.clean_baha,
            "dcard": self.clean_dcard
        }
        clean_func = platform_map.get(platform.lower())
        if not clean_func:
            raise ValueError(f"未知平台，無法清洗: {platform}")
        
        return clean_func(data)

    # Dcard
    def clean_dcard(self, data):
       return self.core_filter_pipeline(data)
    
    # 巴哈
    def clean_baha(self, data):
        return self.core_filter_pipeline(data)

    # fb
    def clean_fb(self, data):
        return self.core_filter_pipeline(data)
    
    # ptt:擷取文章tag
    def extract_article_tag(self, title):
        if not title:
            return ""

        if "[" in title and "]" in title:
            start = title.find("[")
            end = title.find("]")
            return title[start:end+1]

        return ""

    # PTT push 合併
    def combine_push(self, comments_data):
        if not comments_data:
            return []
        
        combined_comments = []

        temp = {
            "comment_tag": comments_data[0].get("comment_tag", ""),
            "comment_author": comments_data[0].get("comment_author", ""),
            "comment": comments_data[0].get("comment", "")
        }

        for i in range(1, len(comments_data)):
            current = comments_data[i]
            current_author = current.get("comment_author", "")
            current_tag = current.get("comment_tag", "")
            current_comment = current.get("comment", "")

            # 條件：同作者，且當前這條是「箭頭」-> 代表是接續上一條的發言
            if current_author == temp["comment_author"] and current_tag == "→":
                # 直接原地串接文字，不要重設 temp！
                temp["comment"] += current_comment
            else:
                combined_comments.append(temp)
                
                temp = {
                    "comment_author": current_author,
                    "comment": current_comment,
                    "comment_tag": current_tag
                }

        combined_comments.append(temp)

        for item in combined_comments:
            item.pop("comment_tag", None)

        return combined_comments

    # ptt
    def clean_ptt(self, data):
        clean_data = []
        for article in data:
            processed_article = article.copy()
            # # 萃取 tag
            # title = article.get("title", "")
            # article["post_tag"] = self.extract_article_tag(title)

            # 合併 push
            if "comments_data" in processed_article:
                # 先合併推文
                combined = self.combine_push(processed_article.get("comments_data", []))
                
                # 對合併後的每一條 PTT 留言進行文字清洗（包含去網址）
                processed_article["comments_data"] = self.process_and_filter_comments(combined)

            # 修正 overall
            true_overall = processed_article.get("like", 0) - processed_article.get("unlike", 0)
            total_reac = processed_article.get("total_reac", "")

            if total_reac == "" or total_reac is None:
                processed_article["total_reac"] = 0
            elif total_reac == "爆":
                processed_article["total_reac"] = true_overall
            elif (
                isinstance(total_reac, str) and total_reac.startswith("X")
            ):
                processed_article["total_reac"] = true_overall
            elif (
                isinstance(total_reac, str) and total_reac.lstrip("-").isdigit()
            ):
                processed_article["total_reac"] = true_overall

            if "post_url" in processed_article:
                del processed_article["post_url"]

            clean_data.append(processed_article)

        return self.core_filter_pipeline(clean_data)
    
    def process_and_filter_comments(self, comments_list, comment_key="comment"):
        if not isinstance(comments_list, list):
            return []
            
        cleaned_list = []
        for c in comments_list:
            if isinstance(c, dict):
                raw_text = c.get(comment_key, "")
                cleaned_text = self.clean_text(raw_text)
                    
                if cleaned_text and cleaned_text.strip() != "":
                    if len(cleaned_text) >= 5:
                        cleaned_list.append({
                            **c,
                            "comment": cleaned_text
                        })
        return cleaned_list

    def core_filter_pipeline(self, data):
        results = []
        for post in data:
            if not isinstance(post, dict):
                continue
                
            # 處理並檢查日期
            raw_date = post.get("post_time")
            cleaned_date = self.clean_date(raw_date)
            
            # 只要貼文日期不是 2025 年，整篇貼文跟留言通通不要
            if not cleaned_date or not cleaned_date.startswith("2025"):
                continue
                
            # 在這裡直接清洗貼文內文
            raw_content = post.get("content", "")
            post["content"] = self.clean_text(raw_content)

            # 更新貼文內的時間為標準格式
            post["post_time"] = cleaned_date
            
            # 進行留言清洗
            raw_comments = post.get("comments_data", [])
            cleaned_comments = self.process_and_filter_comments(raw_comments)
            
            # 如果清洗後留言串變空了，整篇貼文主體也丟棄
            if not cleaned_comments:
                continue
                
            # 更新留言資料，並放入最終清單
            post["comments_data"] = cleaned_comments
            results.append(post)
            
        return results

    # 共用：清洗文字
    def clean_text(self, text):
        if isinstance(text, (list, dict)):
            return text
        if pd.isna(text):
            return None
        text = str(text)

        # 統一將全形英數、全形標點轉為半形
        text = unicodedata.normalize('NFKC', text)

        # 移除網址
        text = text.replace('\n', ' ').replace('\r', ' ').replace('\xa0', ' ')
        text = re.sub(r'https?://[^\s\u4e00-\u9fa5<>""’‘指標“”‘’@!,]+', '', text)
        text = re.sub(r'www\.[^\s\u4e00-\u9fa5<>""’‘指標“”‘’@!,]+', '', text)

        text = re.sub(r'@[a-zA-Z0-9_\.]+(?:/[^\s<>"]*)?(?:\?[^\s<>"]*)?', '', text)
        # 被空白切斷的網址
        text = re.sub(r'https?\s*:\s*/\s*/\S+', '', text,flags=re.IGNORECASE)

        # 移除禮包
        text = re.sub(r'\b(?=[A-Za-z]*\d)(?=\d*[A-Za-z])[A-Za-z0-9]{8,}\b', '', text)
        # 移除好友代碼
        text = re.sub(r'\b\d{12}\b|\b\d{4}\s\d{4}\s\d{4}\b', '', text)
        # 移除巴哈特有的 hot
        text = re.sub(r'^HOT', '', text, flags=re.IGNORECASE)

        # 移除#字號間的所有數字英文與標記
        text = re.sub(r'#[\w:]+#', '', text)
        # 移除[]間所有內容
        text = re.sub(r'\[.*?\]', '', text)
        # 拔除括號顏文字
        text = re.sub(r'\S*?\([^\s)]+?\)\S*?', '', text)

        # 移除表情符號（BERT-Chinese 無法理解）
        text = emoji.replace_emoji(text, replace="")
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])c(?![a-zA-Z0-9])', '', text)
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])c{2,}(?![a-zA-Z0-9])', '', text)
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])0.0(?![a-zA-Z0-9])', '', text)


        # 轉換網路顏文字為對應中文
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])QAQ(?![a-zA-Z0-9])', '好難過', text)
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])QQ(?![a-zA-Z0-9])', '難過', text)
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])orz(?![a-zA-Z0-9])', '無奈倒地', text)
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])lol(?![a-zA-Z0-9])', '大笑', text)
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])TM(?![a-zA-Z0-9])', '他媽', text)
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])XD+(?![a-zA-Z0-9])', '笑', text)

        text = re.sub(r'(?i)(?<![a-zA-Z0-9])[w]{2,}(?!\.)(?![a-zA-Z0-9])', '哈', text)
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])[z]{2,}(?!\.)(?![a-zA-Z0-9])', '睡', text)
        text = re.sub(r'(?i)(?<![a-zA-Z0-9])[w](?![a-zA-Z0-9])', '哈', text)

        text = re.sub(r'=\s*=+|=\s*-+\s*=', '無言', text)
        text = re.sub(r'@@+', '無奈', text)
        text = re.sub(r'><', '害羞', text)
        text = re.sub(r'=\s*3\s*=', '嘟嘴', text)
        text = re.sub(r'(?i):\s*P\b', '', text)
        text = re.sub(r'(?i):\s*D\b', '大笑', text) 
        text = re.sub(r'(?i)=\s*D\b', '大笑', text)        
        
        # 處理 Emoji (若要給 CKIP 斷詞，直接移除)
        text = emoji.replace_emoji(text, replace="")

        # 清空所有特殊雜訊，只留中英數與基本標點
        text = re.sub(r'[^\u4e00-\u9fa5a-zA-Z0-9\s!?,.:;@_=\-+*/~%()\\[\]{}<>]', '', text)

        # 把拔除顏文字後可能留下的「空括號殘渣」清乾淨
        text = re.sub(r'\(\s*\)|\[\s*\]|\{\s*\}|<\s*>', '', text)

        # 收斂中文重複字詞 (例如：啊啊啊啊啊 -> 啊啊)
        text = re.sub(r'(.)\1{2,}', r'\1\1', text)

        # 多餘空白
        text = re.sub(
            r'\s+', ' ', text
        )

        return text.strip()
    
    def process_and_filter_comments(self, comments_list, comment_key="comment"):
        if not isinstance(comments_list, list):
            return []
            
        cleaned_list = []
        for c in comments_list:
            if isinstance(c, dict):
                raw_text = c.get(comment_key, "")
                cleaned_text = self.clean_text(raw_text)
                    
                if (
                cleaned_text
                and cleaned_text.strip() != ""
                and len(cleaned_text.strip()) > 5
                ):
                    cleaned_list.append({
                        **c,
                        "comment": cleaned_text
                })
        return cleaned_list


    # 共用：日期
    def clean_date(self, date_str):
        if pd.isna(date_str):
            return None

        date_str = str(date_str).strip()
        if "年" in date_str and "月" in date_str:
            date_str = (
                date_str
                .replace("年", "-")
                .replace("月", "-")
                .replace("日", "")
            )

        try:
            return (
                pd.to_datetime(date_str).strftime("%Y-%m-%d")
            )
        except:
            return None