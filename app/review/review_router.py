from fastapi import APIRouter, HTTPException, status

from database.mongodb_connection import mongo_db
from review_analysis.preprocessing.example_processor import ExampleProcessor


review_router = APIRouter(
    prefix="/review",
    tags=["review"],
)

SUPPORTED_SITES = {
    "naver",
    "letterboxd",
    "metacritic",
}


@review_router.post(
    "/preprocess/{site_name}",
    status_code=status.HTTP_200_OK,
)
def preprocess_reviews(site_name: str) -> dict:
    normalized_site_name = site_name.strip().lower()

    if normalized_site_name not in SUPPORTED_SITES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                "지원하지 않는 사이트입니다. "
                "naver, letterboxd, metacritic 중 하나를 입력하세요."
            ),
        )

    raw_collection_name = f"raw_{normalized_site_name}"
    processed_collection_name = f"processed_{normalized_site_name}"

    raw_collection = mongo_db[raw_collection_name]
    processed_collection = mongo_db[processed_collection_name]

    documents = list(raw_collection.find())

    if not documents:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{raw_collection_name}에 원본 리뷰가 없습니다.",
        )

    try:
        processor = ExampleProcessor(
            documents=documents,
            site_name=normalized_site_name,
            output_collection=processed_collection,
        )
        processor.preprocess()
        processor.feature_engineering()
        processed_count = processor.save_to_database()

    except ValueError as error:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(error),
        ) from error

    except Exception as error:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"리뷰 전처리 중 오류가 발생했습니다: {error}",
        ) from error

    return {
        "status": "success",
        "site_name": normalized_site_name,
        "raw_collection": raw_collection_name,
        "processed_collection": processed_collection_name,
        "raw_count": len(documents),
        "processed_count": processed_count,
    }
