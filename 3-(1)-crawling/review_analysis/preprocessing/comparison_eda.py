"""Site-level comparison EDA for preprocessed review datasets."""

import argparse
import os
from pathlib import Path

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt
import pandas as pd


SITE_FILES = {
    "Letterboxd": "preprocessed_reviews_letterboxd.csv",
    "Naver": "preprocessed_reviews_naver.csv",
    "Metacritic": "preprocessed_reviews_metacritic.csv",
}


RATING_GROUPS = [
    ("0-2", 0, 2),
    ("3-4", 3, 4),
    ("5-6", 5, 6),
    ("7-8", 7, 8),
    ("9-10", 9, 10),
]


def load_site_data(database_dir: str) -> pd.DataFrame:
    frames: list[pd.DataFrame] = []
    base_dir = Path(database_dir)

    for site, filename in SITE_FILES.items():
        path = base_dir / filename
        if not path.exists():
            raise FileNotFoundError(f"전처리 결과 파일이 없습니다: {path}")

        data = pd.read_csv(path)
        if "rating" not in data.columns:
            raise ValueError(f"{filename}에 rating 컬럼이 없습니다.")

        data = data.copy()
        data["site"] = site
        data["rating"] = pd.to_numeric(data["rating"], errors="coerce")
        data = data.dropna(subset=["rating"])

        if site == "Letterboxd":
            data["rating_10"] = data["rating"] * 2
        else:
            data["rating_10"] = data["rating"]

        frames.append(data)

    return pd.concat(frames, ignore_index=True)


def build_rating_summary(data: pd.DataFrame) -> pd.DataFrame:
    summary = []

    for site, group in data.groupby("site"):
        rounded_rating = group["rating_10"].round().astype(int)
        total = len(group)

        for label, lower, upper in RATING_GROUPS:
            count = int(rounded_rating.between(lower, upper).sum())
            summary.append(
                {
                    "site": site,
                    "rating_group": label,
                    "count": count,
                    "ratio": count / total,
                }
            )

    return pd.DataFrame(summary)


def plot_rating_distribution(summary: pd.DataFrame, output_dir: str) -> None:
    site_order = ["Letterboxd", "Naver", "Metacritic"]
    group_order = [label for label, _, _ in RATING_GROUPS]
    pivot = (
        summary.pivot(index="site", columns="rating_group", values="ratio")
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

        for bar, value, start in zip(bars, values, bottom):
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

        bottom = [start + value for start, value in zip(bottom, values)]

    plt.title("Rating Group Distribution by Site (0-10 Scale)")
    plt.xlabel("Site")
    plt.ylabel("Review Ratio")
    plt.ylim(0, 1)
    plt.legend(title="Rating Group", loc="upper right")
    plt.tight_layout()
    plt.savefig(
        os.path.join(output_dir, "comparison_rating_distribution.png"),
        dpi=200,
        bbox_inches="tight",
    )
    plt.close()


def run_comparison(database_dir: str, output_dir: str) -> None:
    os.makedirs(output_dir, exist_ok=True)

    data = load_site_data(database_dir)
    summary = build_rating_summary(data)
    plot_rating_distribution(summary, output_dir)

    summary.to_csv(
        os.path.join(database_dir, "comparison_rating_summary.csv"),
        index=False,
        encoding="utf-8-sig",
    )

    print("[Comparison EDA] 저장 완료")
    print(f"- {os.path.join(output_dir, 'comparison_rating_distribution.png')}")
    print(f"- {os.path.join(database_dir, 'comparison_rating_summary.csv')}")


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

    run_comparison(args.database_dir, args.output_dir)


if __name__ == "__main__":
    main()
