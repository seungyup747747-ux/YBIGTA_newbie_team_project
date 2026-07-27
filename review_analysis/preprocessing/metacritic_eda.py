"""Exploratory data analysis for preprocessed Metacritic reviews."""

import argparse
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer


WEEKDAY_ORDER = [
    "Monday",
    "Tuesday",
    "Wednesday",
    "Thursday",
    "Friday",
    "Saturday",
    "Sunday",
]

STOPWORDS = {
    "en": {"the", "and", "is", "it", "this", "that", "to", "of", "a", "an", "in", "on", "for", "with", "was", "were", "are", "be", "but", "movie", "film", "avatar"},
    "es": {"el", "la", "los", "las", "de", "del", "y", "que", "en", "un", "una", "es", "por", "para", "con", "se", "pero", "pelicula", "película", "film", "avatar"},
    "pt": {"o", "a", "os", "as", "de", "do", "da", "e", "que", "em", "um", "uma", "é", "por", "para", "com", "se", "mas", "filme", "avatar"},
    "fr": {"le", "la", "les", "de", "des", "du", "et", "que", "en", "un", "une", "est", "pour", "avec", "mais", "film", "avatar"},
    "it": {"il", "la", "i", "gli", "le", "di", "del", "e", "che", "in", "un", "una", "è", "per", "con", "ma", "film", "avatar"},
    "de": {"der", "die", "das", "und", "ist", "ein", "eine", "zu", "von", "mit", "für", "aber", "nicht", "ich", "film", "avatar"},
    "tr": {"ve", "bir", "bu", "da", "de", "ile", "için", "ama", "çok", "ben", "o", "şu", "gibi", "daha", "mi", "film", "avatar"},
}


def load_data(input_path: str) -> pd.DataFrame:
    """전처리 CSV를 불러오고 EDA에 필요한 컬럼·자료형을 검증합니다."""
    data = pd.read_csv(input_path)
    required_columns = {
        "rating",
        "date",
        "cleaned_review",
        "review_length",
        "word_count",
        "weekday",
        "language",
    }
    missing_columns = required_columns - set(data.columns)

    if missing_columns:
        raise ValueError(
            "metacritic_processor.py를 먼저 실행해야 합니다. "
            f"누락 컬럼: {sorted(missing_columns)}"
        )

    data["rating"] = pd.to_numeric(data["rating"], errors="coerce")
    data["date"] = pd.to_datetime(data["date"], errors="coerce")
    data["review_length"] = pd.to_numeric(
        data["review_length"], errors="coerce"
    )
    data["word_count"] = pd.to_numeric(
        data["word_count"], errors="coerce"
    )

    return data.dropna(
        subset=["rating", "date", "review_length", "word_count"]
    ).copy()


def save_plot(filename: str, output_dir: str):
    """현재 Matplotlib Figure를 지정한 출력 폴더에 PNG로 저장하고 닫습니다."""
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, filename),
        dpi=200,
        bbox_inches="tight",
    )
    plt.close()


def plot_rating_distribution(data: pd.DataFrame, output_dir: str):
    """0~10점 Metacritic 사용자 평점의 빈도 분포를 저장합니다."""
    counts = data["rating"].value_counts().sort_index().reindex(
        range(0, 11), fill_value=0
    )

    plt.figure(figsize=(8, 5))
    plt.bar(counts.index.astype(str), counts.values)
    plt.title("Metacritic Rating Distribution")
    plt.xlabel("User Score (0-10)")
    plt.ylabel("Review Count")
    save_plot("metacritic_rating_distribution.png", output_dir)


def plot_review_length_distribution(data: pd.DataFrame, output_dir: str):
    """상위 1%의 긴 리뷰를 숨긴 문자 수 분포를 저장합니다."""
    upper = data["review_length"].quantile(0.99)
    visible = data.loc[data["review_length"] <= upper, "review_length"]

    plt.figure(figsize=(8, 5))
    plt.hist(visible, bins=35, edgecolor="black")
    plt.axvline(
        data["review_length"].median(),
        linestyle="--",
        label="Median",
    )
    plt.title("Metacritic Review Length Distribution (<= 99th pct.)")
    plt.xlabel("Number of Characters")
    plt.ylabel("Review Count")
    plt.legend()
    save_plot("metacritic_review_length_distribution.png", output_dir)


def plot_sentiment_group(data: pd.DataFrame, output_dir: str):
    """평점 기준 부정·중립·긍정 리뷰 수를 막대그래프로 저장합니다."""
    labels = ["Negative (<=4)", "Neutral (5-7)", "Positive (>=8)"]
    counts = [
        int((data["rating"] <= 4).sum()),
        int(data["rating"].between(5, 7).sum()),
        int((data["rating"] >= 8).sum()),
    ]

    plt.figure(figsize=(8, 5))
    bars = plt.bar(labels, counts)
    plt.title("Metacritic Sentiment Group by User Score")
    plt.xlabel("Score Group")
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

    save_plot("metacritic_sentiment_group.png", output_dir)


def plot_median_length_by_rating(data: pd.DataFrame, output_dir: str):
    """평점별 리뷰 길이 중앙값을 비교하는 그래프를 저장합니다."""
    medians = data.groupby("rating")["review_length"].median().reindex(
        range(0, 11)
    )

    plt.figure(figsize=(8, 5))
    plt.bar(medians.index.astype(str), medians.values)
    plt.title("Median Review Length by User Score")
    plt.xlabel("User Score (0-10)")
    plt.ylabel("Median Number of Characters")
    save_plot("metacritic_median_length_by_rating.png", output_dir)


def plot_weekday_review_count(data: pd.DataFrame, output_dir: str):
    """작성 요일별 리뷰 수를 월요일부터 일요일 순서로 저장합니다."""
    counts = data["weekday"].value_counts().reindex(WEEKDAY_ORDER, fill_value=0)

    plt.figure(figsize=(9, 5))
    plt.bar(counts.index, counts.values)
    plt.title("Metacritic Review Count by Weekday")
    plt.xlabel("Weekday")
    plt.ylabel("Review Count")
    plt.xticks(rotation=45)
    save_plot("metacritic_weekday_reviews.png", output_dir)


def plot_yearly_review_count(data: pd.DataFrame, output_dir: str):
    """작성 연도별 리뷰 수를 저장합니다."""
    yearly = data["date"].dt.year.value_counts().sort_index()

    plt.figure(figsize=(8, 5))
    plt.bar(yearly.index.astype(str), yearly.values)
    plt.title("Metacritic Review Count by Year")
    plt.xlabel("Year")
    plt.ylabel("Review Count")
    save_plot("metacritic_yearly_review_count.png", output_dir)


def plot_language_distribution(data: pd.DataFrame, output_dir: str):
    """감지된 상위 12개 언어의 리뷰 수 분포를 저장합니다."""
    counts = data["language"].fillna("unknown").value_counts().head(12)

    plt.figure(figsize=(9, 5))
    plt.bar(counts.index.astype(str), counts.values)
    plt.title("Metacritic Language Distribution")
    plt.xlabel("Detected Language")
    plt.ylabel("Review Count")
    plt.xticks(rotation=45)
    save_plot("metacritic_language_distribution.png", output_dir)


def plot_average_rating_by_language(data: pd.DataFrame, output_dir: str):
    """리뷰가 5개 이상인 언어별 평균 평점을 전체 평균과 함께 저장합니다."""
    stats = (
        data.groupby("language")
        .agg(review_count=("rating", "size"), mean_rating=("rating", "mean"))
        .query("review_count >= 5")
        .sort_values("mean_rating", ascending=False)
    )
    if stats.empty:
        return

    plt.figure(figsize=(9, 5))
    plt.bar(stats.index.astype(str), stats["mean_rating"])
    plt.axhline(data["rating"].mean(), linestyle="--", label="Overall mean")
    plt.ylim(0, 10)
    plt.title("Average User Score by Language (n >= 5)")
    plt.xlabel("Detected Language")
    plt.ylabel("Average User Score")
    plt.xticks(rotation=45)
    plt.legend()
    save_plot("metacritic_average_rating_by_language.png", output_dir)


def plot_top_terms_by_language(data: pd.DataFrame, output_dir: str):
    """상위 언어별로 독립적인 TF-IDF 핵심 단어 그래프를 저장합니다.

    언어를 섞지 않아 각 언어의 불용어가 다른 언어의 키워드를 왜곡하지 않습니다.
    """
    supported = data[data["language"].isin(STOPWORDS)]
    top_languages = supported["language"].value_counts().head(3).index

    for language in top_languages:
        reviews = data.loc[
            data["language"] == language, "cleaned_review"
        ].dropna().astype(str)
        reviews = reviews[reviews.str.len() >= 3]
        if len(reviews) < 5:
            continue

        try:
            vectorizer = TfidfVectorizer(
                stop_words=list(STOPWORDS[language]),
                ngram_range=(1, 2),
                min_df=2 if len(reviews) >= 20 else 1,
                max_df=0.90,
                max_features=500,
                sublinear_tf=True,
            )
            matrix = vectorizer.fit_transform(reviews)
        except ValueError:
            continue

        terms = pd.DataFrame(
            {
                "term": vectorizer.get_feature_names_out(),
                "mean_tfidf": matrix.mean(axis=0).A1,
            }
        ).nlargest(15, "mean_tfidf")

        plt.figure(figsize=(9, 6))
        plt.barh(terms["term"][::-1], terms["mean_tfidf"][::-1])
        plt.title(f"Top TF-IDF Terms: {language}")
        plt.xlabel("Mean TF-IDF")
        plt.ylabel("Term")
        save_plot(f"metacritic_top_terms_{language}.png", output_dir)


def save_summary(data: pd.DataFrame, summary_dir: str):
    """전체 EDA 지표와 언어별 집계 결과를 database CSV로 저장합니다."""
    summary = pd.DataFrame(
        [
            ("review_count", len(data)),
            ("mean_rating", data["rating"].mean()),
            ("median_rating", data["rating"].median()),
            ("positive_review_ratio", (data["rating"] >= 8).mean()),
            ("negative_review_ratio", (data["rating"] <= 4).mean()),
            ("mean_review_length", data["review_length"].mean()),
            ("median_review_length", data["review_length"].median()),
            ("p99_review_length", data["review_length"].quantile(0.99)),
            ("mean_word_count", data["word_count"].mean()),
            ("detected_language_count", data["language"].nunique()),
            ("unknown_language_ratio", (data["language"] == "unknown").mean()),
            ("date_min", data["date"].min()),
            ("date_max", data["date"].max()),
        ],
        columns=["metric", "value"],
    )
    summary.to_csv(
        os.path.join(summary_dir, "metacritic_eda_summary.csv"),
        index=False,
        encoding="utf-8-sig",
    )

    language_summary = (
        data.groupby("language")
        .agg(
            review_count=("rating", "size"),
            mean_rating=("rating", "mean"),
            median_review_length=("review_length", "median"),
        )
        .sort_values("review_count", ascending=False)
        .reset_index()
    )
    language_summary.to_csv(
        os.path.join(summary_dir, "metacritic_language_summary.csv"),
        index=False,
        encoding="utf-8-sig",
    )


def print_summary(data: pd.DataFrame):
    """주요 EDA 지표를 콘솔에 사람이 읽기 쉬운 형태로 출력합니다."""
    print("[Metacritic EDA]")
    print(f"리뷰 수: {len(data)}")
    print(f"평균 평점: {data['rating'].mean():.3f}")
    print(f"중앙값 평점: {data['rating'].median():.3f}")
    print(f"평균 리뷰 길이: {data['review_length'].mean():.3f}")
    print(f"중앙값 리뷰 길이: {data['review_length'].median():.3f}")
    print(f"최대 리뷰 길이: {data['review_length'].max()}")
    print(f"감지 언어 수: {data['language'].nunique(dropna=True)}")


def run_eda(input_path: str, output_dir: str, summary_dir: str):
    """그래프는 plots에, 수치 요약 CSV는 database에 저장하며 EDA를 실행합니다."""
    os.makedirs(output_dir, exist_ok=True)
    os.makedirs(summary_dir, exist_ok=True)
    data = load_data(input_path)

    print_summary(data)
    plot_rating_distribution(data, output_dir)
    plot_review_length_distribution(data, output_dir)
    plot_sentiment_group(data, output_dir)
    plot_median_length_by_rating(data, output_dir)
    plot_weekday_review_count(data, output_dir)
    plot_yearly_review_count(data, output_dir)
    plot_language_distribution(data, output_dir)
    plot_average_rating_by_language(data, output_dir)
    plot_top_terms_by_language(data, output_dir)
    save_summary(data, summary_dir)

    print(f"[Metacritic EDA] 저장 완료: {output_dir}")


def main():
    """명령줄 인자를 받아 Metacritic EDA를 실행합니다."""
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-i",
        "--input_path",
        type=str,
        default="database/preprocessed_reviews_metacritic.csv",
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        type=str,
        default="review_analysis/plots",
    )
    parser.add_argument(
        "-s",
        "--summary_dir",
        type=str,
        default="database",
        help="EDA 요약 CSV를 저장할 폴더입니다.",
    )
    args = parser.parse_args()
    run_eda(args.input_path, args.output_dir, args.summary_dir)


if __name__ == "__main__":
    main()
