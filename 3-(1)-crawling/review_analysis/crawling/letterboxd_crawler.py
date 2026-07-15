import os
import re
import time
from typing import Dict, List, Optional, Set, Tuple
import random
import math

import pandas as pd
from bs4 import BeautifulSoup, Tag
from selenium import webdriver
from selenium.common.exceptions import (
    TimeoutException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

from review_analysis.crawling.base_crawler import BaseCrawler
from utils.logger import setup_logger


class LetterboxdCrawler(BaseCrawler):
    """Letterboxd에서 영화 리뷰를 수집하는 크롤러.

    대상 영화:
        Avatar: The Way of Water (2022)

    수집 항목:
        - rating: 사용자가 부여한 5점 만점 별점
        - date: 리뷰 날짜
        - review: 리뷰 본문

    별점, 날짜, 리뷰 내용이 모두 존재하는 리뷰만 저장한다.
    """

    def __init__(self, output_dir: str):
        """Letterboxd 크롤러를 초기화한다.

        Args:
            output_dir:
                결과 CSV 파일을 저장할 디렉터리 경로.
        """
        super().__init__(output_dir)

        self.base_url = (
            "https://letterboxd.com/"
            "film/avatar-the-way-of-water/reviews/"
        )

        self.target_count = 500
        self.max_pages = 150
        self.max_retries = 1
        self.request_interval = 4 + (random.betavariate(2.4, 3.2) - 2.4/5.6) + (random.uniform(0, 1.34)**2 - 1.34**2/3) + random.choice((-1, 1)) * math.log(random.uniform(3, 10)) * math.sqrt(random.uniform(0.1, 0.3)) * random.uniform(0.2, 0.6) + random.gauss(0, 0.18) + random.triangular(-0.25, 0.25, 0) + (7 if (p := random.random()) < 0.1 else 3 if p < 0.3 else 0)

        self.driver: Optional[WebDriver] = None
        self.reviews: List[Dict[str, str]] = []

        self.logger = setup_logger("letterboxd_crawler.log")

    def start_browser(self) -> None:
        """Headless Chrome WebDriver를 실행한다.

        Raises:
            RuntimeError:
                Chrome WebDriver를 실행하지 못한 경우.
        """
        options = Options()

        # 이미지와 광고가 모두 로드될 때까지 기다리지 않고
        # DOM 접근이 가능해지면 driver.get()을 반환한다.
        options.page_load_strategy = "eager"

        options.add_argument("--headless=new")
        options.add_argument("--disable-gpu")
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=en-US")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")

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
            self.logger.exception(
                "Chrome WebDriver 실행 중 오류가 발생했습니다."
            )

            raise RuntimeError(
                "Chrome WebDriver를 실행할 수 없습니다."
            ) from error

    @staticmethod
    def _find_review_elements(
        soup: BeautifulSoup,
    ) -> List[Tag]:
        """현재 페이지에서 개별 리뷰 요소를 찾는다.

        Args:
            soup:
                현재 페이지의 BeautifulSoup 객체.

        Returns:
            개별 리뷰를 나타내는 HTML 요소 목록.
        """
        selectors = [
            ".production-viewing.-viewing",
            "article.production-viewing",
            "div.production-viewing",
            "li.production-viewing",
            "[data-review-id]",
        ]

        for selector in selectors:
            elements = soup.select(selector)

            valid_elements = [
                element
                for element in elements
                if isinstance(element, Tag)
                and element.select_one(
                    ".js-review-body, .body-text.-prose"
                )
                is not None
            ]

            if valid_elements:
                return valid_elements

        # production-viewing 구조가 변경됐을 경우
        # 리뷰 본문을 기준으로 가장 가까운 부모 요소를 찾는다.
        fallback_elements: List[Tag] = []

        for body in soup.select(
            ".js-review-body, .body-text.-prose"
        ):
            if not isinstance(body, Tag):
                continue

            parent = body.find_parent(
                ["article", "li", "div"],
                class_=lambda value: (
                    value is not None
                    and (
                        "production-viewing" in value
                        or "js-review" in value
                    )
                ),
            )

            if isinstance(parent, Tag):
                fallback_elements.append(parent)

        return fallback_elements

    @staticmethod
    def _normalise_rating(
        raw_value: float,
    ) -> Optional[str]:
        """별점 숫자를 5점 만점 문자열로 변환한다.

        Args:
            raw_value:
                HTML에서 추출한 별점 숫자.

        Returns:
            0.5부터 5.0까지의 별점 문자열.
            유효하지 않은 값이면 ``None``.
        """
        rating = raw_value

        # Letterboxd 내부 별점은 1~10 척도로 저장되는 경우가 있다.
        if rating > 5:
            rating /= 2

        if rating < 0.5 or rating > 5:
            return None

        # 0.5 단위로 정규화한다.
        rating = round(rating * 2) / 2

        return f"{rating:.1f}"

    @classmethod
    def _extract_rating(
        cls,
        review_element: Tag,
    ) -> Optional[str]:
        """리뷰 요소에서 별점을 추출한다.

        다음 표현 방식을 순서대로 처리한다.

        1. data-rating 속성
        2. rated-N CSS 클래스
        3. SVG use의 href="#icon-rating-N"
        4. title 또는 aria-label 텍스트
        5. 별 문자(★★★★½)

        Args:
            review_element:
                개별 리뷰 HTML 요소.

        Returns:
            5점 만점 별점 문자열.
            별점이 없으면 ``None``.
        """
        rating_element = review_element.select_one(
            ".inline-rating, "
            ".glyph.-rating, "
            "[data-rating], "
            "[class*='rated-']"
        )

        if rating_element is None:
            return None

        # 1. data-rating 속성
        for element in [rating_element, *rating_element.find_all(True)]:
            data_rating = element.get("data-rating")

            if isinstance(data_rating, str):
                try:
                    parsed = cls._normalise_rating(
                        float(data_rating.strip())
                    )

                    if parsed is not None:
                        return parsed

                except ValueError:
                    pass

        # 2. rated-N 클래스
        for element in [rating_element, *rating_element.find_all(True)]:
            classes = element.get("class", [])

            if isinstance(classes, str):
                classes = classes.split()

            for class_name in classes:
                match = re.search(
                    r"(?:rated|rating)[-_]?(\d+)",
                    class_name,
                    re.IGNORECASE,
                )

                if match is not None:
                    parsed = cls._normalise_rating(
                        float(match.group(1))
                    )

                    if parsed is not None:
                        return parsed

        # 3. SVG <use href="#icon-rating-7"> 형식
        for use_element in rating_element.select("use"):
            href_values = [
                use_element.get("href"),
                use_element.get("xlink:href"),
            ]

            for href in href_values:
                if not isinstance(href, str):
                    continue

                match = re.search(
                    r"(?:icon-)?rating[-_]?(\d+)",
                    href,
                    re.IGNORECASE,
                )

                if match is not None:
                    parsed = cls._normalise_rating(
                        float(match.group(1))
                    )

                    if parsed is not None:
                        return parsed

        # 4. title, aria-label 등 접근성 텍스트
        text_candidates: List[str] = []

        for element in [rating_element, *rating_element.find_all(True)]:
            for attribute_name in [
                "title",
                "aria-label",
                "data-original-title",
            ]:
                attribute_value = element.get(attribute_name)

                if (
                    isinstance(attribute_value, str)
                    and attribute_value.strip()
                ):
                    text_candidates.append(
                        attribute_value.strip()
                    )

        visible_text = rating_element.get_text(
            " ",
            strip=True,
        )

        if visible_text:
            text_candidates.append(visible_text)

        for candidate in text_candidates:
            # 예: Rated 4.5 out of 5
            match = re.search(
                r"([0-5](?:\.[05])?)"
                r"\s*(?:out\s+of\s+5|stars?)",
                candidate,
                re.IGNORECASE,
            )

            if match is not None:
                parsed = cls._normalise_rating(
                    float(match.group(1))
                )

                if parsed is not None:
                    return parsed

            # 예: rating-9
            match = re.search(
                r"(?:rating|rated)[-_: ]+(\d+)",
                candidate,
                re.IGNORECASE,
            )

            if match is not None:
                parsed = cls._normalise_rating(
                    float(match.group(1))
                )

                if parsed is not None:
                    return parsed

        # 5. 별 문자: ★★★★½
        combined_text = " ".join(text_candidates)

        star_match = re.search(
            r"(★+)(½)?",
            combined_text,
        )

        if star_match is not None:
            full_stars = len(star_match.group(1))
            half_star = 0.5 if star_match.group(2) else 0.0

            parsed = cls._normalise_rating(
                full_stars + half_star
            )

            if parsed is not None:
                return parsed

        return None

    @staticmethod
    def _extract_date(
        review_element: Tag,
    ) -> Optional[str]:
        """리뷰 요소에서 날짜를 추출한다.

        Args:
            review_element:
                개별 리뷰 HTML 요소.

        Returns:
            날짜 문자열.
            날짜가 없으면 ``None``.
        """
        date_selectors = [
            "time[datetime]",
            ".date time",
            ".date",
            ".timestamp",
            "[data-viewing-date]",
        ]

        for selector in date_selectors:
            date_element = review_element.select_one(
                selector
            )

            if date_element is None:
                continue

            for attribute_name in [
                "datetime",
                "data-viewing-date",
                "title",
            ]:
                attribute_value = date_element.get(
                    attribute_name
                )

                if (
                    isinstance(attribute_value, str)
                    and attribute_value.strip()
                ):
                    value = attribute_value.strip()

                    # ISO datetime이면 날짜 부분만 저장
                    iso_match = re.search(
                        r"\d{4}-\d{2}-\d{2}",
                        value,
                    )

                    if iso_match is not None:
                        return iso_match.group(0)

                    return value

            displayed_text = date_element.get_text(
                " ",
                strip=True,
            )

            if displayed_text:
                return displayed_text

        # 부모 전체 텍스트에서 날짜를 찾는 최후 수단
        full_text = review_element.get_text(
            " ",
            strip=True,
        )

        patterns = [
            r"\b\d{1,2}\s+"
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+\d{4}\b",
            r"\b\d{4}-\d{2}-\d{2}\b",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                full_text,
                re.IGNORECASE,
            )

            if match is not None:
                return match.group(0)

        return None

    @staticmethod
    def _extract_review_text(
        review_element: Tag,
    ) -> Optional[str]:
        """리뷰 요소에서 리뷰 본문을 추출한다.

        Args:
            review_element:
                개별 리뷰 HTML 요소.

        Returns:
            공백을 정리한 리뷰 본문.
            본문이 없으면 ``None``.
        """
        text_element = review_element.select_one(
            ".js-review-body, "
            ".body-text.-prose, "
            ".body-text, "
            "[data-review-text]"
        )

        if text_element is None:
            return None

        # 원본 soup을 변경하지 않기 위해 다시 파싱한다.
        copied_soup = BeautifulSoup(
            str(text_element),
            "html.parser",
        )

        for unnecessary in copied_soup.select(
            "script, style, svg, button, "
            ".translate-button, .js-translate"
        ):
            unnecessary.decompose()

        review_text = copied_soup.get_text(
            " ",
            strip=True,
        )

        # Letterboxd 번역 UI의 불필요한 텍스트 제거
        review_text = re.sub(
            r"\bTranslate\b.*$",
            "",
            review_text,
            flags=re.IGNORECASE,
        )

        review_text = re.sub(
            r"\s+",
            " ",
            review_text,
        ).strip()

        if not review_text:
            return None

        return review_text

    def _parse_page(
        self,
        html: str,
        page_number: int,
    ) -> List[Dict[str, str]]:
        """현재 페이지 HTML에서 리뷰를 추출한다.

        Args:
            html:
                현재 페이지 전체 HTML.
            page_number:
                로그에 표시할 페이지 번호.

        Returns:
            조건을 충족한 리뷰 목록.
        """
        soup = BeautifulSoup(
            html,
            "html.parser",
        )

        review_elements = self._find_review_elements(
            soup
        )

        missing_rating = 0
        missing_date = 0
        missing_review = 0

        parsed_reviews: List[Dict[str, str]] = []

        for review_element in review_elements:
            rating = self._extract_rating(
                review_element
            )
            review_date = self._extract_date(
                review_element
            )
            review_text = self._extract_review_text(
                review_element
            )

            if rating is None:
                missing_rating += 1

            if review_date is None:
                missing_date += 1

            if review_text is None:
                missing_review += 1

            if (
                rating is None
                or review_date is None
                or review_text is None
            ):
                continue

            parsed_reviews.append(
                {
                    "rating": rating,
                    "date": review_date,
                    "review": review_text,
                }
            )

        self.logger.info(
            "%d페이지 분석: 리뷰 요소 %d개, "
            "유효 리뷰 %d개, 별점 누락 %d개, "
            "날짜 누락 %d개, 본문 누락 %d개",
            page_number,
            len(review_elements),
            len(parsed_reviews),
            missing_rating,
            missing_date,
            missing_review,
        )

        return parsed_reviews

    def _build_page_url(
        self,
        page_number: int,
    ) -> str:
        """페이지 번호에 대응하는 리뷰 URL을 생성한다."""
        if page_number == 1:
            return self.base_url

        return f"{self.base_url}page/{page_number}/"

    def _load_page(
        self,
        page_url: str,
        page_number: int,
    ) -> Optional[str]:
        """Letterboxd 페이지를 불러와 HTML을 반환한다.

        특정 리뷰 selector를 Selenium에서 기다리지 않고,
        body 요소가 생성되면 페이지 소스를 가져온다. 이후 실제 리뷰 존재
        여부는 BeautifulSoup 파싱 단계에서 판단한다.

        Args:
            page_url: 접속할 Letterboxd 리뷰 페이지 URL.
            page_number: 현재 페이지 번호.

        Returns:
            정상적으로 가져온 페이지 HTML.
            모든 재시도가 실패하면 None.
        """
        if self.driver is None:
            raise RuntimeError(
                "Chrome WebDriver가 생성되지 않았습니다."
            )

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

                # 리뷰 selector가 아니라 기본 body만 기다린다.
                WebDriverWait(self.driver, 10).until(
                    EC.presence_of_element_located(
                        (By.TAG_NAME, "body")
                    )
                )

                # JavaScript가 본문을 반영할 짧은 시간을 준다.
                time.sleep(2)

                html = self.driver.page_source

                if not html or len(html) < 1000:
                    self.logger.warning(
                        "%d페이지 HTML이 비정상적으로 짧습니다.",
                        page_number,
                    )
                    time.sleep(2 * attempt)
                    continue

                blocked_markers = [
                    "Just a moment",
                    "Access denied",
                    "cf-chl-",
                    "Enable JavaScript and cookies",
                ]

                if any(marker in html for marker in blocked_markers):
                    self.logger.warning(
                        "%d페이지에서 접근 제한 화면이 감지되었습니다.",
                        page_number,
                    )
                    time.sleep(4 * attempt)
                    continue

                # 리뷰 selector 검사는 BeautifulSoup 단계에 맡긴다.
                return html

            except TimeoutException:
                self.logger.warning(
                    "%d페이지 body 로딩 시간이 초과되었습니다. "
                    "시도 %d/%d",
                    page_number,
                    attempt,
                    self.max_retries,
                )

                # timeout이어도 이미 HTML이 들어왔을 수 있으므로 반환한다.
                html = self.driver.page_source

                if html and len(html) >= 1000:
                    return html

            except WebDriverException as error:
                self.logger.warning(
                    "%d페이지 접속 오류: %s",
                    page_number,
                    error,
                )

            time.sleep(2 * attempt)

        return None
        
    def _save_checkpoint(self) -> None:
        """현재까지 수집한 리뷰를 중간 CSV로 저장한다."""
        if not self.reviews:
            return

        os.makedirs(
            self.output_dir,
            exist_ok=True,
        )

        checkpoint_path = os.path.join(
            self.output_dir,
            "reviews_letterboxd_checkpoint.csv",
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

    def _save_debug_html(
        self,
        html: str,
        page_number: int,
    ) -> None:
        """분석용 HTML을 저장한다."""
        os.makedirs(
            self.output_dir,
            exist_ok=True,
        )

        debug_path = os.path.join(
            self.output_dir,
            f"letterboxd_debug_page_{page_number}.html",
        )

        with open(
            debug_path,
            "w",
            encoding="utf-8",
        ) as debug_file:
            debug_file.write(html)

        self.logger.error(
            "디버그 HTML을 저장했습니다: %s",
            debug_path,
        )

    def scrape_reviews(self) -> None:
        """Letterboxd 리뷰를 500개 이상 수집한다.

        Raises:
            RuntimeError:
                리뷰를 한 개도 수집하지 못한 경우.
        """
        self.start_browser()

        if self.driver is None:
            raise RuntimeError(
                "Chrome WebDriver가 생성되지 않았습니다."
            )

        seen_reviews: Set[
            Tuple[str, str, str]
        ] = set()

        consecutive_empty_pages = 0

        try:
            for page_number in range(
                1,
                self.max_pages + 1,
            ):
                if (
                    len(self.reviews)
                    >= self.target_count
                ):
                    break

                page_url = self._build_page_url(
                    page_number
                )

                html = self._load_page(
                    page_url,
                    page_number,
                )

                if html is None:
                    self.logger.error(
                        "%d페이지를 불러오지 못했습니다.",
                        page_number,
                    )
                    continue

                page_reviews = self._parse_page(
                    html,
                    page_number,
                )

                if not page_reviews:
                    consecutive_empty_pages += 1

                    self._save_debug_html(
                        html,
                        page_number,
                    )

                    self.logger.warning(
                        "%d페이지에서 유효 리뷰를 "
                        "찾지 못했습니다.",
                        page_number,
                    )

                    # 일시적인 한 페이지 실패 때문에
                    # 전체 크롤링을 즉시 종료하지 않는다.
                    if consecutive_empty_pages >= 3:
                        self.logger.warning(
                            "연속으로 빈 페이지가 3개 발생하여 "
                            "마지막 페이지로 판단합니다."
                        )
                        break

                    time.sleep(
                        self.request_interval
                    )
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

                    if (
                        len(self.reviews)
                        >= self.target_count
                    ):
                        break

                self.logger.info(
                    "현재까지 총 %d개의 리뷰를 "
                    "수집했습니다.",
                    len(self.reviews),
                )

                self._save_checkpoint()

                time.sleep(
                    self.request_interval
                )

        finally:
            if self.driver is not None:
                try:
                    self.driver.quit()

                except WebDriverException:
                    pass

                self.driver = None

                self.logger.info(
                    "Chrome WebDriver를 종료했습니다."
                )

        if not self.reviews:
            raise RuntimeError(
                "리뷰를 한 개도 수집하지 못했습니다. "
                "저장된 debug HTML과 로그를 확인하세요."
            )

        if len(self.reviews) < self.target_count:
            self.logger.warning(
                "목표는 %d개이지만 %d개만 수집했습니다.",
                self.target_count,
                len(self.reviews),
            )

        else:
            self.logger.info(
                "목표 리뷰 수 %d개를 수집했습니다.",
                self.target_count,
            )

    def save_to_database(self) -> None:
        """수집한 리뷰를 최종 CSV 파일로 저장한다.

        Raises:
            RuntimeError:
                저장할 리뷰가 없는 경우.
        """
        if not self.reviews:
            raise RuntimeError(
                "저장할 리뷰가 없습니다. "
                "scrape_reviews()를 먼저 실행해야 합니다."
            )

        os.makedirs(
            self.output_dir,
            exist_ok=True,
        )

        output_path = os.path.join(
            self.output_dir,
            "reviews_letterboxd.csv",
        )

        dataframe = pd.DataFrame(
            self.reviews,
            columns=["rating", "date", "review"],
        )

        dataframe = dataframe.dropna(
            subset=["rating", "date", "review"]
        )

        dataframe["review"] = (
            dataframe["review"]
            .astype(str)
            .str.strip()
        )

        dataframe = dataframe[
            dataframe["review"] != ""
        ]

        dataframe = dataframe.drop_duplicates(
            subset=["rating", "date", "review"]
        )

        dataframe = dataframe.head(
            self.target_count
        )

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
                f"최종 저장 리뷰가 {len(dataframe)}개입니다. "
                f"과제 최소 조건인 {self.target_count}개를 "
                "충족하지 못했습니다."
            )