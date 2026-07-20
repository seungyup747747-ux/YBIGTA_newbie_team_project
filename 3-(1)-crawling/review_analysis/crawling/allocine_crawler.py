"""Allocine audience-review crawler for Avatar: The Way of Water."""

import os
import random
import re
import time
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd  # type: ignore[import-untyped]
from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from review_analysis.crawling.base_crawler import BaseCrawler
from utils.logger import setup_logger


class AllocineCrawler(BaseCrawler):
    """Allocine에서 영화 관람객 리뷰를 수집하는 크롤러.

    대상 영화는 ``Avatar : La Voie de l'eau``(2022)이다. Selenium으로
    리뷰 페이지를 불러온 뒤 BeautifulSoup으로 각 리뷰의 별점, 작성일,
    본문을 추출한다. 세 필드가 모두 존재하는 리뷰만 저장한다.

    Attributes:
        output_dir: 결과 CSV 파일을 저장할 디렉터리.
        base_url: 대상 영화의 Allocine 관람객 리뷰 URL.
        target_count: 최종적으로 저장할 최소 리뷰 개수.
        max_pages: 탐색할 최대 페이지 수.
        driver: Selenium Chrome WebDriver. 실행 전에는 ``None``이다.
        reviews: 수집한 리뷰 딕셔너리 목록.
    """

    def __init__(self, output_dir: str):
        """Allocine 크롤러의 저장 경로와 수집 설정을 초기화한다.

        Args:
            output_dir: ``reviews_allocine.csv``를 저장할 디렉터리 경로.
        """
        super().__init__(output_dir)

        self.base_url = (
            "https://www.allocine.fr/film/fichefilm-178014/"
            "critiques/spectateurs/"
        )
        self.target_count = 500
        self.max_pages = 60
        self.max_retries = 3
        self.driver: Optional[WebDriver] = None
        self.reviews: List[Dict[str, str]] = []
        self.logger = setup_logger("allocine_crawler.log")

    def start_browser(self) -> None:
        """Headless Chrome WebDriver를 생성한다.

        Selenium Manager가 설치된 Chrome에 맞는 드라이버를 자동으로
        준비하므로 별도의 ``chromedriver`` 경로를 코드에 적지 않는다.

        Raises:
            RuntimeError: Chrome 또는 Chrome WebDriver를 실행하지 못한 경우.
        """
        options = Options()
        options.page_load_strategy = "eager"
        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=fr-FR")
        options.add_argument(
            "--user-agent="
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )

        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)
            self.logger.info("Chrome WebDriver를 실행했습니다.")
        except WebDriverException as error:
            self.logger.exception("Chrome WebDriver 실행에 실패했습니다.")
            raise RuntimeError(
                "Chrome WebDriver를 실행할 수 없습니다. "
                "Chrome과 selenium 설치 상태를 확인하세요."
            ) from error

    @staticmethod
    def _clean_text(text: str) -> str:
        """HTML에서 얻은 문자열의 연속된 공백을 하나로 정리한다.

        Args:
            text: 정리 전 문자열.

        Returns:
            앞뒤 공백과 불필요한 줄바꿈이 제거된 문자열.
        """
        return re.sub(r"\s+", " ", text).strip()

    @staticmethod
    def _find_review_cards(soup: BeautifulSoup) -> List[Tag]:
        """페이지에서 개별 관람객 리뷰 카드를 찾는다.

        현재 사용되는 ``div.review-card``를 우선 사용하고, 사이트의 태그
        종류가 바뀌어도 class가 유지되면 동작하도록 보조 선택자를 둔다.

        Args:
            soup: 리뷰 페이지 전체를 파싱한 BeautifulSoup 객체.

        Returns:
            개별 리뷰를 나타내는 HTML 태그 목록.
        """
        selectors = [
            "div.hred.review-card.cf",
            "div.review-card",
            ".review-card",
            "[id^='review_']",
        ]

        for selector in selectors:
            cards = [
                element
                for element in soup.select(selector)
                if isinstance(element, Tag)
                and element.select_one(
                    ".content-txt.review-card-content, "
                    ".review-card-content, "
                    "[itemprop='reviewBody']"
                )
                is not None
            ]
            if cards:
                return cards

        return []

    @classmethod
    def _extract_rating(cls, review_card: Tag) -> Optional[str]:
        """리뷰 카드에서 5점 만점 별점을 추출한다.

        Allocine은 프랑스식 소수점 표기인 ``4,5``를 사용하므로 쉼표를
        마침표로 바꿔 Python에서 처리할 수 있게 한다.

        Args:
            review_card: 한 사용자의 리뷰 카드 HTML 요소.

        Returns:
            소수점 한 자리의 별점 문자열. 추출할 수 없으면 ``None``.
        """
        rating_element = review_card.select_one(
            ".stareval-note, [itemprop='ratingValue']"
        )
        if rating_element is None:
            return None

        candidates = [
            rating_element.get_text(" ", strip=True),
            str(rating_element.get("content", "")),
            str(rating_element.get("aria-label", "")),
        ]

        for candidate in candidates:
            match = re.search(r"(?<!\d)([0-5](?:[.,]\d)?)(?!\d)", candidate)
            if match is None:
                continue

            try:
                rating = float(match.group(1).replace(",", "."))
            except ValueError:
                continue

            if 0.0 <= rating <= 5.0:
                return f"{rating:.1f}"

        return None

    @classmethod
    def _extract_date(cls, review_card: Tag) -> Optional[str]:
        """리뷰 카드에서 작성일을 찾아 ISO 형식으로 변환한다.

        예를 들어 ``Publiée le 27 décembre 2022``는 ``2022-12-27``로
        저장한다. 새로운 표기 때문에 변환하지 못하더라도 날짜 텍스트가
        존재하면 원문에서 접두사만 제거하여 보존한다.

        Args:
            review_card: 한 사용자의 리뷰 카드 HTML 요소.

        Returns:
            ``YYYY-MM-DD`` 형식의 날짜 또는 정리된 원문 날짜.
            날짜 요소가 없으면 ``None``.
        """
        date_element = review_card.select_one(
            ".review-card-meta-date, time[datetime], [itemprop='datePublished']"
        )
        if date_element is None:
            return None

        for attribute in ("datetime", "content"):
            value = date_element.get(attribute)
            if isinstance(value, str):
                iso_match = re.search(r"\d{4}-\d{2}-\d{2}", value)
                if iso_match is not None:
                    return iso_match.group(0)

        raw_date = cls._clean_text(date_element.get_text(" ", strip=True))
        raw_date = re.sub(
            r"^Publi[ée]e?\s+le\s+",
            "",
            raw_date,
            flags=re.IGNORECASE,
        ).strip()

        months = {
            "janvier": 1,
            "février": 2,
            "fevrier": 2,
            "mars": 3,
            "avril": 4,
            "mai": 5,
            "juin": 6,
            "juillet": 7,
            "août": 8,
            "aout": 8,
            "septembre": 9,
            "octobre": 10,
            "novembre": 11,
            "décembre": 12,
            "decembre": 12,
        }
        match = re.fullmatch(
            r"(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})",
            raw_date,
        )
        if match is not None:
            day = int(match.group(1))
            month = months.get(match.group(2).lower())
            year = int(match.group(3))
            if month is not None and 1 <= day <= 31:
                return f"{year:04d}-{month:02d}-{day:02d}"

        return raw_date or None

    @classmethod
    def _extract_review_text(cls, review_card: Tag) -> Optional[str]:
        """리뷰 카드에서 리뷰 본문을 추출한다.

        Args:
            review_card: 한 사용자의 리뷰 카드 HTML 요소.

        Returns:
            공백이 정리된 리뷰 본문. 본문이 비어 있으면 ``None``.
        """
        text_element = review_card.select_one(
            ".content-txt.review-card-content, "
            ".review-card-content, "
            "[itemprop='reviewBody']"
        )
        if text_element is None:
            return None

        copied_soup = BeautifulSoup(str(text_element), "html.parser")
        for unnecessary in copied_soup.select("script, style, svg, button"):
            unnecessary.decompose()

        review_text = cls._clean_text(copied_soup.get_text(" ", strip=True))
        return review_text or None

    def _parse_page(self, html: str, page_number: int) -> List[Dict[str, str]]:
        """한 페이지의 HTML을 별점·날짜·본문 레코드로 변환한다.

        Args:
            html: Selenium이 가져온 페이지 전체 HTML.
            page_number: 로그에 표시할 현재 페이지 번호.

        Returns:
            필수 필드 세 개가 모두 존재하는 리뷰 딕셔너리 목록.
        """
        soup = BeautifulSoup(html, "html.parser")
        review_cards = self._find_review_cards(soup)
        parsed_reviews: List[Dict[str, str]] = []
        missing_rating = 0
        missing_date = 0
        missing_review = 0

        for review_card in review_cards:
            rating = self._extract_rating(review_card)
            review_date = self._extract_date(review_card)
            review_text = self._extract_review_text(review_card)

            if rating is None:
                missing_rating += 1
            if review_date is None:
                missing_date += 1
            if review_text is None:
                missing_review += 1

            if rating is None or review_date is None or review_text is None:
                continue

            parsed_reviews.append(
                {
                    "rating": rating,
                    "date": review_date,
                    "review": review_text,
                }
            )

        self.logger.info(
            "%d페이지 분석: 카드 %d개, 유효 리뷰 %d개, "
            "별점 누락 %d개, 날짜 누락 %d개, 본문 누락 %d개",
            page_number,
            len(review_cards),
            len(parsed_reviews),
            missing_rating,
            missing_date,
            missing_review,
        )
        return parsed_reviews

    def _build_page_url(self, page_number: int) -> str:
        """페이지 번호가 포함된 Allocine 리뷰 URL을 반환한다."""
        return f"{self.base_url}?page={page_number}"

    def _load_page(self, page_number: int) -> Optional[str]:
        """리뷰 페이지를 재시도와 함께 불러온다.

        Args:
            page_number: 불러올 리뷰 페이지 번호.

        Returns:
            정상적으로 로드한 HTML. 모든 시도가 실패하면 ``None``.

        Raises:
            RuntimeError: ``start_browser()``가 호출되지 않은 경우.
        """
        if self.driver is None:
            raise RuntimeError("Chrome WebDriver가 생성되지 않았습니다.")

        page_url = self._build_page_url(page_number)
        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(
                    "%d페이지 접속 시도 %d/%d: %s",
                    page_number,
                    attempt,
                    self.max_retries,
                    page_url,
                )
                self.driver.get(page_url)
                WebDriverWait(self.driver, 20).until(
                    EC.presence_of_element_located(
                        (By.CSS_SELECTOR, ".review-card")
                    )
                )
                html = self.driver.page_source

                blocked_markers = (
                    "Access denied",
                    "Just a moment",
                    "cf-chl-",
                )
                if any(marker.lower() in html.lower() for marker in blocked_markers):
                    self.logger.warning(
                        "%d페이지에서 접근 제한 화면을 감지했습니다.",
                        page_number,
                    )
                    time.sleep(3 * attempt)
                    continue

                if len(html) < 1000:
                    self.logger.warning(
                        "%d페이지 HTML이 비정상적으로 짧습니다.",
                        page_number,
                    )
                    time.sleep(2 * attempt)
                    continue

                return html

            except TimeoutException:
                self.logger.warning(
                    "%d페이지 로딩 시간이 초과되었습니다. 시도 %d/%d",
                    page_number,
                    attempt,
                    self.max_retries,
                )
                html = self.driver.page_source
                if ".review-card" in html or "review-card" in html:
                    return html
            except WebDriverException as error:
                self.logger.warning(
                    "%d페이지 접속 중 WebDriver 오류: %s",
                    page_number,
                    error,
                )

            time.sleep(2 * attempt)

        return None

    def _save_checkpoint(self) -> None:
        """현재까지 수집한 리뷰를 중간 CSV 파일에 덮어쓴다."""
        if not self.reviews:
            return

        os.makedirs(self.output_dir, exist_ok=True)
        checkpoint_path = os.path.join(
            self.output_dir,
            "reviews_allocine_checkpoint.csv",
        )
        dataframe = pd.DataFrame(
            self.reviews,
            columns=["rating", "date", "review"],
        )
        dataframe.to_csv(
            checkpoint_path,
            index=False,
            encoding="utf-8-sig",
        )

    def _save_debug_html(self, html: str, page_number: int) -> None:
        """선택자 오류를 확인할 수 있도록 실패 페이지 HTML을 저장한다."""
        os.makedirs(self.output_dir, exist_ok=True)
        debug_path = os.path.join(
            self.output_dir,
            f"allocine_debug_page_{page_number}.html",
        )
        with open(debug_path, "w", encoding="utf-8") as debug_file:
            debug_file.write(html)
        self.logger.error("디버그 HTML을 저장했습니다: %s", debug_path)

    def scrape_reviews(self) -> None:
        """Allocine에서 조건을 충족하는 리뷰를 최소 500개 수집한다.

        페이지 사이에 임의의 대기 시간을 두어 서버에 과도한 요청을 보내지
        않는다. 페이지별 결과는 중간 CSV에 저장하며, 같은 별점·날짜·본문을
        가진 리뷰는 중복으로 추가하지 않는다. 브라우저는 성공 여부와 관계없이
        항상 종료한다.

        Raises:
            RuntimeError: 리뷰를 한 개도 수집하지 못한 경우.
        """
        self.start_browser()
        if self.driver is None:
            raise RuntimeError("Chrome WebDriver가 생성되지 않았습니다.")

        seen_reviews: Set[Tuple[str, str, str]] = set()
        consecutive_empty_pages = 0

        try:
            for page_number in range(1, self.max_pages + 1):
                if len(self.reviews) >= self.target_count:
                    break

                html = self._load_page(page_number)
                if html is None:
                    self.logger.error(
                        "%d페이지를 모든 재시도 후에도 불러오지 못했습니다.",
                        page_number,
                    )
                    continue

                page_reviews = self._parse_page(html, page_number)
                if not page_reviews:
                    consecutive_empty_pages += 1
                    self._save_debug_html(html, page_number)
                    if consecutive_empty_pages >= 3:
                        self.logger.warning(
                            "유효 리뷰가 없는 페이지가 3회 연속 나타나 "
                            "크롤링을 종료합니다."
                        )
                        break
                    time.sleep(random.uniform(2.0, 4.0))
                    continue

                consecutive_empty_pages = 0
                for review in page_reviews:
                    review_key = (
                        review["rating"],
                        review["date"],
                        review["review"],
                    )
                    if review_key in seen_reviews:
                        continue

                    seen_reviews.add(review_key)
                    self.reviews.append(review)
                    if len(self.reviews) >= self.target_count:
                        break

                self.logger.info(
                    "현재까지 총 %d개의 리뷰를 수집했습니다.",
                    len(self.reviews),
                )
                self._save_checkpoint()
                time.sleep(random.uniform(1.5, 3.0))
        finally:
            if self.driver is not None:
                try:
                    self.driver.quit()
                except WebDriverException:
                    pass
                self.driver = None
                self.logger.info("Chrome WebDriver를 종료했습니다.")

        if not self.reviews:
            raise RuntimeError(
                "Allocine 리뷰를 한 개도 수집하지 못했습니다. "
                "로그와 allocine_debug_page_*.html을 확인하세요."
            )

        if len(self.reviews) < self.target_count:
            self.logger.warning(
                "목표는 %d개이지만 %d개만 수집했습니다.",
                self.target_count,
                len(self.reviews),
            )
        else:
            self.logger.info("목표 리뷰 수 %d개를 수집했습니다.", self.target_count)

    def save_to_database(self) -> None:
        """수집 결과를 ``reviews_allocine.csv``로 저장하고 검증한다.

        빈 필드와 중복 행을 제거한 뒤 정확히 500개까지 저장한다. 최종 데이터가
        과제 최소 조건인 500개에 미달하면 조용히 성공한 것처럼 끝내지 않고
        예외를 발생시킨다.

        Raises:
            RuntimeError: 저장할 리뷰가 없거나 최종 유효 리뷰가 500개 미만인 경우.
        """
        if not self.reviews:
            raise RuntimeError(
                "저장할 리뷰가 없습니다. scrape_reviews()를 먼저 실행하세요."
            )

        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, "reviews_allocine.csv")
        dataframe = pd.DataFrame(
            self.reviews,
            columns=["rating", "date", "review"],
        )
        dataframe = dataframe.dropna(subset=["rating", "date", "review"])

        for column in ("rating", "date", "review"):
            dataframe[column] = dataframe[column].astype(str).str.strip()

        dataframe = dataframe[
            (dataframe["rating"] != "")
            & (dataframe["date"] != "")
            & (dataframe["review"] != "")
        ]
        dataframe = dataframe.drop_duplicates(
            subset=["rating", "date", "review"]
        ).head(self.target_count)
        dataframe.to_csv(
            output_path,
            index=False,
            encoding="utf-8-sig",
        )

        self.logger.info(
            "%d개의 리뷰를 저장했습니다: %s",
            len(dataframe),
            output_path,
        )
        if len(dataframe) < self.target_count:
            raise RuntimeError(
                f"최종 유효 리뷰가 {len(dataframe)}개입니다. "
                f"과제 최소 조건인 {self.target_count}개를 충족하지 못했습니다."
            )