import os
import pandas as pd
import torch
from dotenv import load_dotenv
from sklearn.model_selection import train_test_split
from transformers import BertTokenizer, BertForSequenceClassification, Trainer, TrainingArguments, TrainerCallback
from huggingface_hub import InferenceClient
import torch.nn.functional as F
from datasets import Dataset
from transformers import BertTokenizerFast


def train_model(input_file="comments_combined.xlsx"):
    """進行 BERT 模型訓練"""

    # 讀取資料
    df_original = pd.read_excel(input_file)

    # 欄位名稱修正以符合 Huggingface
    df = df_original[['comment', 'label']].copy()
    df.columns = ['text', 'label']

    train_df, test_df = train_test_split(
        df, test_size=0.2, random_state=42,
        stratify=df['label']
    )

    # 轉為 Huggingface Dataset 格式
    train_dataset = Dataset.from_pandas(train_df)
    test_dataset = Dataset.from_pandas(test_df)

    # Tokenizer
    tokenizer = BertTokenizerFast.from_pretrained('ckiplab/bert-base-chinese')

    def tokenize_function(examples):
        return tokenizer(
            examples['text'],
            padding='max_length',
            truncation=True,
            max_length=128
        )

    tokenized_train = train_dataset.map(tokenize_function, batched=True)
    tokenized_test = test_dataset.map(tokenize_function, batched=True)

    # 模型
    model = BertForSequenceClassification.from_pretrained(
        'ckiplab/bert-base-chinese',
        num_labels=3
    )

    training_args = TrainingArguments(
        output_dir="./results",
        eval_strategy="epoch",
        save_strategy="epoch",
        learning_rate=2e-5,
        per_device_train_batch_size=8,
        num_train_epochs=6,
        label_smoothing_factor=0.1,
        weight_decay=0.01,
        load_best_model_at_end=True,
        logging_dir="./logs",
        logging_strategy="epoch"
    )

    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=tokenized_train,
        eval_dataset=tokenized_test
    )

    print("開始訓練")
    trainer.train()
    trainer.save_model("./poc_model")
    print("已儲存 ./poc_model")

    return trainer


def evaluate_accuracy(log_history, test_cases=None, model_path="./poc_model"):
    """測試模型準確度，並印出 loss 歷史紀錄"""

    # loss 歷史紀錄
    print("\n*** loss 歷史紀錄 ***")
    for log in log_history:
        epoch = log.get("epoch")
        train_loss = log.get("loss")
        eval_loss = log.get("eval_loss")
        if train_loss or eval_loss:
            print(f"epoch {epoch}, train_loss: {train_loss}, eval_loss: {eval_loss}")

    # 從路徑載入模型
    tokenizer = BertTokenizer.from_pretrained('ckiplab/bert-base-chinese')
    model = BertForSequenceClassification.from_pretrained(
        os.path.abspath(model_path)
    )

    model.eval()
    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')
    model.to(device)

    def predict(text):
        inputs = tokenizer(
            text,
            return_tensors="pt",
            padding='max_length',
            truncation=True,
            max_length=128
        )
        inputs = {key: value.to(device) for key, value in inputs.items()}
        with torch.no_grad():
            outputs = model(**inputs)
        logits = outputs.logits
        probs = torch.nn.functional.softmax(logits, dim=1)
        predicted_label = torch.argmax(logits, dim=1).item()

        print(f"Logits: {logits.cpu().numpy()}")
        print(f"機率分配: 負:{probs[0][0]:.2%}, 中:{probs[0][1]:.2%}, 正:{probs[0][2]:.2%}")

        return predicted_label

    if test_cases:
        print("\n*** 測試案例 ***")
        for text, expected in test_cases:
            result = predict(text)
            print(f"測試: {text} → 預測: {result}（期待: {expected}）")


def export_predictions(input_file, output_file, model_path="./poc_model"):
    """輸出預測結果檔案"""

    device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

    # 從路徑載入模型
    print("loading model...")
    tokenizer = BertTokenizerFast.from_pretrained('ckiplab/bert-base-chinese')
    model = BertForSequenceClassification.from_pretrained(
        os.path.abspath(model_path)
    ).to(device)

    df = pd.read_csv(input_file)
    texts = df['comment'].fillna("").tolist()

    test_dataset = Dataset.from_pandas(pd.DataFrame({'text': texts}))

    def tokenize_function(examples):
        return tokenizer(
            examples['text'],
            padding='max_length',
            truncation=True,
            max_length=128
        )

    tokenized_dataset = test_dataset.map(tokenize_function, batched=True)

    # 預測
    training_args = TrainingArguments(
        output_dir="./temp",
        per_device_eval_batch_size=32
    )
    trainer = Trainer(model=model, args=training_args)

    print("start label all comments")
    raw_prediction = trainer.predict(tokenized_dataset)
    logits = torch.from_numpy(raw_prediction.predictions)

    probs = F.softmax(logits, dim=1).numpy()
    predicted_labels = probs.argmax(axis=1)

    df['predict_label'] = predicted_labels
    df['confidence_matrix'] = [
        f"負:{p[0]:.2%}, 中:{p[1]:.2%}, 正:{p[2]:.2%}" for p in probs
    ]

    df.to_excel(output_file, index=False)
    print(f"結果儲存至 {output_file}")


def check_label_ratio(input_file):
    """確認資料標籤比例"""

    df = pd.read_excel(input_file)

    label_count = df['predict_label'].value_counts()
    print("\n*** 情感標籤比例 ***")
    print(label_count)


if __name__ == "__main__":
    load_dotenv()
    token = os.getenv("HUGGINGFACE_TOKEN") # 填入自己的token

    test_cases = [
        ("這補償好有誠意 超讚", 2),
        ("色違超好看 我一定抓", 2),
        ("新年快樂", 1),
        ("天佑台灣 加油", 1),
        ("這遊戲好爛...", 0),
    ]

    trainer = train_model(input_file="comments_combined.xlsx")
    evaluate_accuracy(
        log_history=trainer.state.log_history,
        test_cases=test_cases
    )
    export_predictions(
        input_file="PokemonGO_cleaned_all.csv",
        output_file="predict_first_round.xlsx"
    )
    check_label_ratio(input_file="predict_first_round.xlsx")