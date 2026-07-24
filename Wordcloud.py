import pandas as pd
import jieba
from wordcloud import WordCloud
import matplotlib.pyplot as plt

# 特定用字
POGO_WORDS = ["異色", "色違", "星塵", "復刻", "機率", "bug", "極巨", "背卡"]

# 停用字
STOP_WORDS = {
    "今天", "又", "了", "根本", "是", "一堆", "太", "啦", "終於", "一",
    "真的", "不是", "沒有", "可以", "現在", "看到", "什麼", "不會", "只有", "怎麼",
    "一個", "可能", "這樣", "直接", "還是", "所以", "應該", "就是", "知道", "那個",
    "這個", "因為", "一樣", "有人", "好像", "如果",
}

INPUT_FILE = "predict_final.xlsx"
OUTPUT_FILE = "pogo_keywords_for_bi.csv"
FONT_PATH = "msjh.ttc"  # 正黑體


# 斷詞 / 關鍵字表
def setup_jieba(custom_words):
    """把自訂詞加入 jieba 字典，避免被切成單字"""
    for word in custom_words:
        jieba.add_word(word)


def load_data(path):
    """讀取原始 Excel 資料，並補上 doc_id 欄位"""
    df = pd.read_excel(path)
    df_raw = df.copy()
    df_raw["doc_id"] = df_raw.index + 1
    return df, df_raw


def extract_keywords(text, stop_words):
    """
    斷詞並過濾掉停用字、空白字元以及長度小於 2 的字
    """
    if pd.isna(text):
        return []
    words = jieba.lcut(text)
    meaningful_words = [
        w
        for w in words
        if w.strip() and w not in stop_words and (len(w) >= 2 or w.isalpha())
    ]
    return meaningful_words


def build_keyword_table(df_raw, stop_words):
    """套用斷詞、攤平成 (doc_id, predict_label, Keyword) 的長格式表"""
    df_raw = df_raw.copy()
    df_raw["keywords"] = df_raw["comment"].apply(
        lambda text: extract_keywords(text, stop_words)
    )

    df_keyword_table = df_raw.explode("keywords")
    df_keyword_table = df_keyword_table.dropna(subset=["keywords"])
    df_keyword_table = df_keyword_table.rename(columns={"keywords": "Keyword"})

    df_output = df_keyword_table[["doc_id", "predict_label", "Keyword"]]
    return df_output


def export_keyword_table(df_output, path):
    """輸出成 CSV 供 Power BI 匯入"""
    print("--- 攤平後的關鍵字資料表 (準備匯入 Power BI) ---")
    print(df_output.head())
    df_output.to_csv(path, index=False, encoding="utf-8-sig")


def get_bad_comments(df):
    """篩選出 predict_label == 0 (負面) 的留言"""
    mask = df["predict_label"] == 0
    bad_comment = df.loc[mask, "comment"].dropna()
    return bad_comment


# 文字雲
def build_wordcloud_text(bad_comment):
    """把負評留言合併成單一字串"""
    text = " ".join(bad_comment.astype(str))
    return text


def generate_wordcloud(text, stop_words, font_path):
    """斷詞（僅取長度 >= 2 的詞）後產生 WordCloud 物件"""
    wordcloud = WordCloud(
        width=800,
        height=400,
        background_color="white",
        max_words=100,
        contour_width=3,
        contour_color="steelblue",
        font_path=font_path,
        stopwords=stop_words,
    )
    segmented_text = " ".join([e for e in jieba.lcut(text) if len(e) >= 2])
    wordcloud.generate(segmented_text)
    return wordcloud


def plot_wordcloud(wordcloud, title="Negative Sentiment WordCloud"):
    """顯示文字雲"""
    plt.figure(figsize=(10, 5))
    plt.imshow(wordcloud)
    plt.axis("off")
    plt.title(title)
    plt.show()


def show_negative_wordcloud(bad_comment, stop_words, font_path):
    """整合：合併文字 -> 產生文字雲 -> 顯示"""
    text = build_wordcloud_text(bad_comment)
    wordcloud = generate_wordcloud(text, stop_words, font_path)
    plot_wordcloud(wordcloud)


def main():
    setup_jieba(POGO_WORDS)

    df, df_raw = load_data(INPUT_FILE)

    df_output = build_keyword_table(df_raw, STOP_WORDS)
    export_keyword_table(df_output, OUTPUT_FILE)

    bad_comment = get_bad_comments(df)
    show_negative_wordcloud(bad_comment, STOP_WORDS, FONT_PATH)


if __name__ == "__main__":
    main()
