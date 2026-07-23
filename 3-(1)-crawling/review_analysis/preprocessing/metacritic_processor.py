"""Metacritic review preprocessing and feature engineering."""

import os
import re
import unicodedata
from typing import Optional

import joblib
import pandas as pd
from langdetect import DetectorFactory, LangDetectException, detect_langs
from sklearn.feature_extraction.text import TfidfVectorizer

from review_analysis.preprocessing.base_processor import BaseDataProcessor


DetectorFactory.seed = 42


class MetacriticProcessor(BaseDataProcessor):
    """Metacritic 0~10점 사용자 리뷰를 분석 가능한 형태로 변환합니다.

    원문 리뷰는 보존하고, 정제 텍스트·언어 정보·날짜/평점 파생 변수와
    다국어 대응 TF-IDF 벡터라이저를 별도로 생성합니다.
    """

    REQUIRED_COLUMNS = {"rate", "date", "review"}

    def __init__(self, input_path: str, output_dir: str):
        super().__init__(input_path, output_dir)
        self.data: Optional[pd.DataFrame] = None
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.summary: dict[str, object] = {}

    def preprocess(self):
        """형식 오류, 빈값, 미래 날짜, 완전 중복을 제거하고 언어를 감지합니다."""
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

        # 원문은 보존하고, 다국어 문자까지 유지한 분석용 텍스트를 따로 만듭니다.
        data["cleaned_review"] = data["review"].apply(self._clean_text)

        before = len(data)
        data = data[data["cleaned_review"] != ""]
        self.summary["cleaning_empty_removed"] = before - len(data)

        before = len(data)
        data = data.drop_duplicates(
            subset=["rating", "date", "cleaned_review"]
        )
        self.summary["duplicate_removed"] = before - len(data)

        language_result = data["review"].apply(self._detect_language)
        data["language"] = language_result.map(lambda value: value[0])
        data["language_confidence"] = language_result.map(
            lambda value: value[1]
        )

        if data.empty:
            raise RuntimeError("No Metacritic reviews remain after preprocessing.")

        self.data = data.reset_index(drop=True)
        self.summary["final_count_after_preprocess"] = len(self.data)

    def feature_engineering(self):
        """텍스트·날짜·평점 파생 변수와 character n-gram TF-IDF를 생성합니다."""
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

        # 여러 언어와 문자 체계에 공통으로 적용 가능한 character n-gram을 사용합니다.
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=2 if len(data) >= 50 else 1,
            max_features=1500,
            sublinear_tf=True,
            lowercase=False,
        )
        tfidf_matrix = self.vectorizer.fit_transform(data["cleaned_review"])
        self.summary["tfidf_feature_count"] = int(tfidf_matrix.shape[1])

        self.data = data
        self.summary["final_count"] = len(data)

    def save_to_database(self):
        """전처리 CSV, 처리 요약 CSV, TF-IDF 벡터라이저를 저장합니다."""
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
        """URL·중복 공백만 정리하고 모든 언어의 문자는 보존합니다."""
        text = unicodedata.normalize("NFKC", str(text))
        text = re.sub(r"https?://\S+|www\.\S+", " ", text)
        text = re.sub(r"\s+", " ", text)
        return text.strip()

    @classmethod
    def _detect_language(cls, text: str) -> tuple[str, float]:
        """리뷰 언어와 신뢰도를 반환하며, 짧거나 불확실한 문장은 unknown 처리합니다."""
        compact = re.sub(r"\s+", " ", text).strip()
        letter_count = sum(
            unicodedata.category(character).startswith("L")
            for character in compact
        )
        if letter_count < 8:
            return "unknown", 0.0

        script_language = cls._detect_script_language(compact)
        if script_language is not None:
            return script_language, 1.0

        try:
            candidates = detect_langs(compact)
        except LangDetectException:
            return "unknown", 0.0

        if not candidates:
            return "unknown", 0.0

        best = candidates[0]
        confidence = float(best.prob)
        if confidence < 0.70:
            return "unknown", confidence

        return best.lang, confidence

    @staticmethod
    def _detect_script_language(text: str) -> Optional[str]:
        """고유 문자 체계가 뚜렷한 언어를 langdetect보다 먼저 판별합니다."""
        kana_count = sum(0x3040 <= ord(char) <= 0x30FF for char in text)
        if kana_count >= 2:
            return "ja"

        for language, start, end in [
            ("ko", 0xAC00, 0xD7AF),
            ("ru", 0x0400, 0x04FF),
            ("el", 0x0370, 0x03FF),
            ("ar", 0x0600, 0x06FF),
            ("th", 0x0E00, 0x0E7F),
            ("zh", 0x4E00, 0x9FFF),
        ]:
            if sum(start <= ord(char) <= end for char in text) >= 3:
                return language

        return None
