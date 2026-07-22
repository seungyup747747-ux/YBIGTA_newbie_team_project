"""
Naver review preprocessing
"""

import html
import os
import re
import unicodedata
from typing import Optional

import numpy as np
import pandas as pd
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from review_analysis.preprocessing.base_processor import BaseDataProcessor


class NaverProcessor(BaseDataProcessor):

    REQUIRED_COLUMNS = {"rating", "date", "review"}

    URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
    HTML_PATTERN = re.compile(r"<[^>]+>")
    WHITESPACE_PATTERN = re.compile(r"\s+")
    ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200d\ufeff]")

    def __init__(self, input_path: str, output_dir: str):
        super().__init__(input_path, output_dir)
        self.data: Optional[pd.DataFrame] = None
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.svd: Optional[TruncatedSVD] = None
        self.preprocessing_summary: dict[str, object] = {}

    def preprocess(self):
        """결측치, 형식 오류, 이상치, 중복 리뷰를 처리합니다."""
        data = pd.read_csv(self.input_path)

        missing_columns = self.REQUIRED_COLUMNS - set(data.columns)
        if missing_columns:
            raise ValueError(
                f"필수 컬럼이 없습니다: {sorted(missing_columns)}"
            )

        keep_columns = ["rating", "date", "review"]
        if "reviewer" in data.columns:
            keep_columns.append("reviewer")

        data = data[keep_columns].copy()
        self.preprocessing_summary["original_count"] = len(data)

        data["rating"] = pd.to_numeric(data["rating"], errors="coerce")
        data["date"] = pd.to_datetime(data["date"], errors="coerce")

        before = len(data)
        data = data.dropna(subset=["rating", "date", "review"])
        self.preprocessing_summary["missing_or_invalid_removed"] = (
            before - len(data)
        )

        before = len(data)
        data = data[data["rating"].between(0, 10)]
        self.preprocessing_summary["invalid_rating_removed"] = (
            before - len(data)
        )

        before = len(data)
        today = pd.Timestamp.today().normalize()
        data = data[
            (data["date"] >= pd.Timestamp("2000-01-01"))
            & (data["date"] <= today)
        ]
        self.preprocessing_summary["date_outlier_removed"] = (
            before - len(data)
        )

        data["raw_review"] = data["review"].astype(str).str.strip()
        data["normalized_review"] = data["raw_review"].apply(
            self._normalize_text
        )
        data["cleaned_review"] = data["normalized_review"].apply(
            self._clean_for_vectorization
        )

        before = len(data)
        data = data[data["cleaned_review"].str.len() >= 3]
        self.preprocessing_summary["short_review_removed"] = (
            before - len(data)
        )

        before = len(data)
        data = data[data["normalized_review"].str.len() <= 1000]
        self.preprocessing_summary["long_review_removed"] = (
            before - len(data)
        )

        before = len(data)
        data = data.drop_duplicates(
            subset=["rating", "date", "cleaned_review"]
        )
        self.preprocessing_summary["exact_duplicates_removed"] = (
            before - len(data)
        )

        self.data = data.reset_index(drop=True)
        self.preprocessing_summary["final_count_after_preprocess"] = len(
            self.data
        )

        print(
            "[Naver] preprocess 완료: "
            f"{self.preprocessing_summary['original_count']}개 -> "
            f"{len(self.data)}개"
        )

    def feature_engineering(self):
        if self.data is None:
            raise RuntimeError("preprocess()를 먼저 실행해야 합니다.")

        data = self.data.copy()

        data["review_length"] = data["normalized_review"].str.len()
        data["word_count"] = data["cleaned_review"].str.split().str.len()
        data["review_length_log1p"] = np.log1p(data["review_length"])

        q1 = data["review_length"].quantile(0.25)
        q3 = data["review_length"].quantile(0.75)
        iqr = q3 - q1
        long_threshold = q3 + 3 * iqr
        data["is_long_review"] = (
            data["review_length"] > long_threshold
        ).astype(int)

        data["year"] = data["date"].dt.year
        data["month"] = data["date"].dt.month
        data["day"] = data["date"].dt.day
        data["weekday"] = data["date"].dt.day_name()
        data["hour"] = data["date"].dt.hour
        data["is_weekend"] = (data["date"].dt.weekday >= 5).astype(int)
        data["time_period"] = data["hour"].apply(self._time_period)

        data["is_positive"] = (data["rating"] >= 8.0).astype(int)
        data["is_negative"] = (data["rating"] <= 4.0).astype(int)
        data["rating_centered"] = data["rating"] - data["rating"].mean()
        data["site"] = "naver"

        min_df = 2 if len(data) >= 50 else 1
        self.vectorizer = TfidfVectorizer(
            analyzer="word",
            ngram_range=(1, 2),
            min_df=min_df,
            max_features=1000,
            token_pattern=r"(?u)\b\w\w+\b",
            sublinear_tf=True,
        )
        tfidf_matrix = self.vectorizer.fit_transform(
            data["cleaned_review"]
        )

        max_components = min(
            10,
            tfidf_matrix.shape[0] - 1,
            tfidf_matrix.shape[1] - 1,
        )

        if max_components >= 2:
            self.svd = TruncatedSVD(
                n_components=max_components,
                random_state=42,
            )
            reduced = self.svd.fit_transform(tfidf_matrix)
            svd_columns = [
                f"text_svd_{index:02d}"
                for index in range(1, max_components + 1)
            ]
            svd_data = pd.DataFrame(
                reduced,
                columns=svd_columns,
                index=data.index,
            )
            data = pd.concat([data, svd_data], axis=1)
            self.preprocessing_summary["svd_explained_variance"] = float(
                self.svd.explained_variance_ratio_.sum()
            )
        else:
            self.preprocessing_summary["svd_explained_variance"] = 0.0

        data["tfidf_nonzero_count"] = (tfidf_matrix > 0).sum(axis=1).A1

        self.preprocessing_summary["long_review_threshold"] = float(
            long_threshold
        )
        self.preprocessing_summary["long_review_count"] = int(
            data["is_long_review"].sum()
        )
        self.preprocessing_summary["tfidf_feature_count"] = int(
            tfidf_matrix.shape[1]
        )
        self.preprocessing_summary["svd_component_count"] = int(
            max_components
        )
        self.preprocessing_summary["final_count"] = len(data)

        self.data = data
        print("[Naver] feature_engineering 완료")

    def save_to_database(self):
        if self.data is None:
            raise RuntimeError("저장할 데이터가 없습니다.")

        os.makedirs(self.output_dir, exist_ok=True)

        output_path = os.path.join(
            self.output_dir,
            "preprocessed_reviews_naver.csv",
        )
        summary_path = os.path.join(
            self.output_dir,
            "naver_preprocessing_summary.csv",
        )

        self.data.to_csv(
            output_path,
            index=False,
            encoding="utf-8-sig",
        )

        pd.DataFrame(
            {
                "item": list(self.preprocessing_summary.keys()),
                "value": list(self.preprocessing_summary.values()),
            }
        ).to_csv(
            summary_path,
            index=False,
            encoding="utf-8-sig",
        )

        print(f"[Naver] 저장 완료: {output_path}")

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        text = html.unescape(str(text))
        text = unicodedata.normalize("NFKC", text)
        text = cls.ZERO_WIDTH_PATTERN.sub("", text)
        text = cls.URL_PATTERN.sub(" ", text)
        text = cls.HTML_PATTERN.sub(" ", text)
        text = cls.WHITESPACE_PATTERN.sub(" ", text).strip()
        return text

    @staticmethod
    def _clean_for_vectorization(text: str) -> str:
        result: list[str] = []
        for character in text.casefold():
            category = unicodedata.category(character)
            if (
                category.startswith("L")
                or category.startswith("N")
                or category.startswith("M")
            ):
                result.append(character)
            else:
                result.append(" ")
        return re.sub(r"\s+", " ", "".join(result)).strip()

    @staticmethod
    def _time_period(hour: int) -> str:
        if 5 <= hour < 12:
            return "morning"
        if 12 <= hour < 18:
            return "afternoon"
        if 18 <= hour < 24:
            return "evening"
        return "night"
