# 跨平台社群聲量監測
針對手遊產品建置一站式輿情監測流程。開發具容錯與抗阻擋能力的跨平台爬蟲，結合深度學習模型進行情緒標籤預測。\
本專案以Pokemon GO為例，針對批踢踢 (PTT)、巴哈姆特與 Dcard 之2025版面進行自動化爬蟲，並透過 Power BI 建立儀表板，將社群留言轉化為可輔助決策的量化指標。

## 主要功能
- **數據爬取**：自動化收集 PTT、巴哈姆特、Dcard 相關討論板文章。
- **資料清理**：自動轉換與清洗文字資料。
- **NLP 模型**：使用 BERT 模型進行文本分類與聲量分析。
- **報表視覺化**：整合 Power BI 呈現 2025 活動聲量趨勢。

## 快速開始

### 1. 安裝環境
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
- crawlers/: 各平台爬蟲模組
- utils/: 資料清理與格式轉換工具
- bert_train.py: BERT 模型訓練腳本
- reports/: Power BI 視覺化分析報表
