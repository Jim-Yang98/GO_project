import os
import json
from abc import abstractmethod

class BaseCrawler:
    def __init__(self, topic_name, save_folder):
        self.topic_name = topic_name
        self.save_folder = save_folder
        if not os.path.exists(save_folder):
            os.makedirs(save_folder)

    def save_data(self, data, filename):
        file_path = os.path.join(self.save_folder, f"{self.topic_name}_{filename}.json")
        try:
            with open(file_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, ensure_ascii=False, indent=4)
            print(f"成功儲存: {file_path}")
        except Exception as e:
            print(f"存檔失敗: {e}")

    @abstractmethod
    def format_data(self, post, comments):
        pass