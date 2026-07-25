"""Site-level comparison EDA for preprocessed review datasets."""

import argparse
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd
from sklearn.feature_extraction.text import (
    ENGLISH_STOP_WORDS,
    TfidfVectorizer,
)


SITE_FILES = {
    "Letterboxd": "preprocessed_reviews_letterboxd.csv",
    "Naver": "preprocessed_reviews_naver.csv",
    "Metacritic": "preprocessed_reviews_metacritic.csv",
}

SITE_ORDER = ["Letterboxd", "Metacritic", "Naver"]

RATING_GROUPS = [
    ("0-2", 0, 2),
    ("3-4", 3, 4),
    ("5-6", 5, 6),
    ("7-8", 7, 8),
    ("9-10", 9, 10),
]


ENGLISH_CUSTOM_STOPWORDS = {
    "avatar",
    "film",
    "movie",
    "movies",
    "way",
    "water",
    "really",
    "just",
    "like",
    "one",
    "first",
    "second",
    "time",
    "still",
    "much",
    "also",
    "good",
    "great",
    "watch",
    "watched",
    "thing",
    "make",
    "makes",
    "made",
    "story",
    "did",
    "does",
    "it's",
    "it’s",
}

KOREAN_STOPWORDS = {
    "영화",
    "아바타",
    "물의",
    "정말",
    "진짜",
    "너무",
    "그냥",
    "보고",
    "봤는데",
    "봤어요",
    "봤습니다",
    "입니다",
    "있다",
    "있는",
    "같다",
    "같은",
    "그리고",
    "하지만",
    "그래도",
    "이번",
    "정도",
    "조금",
    "완전",
    "아주",
    "더욱",
    "역시",
    "대한",
    "장면",
    "하는",
    "보는",
    "이런",
    "좋은",
}

NAVER_NORMALIZATION = {
    "영상미가": "영상미",
    "영상미는": "영상미",
    "영상미를": "영상미",
    "스토리는": "스토리",
    "스토리가": "스토리",
    "스토리를": "스토리",
    "영화관에서": "영화관",
    "영화관으로": "영화관",
    "영화는": "영화",
    "영화를": "영화",
    "아바타는": "아바타",
    "아바타가": "아바타",
}


def configure_korean_font() -> None:
    """한글이 그래프에서 깨지지 않도록 폰트를 설정한다."""

    candidates = [
        "AppleGothic",
        "Arial Unicode MS",
        "NanumGothic",
        "Noto Sans CJK KR",
    ]

    installed_fonts = {
        font.name for font in font_manager.fontManager.ttflist
    }

    for candidate in candidates:
        if candidate in installed_fonts:
            plt.rcParams["font.family"] = candidate
            break

    plt.rcParams["axes.unicode_minus"] = False


def load_site_frames(database_dir: str) -> dict[str, pd.DataFrame]:
    """사이트별 전처리 CSV를 불러온다."""

    frames: dict[str, pd.DataFrame] = {}
    base_dir = Path(database_dir)

    for site, filename in SITE_FILES.items():
        path = base_dir / filename

        if not path.exists():
            raise FileNotFoundError(
                f"전처리 결과 파일이 없습니다: {path}"
            )

        data = pd.read_csv(path)

        if "rating" not in data.columns:
            raise ValueError(
                f"{filename}에 rating 컬럼이 없습니다."
            )

        data = data.copy()
        data["site"] = site
        data["rating"] = pd.to_numeric(
            data["rating"],
            errors="coerce",
        )
        data = data.dropna(subset=["rating"])

        if site == "Letterboxd":
            data["rating_10"] = data["rating"] * 2
        else:
            data["rating_10"] = data["rating"]

        frames[site] = data

    return frames


def build_rating_summary(data: pd.DataFrame) -> pd.DataFrame:
    """사이트별 평점 구간 비율을 계산한다."""

    summary = []

    for site, group in data.groupby("site"):
        rounded_rating = group["rating_10"].round().astype(int)
        total = len(group)

        for label, lower, upper in RATING_GROUPS:
            count = int(
                rounded_rating.between(lower, upper).sum()
            )

            summary.append(
                {
                    "site": site,
                    "rating_group": label,
                    "count": count,
                    "ratio": count / total,
                }
            )

    return pd.DataFrame(summary)


def plot_rating_distribution(
    summary: pd.DataFrame,
    output_dir: str,
) -> None:
    """사이트별 평점 분포를 누적 막대그래프로 저장한다."""

    site_order = ["Letterboxd", "Naver", "Metacritic"]
    group_order = [
        label for label, _, _ in RATING_GROUPS
    ]

    pivot = (
        summary.pivot(
            index="site",
            columns="rating_group",
            values="ratio",
        )
        .reindex(site_order)
        .reindex(columns=group_order)
    )

    colors = {
        "0-2": "#8c2d04",
        "3-4": "#d95f0e",
        "5-6": "#756bb1",
        "7-8": "#2b8cbe",
        "9-10": "#1b9e77",
    }

    plt.figure(figsize=(9, 5))
    bottom = [0.0] * len(pivot)

    for group_label in group_order:
        values = pivot[group_label].fillna(0)

        bars = plt.bar(
            pivot.index,
            values,
            bottom=bottom,
            label=group_label,
            color=colors[group_label],
        )

        for bar, value, start in zip(
            bars,
            values,
            bottom,
        ):
            if value >= 0.06:
                plt.text(
                    bar.get_x() + bar.get_width() / 2,
                    start + value / 2,
                    f"{value * 100:.1f}%",
                    ha="center",
                    va="center",
                    color="white",
                    fontsize=9,
                )

        bottom = [
            start + value
            for start, value in zip(bottom, values)
        ]

    plt.title(
        "Rating Group Distribution by Site (0-10 Scale)"
    )
    plt.xlabel("Site")
    plt.ylabel("Review Ratio")
    plt.ylim(0, 1)
    plt.legend(title="Rating Group", loc="upper right")
    plt.tight_layout()

    plt.savefig(
        os.path.join(
            output_dir,
            "comparison_rating_distribution.png",
        ),
        dpi=200,
        bbox_inches="tight",
    )

    plt.close()


def get_text_column(data: pd.DataFrame) -> str:
    """분석에 사용할 리뷰 텍스트 컬럼을 찾는다."""

    candidates = [
        "cleaned_review",
        "normalized_review",
        "review",
    ]

    for column in candidates:
        if column in data.columns:
            return column

    raise ValueError(
        "cleaned_review, normalized_review, review 중 "
        "사용 가능한 텍스트 컬럼이 없습니다."
    )


def select_keyword_texts(
    site: str,
    data: pd.DataFrame,
) -> pd.Series:
    """키워드 분석에 사용할 리뷰를 선택하고 정규화한다."""

    text_column = get_text_column(data)
    selected = data.copy()

    # Letterboxd와 Metacritic은 영어 리뷰를 중심으로 비교한다.
    if site in {"Letterboxd", "Metacritic"}:
        if "language" in selected.columns:
            language = (
                selected["language"]
                .astype(str)
                .str.lower()
                .str.strip()
            )

            english_mask = language.isin(
                ["en", "english"]
            )

            # 영어 리뷰가 충분한 경우에만 영어 리뷰로 제한한다.
            if int(english_mask.sum()) >= 30:
                selected = selected.loc[english_mask]

    texts = (
        selected[text_column]
        .fillna("")
        .astype(str)
        .str.strip()
    )

    # 조사 때문에 같은 한국어 단어가 분리되는 문제를 일부 보정한다.
    if site == "Naver":
        for original, normalized in NAVER_NORMALIZATION.items():
            texts = texts.str.replace(
                original,
                normalized,
                regex=False,
            )

    return texts[texts.str.len() > 0]


def extract_top_keywords(
    site: str,
    data: pd.DataFrame,
    top_n: int = 15,
) -> pd.DataFrame:
    """사이트별 평균 TF-IDF 점수가 높은 단어를 추출한다."""

    texts = select_keyword_texts(site, data)

    if site == "Naver":
        stop_words = sorted(KOREAN_STOPWORDS)
        token_pattern = (
            r"(?u)\b(?:[가-힣]{2,}|[A-Za-z]{2,})\b"
        )
    else:
        stop_words = sorted(
            set(ENGLISH_STOP_WORDS)
            | ENGLISH_CUSTOM_STOPWORDS
        )
        token_pattern = (
            r"(?u)\b[A-Za-z][A-Za-z'’]{1,}\b"
        )

    vectorizer = TfidfVectorizer(
        lowercase=True,
        stop_words=stop_words,
        token_pattern=token_pattern,
        ngram_range=(1, 1),
        min_df=2,
        max_df=0.90,
        max_features=3000,
    )

    try:
        matrix = vectorizer.fit_transform(texts)
    except ValueError as error:
        raise ValueError(
            f"{site} 키워드 분석에 사용할 단어가 부족합니다."
        ) from error

    terms = vectorizer.get_feature_names_out()
    mean_scores = matrix.mean(axis=0).A1
    document_counts = (matrix > 0).sum(axis=0).A1

    result = pd.DataFrame(
        {
            "site": site,
            "keyword": terms,
            "tfidf_score": mean_scores,
            "document_count": document_counts,
        }
    )

    result = (
        result.sort_values(
            ["tfidf_score", "document_count"],
            ascending=False,
        )
        .head(top_n)
        .reset_index(drop=True)
    )

    result["rank"] = range(1, len(result) + 1)

    return result[
        [
            "site",
            "rank",
            "keyword",
            "tfidf_score",
            "document_count",
        ]
    ]


def build_keyword_summary(
    site_frames: dict[str, pd.DataFrame],
    top_n: int = 15,
) -> pd.DataFrame:
    """모든 사이트의 주요 키워드를 하나의 표로 만든다."""

    summaries = []

    for site in SITE_ORDER:
        summaries.append(
            extract_top_keywords(
                site,
                site_frames[site],
                top_n=top_n,
            )
        )

    return pd.concat(summaries, ignore_index=True)


def plot_keyword_comparison(
    summary: pd.DataFrame,
    output_dir: str,
) -> None:
    """사이트별 주요 키워드를 하나의 이미지로 저장한다."""

    configure_korean_font()

    figure, axes = plt.subplots(
        1,
        3,
        figsize=(18, 7),
    )

    for axis, site in zip(axes, SITE_ORDER):
        site_data = (
            summary.loc[summary["site"] == site]
            .sort_values("tfidf_score")
        )

        axis.barh(
            site_data["keyword"],
            site_data["tfidf_score"],
        )

        axis.set_title(f"{site} 주요 키워드")
        axis.set_xlabel("Mean TF-IDF Score")
        axis.set_ylabel("Keyword")
        axis.grid(
            axis="x",
            alpha=0.25,
        )

    figure.suptitle(
        "Top Keywords by Review Platform",
        fontsize=16,
    )

    figure.tight_layout()

    figure.savefig(
        os.path.join(
            output_dir,
            "comparison_keyword_frequency.png",
        ),
        dpi=200,
        bbox_inches="tight",
    )

    plt.close(figure)


def run_comparison(
    database_dir: str,
    output_dir: str,
) -> None:
    """평점 비교와 주요 키워드 비교를 실행한다."""

    os.makedirs(output_dir, exist_ok=True)

    site_frames = load_site_frames(database_dir)

    combined_data = pd.concat(
        site_frames.values(),
        ignore_index=True,
    )

    rating_summary = build_rating_summary(
        combined_data
    )

    plot_rating_distribution(
        rating_summary,
        output_dir,
    )

    rating_summary.to_csv(
        os.path.join(
            database_dir,
            "comparison_rating_summary.csv",
        ),
        index=False,
        encoding="utf-8-sig",
    )

    keyword_summary = build_keyword_summary(
        site_frames,
        top_n=15,
    )

    plot_keyword_comparison(
        keyword_summary,
        output_dir,
    )

    keyword_summary.to_csv(
        os.path.join(
            database_dir,
            "comparison_keyword_summary.csv",
        ),
        index=False,
        encoding="utf-8-sig",
    )

    print("[Comparison EDA] 저장 완료")
    print(
        "- "
        + os.path.join(
            output_dir,
            "comparison_rating_distribution.png",
        )
    )
    print(
        "- "
        + os.path.join(
            database_dir,
            "comparison_rating_summary.csv",
        )
    )
    print(
        "- "
        + os.path.join(
            output_dir,
            "comparison_keyword_frequency.png",
        )
    )
    print(
        "- "
        + os.path.join(
            database_dir,
            "comparison_keyword_summary.csv",
        )
    )


def main() -> None:
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-d",
        "--database_dir",
        type=str,
        default="database",
    )

    parser.add_argument(
        "-o",
        "--output_dir",
        type=str,
        default="review_analysis/plots",
    )

    args = parser.parse_args()

    run_comparison(
        args.database_dir,
        args.output_dir,
    )


if __name__ == "__main__":
    main()