import os
import time
from datetime import datetime
from typing import Dict, List, Optional, Set
from urllib.parse import quote

import pandas as pd
from bs4 import BeautifulSoup, NavigableString, Tag
from selenium import webdriver
from selenium.common.exceptions import (
    ElementClickInterceptedException,
    ElementNotInteractableException,
    WebDriverException,
)
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.action_chains import ActionChains
from selenium.webdriver.common.by import By

from review_analysis.crawling.base_crawler import BaseCrawler
from utils.logger import setup_logger


class NaverCrawler(BaseCrawler):
    """네이버 통합검색의 영화 관람평(리뷰)을 수집하는 크롤러.

    대상 영화:
        Avatar: The Way of Water (2022) — 네이버 영화 코드 74977

    수집 항목:
        - rating: 10점 만점 별점
        - date: 리뷰 작성 일시
        - review: 리뷰 본문

    별점, 날짜, 리뷰 내용이 모두 존재하는 리뷰만 저장한다.

    구현 노트:
        네이버 통합검색의 관람평 목록은 무한 스크롤 방식이다. 목록을 담은
        컨테이너(``div.lego_review_list_scroller``)를 끝까지 스크롤하면
        내부적으로 opaque한 ``enc_pageid`` 파라미터를 쓰는 API가 호출되어
        추가 리뷰가 로드되는데, 이 파라미터는 직접 구성하기 어렵다.
        그래서 이 값을 흉내내지 않고, Selenium으로 실제 스크롤 이벤트를
        발생시켜 페이지 자체의 JS가 자연스럽게 추가 리뷰를 불러오게 한다.

        각 리뷰는 ``<li class="area_card_item">`` 로 렌더링되며, 다음
        data 속성에 필요한 정보가 이미 다 들어있다.

            - data-movie-code: 영화 코드(다른 영화 리뷰가 섞이지 않았는지
              검증하는 용도)
            - data-rating-id: 리뷰 고유 id (중복 제거용)
            - data-report-title: 리뷰 본문 전체. "더보기" 버튼은 CSS로
              긴 텍스트를 시각적으로만 접어두는 것이라, 이 속성에는
              접힘과 무관하게 항상 전체 텍스트가 들어있다.
            - data-report-time: 작성 일시 ("YYYYMMDD HH:MM" 형식)
            - data-report-writer-id: 작성자 닉네임

        별점(10점 만점)은 별도 속성이 아니라
        ``div.area_title_box .lego_movie_pure_star .area_text_box``
        안의 텍스트 노드(예: "10")로 렌더링되어 있어 별도로 파싱한다.
    """

    MOVIE_CODE = "74977"
    REVIEW_CARD_SELECTOR = "li.area_card_item, li.area_card._item"
    REVIEW_MOVIE_CARD_SELECTOR = (
        "li.area_card_item[data-movie-code='{movie_code}'], "
        "li.area_card._item[data-movie-code='{movie_code}']"
    )
    REVIEW_CONTAINER_SELECTOR = (
        "div.lego_review_list_scroller, div.lego_review_list._scroller"
    )
    # "평점"까지 붙여 관람평 탭으로 바로 진입하는 URL은 자동화 세션에서
    # 위젯이 제대로 초기화되지 않는 경우가 있어, 영화 개요("전체" 탭)
    # 페이지로 들어간 뒤 "관람평" 탭을 실제로 클릭해 진입한다.
    SEARCH_URL = "https://search.naver.com/search.naver?query=" + quote(
        "아바타 물의 길"
    )

    def __init__(self, output_dir: str):
        """네이버 크롤러를 초기화한다.

        Args:
            output_dir: 크롤링 결과 CSV 파일을 저장할 디렉터리 경로.
        """
        super().__init__(output_dir)

        self.target_count = 500
        self.max_scroll_attempts = 400
        self.max_stall_attempts = 8
        self.scroll_pause = 1.2

        self.driver: Optional[WebDriver] = None
        self.reviews: List[Dict[str, str]] = []

        self.logger = setup_logger("naver_crawler.log")

    def start_browser(self) -> None:
        """Headless Chrome WebDriver를 실행한다.

        Raises:
            RuntimeError: Chrome WebDriver를 실행하지 못한 경우.
        """
        options = Options()

        options.page_load_strategy = "eager"

        # 네이버가 headless 브라우저에서는 관람평 위젯을 렌더링하지 않는
        # 것으로 확인되어, 화면에 실제 창을 띄우는 방식으로 실행한다.
        options.add_argument("--no-sandbox")
        options.add_argument("--disable-dev-shm-usage")
        options.add_argument("--window-size=1920,1080")
        options.add_argument("--lang=ko-KR")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-popup-blocking")

        options.add_argument(
            "--user-agent="
            "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/126.0.0.0 Safari/537.36"
        )

        # 네이버 등 일부 사이트가 자동화 브라우저(webdriver=true)를 감지해
        # 위젯을 아예 렌더링하지 않는 경우가 있어, 자동화 흔적을 최대한
        # 숨긴다.
        options.add_argument("--disable-blink-features=AutomationControlled")
        options.add_experimental_option(
            "excludeSwitches", ["enable-automation"]
        )
        options.add_experimental_option("useAutomationExtension", False)

        try:
            self.driver = webdriver.Chrome(options=options)
            self.driver.set_page_load_timeout(30)

            try:
                self.driver.execute_cdp_cmd(
                    "Page.addScriptToEvaluateOnNewDocument",
                    {
                        "source": (
                            "Object.defineProperty(navigator, 'webdriver', "
                            "{get: () => undefined});"
                        )
                    },
                )
            except WebDriverException:
                self.logger.warning(
                    "navigator.webdriver 은폐 스크립트 주입에 실패했습니다."
                )

            self.logger.info("Chrome WebDriver를 실행했습니다.")

        except WebDriverException as error:
            self.logger.exception(
                "Chrome WebDriver 실행 중 오류가 발생했습니다."
            )
            raise RuntimeError(
                "Chrome WebDriver를 실행할 수 없습니다."
            ) from error

    @staticmethod
    def _extract_rating(card: Tag) -> Optional[str]:
        """리뷰 카드에서 별점 텍스트를 추출한다.

        Args:
            card: ``li.area_card_item`` 태그.

        Returns:
            "10" 같은 별점 문자열. 찾지 못하면 ``None``.
        """
        text_box = card.select_one(
            "div.area_title_box .lego_movie_pure_star .area_text_box"
        )
        if text_box is None:
            return None

        for content in reversed(text_box.contents):
            if isinstance(content, NavigableString):
                candidate = str(content).strip()
                if candidate:
                    return candidate

        return None

    @staticmethod
    def _format_date(raw_time: Optional[str]) -> Optional[str]:
        """``20221215 17:14`` 형태를 ``2022-12-15 17:14``로 변환한다.

        Args:
            raw_time: ``data-report-time`` 속성 원본 값.

        Returns:
            보기 좋게 변환된 날짜 문자열. 파싱할 수 없으면 원본 그대로
            반환하고, 값 자체가 없으면 ``None``을 반환한다.
        """
        if not raw_time:
            return None

        try:
            parsed = datetime.strptime(raw_time.strip(), "%Y%m%d %H:%M")
            return parsed.strftime("%Y-%m-%d %H:%M")
        except ValueError:
            return raw_time.strip()

    def _extract_review(self, card: Tag) -> Optional[Dict[str, str]]:
        """리뷰 카드 하나를 rating/date/review/reviewer로 변환한다.

        Args:
            card: ``li.area_card_item`` 태그.

        Returns:
            rating_id/rating/date/review/reviewer 키를 가진 딕셔너리.
            다른 영화의 리뷰이거나 필수 필드가 없으면 ``None``.
        """
        if card.get("data-movie-code") != self.MOVIE_CODE:
            return None

        rating_id = card.get("data-rating-id")
        rating = self._extract_rating(card)
        date_text = self._format_date(card.get("data-report-time"))

        review_text = str(card.get("data-report-title") or "").strip()
        if not review_text:
            desc = card.select_one("span.desc_text")
            if desc is not None:
                review_text = desc.get_text(" ", strip=True)

        if not rating_id or not rating or not date_text or not review_text:
            return None

        return {
            "rating_id": str(rating_id),
            "rating": rating,
            "date": date_text,
            "review": review_text,
            "reviewer": str(card.get("data-report-writer-id") or ""),
        }

    def _try_locate_review_frame(self) -> bool:
        """리뷰 카드(``li.area_card_item``)가 있는 프레임으로 전환한다.

        최상위 문서에 있으면 전환 없이 True를 반환하고, 어떤 iframe
        안에 있으면 그 iframe으로 전환한 채로 True를 반환한다. 어디에도
        없으면 최상위 문서로 되돌려놓고 False를 반환한다.

        Returns:
            리뷰 카드를 찾아 그 프레임으로 전환했으면 True.
        """
        if self.driver is None:
            raise RuntimeError("Chrome WebDriver가 생성되지 않았습니다.")

        self.driver.switch_to.default_content()

        if self.driver.find_elements(
            By.CSS_SELECTOR, self.REVIEW_CARD_SELECTOR
        ):
            return True

        iframes = self.driver.find_elements(By.TAG_NAME, "iframe")

        for idx, iframe in enumerate(iframes):
            self.driver.switch_to.default_content()

            try:
                self.driver.switch_to.frame(iframe)
            except WebDriverException:
                continue

            if self.driver.find_elements(
                By.CSS_SELECTOR, self.REVIEW_CARD_SELECTOR
            ):
                self.logger.info("%d번째 iframe에서 리뷰 카드를 찾았습니다.", idx)
                return True

        self.driver.switch_to.default_content()
        return False

    def _wait_for_review_frame(self, timeout: float = 25.0) -> bool:
        """리뷰 카드가 나타날 때까지(최상위 문서든 iframe이든) 기다린다.

        Args:
            timeout: 최대 대기 시간(초).

        Returns:
            제한 시간 안에 리뷰 카드를 찾았으면 True.
        """
        deadline = time.time() + timeout

        while time.time() < deadline:
            if self._try_locate_review_frame():
                return True
            time.sleep(1.0)

        return False

    def _log_debug_snapshot(self) -> None:
        """리뷰 카드를 못 찾았을 때 디버깅에 필요한 정보를 로그로 남긴다."""
        if self.driver is None:
            return

        self.driver.switch_to.default_content()

        self.logger.error("페이지 title=%r", self.driver.title)

        iframes = self.driver.find_elements(By.TAG_NAME, "iframe")
        self.logger.error("페이지 내 iframe 개수: %d", len(iframes))

        os.makedirs(self.output_dir, exist_ok=True)

        top_debug_path = os.path.join(
            self.output_dir, "naver_debug_page.html"
        )
        with open(top_debug_path, "w", encoding="utf-8") as debug_file:
            debug_file.write(self.driver.page_source)
        self.logger.error("최상위 문서 HTML 저장: %s", top_debug_path)

        for idx, iframe in enumerate(iframes):
            self.driver.switch_to.default_content()
            try:
                src = iframe.get_attribute("src")
            except WebDriverException:
                src = "(속성 조회 실패)"
            self.logger.error("iframe[%d] src=%s", idx, src)

            try:
                self.driver.switch_to.frame(iframe)
                iframe_debug_path = os.path.join(
                    self.output_dir, f"naver_debug_iframe_{idx}.html"
                )
                with open(
                    iframe_debug_path, "w", encoding="utf-8"
                ) as debug_file:
                    debug_file.write(self.driver.page_source)
                self.logger.error(
                    "iframe[%d] 문서 HTML 저장: %s", idx, iframe_debug_path
                )
            except WebDriverException:
                self.logger.error("iframe[%d] 문서를 읽지 못했습니다.", idx)

        self.driver.switch_to.default_content()

    def _click_review_tab(self, timeout: float = 15.0) -> bool:
        """영화 정보 위젯의 "관람평" 탭을 실제로 클릭해 진입한다.

        ``execute_script``로 ``element.click()``을 호출하면 브라우저가
        신뢰할 수 없는(비신뢰, ``isTrusted: false``) 클릭으로 처리해,
        사이트의 탭 전환 로직이 이를 무시하는 것으로 확인됐다. 그래서
        Selenium의 네이티브 클릭(WebDriver 프로토콜을 통한 실제 입력
        이벤트)을 사용한다.

        "관람평"이라는 텍스트를 가진 요소가 페이지에 여러 개(다른 영화
        추천 위젯 등) 있을 수 있어, 후보를 하나씩 클릭해보고 실제로
        이 영화(``MOVIE_CODE``)의 리뷰 카드가 나타나는지 확인한다.

        Args:
            timeout: 탭 버튼을 찾고 클릭을 시도할 최대 시간(초).

        Returns:
            올바른 탭을 클릭해 리뷰 카드를 확인했으면 True.

        Raises:
            RuntimeError: WebDriver가 아직 생성되지 않은 경우.
        """
        if self.driver is None:
            raise RuntimeError("Chrome WebDriver가 생성되지 않았습니다.")

        deadline = time.time() + timeout

        while time.time() < deadline:
            self.driver.switch_to.default_content()

            candidates = self.driver.find_elements(
                By.XPATH,
                "//*[self::a or self::button or self::span]"
                "[normalize-space(text())='관람평']",
            )

            for candidate in candidates:
                try:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});",
                        candidate,
                    )
                    time.sleep(0.3)
                    # 네이티브 클릭(신뢰된 입력 이벤트)을 사용한다.
                    candidate.click()
                except (
                    ElementClickInterceptedException,
                    ElementNotInteractableException,
                    WebDriverException,
                ):
                    try:
                        ActionChains(self.driver).move_to_element(
                            candidate
                        ).pause(0.2).click().perform()
                    except WebDriverException:
                        continue

                time.sleep(1.0)

                matched = self.driver.find_elements(
                    By.CSS_SELECTOR,
                    self.REVIEW_MOVIE_CARD_SELECTOR.format(
                        movie_code=self.MOVIE_CODE
                    ),
                )
                if matched:
                    self.logger.info(
                        "'관람평' 탭을 클릭해 이 영화의 리뷰 카드를 "
                        "확인했습니다."
                    )
                    return True

            time.sleep(1.0)

        return False

    def _scroll_to_widget(self, timeout: float = 15.0) -> bool:
        """리뷰 위젯 컨테이너(``div.lego_review_list_scroller``)를 찾아
        화면 중앙으로 바로 스크롤한다.

        무작정 페이지를 조금씩 스크롤하면 위젯을 지나쳐버릴 수 있어,
        컨테이너 요소 자체를 찾아 ``scrollIntoView``로 정확히 그
        위치로 이동한다. 컨테이너는 리뷰가 채워지기 전에도 빈 채로
        DOM에 존재한다.

        Args:
            timeout: 컨테이너를 찾기 위해 기다릴 최대 시간(초).

        Returns:
            컨테이너를 찾아 스크롤했으면 True.

        Raises:
            RuntimeError: WebDriver가 아직 생성되지 않은 경우.
        """
        if self.driver is None:
            raise RuntimeError("Chrome WebDriver가 생성되지 않았습니다.")

        deadline = time.time() + timeout

        while time.time() < deadline:
            self.driver.switch_to.default_content()
            elements = self.driver.find_elements(
                By.CSS_SELECTOR, self.REVIEW_CONTAINER_SELECTOR
            )
            if elements:
                try:
                    ActionChains(self.driver).move_to_element(
                        elements[0]
                    ).perform()
                except WebDriverException:
                    self.driver.execute_script(
                        "arguments[0].scrollIntoView({block: 'center'});",
                        elements[0],
                    )
                return True

            time.sleep(1.0)

        return False

    def _scroll_review_container(self) -> bool:
        """리뷰 목록 내부의 실제 세로 스크롤 요소를 끝까지 내린다.

        ``window.scrollBy``를 사용하면 브라우저 전체 페이지가 내려가므로,
        리뷰 위젯 안에서 ``overflow-y``가 설정된 실제 스크롤 요소를 찾아
        해당 요소의 ``scrollTop``만 변경한다.

        Returns:
            리뷰 내부 스크롤을 실행했으면 ``True``, 리뷰 영역을 찾지
            못했으면 ``False``.

        Raises:
            RuntimeError: WebDriver가 아직 생성되지 않은 경우.
        """
        if self.driver is None:
            raise RuntimeError("Chrome WebDriver가 생성되지 않았습니다.")

        # 리뷰 카드가 존재하는 문서 또는 iframe으로 먼저 전환한다.
        if not self._try_locate_review_frame():
            return False

        containers = self.driver.find_elements(
            By.CSS_SELECTOR, self.REVIEW_CONTAINER_SELECTOR
        )
        if not containers:
            return False

        container = containers[0]

        # 네이버의 DOM 구조가 조금 달라져도 대응하도록, 컨테이너 자신과
        # 자식·부모 요소 중 실제로 세로 스크롤 가능한 요소를 찾는다.
        scroll_element = self.driver.execute_script(
            """
            const root = arguments[0];

            function isScrollable(element) {
                const style = window.getComputedStyle(element);
                const overflowY = style.overflowY;

                return (
                    (overflowY === "auto" || overflowY === "scroll") &&
                    element.scrollHeight > element.clientHeight + 1
                );
            }

            if (isScrollable(root)) {
                return root;
            }

            for (const child of root.querySelectorAll("*")) {
                if (isScrollable(child)) {
                    return child;
                }
            }

            let parent = root.parentElement;
            while (parent && parent !== document.body) {
                if (isScrollable(parent)) {
                    return parent;
                }
                parent = parent.parentElement;
            }

            return root;
            """,
            container,
        )

        if scroll_element is None:
            return False

        self.driver.execute_script(
            """
            const element = arguments[0];

            element.scrollTop = element.scrollHeight;

            element.dispatchEvent(
                new Event("scroll", {bubbles: true})
            );
            """,
            scroll_element,
        )

        return True

    def _click_review_sort_tab(self, tab_name: str) -> bool:
        """리뷰 목록의 정렬 탭을 클릭한다.

        Args:
            tab_name: "공감순", "최신순" 같은 정렬 탭 이름.

        Returns:
            탭을 찾아 클릭했으면 ``True``.

        Raises:
            RuntimeError: WebDriver가 아직 생성되지 않은 경우.
        """
        if self.driver is None:
            raise RuntimeError("Chrome WebDriver가 생성되지 않았습니다.")

        if not self._try_locate_review_frame():
            return False

        tab_literal = f'"{tab_name}"'
        candidates = self.driver.find_elements(
            By.XPATH,
            "//li[contains(concat(' ', normalize-space(@class), ' '), "
            "' tab ')]//span[normalize-space(text())="
            f"{tab_literal}]/ancestor::a[1]",
        )

        if not candidates:
            candidates = self.driver.find_elements(
                By.XPATH,
                f"//*[normalize-space(text())={tab_literal}]/ancestor::a[1]",
            )

        for candidate in candidates:
            try:
                candidate.click()
                return True
            except (
                ElementClickInterceptedException,
                ElementNotInteractableException,
                WebDriverException,
            ):
                try:
                    ActionChains(self.driver).move_to_element(
                        candidate
                    ).pause(0.2).click().perform()
                    return True
                except WebDriverException:
                    continue

        return False

    def _collect_from_page_source(self, seen_ids: Set[str]) -> int:
        """현재 페이지 소스에서 아직 보지 못한 리뷰를 모두 수집한다.

        Args:
            seen_ids: 지금까지 수집한 ``rating_id`` 집합. 이 메서드가
                새로 찾은 id를 계속 추가한다.

        Returns:
            새로 추가된 리뷰 개수.

        Raises:
            RuntimeError: WebDriver가 아직 생성되지 않은 경우.
        """
        if self.driver is None:
            raise RuntimeError("Chrome WebDriver가 생성되지 않았습니다.")

        soup = BeautifulSoup(self.driver.page_source, "html.parser")
        cards = soup.select(self.REVIEW_CARD_SELECTOR)

        new_count = 0
        for card in cards:
            review = self._extract_review(card)
            if review is None:
                continue

            rating_id = review.pop("rating_id")
            if rating_id in seen_ids:
                continue

            seen_ids.add(rating_id)
            self.reviews.append(review)
            new_count += 1

        return new_count

    def scrape_reviews(self) -> None:
        """네이버 관람평을 500개 이상 수집한다.

        관람평 목록의 스크롤 컨테이너를 반복적으로 끝까지 내려 추가
        리뷰가 로드되도록 하고, 목표 개수에 도달하거나 더 이상 새 리뷰가
        생기지 않으면 중단한다.

        Raises:
            RuntimeError: 리뷰를 한 개도 수집하지 못한 경우.
        """
        self.start_browser()

        if self.driver is None:
            raise RuntimeError("Chrome WebDriver가 생성되지 않았습니다.")

        seen_ids: Set[str] = set()

        try:
            self.logger.info("검색 페이지 접속: %s", self.SEARCH_URL)
            self.driver.get(self.SEARCH_URL)

            time.sleep(2)

            # 쿼리스트링만으로 관람평 탭에 바로 진입하면 위젯 내부 상태가
            # 제대로 초기화되지 않는 경우가 있어, 실제 사용자처럼 "관람평"
            # 탭을 클릭해서 진입한다.
            if self._click_review_tab(15.0):
                self.logger.info("'관람평' 탭을 클릭했습니다.")
                time.sleep(1.5)
            else:
                self.logger.warning(
                    "'관람평' 탭 버튼을 찾지 못했습니다. 이미 관람평 "
                    "탭이거나, 위젯 위치로 직접 스크롤합니다."
                )

            # 무작정 페이지를 스크롤하면 위젯을 지나쳐버릴 수 있어, 먼저
            # 위젯 컨테이너 위치로 정확히 점프한다.
            if self._scroll_to_widget(15.0):
                self.logger.info("리뷰 위젯 위치로 스크롤했습니다.")
            else:
                self.logger.warning(
                    "리뷰 위젯 컨테이너를 찾지 못해 페이지 전체를 "
                    "스크롤하며 찾아봅니다."
                )
            time.sleep(1.5)

            self._try_locate_review_frame()
            self._collect_from_page_source(seen_ids)
            self._save_checkpoint()

            stall_count = 0
            warmup_stall_limit = 60
            switched_to_latest = False

            for attempt in range(1, self.max_scroll_attempts + 1):
                if len(self.reviews) >= self.target_count:
                    break

                # 브라우저 전체가 아니라 리뷰 목록 내부만 스크롤한다.
                if not self._scroll_review_container():
                    self.logger.warning(
                        "리뷰 내부 스크롤 영역을 찾지 못했습니다."
                    )
                    new_count = 0
                else:
                    time.sleep(self.scroll_pause)

                    if self._try_locate_review_frame():
                        new_count = self._collect_from_page_source(seen_ids)
                    else:
                        new_count = 0

                self.logger.info(
                    "%d번째 스크롤 후 현재까지 총 %d개 수집했습니다. "
                    "(이번에 %d개 추가)",
                    attempt,
                    len(self.reviews),
                    new_count,
                )

                self._save_checkpoint()

                if new_count == 0:
                    stall_count += 1
                    stall_limit = (
                        self.max_stall_attempts
                        if self.reviews
                        else warmup_stall_limit
                    )
                    if stall_count >= stall_limit:
                        if (
                            self.reviews
                            and not switched_to_latest
                            and len(self.reviews) < self.target_count
                            and self._click_review_sort_tab("최신순")
                        ):
                            switched_to_latest = True
                            stall_count = 0
                            self.logger.info(
                                "공감순에서 새 리뷰가 멈춰 최신순으로 "
                                "전환했습니다."
                            )
                            time.sleep(self.scroll_pause)

                            if self._try_locate_review_frame():
                                latest_count = self._collect_from_page_source(
                                    seen_ids
                                )
                            else:
                                latest_count = 0

                            self.logger.info(
                                "최신순 전환 후 현재까지 총 %d개 "
                                "수집했습니다. (이번에 %d개 추가)",
                                len(self.reviews),
                                latest_count,
                            )
                            self._save_checkpoint()
                            continue

                        self.logger.info(
                            "%d번 연속으로 새 리뷰가 로드되지 않아 중단합니다.",
                            stall_count,
                        )
                        break
                else:
                    stall_count = 0

            if not self.reviews:
                self.logger.error(
                    "스크롤을 다 해봐도 리뷰 카드를 찾지 못했습니다."
                )
                self._log_debug_snapshot()

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
                "리뷰를 한 개도 수집하지 못했습니다. 로그를 확인하세요."
            )

        if len(self.reviews) < self.target_count:
            self.logger.warning(
                "목표는 %d개이지만 %d개만 수집했습니다.",
                self.target_count,
                len(self.reviews),
            )
        else:
            self.logger.info("목표 리뷰 수 %d개를 수집했습니다.", self.target_count)

    def _save_checkpoint(self) -> None:
        """현재까지 수집한 리뷰를 중간 CSV로 저장한다."""
        if not self.reviews:
            return

        os.makedirs(self.output_dir, exist_ok=True)

        checkpoint_path = os.path.join(
            self.output_dir, "reviews_naver_checkpoint.csv"
        )

        dataframe = pd.DataFrame(
            self.reviews, columns=["rating", "date", "review", "reviewer"]
        )
        dataframe.to_csv(checkpoint_path, index=False, encoding="utf-8-sig")

    def save_to_database(self) -> None:
        """수집한 리뷰를 최종 CSV 파일로 저장한다.

        Raises:
            RuntimeError: 저장할 리뷰가 없거나 최소 조건을 만족하지 못한 경우.
        """
        if not self.reviews:
            raise RuntimeError(
                "저장할 리뷰가 없습니다. scrape_reviews()를 먼저 실행해야 합니다."
            )

        os.makedirs(self.output_dir, exist_ok=True)

        output_path = os.path.join(self.output_dir, "reviews_naver.csv")

        dataframe = pd.DataFrame(
            self.reviews, columns=["rating", "date", "review", "reviewer"]
        )

        dataframe = dataframe.dropna(subset=["rating", "date", "review"])

        dataframe["review"] = dataframe["review"].astype(str).str.strip()
        dataframe = dataframe[dataframe["review"] != ""]

        dataframe = dataframe.drop_duplicates(
            subset=["rating", "date", "review", "reviewer"]
        )

        dataframe = dataframe.head(self.target_count)

        dataframe.to_csv(output_path, index=False, encoding="utf-8-sig")

        self.logger.info(
            "%d개의 리뷰를 저장했습니다: %s", len(dataframe), output_path
        )

        if len(dataframe) < self.target_count:
            raise RuntimeError(
                f"최종 저장 리뷰가 {len(dataframe)}개입니다. "
                f"과제 최소 조건인 {self.target_count}개를 충족하지 못했습니다."
            )
