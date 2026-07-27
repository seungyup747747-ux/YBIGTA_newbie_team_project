"""
Letterboxd multilingual EDA
Version: 2026-07-22-multilingual-v2
"""

import argparse
import os

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer


# 언어별 기능어와 분석 가치가 낮은 일반 영화 단어를 함께 제외합니다.
STOPWORDS = {
    "en": {
        "the", "and", "is", "it", "this", "that", "to", "of", "a", "an",
        "in", "on", "for", "with", "was", "were", "are", "be", "but",
        "my", "so", "as", "at", "its", "i", "me", "you", "they", "we",
        "movie", "film", "avatar",
    },
    "es": {
        "el", "la", "los", "las", "de", "del", "y", "que", "en", "un",
        "una", "es", "por", "para", "con", "se", "me", "muy", "pero",
        "lo", "como", "más", "mi", "pelicula", "película", "film", "avatar",
    },
    "pt": {
        "o", "a", "os", "as", "de", "do", "da", "e", "que", "em", "um",
        "uma", "é", "por", "para", "com", "se", "me", "muito", "mas",
        "mais", "eu", "filme", "avatar",
    },
    "fr": {
        "le", "la", "les", "de", "des", "du", "et", "que", "en", "un",
        "une", "est", "pour", "avec", "ce", "ça", "mais", "plus", "je",
        "il", "elle", "film", "avatar",
    },
    "id": {
        "yang", "dan", "di", "ke", "dari", "ini", "itu", "untuk", "dengan",
        "aku", "saya", "tapi", "lebih", "sangat", "film", "nya", "avatar",
    },
    "tr": {
        "ve", "bir", "bu", "da", "de", "ile", "için", "ama", "çok",
        "ben", "o", "şu", "gibi", "daha", "mi", "film", "avatar",
    },
    "it": {
        "il", "la", "i", "gli", "le", "di", "del", "e", "che", "in",
        "un", "una", "è", "per", "con", "ma", "più", "io", "film", "avatar",
    },
    "de": {
        "der", "die", "das", "und", "ist", "ein", "eine", "zu", "von",
        "mit", "für", "aber", "nicht", "ich", "es", "im", "den",
        "film", "avatar",
    },
}


def load_data(input_path: str) -> pd.DataFrame:
    """전처리 결과 CSV를 불러오고 필요한 컬럼을 검사합니다."""
    data = pd.read_csv(input_path)

    required_columns = {
        "rating",
        "date",
        "review",
        "cleaned_review",
        "review_length",
        "language",
    }
    missing_columns = required_columns - set(data.columns)

    if missing_columns:
        raise ValueError(
            "최신 letterboxd_processor.py를 먼저 실행해야 합니다. "
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
    counts = (
        data["rating"]
        .value_counts()
        .sort_index()
        .reindex(np.arange(0.5, 5.1, 0.5), fill_value=0)
    )

    plt.figure(figsize=(8, 5))
    plt.bar(counts.index.astype(str), counts.values)
    plt.title("Letterboxd Rating Distribution")
    plt.xlabel("Rating")
    plt.ylabel("Review Count")
    save_plot("letterboxd_rating_distribution.png", output_dir)


def plot_review_length_distribution(
    data: pd.DataFrame,
    output_dir: str,
):
    # 긴 꼬리 때문에 본체가 눌리지 않도록 99백분위까지만 표시합니다.
    upper = data["review_length"].quantile(0.99)
    visible = data.loc[
        data["review_length"] <= upper,
        "review_length",
    ]

    plt.figure(figsize=(8, 5))
    plt.hist(visible, bins=35, edgecolor="black")
    plt.axvline(
        data["review_length"].median(),
        linestyle="--",
        label="Median",
    )
    plt.title("Letterboxd Review Length Distribution (<= 99th pct.)")
    plt.xlabel("Number of Characters")
    plt.ylabel("Review Count")
    plt.legend()
    save_plot(
        "letterboxd_review_length_distribution.png",
        output_dir,
    )


def plot_review_length_boxplot(
    data: pd.DataFrame,
    output_dir: str,
):
    plt.figure(figsize=(8, 4))
    plt.boxplot(data["review_length"], vert=False)
    plt.title("Letterboxd Review Length Boxplot")
    plt.xlabel("Number of Characters")
    save_plot(
        "letterboxd_review_length_boxplot.png",
        output_dir,
    )


def plot_language_distribution(
    data: pd.DataFrame,
    output_dir: str,
):
    counts = (
        data["language"]
        .fillna("unknown")
        .value_counts()
        .head(12)
    )

    plt.figure(figsize=(9, 5))
    plt.bar(counts.index.astype(str), counts.values)
    plt.title("Letterboxd Language Distribution")
    plt.xlabel("Detected Language")
    plt.ylabel("Review Count")
    plt.xticks(rotation=45)
    save_plot(
        "letterboxd_language_distribution.png",
        output_dir,
    )


def plot_average_rating_by_language(
    data: pd.DataFrame,
    output_dir: str,
):
    stats = (
        data.groupby("language")
        .agg(
            review_count=("rating", "size"),
            mean_rating=("rating", "mean"),
        )
        .query("review_count >= 5")
        .sort_values("mean_rating", ascending=False)
    )

    if stats.empty:
        return

    plt.figure(figsize=(9, 5))
    plt.bar(
        stats.index.astype(str),
        stats["mean_rating"],
    )
    plt.axhline(
        data["rating"].mean(),
        linestyle="--",
        label="Overall mean",
    )
    plt.ylim(0, 5)
    plt.title("Average Rating by Language (n >= 5)")
    plt.xlabel("Detected Language")
    plt.ylabel("Average Rating")
    plt.xticks(rotation=45)
    plt.legend()
    save_plot(
        "letterboxd_average_rating_by_language.png",
        output_dir,
    )


def plot_median_length_by_rating(
    data: pd.DataFrame,
    output_dir: str,
):
    medians = (
        data.groupby("rating")["review_length"]
        .median()
        .sort_index()
    )

    plt.figure(figsize=(8, 5))
    plt.bar(medians.index.astype(str), medians.values)
    plt.title("Median Review Length by Rating")
    plt.xlabel("Rating")
    plt.ylabel("Median Number of Characters")
    save_plot(
        "letterboxd_median_length_by_rating.png",
        output_dir,
    )


def plot_yearly_review_count(
    data: pd.DataFrame,
    output_dir: str,
):
    yearly = data["date"].dt.year.value_counts().sort_index()

    plt.figure(figsize=(8, 5))
    plt.bar(yearly.index.astype(str), yearly.values)
    plt.title("Letterboxd Review Count by Year")
    plt.xlabel("Year")
    plt.ylabel("Review Count")
    save_plot(
        "letterboxd_yearly_review_count.png",
        output_dir,
    )


def plot_latest_year_monthly_count(
    data: pd.DataFrame,
    output_dir: str,
):
    latest_year = int(data["date"].dt.year.max())
    latest = data[data["date"].dt.year == latest_year]

    monthly = (
        latest["date"]
        .dt.month
        .value_counts()
        .sort_index()
        .reindex(range(1, 13), fill_value=0)
    )

    plt.figure(figsize=(8, 5))
    plt.bar(monthly.index.astype(str), monthly.values)
    plt.title(f"Monthly Review Count in {latest_year}")
    plt.xlabel("Month")
    plt.ylabel("Review Count")
    save_plot(
        "letterboxd_latest_year_monthly_count.png",
        output_dir,
    )


def plot_top_terms_by_language(
    data: pd.DataFrame,
    output_dir: str,
    max_languages: int = 3,
):
    """
    언어를 섞지 않고 주요 언어별로 TF-IDF 키워드를 계산합니다.
    이 함수가 이전 버전에는 누락되어 있었습니다.
    """
    supported = data[data["language"].isin(STOPWORDS)]

    top_languages = (
        supported["language"]
        .value_counts()
        .head(max_languages)
        .index
        .tolist()
    )

    for language in top_languages:
        reviews = data.loc[
            data["language"] == language,
            "cleaned_review",
        ].dropna()

        reviews = reviews[reviews.str.len() >= 3]

        if len(reviews) < 5:
            continue

        min_df = 2 if len(reviews) >= 20 else 1

        vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=min_df,
            max_df=0.90,
            max_features=500,
            stop_words=list(STOPWORDS[language]),
            token_pattern=r"(?u)\b\w\w+\b",
            sublinear_tf=True,
        )

        try:
            matrix = vectorizer.fit_transform(reviews)
        except ValueError:
            continue

        term_data = (
            pd.DataFrame(
                {
                    "term": vectorizer.get_feature_names_out(),
                    "mean_tfidf": matrix.mean(axis=0).A1,
                }
            )
            .sort_values("mean_tfidf", ascending=False)
            .head(15)
        )

        if term_data.empty:
            continue

        plt.figure(figsize=(9, 6))
        plt.barh(
            term_data["term"][::-1],
            term_data["mean_tfidf"][::-1],
        )
        plt.title(f"Top TF-IDF Terms: {language}")
        plt.xlabel("Mean TF-IDF")
        plt.ylabel("Term")
        save_plot(
            f"letterboxd_top_terms_{language}.png",
            output_dir,
        )


def save_summary(data: pd.DataFrame, output_dir: str):
    summary = pd.DataFrame(
        [
            ("review_count", len(data)),
            ("mean_rating", data["rating"].mean()),
            ("median_rating", data["rating"].median()),
            (
                "positive_review_ratio",
                (data["rating"] >= 4.0).mean(),
            ),
            (
                "mean_review_length",
                data["review_length"].mean(),
            ),
            (
                "median_review_length",
                data["review_length"].median(),
            ),
            (
                "p99_review_length",
                data["review_length"].quantile(0.99),
            ),
            (
                "unknown_language_ratio",
                (data["language"] == "unknown").mean(),
            ),
        ],
        columns=["metric", "value"],
    )

    summary.to_csv(
        os.path.join(
            output_dir,
            "letterboxd_eda_summary.csv",
        ),
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
        os.path.join(
            output_dir,
            "letterboxd_language_summary.csv",
        ),
        index=False,
        encoding="utf-8-sig",
    )


def print_summary(data: pd.DataFrame):
    print("[Letterboxd EDA]")
    print(f"리뷰 수: {len(data)}")
    print(f"평균 별점: {data['rating'].mean():.3f}")
    print(f"중앙값 별점: {data['rating'].median():.3f}")
    print(f"평균 리뷰 길이: {data['review_length'].mean():.3f}")
    print(f"중앙값 리뷰 길이: {data['review_length'].median():.3f}")
    print(f"최대 리뷰 길이: {data['review_length'].max()}")
    print(
        "감지 언어 수: "
        f"{data['language'].nunique(dropna=True)}"
    )


def run_eda(input_path: str, output_dir: str):
    os.makedirs(output_dir, exist_ok=True)

    data = load_data(input_path)

    print_summary(data)
    plot_rating_distribution(data, output_dir)
    plot_review_length_distribution(data, output_dir)
    plot_review_length_boxplot(data, output_dir)
    plot_language_distribution(data, output_dir)
    plot_average_rating_by_language(data, output_dir)
    plot_median_length_by_rating(data, output_dir)
    plot_yearly_review_count(data, output_dir)
    plot_latest_year_monthly_count(data, output_dir)
    plot_top_terms_by_language(data, output_dir)
    save_summary(data, output_dir)

    print(f"[Letterboxd EDA] 저장 완료: {output_dir}")


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-i",
        "--input_path",
        type=str,
        default="database/preprocessed_reviews_letterboxd.csv",
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