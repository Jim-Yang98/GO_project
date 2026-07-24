# 寶可夢 GO 2025 聲量分析與爬蟲專案
本專案針對批踢踢 (PTT)、巴哈姆特與 Dcard 之 Pokemon GO 版面進行自動化爬蟲，並透過 BERT 模型進行文本標籤與聲量分析。

## 主要功能
- **數據爬取**：自動化收集 PTT、巴哈姆特、Dcard 相關討論板文章。
- **資料清理**：自動轉換與清洗文字資料。
- **NLP 模型**：使用 BERT 模型進行文本分類與聲量分析。
- **報表視覺化**：整合 Power BI 呈現 2025 活動聲量趨勢。

## 快速開始

### 1. 安裝環境依賴
```bash
pip install -r requirements.txt
```

### 2.設定環境變數
請複製 .env.example 並建立 .env 檔案，填入你的 Token：
HUGGINGFACE_TOKEN=your_token_here

### 3. 執行主程式
```bash
python main.py
```

## 專案結構
--crawlers/: 各平台爬蟲模組
--utils/: 資料清理與格式轉換工具
--bert_train.py: BERT 模型訓練腳本
--reports/: Power BI 視覺化分析報表