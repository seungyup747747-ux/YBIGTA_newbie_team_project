"""
Letterboxd multilingual preprocessing
Version: 2026-07-22-multilingual-v2
"""

import argparse
import html
import os
import re
import unicodedata
from typing import Optional

import joblib
import numpy as np
import pandas as pd
from langdetect import DetectorFactory, LangDetectException, detect_langs
from sklearn.decomposition import TruncatedSVD
from sklearn.feature_extraction.text import TfidfVectorizer

from review_analysis.preprocessing.base_processor import BaseDataProcessor


DetectorFactory.seed = 42


class LetterboxdProcessor(BaseDataProcessor):
    """
    Letterboxd 리뷰 전처리 및 Feature Engineering.

    핵심 원칙
    ---------
    - 여러 언어의 원문을 삭제하거나 영어로 강제 변환하지 않습니다.
    - 짧은 리뷰와 긴 리뷰를 길이만으로 삭제하지 않습니다.
    - 플랫폼 안내 문구와 명백한 형식 오류만 제거합니다.
    - 언어에 비교적 덜 민감한 character n-gram TF-IDF를 사용합니다.
    """

    REQUIRED_COLUMNS = {"rating", "date", "review"}

    NON_REVIEW_TEXTS = {
        "this review may contain spoilers. i can handle the truth.",
    }

    URL_PATTERN = re.compile(r"https?://\S+|www\.\S+", re.IGNORECASE)
    HTML_PATTERN = re.compile(r"<[^>]+>")
    ZERO_WIDTH_PATTERN = re.compile(r"[\u200b-\u200d\ufeff]")
    WHITESPACE_PATTERN = re.compile(r"\s+")

    def __init__(self, input_path: str, output_dir: str):
        super().__init__(input_path, output_dir)

        self.data: Optional[pd.DataFrame] = None
        self.vectorizer: Optional[TfidfVectorizer] = None
        self.svd: Optional[TruncatedSVD] = None
        self.preprocessing_summary: dict[str, object] = {}

    def preprocess(self):
        """결측치·형식 오류·완전 중복·플랫폼 안내 문구를 처리합니다."""
        data = pd.read_csv(self.input_path)

        missing_columns = self.REQUIRED_COLUMNS - set(data.columns)
        if missing_columns:
            raise ValueError(
                f"필수 컬럼이 없습니다: {sorted(missing_columns)}"
            )

        data = data[["rating", "date", "review"]].copy()
        self.preprocessing_summary["original_count"] = len(data)

        # 타입 변환 실패값은 NaN/NaT로 바꿉니다.
        data["rating"] = pd.to_numeric(data["rating"], errors="coerce")
        data["date"] = pd.to_datetime(data["date"], errors="coerce")

        before = len(data)
        data = data.dropna(subset=["rating", "date", "review"])
        self.preprocessing_summary["missing_or_invalid_removed"] = (
            before - len(data)
        )

        # 원문은 유지하고 비교 및 분석용 정규화 문장을 별도로 만듭니다.
        data["review"] = data["review"].astype(str).str.strip()
        data["normalized_review"] = data["review"].apply(
            self._normalize_text
        )

        before = len(data)
        data = data[data["normalized_review"].str.len() > 0]
        self.preprocessing_summary["empty_review_removed"] = (
            before - len(data)
        )

        # 동일한 별점·날짜·문장이 모두 같은 경우만 완전 중복으로 제거합니다.
        before = len(data)
        data = data.drop_duplicates(
            subset=["rating", "date", "normalized_review"]
        )
        self.preprocessing_summary["exact_duplicates_removed"] = (
            before - len(data)
        )

        # Letterboxd 별점은 0.5~5.0, 0.5점 단위입니다.
        before = len(data)
        valid_range = data["rating"].between(0.5, 5.0)
        valid_half_step = np.isclose(
            data["rating"] * 2,
            np.round(data["rating"] * 2),
        )
        data = data[valid_range & valid_half_step]
        self.preprocessing_summary["invalid_rating_removed"] = (
            before - len(data)
        )

        # 실행일 이후의 미래 날짜만 제거합니다.
        # 개봉 전 날짜는 사용자 입력 오류일 수 있으나 근거 없이 삭제하지 않습니다.
        before = len(data)
        today = pd.Timestamp.today().normalize()
        data = data[data["date"] <= today]
        self.preprocessing_summary["future_date_removed"] = (
            before - len(data)
        )

        # 실제 리뷰가 아닌 Letterboxd 안내 문구를 제거합니다.
        before = len(data)
        notice_key = data["normalized_review"].str.casefold()
        data = data[~notice_key.isin(self.NON_REVIEW_TEXTS)]
        self.preprocessing_summary["platform_notice_removed"] = (
            before - len(data)
        )

        # 다국어 문자와 숫자를 보존한 벡터화용 문장을 만듭니다.
        data["cleaned_review"] = data["normalized_review"].apply(
            self._clean_for_vectorization
        )

        before = len(data)
        data = data[data["cleaned_review"].str.len() > 0]
        self.preprocessing_summary["cleaning_empty_removed"] = (
            before - len(data)
        )

        # 다른 날짜나 별점에서 반복된 동일 문장은 제거하지 않고 표시만 합니다.
        data["is_text_duplicate"] = (
            data["cleaned_review"].duplicated(keep=False).astype(int)
        )

        # 매우 짧은 문장의 언어 감지는 불안정하므로 unknown으로 둡니다.
        language_result = data["normalized_review"].apply(
            self._detect_language
        )
        data["language"] = language_result.map(lambda value: value[0])
        data["language_confidence"] = language_result.map(
            lambda value: value[1]
        )

        self.data = data.reset_index(drop=True)
        self.preprocessing_summary["final_count_after_preprocess"] = len(
            self.data
        )

        print(
            "[Letterboxd] preprocess 완료: "
            f"{self.preprocessing_summary['original_count']}개 → "
            f"{len(self.data)}개"
        )

    def feature_engineering(self):
        """텍스트·날짜·평점 파생변수와 TF-IDF-SVD 변수를 생성합니다."""
        if self.data is None:
            raise RuntimeError("preprocess()를 먼저 실행해야 합니다.")

        data = self.data.copy()

        # 텍스트 관련 파생변수
        data["review_length"] = data["normalized_review"].str.len()
        data["word_count"] = (
            data["cleaned_review"].str.split().str.len()
        )
        data["emoji_count"] = data["normalized_review"].apply(
            self._count_emoji_like_chars
        )
        data["exclamation_count"] = (
            data["normalized_review"].str.count("!")
        )
        data["question_count"] = (
            data["normalized_review"].str.count(r"\?")
        )
        data["uppercase_ratio"] = data["review"].apply(
            self._uppercase_ratio
        )

        # 긴 리뷰는 오류라고 단정할 수 없으므로 삭제하지 않습니다.
        q1 = data["review_length"].quantile(0.25)
        q3 = data["review_length"].quantile(0.75)
        iqr = q3 - q1
        long_threshold = q3 + 3 * iqr

        data["is_long_review"] = (
            data["review_length"] > long_threshold
        ).astype(int)
        data["review_length_log1p"] = np.log1p(
            data["review_length"]
        )
        data["review_length_capped"] = data["review_length"].clip(
            upper=long_threshold
        )

        self.preprocessing_summary["long_review_threshold"] = float(
            long_threshold
        )
        self.preprocessing_summary["long_review_count"] = int(
            data["is_long_review"].sum()
        )

        # 날짜 관련 파생변수
        data["year"] = data["date"].dt.year
        data["month"] = data["date"].dt.month
        data["day"] = data["date"].dt.day
        data["weekday"] = data["date"].dt.day_name()
        data["is_weekend"] = (
            data["date"].dt.weekday >= 5
        ).astype(int)

        # 평점 관련 파생변수
        data["is_positive"] = (data["rating"] >= 4.0).astype(int)
        data["is_negative"] = (data["rating"] <= 2.0).astype(int)
        data["rating_centered"] = (
            data["rating"] - data["rating"].mean()
        )
        data["site"] = "letterboxd"

        # 다국어 대응용 character n-gram TF-IDF
        min_df = 2 if len(data) >= 50 else 1
        self.vectorizer = TfidfVectorizer(
            analyzer="char_wb",
            ngram_range=(3, 5),
            min_df=min_df,
            max_features=1500,
            sublinear_tf=True,
            lowercase=False,
        )

        tfidf_matrix = self.vectorizer.fit_transform(
            data["cleaned_review"]
        )

        max_components = min(
            20,
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

            self.preprocessing_summary["tfidf_feature_count"] = int(
                tfidf_matrix.shape[1]
            )
            self.preprocessing_summary["svd_component_count"] = int(
                max_components
            )
            self.preprocessing_summary["svd_explained_variance"] = float(
                self.svd.explained_variance_ratio_.sum()
            )
        else:
            self.preprocessing_summary["tfidf_feature_count"] = int(
                tfidf_matrix.shape[1]
            )
            self.preprocessing_summary["svd_component_count"] = 0
            self.preprocessing_summary["svd_explained_variance"] = 0.0

        self.data = data
        self.preprocessing_summary["final_count"] = len(data)

        print("[Letterboxd] feature_engineering 완료")

    def save_to_database(self):
        """전처리 결과와 모델 및 요약 파일을 저장합니다."""
        if self.data is None:
            raise RuntimeError("저장할 데이터가 없습니다.")

        os.makedirs(self.output_dir, exist_ok=True)

        output_path = os.path.join(
            self.output_dir,
            "preprocessed_reviews_letterboxd.csv",
        )
        summary_path = os.path.join(
            self.output_dir,
            "letterboxd_preprocessing_summary.csv",
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

        if self.vectorizer is not None:
            joblib.dump(
                self.vectorizer,
                os.path.join(
                    self.output_dir,
                    "letterboxd_char_tfidf_vectorizer.joblib",
                ),
            )

        if self.svd is not None:
            joblib.dump(
                self.svd,
                os.path.join(
                    self.output_dir,
                    "letterboxd_tfidf_svd.joblib",
                ),
            )

        print(f"[Letterboxd] 저장 완료: {output_path}")

    @classmethod
    def _normalize_text(cls, text: str) -> str:
        """HTML entity, URL, 태그, 제로폭 문자, 중복 공백을 정리합니다."""
        text = html.unescape(str(text))
        text = unicodedata.normalize("NFKC", text)
        text = cls.ZERO_WIDTH_PATTERN.sub("", text)
        text = cls.URL_PATTERN.sub(" ", text)
        text = cls.HTML_PATTERN.sub(" ", text)
        text = cls.WHITESPACE_PATTERN.sub(" ", text).strip()
        return text

    @staticmethod
    def _clean_for_vectorization(text: str) -> str:
        """Unicode 문자·숫자·결합기호를 보존하고 나머지는 공백 처리합니다."""
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

    @classmethod
    def _detect_language(cls, text: str) -> tuple[str, float]:
        """문자 체계와 langdetect를 함께 사용해 언어를 추정합니다."""
        compact = cls.WHITESPACE_PATTERN.sub(" ", text).strip()
        letter_count = sum(
            unicodedata.category(char).startswith("L")
            for char in compact
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
        # 일본어는 한자도 사용하므로 가나를 먼저 확인합니다.
        kana_count = sum(
            0x3040 <= ord(char) <= 0x30FF
            for char in text
        )
        if kana_count >= 2:
            return "ja"

        ranges = [
            ("ko", 0xAC00, 0xD7AF),
            ("ru", 0x0400, 0x04FF),
            ("el", 0x0370, 0x03FF),
            ("ar", 0x0600, 0x06FF),
            ("th", 0x0E00, 0x0E7F),
            ("zh", 0x4E00, 0x9FFF),
        ]

        for language, start, end in ranges:
            count = sum(
                start <= ord(char) <= end
                for char in text
            )
            if count >= 3:
                return language

        return None

    @staticmethod
    def _count_emoji_like_chars(text: str) -> int:
        count = 0

        for character in text:
            code = ord(character)
            category = unicodedata.category(character)

            if (
                category == "So"
                or 0x1F300 <= code <= 0x1FAFF
                or 0x2600 <= code <= 0x27BF
            ):
                count += 1

        return count

    @staticmethod
    def _uppercase_ratio(text: str) -> float:
        letters = [char for char in text if char.isalpha()]

        if not letters:
            return 0.0

        uppercase_count = sum(char.isupper() for char in letters)
        return uppercase_count / len(letters)


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "-i",
        "--input_path",
        type=str,
        default="database/reviews_letterboxd.csv",
    )
    parser.add_argument(
        "-o",
        "--output_dir",
        type=str,
        default="database",
    )

    args = parser.parse_args()

    processor = LetterboxdProcessor(
        input_path=args.input_path,
        output_dir=args.output_dir,
    )
    processor.preprocess()
    processor.feature_engineering()
    processor.save_to_database()


if __name__ == "__main__":
    main()