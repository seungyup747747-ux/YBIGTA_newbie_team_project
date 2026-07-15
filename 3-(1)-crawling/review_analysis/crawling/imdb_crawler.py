from typing import Dict, List, Optional

from selenium.webdriver.chrome.webdriver import WebDriver

from review_analysis.crawling.base_crawler import BaseCrawler
from utils.logger import setup_logger


class IMDbCrawler(BaseCrawler):
    """IMDb에서 영화 리뷰를 수집하는 크롤러."""

    def __init__(self, output_dir: str):
        """IMDb 크롤러를 초기화한다.

        Args:
            output_dir: 크롤링 결과 CSV 파일을 저장할 디렉터리 경로.
        """
        super().__init__(output_dir)

        self.base_url = ""
        self.target_count = 500

        self.driver: Optional[WebDriver] = None
        self.reviews: List[Dict[str, str]] = []
        self.logger = setup_logger("imdb_crawler.log")

    def start_browser(self) -> None:
        """Selenium Chrome WebDriver를 실행한다."""
        pass

    def scrape_reviews(self) -> None:
        """IMDb에서 별점, 날짜, 리뷰 본문을 수집한다."""
        pass

    def save_to_database(self) -> None:
        """수집한 리뷰를 CSV 파일로 저장한다."""
        pass