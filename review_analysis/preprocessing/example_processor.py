import json
import tempfile
from typing import Any

import pandas as pd

from review_analysis.preprocessing.base_processor import BaseDataProcessor
from review_analysis.preprocessing.letterboxd_processor import (
    LetterboxdProcessor,
)
from review_analysis.preprocessing.metacritic_processor import (
    MetacriticProcessor,
)
from review_analysis.preprocessing.naver_processor import NaverProcessor


PROCESSOR_BY_SITE = {
    "naver": NaverProcessor,
    "letterboxd": LetterboxdProcessor,
    "metacritic": MetacriticProcessor,
}


class ExampleProcessor(BaseDataProcessor):
    """MongoDB 문서를 기존 사이트별 전처리 클래스에 연결하는 어댑터."""

    def __init__(
        self,
        documents: list[dict],
        site_name: str,
        output_collection: Any,
    ) -> None:
        normalized_site_name = site_name.strip().lower()

        if normalized_site_name not in PROCESSOR_BY_SITE:
            raise ValueError(
                "지원하지 않는 사이트입니다. "
                "naver, letterboxd, metacritic 중 하나를 입력하세요."
            )

        if not documents:
            raise ValueError("전처리할 리뷰가 없습니다.")

        self.site_name = normalized_site_name
        self.output_collection = output_collection
        self._temporary_directory = tempfile.TemporaryDirectory()

        input_path = (
            f"{self._temporary_directory.name}/"
            f"raw_{self.site_name}.csv"
        )

        rows = [
            {
                key: value
                for key, value in document.items()
                if key != "_id"
            }
            for document in documents
        ]
        pd.DataFrame(rows).to_csv(
            input_path,
            index=False,
            encoding="utf-8",
        )

        super().__init__(
            input_path=input_path,
            output_dir=self._temporary_directory.name,
        )

        processor_class = PROCESSOR_BY_SITE[self.site_name]
        self.processor = processor_class(
            self.input_path,
            self.output_dir,
        )
        self.data: pd.DataFrame | None = None
        self.summary: dict[str, Any] = {}

    def preprocess(self) -> None:
        self.processor.preprocess()
        self.data = self.processor.data
        self._update_summary()

    def feature_engineering(self) -> None:
        if self.data is None:
            raise RuntimeError("preprocess()를 먼저 실행해야 합니다.")

        self.processor.feature_engineering()
        self.data = self.processor.data
        self._update_summary()

    def save_to_database(self) -> int:
        if self.data is None:
            raise RuntimeError("저장할 전처리 데이터가 없습니다.")

        records = json.loads(
            self.data.to_json(
                orient="records",
                date_format="iso",
                force_ascii=False,
            )
        )

        try:
            self.output_collection.delete_many({})

            if records:
                self.output_collection.insert_many(records)

            return len(records)
        finally:
            self._temporary_directory.cleanup()

    def _update_summary(self) -> None:
        if hasattr(self.processor, "preprocessing_summary"):
            self.summary = dict(
                self.processor.preprocessing_summary
            )
        elif hasattr(self.processor, "summary"):
            self.summary = dict(self.processor.summary)
