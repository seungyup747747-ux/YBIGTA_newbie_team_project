"""
Naver review EDA
"""

import argparse
import os
from collections import Counter

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from matplotlib import font_manager


STOPWORDS = {
    "너무",
    "정말",
    "진짜",
    "그냥",
    "있는",
    "보고",
    "봤습니다",
    "영화",
    "아바타",
}


def configure_font():
    available_fonts = {font.name for font in font_manager.fontManager.ttflist}
    for font_name in ["AppleGothic", "NanumGothic", "Malgun Gothic"]:
        if font_name in available_fonts:
            plt.rcParams["font.family"] = font_name
            break
    plt.rcParams["axes.unicode_minus"] = False


def load_data(input_path: str) -> pd.DataFrame:
    data = pd.read_csv(input_path)
    required_columns = {
        "rating",
        "date",
        "normalized_review",
        "cleaned_review",
        "review_length",
        "weekday",
    }
    missing_columns = required_columns - set(data.columns)
    if missing_columns:
        raise ValueError(
            "naver_processor.py를 먼저 실행해야 합니다. "
            f"누락 컬럼: {sorted(missing_columns)}"
        )

    data["rating"] = pd.to_numeric(data["rating"], errors="coerce")
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["review_length"] = pd.to_numeric(
        data["review_length"],
        errors="coerce",
    )

    return data.dropna(
        subset=["rating", "date", "review_length"]
    ).copy()


def save_plot(filename: str, output_dir: str):
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, filename),
        dpi=200,
        bbox_inches="tight",
    )
    plt.close()


def plot_rating_distribution(data: pd.DataFrame, output_dir: str):
    counts = data["rating"].value_counts().sort_index()

    plt.figure(figsize=(8, 5))
    plt.bar(counts.index.astype(str), counts.values)
    plt.title("Naver Rating Distribution")
    plt.xlabel("Rating")
    plt.ylabel("Review Count")
    save_plot("naver_rating_distribution.png", output_dir)


def plot_review_length_distribution(data: pd.DataFrame, output_dir: str):
    upper = data["review_length"].quantile(0.99)
    visible = data.loc[data["review_length"] <= upper, "review_length"]

    plt.figure(figsize=(8, 5))
    plt.hist(visible, bins=30, edgecolor="black")
    plt.axvline(
        data["review_length"].median(),
        linestyle="--",
        label="Median",
    )
    plt.title("Naver Review Length Distribution (<= 99th pct.)")
    plt.xlabel("Number of Characters")
    plt.ylabel("Review Count")
    plt.legend()
    save_plot("naver_review_length_distribution.png", output_dir)


def plot_sentiment_group(data: pd.DataFrame, output_dir: str):
    labels = ["Negative (<=4)", "Neutral (5-7)", "Positive (>=8)"]
    counts = [
        int((data["rating"] <= 4).sum()),
        int(data["rating"].between(5, 7).sum()),
        int((data["rating"] >= 8).sum()),
    ]

    plt.figure(figsize=(8, 5))
    bars = plt.bar(labels, counts)
    plt.title("Naver Sentiment Group by Rating")
    plt.xlabel("Rating Group")
    plt.ylabel("Review Count")
    plt.xticks(rotation=15)

    for bar, count in zip(bars, counts):
        plt.text(
            bar.get_x() + bar.get_width() / 2,
            bar.get_height(),
            str(count),
            ha="center",
            va="bottom",
        )

    save_plot("naver_sentiment_group.png", output_dir)


def plot_weekday_review_count(data: pd.DataFrame, output_dir: str):
    order = [
        "Monday",
        "Tuesday",
        "Wednesday",
        "Thursday",
        "Friday",
        "Saturday",
        "Sunday",
    ]
    counts = data["weekday"].value_counts().reindex(order, fill_value=0)

    plt.figure(figsize=(9, 5))
    plt.bar(counts.index, counts.values)
    plt.title("Naver Review Count by Weekday")
    plt.xlabel("Weekday")
    plt.ylabel("Review Count")
    plt.xticks(rotation=45)
    save_plot("naver_weekday_reviews.png", output_dir)


def plot_top_words(data: pd.DataFrame, output_dir: str):
    counter: Counter[str] = Counter()
    for text in data["cleaned_review"].fillna(""):
        counter.update(
            token
            for token in str(text).split()
            if len(token) >= 2
            and not token.isdigit()
            and token not in STOPWORDS
        )

    top_words = pd.DataFrame(
        counter.most_common(15),
        columns=["word", "count"],
    )

    if top_words.empty:
        return

    plt.figure(figsize=(9, 6))
    plt.barh(top_words["word"][::-1], top_words["count"][::-1])
    plt.title("Naver Top Words")
    plt.xlabel("Frequency")
    plt.ylabel("Word")
    save_plot("naver_top_words.png", output_dir)


def save_summary(data: pd.DataFrame, output_dir: str):
    summary = pd.DataFrame(
        [
            ("review_count", len(data)),
            ("mean_rating", data["rating"].mean()),
            ("median_rating", data["rating"].median()),
            ("positive_review_ratio", (data["rating"] >= 8.0).mean()),
            ("mean_review_length", data["review_length"].mean()),
            ("median_review_length", data["review_length"].median()),
            ("p99_review_length", data["review_length"].quantile(0.99)),
            ("date_min", data["date"].min()),
            ("date_max", data["date"].max()),
        ],
        columns=["metric", "value"],
    )

    summary.to_csv(
        os.path.join(output_dir, "naver_eda_summary.csv"),
        index=False,
        encoding="utf-8-sig",
    )


def print_summary(data: pd.DataFrame):
    print("[Naver EDA]")
    print(f"리뷰 수: {len(data)}")
    print(f"평균 별점: {data['rating'].mean():.3f}")
    print(f"중앙값 별점: {data['rating'].median():.3f}")
    print(f"평균 리뷰 길이: {data['review_length'].mean():.3f}")
    print(f"중앙값 리뷰 길이: {data['review_length'].median():.3f}")
    print(f"최대 리뷰 길이: {data['review_length'].max()}")


def run_eda(input_path: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)
    configure_font()

    data = load_data(input_path)

    print_summary(data)
    plot_rating_distribution(data, output_dir)
    plot_review_length_distribution(data, output_dir)
    plot_sentiment_group(data, output_dir)
    plot_weekday_review_count(data, output_dir)
    plot_top_words(data, output_dir)
    save_summary(data, output_dir)

    print(f"[Naver EDA] 저장 완료: {output_dir}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-i",
        "--input_path",
        type=str,
        default="database/preprocessed_reviews_naver.csv",
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        type=str,
        default="review_analysis/plots",
    )

    args = parser.parse_args()
    run_eda(args.input_path, args.output_dir)


if __name__ == "__main__":
    main()
