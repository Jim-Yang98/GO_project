# 寶可夢 GO 聲量分析與爬蟲專案

本專案針對批踢踢 (PTT)、巴哈姆特與 Dcard 之 Pokemon GO 版面進行自動化爬蟲，
並透過 Gemini API 進行文本情緒標籤與聲量分析，整體流程以 Airflow DAG 排程自動化執行。

## 主要功能
- **數據爬取**：自動化收集 PTT、巴哈姆特、Dcard 相關討論板文章。
- **資料清理**：自動轉換與清洗文字資料。
- **情緒標註**：串接 Gemini API 進行快速情緒標籤分類。
- **流程自動化**：以 Airflow 建立 DAG，串連爬蟲、清理、資料庫寫入與標籤分類。
- **報表視覺化**：整合 Power BI 呈現活動聲量趨勢。

## 快速開始

### 1. 安裝環境依賴
​```bash
pip install -r requirements.txt
​```

### 2. 設定環境變數
請複製 .env.example 並建立 .env 檔案，填入你的金鑰：
GEMINI_API_KEY=your_key_here

### 3. 執行主程式
​```bash
python main.py
​```

## 專案結構
--crawlers/: 各平台爬蟲模組
--utils/: 資料清理與格式轉換工具
--dags/: Airflow DAG 定義
--reports/: Power BI 視覺化分析報表