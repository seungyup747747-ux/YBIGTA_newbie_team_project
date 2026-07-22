"""Metacritic review preprocessing and feature engineering."""

import os
import re
from typing import Optional

import joblib
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer

from review_analysis.preprocessing.base_processor import BaseDataProcessor


class MetacriticProcessor(BaseDataProcessor):
    """Preprocess Metacritic's 0-10 user-review data."""

    REQUIRED_COLUMNS = {"rate", "date", "review"}

    def __init__(self, input_path: str, output_dir: str):
        super().__init__(input_path, output_dir)
        self.data: Optional[pd.DataFrame] = None
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.summary: dict[str, object] = {}

    def preprocess(self):
        """Remove invalid, empty, future-dated, and duplicate reviews."""
        data = pd.read_csv(self.input_path)

        missing_columns = self.REQUIRED_COLUMNS - set(data.columns)
        if missing_columns:
            raise ValueError(
                f"Required columns are missing: {sorted(missing_columns)}"
            )

        # Standardize Metacritic's `rate` column to the shared `rating` name.
        # Selecting columns also removes a crawler-created `Unnamed: 0` index.
        data = data[["rate", "date", "review"]].copy()
        data = data.rename(columns={"rate": "rating"})
        self.summary["original_count"] = len(data)

        data["rating"] = pd.to_numeric(data["rating"], errors="coerce")
        # 원본에는 "May 11, 2026"처럼 여러 월/일 형식이 섞여 있다.
        data["date"] = pd.to_datetime(
            data["date"], format="mixed", errors="coerce"
        )
        data["review"] = data["review"].astype(str).str.strip()

        before = len(data)
        data = data.dropna(subset=["rating", "date", "review"])
        data = data[data["review"] != ""]
        self.summary["missing_or_empty_removed"] = before - len(data)

        # Metacritic user scores are on a 0-10 scale.
        before = len(data)
        data = data[data["rating"].between(0, 10)]
        self.summary["invalid_rating_removed"] = before - len(data)

        before = len(data)
        today = pd.Timestamp.today().normalize()
        data = data[data["date"] <= today]
        self.summary["future_date_removed"] = before - len(data)

        data["cleaned_review"] = data["review"].apply(self._clean_text)

        before = len(data)
        data = data[data["cleaned_review"] != ""]
        self.summary["cleaning_empty_removed"] = before - len(data)

        before = len(data)
        data = data.drop_duplicates(
            subset=["rating", "date", "cleaned_review"]
        )
        self.summary["duplicate_removed"] = before - len(data)

        if data.empty:
            raise RuntimeError("No Metacritic reviews remain after preprocessing.")

        self.data = data.reset_index(drop=True)
        self.summary["final_count_after_preprocess"] = len(self.data)

    def feature_engineering(self):
        """Create text, date, rating, and TF-IDF features."""
        if self.data is None:
            raise RuntimeError("Run preprocess() before feature_engineering().")

        data = self.data.copy()

        data["review_length"] = data["cleaned_review"].str.len()
        data["word_count"] = data["cleaned_review"].str.split().str.len()
        data["exclamation_count"] = data["cleaned_review"].str.count("!")
        data["question_count"] = data["cleaned_review"].str.count(r"\?")

        data["year"] = data["date"].dt.year
        data["month"] = data["date"].dt.month
        data["weekday"] = data["date"].dt.day_name()
        data["is_weekend"] = (data["date"].dt.weekday >= 5).astype(int)

        data["rating_scaled"] = data["rating"] / 10
        data["is_positive"] = (data["rating"] >= 8).astype(int)
        data["is_negative"] = (data["rating"] <= 4).astype(int)
        data["site"] = "metacritic"

        self.vectorizer = TfidfVectorizer(
            stop_words="english",
            max_features=500,
            ngram_range=(1, 2),
        )
        tfidf_matrix = self.vectorizer.fit_transform(data["cleaned_review"])
        self.summary["tfidf_feature_count"] = int(tfidf_matrix.shape[1])

        self.data = data
        self.summary["final_count"] = len(data)

    def save_to_database(self):
        """Save processed data, its summary, and the TF-IDF vectorizer."""
        if self.data is None:
            raise RuntimeError("There is no data to save.")

        os.makedirs(self.output_dir, exist_ok=True)

        output_path = os.path.join(
            self.output_dir,
            "preprocessed_reviews_metacritic.csv",
        )
        summary_path = os.path.join(
            self.output_dir,
            "metacritic_preprocessing_summary.csv",
        )

        self.data.to_csv(output_path, index=False, encoding="utf-8-sig")

        pd.DataFrame(
            {
                "item": list(self.summary.keys()),
                "value": list(self.summary.values()),
            }
        ).to_csv(summary_path, index=False, encoding="utf-8-sig")

        if self.vectorizer is not None:
            joblib.dump(
                self.vectorizer,
                os.path.join(
                    self.output_dir,
                    "metacritic_tfidf_vectorizer.joblib",
                ),
            )

        print(f"[Metacritic] Saved: {output_path}")

    @staticmethod
    def _clean_text(text: str) -> str:
        """Remove URLs and collapse repeated whitespace."""
        text = re.sub(r"https?://\S+|www\.\S+", " ", str(text))
        text = re.sub(r"\s+", " ", text)
        return text.strip()
