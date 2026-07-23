import glob
import os
from argparse import ArgumentParser
from typing import Dict, Type

from review_analysis.preprocessing.base_processor import BaseDataProcessor
from review_analysis.preprocessing.example_processor import ExampleProcessor
from review_analysis.preprocessing.letterboxd_processor import (
    LetterboxdProcessor,
)
from review_analysis.preprocessing.naver_processor import NaverProcessor

from review_analysis.preprocessing.metacritic_processor import (
    MetacriticProcessor,
)


# 모든 preprocessing 클래스를 예시 형식으로 등록합니다.
# key는 원본 CSV 파일명에서 확장자를 제외한 이름입니다.
# 예: reviews_letterboxd.csv -> reviews_letterboxd
PREPROCESS_CLASSES: Dict[str, Type[BaseDataProcessor]] = {
    "reviews_example": ExampleProcessor,
    "reviews_letterboxd": LetterboxdProcessor,
    "reviews_naver": NaverProcessor,
    "reviews_metacritic": MetacriticProcessor,
}


# main.py의 위치를 기준으로 프로젝트 경로를 계산합니다.
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))

DEFAULT_DATABASE_DIR = os.path.abspath(
    os.path.join(
        CURRENT_DIR,
        "..",
        "..",
        "database",
    )
)


def get_review_collections() -> list[str]:
    """
    database 폴더 안의 reviews_*.csv 파일 목록을 반환합니다.

    preprocessed_reviews_*.csv는 파일명이 reviews_로 시작하지 않으므로
    자동으로 제외됩니다.
    """
    pattern = os.path.join(
        DEFAULT_DATABASE_DIR,
        "reviews_*.csv",
    )

    return sorted(glob.glob(pattern))


def create_parser() -> ArgumentParser:
    parser = ArgumentParser()

    parser.add_argument(
        "-o",
        "--output_dir",
        type=str,
        required=False,
        default=DEFAULT_DATABASE_DIR,
        help=(
            "전처리 결과를 저장할 폴더입니다. "
            f"기본값: {DEFAULT_DATABASE_DIR}"
        ),
    )

    parser.add_argument(
        "-c",
        "--preprocessor",
        type=str,
        required=False,
        choices=PREPROCESS_CLASSES.keys(),
        help=(
            "실행할 전처리기를 선택합니다. "
            f"Choices: {', '.join(PREPROCESS_CLASSES.keys())}"
        ),
    )

    parser.add_argument(
        "-a",
        "--all",
        action="store_true",
        help="등록된 모든 데이터 전처리기를 실행합니다.",
    )

    return parser


def run_preprocessor(
    csv_file: str,
    output_dir: str,
) -> None:
    """
    CSV 파일명에 맞는 전처리 클래스를 찾아 실행합니다.
    """
    base_name = os.path.splitext(
        os.path.basename(csv_file)
    )[0]

    if base_name not in PREPROCESS_CLASSES:
        print(
            f"[Skip] 등록된 전처리기가 없습니다: "
            f"{os.path.basename(csv_file)}"
        )
        return

    preprocessor_class = PREPROCESS_CLASSES[base_name]

    print(
        f"[Start] {base_name} "
        f"-> {preprocessor_class.__name__}"
    )

    preprocessor = preprocessor_class(
        csv_file,
        output_dir,
    )

    preprocessor.preprocess()
    preprocessor.feature_engineering()
    preprocessor.save_to_database()

    print(f"[Done] {base_name}")


def find_selected_csv(
    preprocessor_name: str,
) -> str:
    """
    선택한 전처리기 이름에 해당하는 원본 CSV 경로를 반환합니다.
    """
    csv_path = os.path.join(
        DEFAULT_DATABASE_DIR,
        f"{preprocessor_name}.csv",
    )

    if not os.path.exists(csv_path):
        raise FileNotFoundError(
            f"원본 CSV 파일을 찾을 수 없습니다: {csv_path}"
        )

    return csv_path


def main() -> None:
    parser = create_parser()
    args = parser.parse_args()

    output_dir = os.path.abspath(args.output_dir)
    os.makedirs(output_dir, exist_ok=True)

    if args.all:
        review_collections = get_review_collections()

        if not review_collections:
            raise FileNotFoundError(
                "database 폴더에서 reviews_*.csv 파일을 "
                f"찾을 수 없습니다: {DEFAULT_DATABASE_DIR}"
            )

        executed_count = 0

        for csv_file in review_collections:
            base_name = os.path.splitext(
                os.path.basename(csv_file)
            )[0]

            if base_name in PREPROCESS_CLASSES:
                run_preprocessor(
                    csv_file,
                    output_dir,
                )
                executed_count += 1
            else:
                print(
                    f"[Skip] 등록된 전처리기가 없습니다: "
                    f"{os.path.basename(csv_file)}"
                )

        if executed_count == 0:
            raise RuntimeError(
                "실행 가능한 전처리기가 없습니다. "
                "PREPROCESS_CLASSES 등록 상태를 확인하세요."
            )

        return

    if args.preprocessor:
        csv_file = find_selected_csv(
            args.preprocessor
        )

        run_preprocessor(
            csv_file,
            output_dir,
        )
        return

    parser.error(
        "--all 또는 --preprocessor 중 하나를 지정해야 합니다."
    )


if __name__ == "__main__":
    main()
