from datetime import datetime, timedelta
from airflow import DAG
from airflow.operators.python import PythonOperator
from airflow.exceptions import AirflowException

# 預設 Task 參數
default_args = {
    'owner': 'Jim_Yang',
    'depends_on_past': False,
    'email_on_failure': False,
    'email_on_retry': False,
    'retries': 2,
    'retry_delay': timedelta(minutes=5),
}

GAME_KEYWORD = "PokemonGO"
PLATFORMS = ["ptt", "dcard", "baha"]
KNOWN_UNSTABLE_PLATFORMS = {"dcard"}


def run_crawl_clean_store_task(**context):
    from main import run as run_pipeline
    failed_platforms = {}

    for platform in PLATFORMS:
        print(f"[Task 1] 開始處理平台: {platform}")
        try:
            run_pipeline(game_keyword=GAME_KEYWORD, platform_name=platform, output_type="postgres")
            print(f"[Task 1] {platform} 處理完成")
        except Exception as e:
            print(f"[Task 1][ERROR] {platform} 處理失敗，記錄後繼續下一個平台: {e}")
            failed_platforms[platform] = str(e)

    unexpected_failures = {p: e for p, e in failed_platforms.items() if p not in KNOWN_UNSTABLE_PLATFORMS}

    if failed_platforms:
        print(f"[Task 1][警告] 以下平台本次未成功: {failed_platforms}")

    if unexpected_failures:
        raise AirflowException(f"非預期平台失敗: {unexpected_failures}")

    print("[Task 1] 處理完成（略過已知不穩定的平台）。")


def run_model_prediction_task(**context):
    """ Task 2: 呼叫 Gemini 進行情緒分類預測，並回寫至 DB (predict_label) """
    print("[Task 2] 啟動 Gemini 情緒預測")
    from light_prediction import run_predict

    run_predict()
    print("[Task 2] 預測完成，predict_label 已寫入資料庫！")


# DAG 設定
with DAG(
    dag_id='game_public_opinion_pipeline',
    default_args=default_args,
    description='社群輿情爬蟲 -> 清洗 -> 存庫 -> Gemini情緒預測 完整自動化 Pipeline',
    schedule='0 2 * * *',
    start_date=datetime(2026, 9, 14),
    catchup=False,
    tags=['輿情分析', 'Gemini', 'PostgreSQL'],
) as dag:

    task_crawl_clean_store = PythonOperator(
        task_id='crawl_clean_store_all_platforms',
        python_callable=run_crawl_clean_store_task,
    )

    task_predict = PythonOperator(
        task_id='run_gemini_prediction_and_update',
        python_callable=run_model_prediction_task,
    )

    task_crawl_clean_store >> task_predict