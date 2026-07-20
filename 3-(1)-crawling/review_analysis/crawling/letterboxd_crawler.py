"""Letterboxd 영화 리뷰 크롤러.

최근 Letterboxd 크롤러들이 사용하는 방식에 맞춰 다음을 적용한다.

- Selenium 대신 HTTP 세션을 재사용한다.
- curl_cffi가 설치되어 있으면 Chrome TLS fingerprint를 사용한다.
- 403, 429, 5xx 및 네트워크 오류에 대해 지수 백오프로 재시도한다.
- 현재 페이지의 ``Older`` 링크를 우선 사용해 다음 페이지로 이동한다.
- 다음 페이지가 이전 페이지와 같은 내용을 반환하면 세션을 재생성한다.
- 페이지 파싱 실패 시 HTML을 저장하고 같은 페이지를 다시 요청한다.
"""

from __future__ import annotations

import os
import random
import re
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urljoin, urlparse

import pandas as pd  # type: ignore[import-untyped]
from bs4 import BeautifulSoup, Tag

from review_analysis.crawling.base_crawler import BaseCrawler  # type: ignore[import-untyped]
from utils.logger import setup_logger  # type: ignore[import-untyped]

try:
    # Letterboxd의 Cloudflare 응답에 더 안정적인 최근 구현 방식.
    from curl_cffi import requests as http_requests

    CURL_CFFI_AVAILABLE = True
except ImportError:
    # 기본 requests로도 접속 가능한 환경을 위해 fallback을 둔다.
    import requests as http_requests  # type: ignore[no-redef]

    CURL_CFFI_AVAILABLE = False


@dataclass(frozen=True)
class PageResult:
    """한 페이지의 요청 및 파싱 결과."""

    html: str
    final_url: str
    reviews: List[Dict[str, str]]
    next_url: Optional[str]
    signature: Tuple[str, ...]


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

    def start_browser(self) -> None:
        """HTTP 세션을 생성하여 크롤링 실행 환경을 준비한다.

        이 구현은 Selenium WebDriver 대신 Chrome의 TLS fingerprint를
        재현하는 ``curl_cffi`` 세션을 사용한다. 일반 ``requests``는 현재
        Letterboxd에서 첫 페이지부터 HTTP 403을 받을 가능성이 높으므로,
        ``curl_cffi``가 없으면 오래 재시도하지 않고 설치 방법을 안내한다.

        Raises:
            RuntimeError: ``curl_cffi``가 설치되어 있지 않은 경우.
        """
        if not CURL_CFFI_AVAILABLE:
            raise RuntimeError(
                "Letterboxd 접속에는 curl_cffi가 필요합니다. "
                "python -m pip install -U curl-cffi 명령으로 설치하세요."
            )

        self._create_session()

    def __init__(self, output_dir: str):
        """크롤러를 초기화한다.

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
        self.max_retries = 4

        # 페이지마다 정확히 같은 간격으로 요청하지 않도록 범위를 사용한다.
        self.min_request_interval = 2.5
        self.max_request_interval = 4.5

        self.connect_timeout = 15
        self.read_timeout = 35

        self.reviews: List[Dict[str, str]] = []
        self.logger = setup_logger("letterboxd_crawler.log")

        self.session: Any = None
        self._using_curl_cffi = CURL_CFFI_AVAILABLE
        self._last_requested_url: Optional[str] = None

    # ------------------------------------------------------------------
    # HTTP 세션 및 요청
    # ------------------------------------------------------------------
    def _create_session(self) -> None:
        """새 HTTP 세션을 생성한다.

        ``curl_cffi``가 설치되어 있으면 해당 세션을 사용하고, 그렇지 않으면
        일반 ``requests.Session``을 사용한다.
        """
        self._close_session()
        self.session = http_requests.Session()

        # requests와 curl_cffi Session 모두 headers.update를 지원한다.
        # User-Agent는 curl_cffi의 impersonate 옵션이 TLS fingerprint와
        # 일치하는 값으로 자동 설정한다. 별도의 Chrome 버전을 강제로
        # 지정하면 HTTP 헤더와 TLS 정보가 불일치하여 오히려 차단될 수 있다.
        self.session.headers.update(
            {
                "Accept": (
                    "text/html,application/xhtml+xml,application/xml;q=0.9,"
                    "image/avif,image/webp,*/*;q=0.8"
                ),
                "Accept-Language": "en-US,en;q=0.9",
                "Referer": "https://letterboxd.com/",
                "Upgrade-Insecure-Requests": "1",
            }
        )

        backend = "curl_cffi" if self._using_curl_cffi else "requests"
        self.logger.info("HTTP 세션을 생성했습니다. backend=%s", backend)

    def _close_session(self) -> None:
        """현재 HTTP 세션을 안전하게 종료한다."""
        if self.session is None:
            return

        try:
            self.session.close()
        except Exception:  # 세션 정리 실패는 크롤링 결과에 영향 없음
            pass
        finally:
            self.session = None

    @staticmethod
    def _is_blocked_response(html: str) -> bool:
        """접근 제한 또는 Cloudflare 도전 페이지인지 확인한다."""
        lowered = html.lower()

        # 정상 HTML의 스크립트나 CSS에도 captcha, cf-chl 같은 문자열이
        # 포함될 수 있다. 실제 리뷰 컨테이너와 본문이 있으면 정상 페이지로
        # 우선 판정하여 Allocine에서 발생했던 것과 같은 오탐을 막는다.
        review_container_markers = (
            "film-detail",
            "production-viewing",
            "data-review-id",
        )
        review_body_markers = (
            "js-review-body",
            "body-text",
            "data-review-text",
        )
        has_review_content = (
            any(marker in lowered for marker in review_container_markers)
            and any(marker in lowered for marker in review_body_markers)
        )
        if has_review_content:
            return False

        blocked_markers = (
            "<title>just a moment",
            "<title>access denied",
            "cf-chl-challenge",
            "cf-chl-captcha",
            "enable javascript and cookies",
            "verify you are human",
            "checking your browser",
            "security challenge",
        )
        return any(marker in lowered for marker in blocked_markers)

    def _request_once(self, url: str) -> Any:
        """현재 세션으로 URL을 한 번 요청한다."""
        if self.session is None:
            self._create_session()

        headers: Dict[str, str] = {}
        if self._last_requested_url is not None:
            headers["Referer"] = self._last_requested_url

        kwargs: Dict[str, Any] = {
            "headers": headers,
            "timeout": (self.connect_timeout, self.read_timeout),
            "allow_redirects": True,
        }

        if self._using_curl_cffi:
            kwargs["impersonate"] = "chrome"

        return self.session.get(url, **kwargs)

    def _load_page(self, page_url: str, page_number: int) -> Tuple[str, str]:
        """페이지를 재시도와 세션 복구를 적용해 불러온다.

        Args:
            page_url:
                요청할 리뷰 페이지 URL.
            page_number:
                로그에 표시할 페이지 번호.

        Returns:
            ``(HTML 문자열, 최종 URL)``.

        Raises:
            RuntimeError:
                모든 재시도가 실패한 경우.
        """
        last_error: Optional[BaseException] = None
        last_status: Optional[int] = None

        for attempt in range(1, self.max_retries + 1):
            try:
                self.logger.info(
                    "%d페이지 요청 %d/%d: %s",
                    page_number,
                    attempt,
                    self.max_retries,
                    page_url,
                )

                response = self._request_once(page_url)
                status_code = int(getattr(response, "status_code", 0))
                last_status = status_code
                html = str(getattr(response, "text", ""))
                final_url = str(getattr(response, "url", page_url))

                if status_code == 200 and len(html) >= 1000:
                    if self._is_blocked_response(html):
                        self._save_debug_html(
                            html,
                            page_number,
                            suffix=f"blocked_{attempt}",
                        )
                        raise RuntimeError("접근 제한 화면이 반환되었습니다.")

                    self._last_requested_url = final_url
                    return html, final_url

                retryable = status_code in {403, 408, 425, 429} or status_code >= 500
                message = (
                    f"HTTP {status_code}, HTML 길이 {len(html)}"
                    if status_code
                    else f"응답 상태 코드 없음, HTML 길이 {len(html)}"
                )

                if not retryable:
                    raise RuntimeError(message)

                if html:
                    self._save_debug_html(
                        html,
                        page_number,
                        suffix=f"http_{status_code}_{attempt}",
                    )

                last_error = RuntimeError(message)

            except Exception as error:
                last_error = error
                self.logger.warning(
                    "%d페이지 요청 실패(%d/%d): %s",
                    page_number,
                    attempt,
                    self.max_retries,
                    error,
                )

            if attempt < self.max_retries:
                # 차단 또는 세션 손상 가능성이 있으므로 새 세션으로 교체한다.
                self._create_session()
                wait_seconds = min(30.0, 2.0 ** attempt) + random.uniform(0.5, 1.5)
                self.logger.info("%.1f초 후 같은 페이지를 재시도합니다.", wait_seconds)
                time.sleep(wait_seconds)

        backend_hint = ""
        if not self._using_curl_cffi and last_status == 403:
            backend_hint = (
                " curl_cffi를 설치한 뒤 다시 실행하세요: "
                "python -m pip install -U curl-cffi"
            )

        raise RuntimeError(
            f"{page_number}페이지를 {self.max_retries}회 요청했지만 실패했습니다."
            f" 마지막 오류: {last_error}.{backend_hint}"
        )

    # ------------------------------------------------------------------
    # HTML 파싱
    # ------------------------------------------------------------------
    @staticmethod
    def _find_review_elements(soup: BeautifulSoup) -> List[Tag]:
        """현재 페이지에서 개별 리뷰 컨테이너를 찾는다."""
        selectors = (
            "li.film-detail",
            "div.film-detail",
            "article.film-detail",
            ".production-viewing.-viewing",
            "article.production-viewing",
            "li.production-viewing",
            "div.production-viewing",
            "[data-review-id]",
        )

        body_selector = (
            ".js-review-body, "
            ".film-detail-content .body-text, "
            ".body-text.-prose, "
            ".body-text, "
            "[data-review-text]"
        )

        for selector in selectors:
            found: List[Tag] = []
            seen_ids: Set[int] = set()

            for element in soup.select(selector):
                if not isinstance(element, Tag):
                    continue
                if element.select_one(body_selector) is None:
                    continue

                identity = id(element)
                if identity not in seen_ids:
                    found.append(element)
                    seen_ids.add(identity)

            if found:
                return found

        # 클래스명이 다시 변경되더라도 본문 요소에서 가까운 리뷰 부모를 찾는다.
        fallback: List[Tag] = []
        fallback_seen_ids: Set[int] = set()

        for body in soup.select(body_selector):
            if not isinstance(body, Tag):
                continue

            parent = body.find_parent(
                ["li", "article", "div"],
                class_=lambda classes: (
                    classes is not None
                    and any(
                        keyword in " ".join(classes if isinstance(classes, list) else [classes])
                        for keyword in ("film-detail", "production-viewing", "review")
                    )
                ),
            )

            if isinstance(parent, Tag) and id(parent) not in fallback_seen_ids:
                fallback.append(parent)
                fallback_seen_ids.add(id(parent))

        return fallback

    @staticmethod
    def _normalise_rating(raw_value: float) -> Optional[str]:
        """HTML 별점 값을 0.5~5.0 범위의 문자열로 변환한다."""
        rating = raw_value / 2 if raw_value > 5 else raw_value
        if rating < 0.5 or rating > 5:
            return None

        rating = round(rating * 2) / 2
        return f"{rating:.1f}"

    @classmethod
    def _extract_rating(cls, review_element: Tag) -> Optional[str]:
        """리뷰 컨테이너에서 별점을 추출한다."""
        rating_selectors = (
            ".rating",
            ".inline-rating",
            ".glyph.-rating",
            "[data-rating]",
            "[class*='rated-']",
            "[class*='rating-']",
        )

        candidates: List[Tag] = []
        for selector in rating_selectors:
            for element in review_element.select(selector):
                if isinstance(element, Tag):
                    candidates.append(element)

        # 일부 구조에서는 별점 클래스가 리뷰 컨테이너 자체에 붙는다.
        candidates.insert(0, review_element)

        for element in candidates:
            data_rating = element.get("data-rating")
            if isinstance(data_rating, str):
                try:
                    parsed = cls._normalise_rating(float(data_rating.strip()))
                    if parsed is not None:
                        return parsed
                except ValueError:
                    pass

            raw_classes = element.get("class")
            class_names: List[str]
            if isinstance(raw_classes, str):
                class_names = raw_classes.split()
            elif isinstance(raw_classes, list):
                class_names = [str(value) for value in raw_classes]
            else:
                class_names = []

            for class_name in class_names:
                match = re.search(
                    r"(?:rated|rating)[-_]?(\d+(?:\.\d+)?)",
                    str(class_name),
                    re.IGNORECASE,
                )
                if match is not None:
                    parsed = cls._normalise_rating(float(match.group(1)))
                    if parsed is not None:
                        return parsed

            for attribute_name in ("title", "aria-label", "data-original-title"):
                value = element.get(attribute_name)
                if not isinstance(value, str):
                    continue

                match = re.search(
                    r"([0-5](?:\.[05])?)\s*(?:out\s+of\s+5|stars?|star\s+rating)",
                    value,
                    re.IGNORECASE,
                )
                if match is not None:
                    return cls._normalise_rating(float(match.group(1)))

            for use_element in element.select("use"):
                href = use_element.get("href") or use_element.get("xlink:href")
                if not isinstance(href, str):
                    continue

                match = re.search(r"(?:icon-)?rating[-_]?(\d+)", href, re.IGNORECASE)
                if match is not None:
                    parsed = cls._normalise_rating(float(match.group(1)))
                    if parsed is not None:
                        return parsed

        # Letterboxd가 화면에 출력하는 ★★★★½ 형식도 처리한다.
        visible_text = review_element.get_text(" ", strip=True)
        star_match = re.search(r"(★{1,5})(½)?", visible_text)
        if star_match is not None:
            rating = len(star_match.group(1)) + (0.5 if star_match.group(2) else 0.0)
            return cls._normalise_rating(rating)

        return None

    @staticmethod
    def _extract_date(review_element: Tag) -> Optional[str]:
        """리뷰 컨테이너에서 작성 또는 관람 날짜를 추출한다."""
        selectors = (
            "time[datetime]",
            ".film-detail-meta time",
            ".date time",
            ".date",
            ".timestamp",
            "[data-viewing-date]",
        )

        for selector in selectors:
            for date_element in review_element.select(selector):
                if not isinstance(date_element, Tag):
                    continue

                for attribute_name in ("datetime", "data-viewing-date", "title"):
                    value = date_element.get(attribute_name)
                    if not isinstance(value, str) or not value.strip():
                        continue

                    value = value.strip()
                    iso_match = re.search(r"\d{4}-\d{2}-\d{2}", value)
                    return iso_match.group(0) if iso_match is not None else value

                displayed = date_element.get_text(" ", strip=True)
                if displayed:
                    return displayed

        full_text = review_element.get_text(" ", strip=True)
        date_patterns = (
            r"\b\d{4}-\d{2}-\d{2}\b",
            r"\b\d{1,2}\s+"
            r"(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+\d{4}\b",
            r"\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)"
            r"\s+\d{1,2},\s+\d{4}\b",
        )

        for pattern in date_patterns:
            match = re.search(pattern, full_text, re.IGNORECASE)
            if match is not None:
                return match.group(0)

        return None

    @staticmethod
    def _extract_review_text(review_element: Tag) -> Optional[str]:
        """리뷰 컨테이너에서 리뷰 본문을 추출한다."""
        text_element = review_element.select_one(
            ".js-review-body, "
            ".film-detail-content .body-text, "
            ".body-text.-prose, "
            ".body-text, "
            "[data-review-text]"
        )
        if text_element is None:
            return None

        copied_soup = BeautifulSoup(str(text_element), "html.parser")
        for unnecessary in copied_soup.select(
            "script, style, svg, button, .translate-button, .js-translate, "
            ".translation, .js-translation"
        ):
            unnecessary.decompose()

        review_text = copied_soup.get_text(" ", strip=True)
        review_text = re.sub(
            r"\bTranslate\b(?:\s+Translated\s+from.*)?$",
            "",
            review_text,
            flags=re.IGNORECASE,
        )
        review_text = re.sub(r"\s+", " ", review_text).strip()

        return review_text or None

    def _parse_page(self, html: str, page_number: int) -> List[Dict[str, str]]:
        """한 페이지의 HTML에서 유효한 리뷰를 추출한다."""
        soup = BeautifulSoup(html, "html.parser")
        review_elements = self._find_review_elements(soup)

        parsed_reviews: List[Dict[str, str]] = []
        missing_rating = 0
        missing_date = 0
        missing_review = 0

        for review_element in review_elements:
            rating = self._extract_rating(review_element)
            review_date = self._extract_date(review_element)
            review_text = self._extract_review_text(review_element)

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
            "%d페이지 분석: 요소 %d개, 유효 %d개, "
            "별점 누락 %d개, 날짜 누락 %d개, 본문 누락 %d개",
            page_number,
            len(review_elements),
            len(parsed_reviews),
            missing_rating,
            missing_date,
            missing_review,
        )

        return parsed_reviews

    # ------------------------------------------------------------------
    # 페이지 이동
    # ------------------------------------------------------------------
    def _build_page_url(self, page_number: int) -> str:
        """페이지 번호를 Letterboxd의 canonical URL 형식으로 변환한다."""
        if page_number <= 1:
            return self.base_url
        return urljoin(self.base_url, f"page/{page_number}/")

    def _extract_next_url(self, html: str, current_url: str) -> Optional[str]:
        """현재 페이지의 ``Older`` 또는 ``rel=next`` 링크를 찾는다."""
        soup = BeautifulSoup(html, "html.parser")

        selectors = (
            "a[rel='next']",
            "a[aria-label*='Older' i]",
            "a[title*='Older' i]",
            ".paginate-nextprev a.next",
            ".pagination a.next",
            "a.next",
        )

        candidate: Optional[Tag] = None
        for selector in selectors:
            found = soup.select_one(selector)
            if isinstance(found, Tag):
                candidate = found
                break

        if candidate is None:
            for anchor in soup.find_all("a", href=True):
                if not isinstance(anchor, Tag):
                    continue
                text = anchor.get_text(" ", strip=True).lower()
                if text == "older" or "older reviews" in text:
                    candidate = anchor
                    break

        if candidate is None:
            return None

        href = candidate.get("href")
        if not isinstance(href, str) or not href.strip():
            return None

        href = href.strip()

        # ``page/3/`` 같은 상대 경로를 현재 ``page/2/``에 붙이면
        # ``.../page/2/page/3/``가 되므로 영화 리뷰 기준 URL에 붙인다.
        if re.fullmatch(r"page/\d+/?", href, re.IGNORECASE):
            next_url = urljoin(self.base_url, href)
        else:
            next_url = urljoin(current_url, href)

        # 외부 링크나 다른 영화로 잘못 이동하지 않도록 검증한다.
        parsed_next = urlparse(next_url)
        parsed_base = urlparse(self.base_url)
        if parsed_next.netloc != parsed_base.netloc:
            return None

        base_path = parsed_base.path.rstrip("/") + "/"
        if not parsed_next.path.startswith(base_path):
            return None

        # trailing slash를 통일한다. 쿼리 문자열은 그대로 유지한다.
        normalized_path = parsed_next.path.rstrip("/") + "/"
        return parsed_next._replace(path=normalized_path, fragment="").geturl()

    @staticmethod
    def _make_page_signature(reviews: List[Dict[str, str]]) -> Tuple[str, ...]:
        """동일 페이지가 반복 반환되는지 확인할 간단한 서명을 만든다."""
        return tuple(
            f"{review['rating']}|{review['date']}|{review['review'][:120]}"
            for review in reviews[:3]
        )

    def _fetch_and_parse_page(self, page_url: str, page_number: int) -> PageResult:
        """한 페이지를 요청하고 파싱한다.

        HTML은 정상인데 리뷰 요소가 0개인 경우 세션을 바꿔 같은 페이지를
        한 번 더 요청한다. 이 방식은 페이지 전환 직후 차단 페이지나 불완전한
        응답이 섞여 들어오는 경우를 복구한다.
        """
        parse_attempts = 2
        last_html = ""
        last_final_url = page_url

        for parse_attempt in range(1, parse_attempts + 1):
            html, final_url = self._load_page(page_url, page_number)
            last_html = html
            last_final_url = final_url
            reviews = self._parse_page(html, page_number)

            if reviews:
                return PageResult(
                    html=html,
                    final_url=final_url,
                    reviews=reviews,
                    next_url=self._extract_next_url(html, final_url),
                    signature=self._make_page_signature(reviews),
                )

            self._save_debug_html(html, page_number, suffix=f"parse_{parse_attempt}")

            if parse_attempt < parse_attempts:
                self.logger.warning(
                    "%d페이지의 리뷰 파싱 결과가 비어 있어 새 세션으로 재요청합니다.",
                    page_number,
                )
                self._create_session()
                time.sleep(random.uniform(3.0, 5.0))

        return PageResult(
            html=last_html,
            final_url=last_final_url,
            reviews=[],
            next_url=self._extract_next_url(last_html, last_final_url),
            signature=(),
        )

    # ------------------------------------------------------------------
    # 저장 및 실행
    # ------------------------------------------------------------------
    def _checkpoint_path(self) -> str:
        """체크포인트 CSV 경로를 반환한다."""
        return os.path.join(self.output_dir, "reviews_letterboxd_checkpoint.csv")

    def _load_checkpoint(self) -> None:
        """기존 체크포인트가 있으면 중복 없이 불러온다."""
        path = self._checkpoint_path()
        if not os.path.exists(path):
            return

        try:
            dataframe = pd.read_csv(path, dtype=str)
            required_columns = {"rating", "date", "review"}
            if not required_columns.issubset(dataframe.columns):
                return

            dataframe = dataframe.dropna(subset=["rating", "date", "review"])
            dataframe = dataframe.drop_duplicates(subset=["rating", "date", "review"])
            self.reviews = dataframe[["rating", "date", "review"]].to_dict("records")
            self.logger.info("체크포인트에서 %d개 리뷰를 복구했습니다.", len(self.reviews))
        except Exception as error:
            self.logger.warning("체크포인트를 읽지 못했습니다: %s", error)

    def _save_checkpoint(self) -> None:
        """현재까지 수집한 리뷰를 중간 CSV로 저장한다."""
        if not self.reviews:
            return

        os.makedirs(self.output_dir, exist_ok=True)
        dataframe = pd.DataFrame(
            self.reviews,
            columns=["rating", "date", "review"],
        )
        dataframe.to_csv(
            self._checkpoint_path(),
            index=False,
            encoding="utf-8-sig",
        )

    def _save_debug_html(self, html: str, page_number: int, suffix: str = "") -> None:
        """실패한 페이지의 HTML을 분석용 파일로 저장한다."""
        os.makedirs(self.output_dir, exist_ok=True)
        suffix_part = f"_{suffix}" if suffix else ""
        debug_path = os.path.join(
            self.output_dir,
            f"letterboxd_debug_page_{page_number}{suffix_part}.html",
        )

        with open(debug_path, "w", encoding="utf-8") as debug_file:
            debug_file.write(html)

        self.logger.warning("디버그 HTML을 저장했습니다: %s", debug_path)

    def scrape_reviews(self) -> None:
        """Letterboxd 리뷰를 목표 개수까지 수집한다."""
        self._load_checkpoint()

        if len(self.reviews) >= self.target_count:
            self.logger.info(
                "체크포인트에 이미 %d개의 리뷰가 있어 요청을 생략합니다.",
                len(self.reviews),
            )
            return

        self.start_browser()

        seen_reviews: Set[Tuple[str, str, str]] = {
            (review["rating"], review["date"], review["review"])
            for review in self.reviews
        }
        visited_urls: Set[str] = set()
        seen_page_signatures: Set[Tuple[str, ...]] = set()

        current_url = self.base_url
        consecutive_empty_pages = 0

        try:
            for page_number in range(1, self.max_pages + 1):
                if len(self.reviews) >= self.target_count:
                    break

                if current_url in visited_urls:
                    raise RuntimeError(
                        f"이미 방문한 페이지 URL이 다시 나타났습니다: {current_url}"
                    )
                visited_urls.add(current_url)

                result = self._fetch_and_parse_page(current_url, page_number)

                if not result.reviews:
                    consecutive_empty_pages += 1
                    self.logger.warning(
                        "%d페이지에서 유효 리뷰를 찾지 못했습니다.",
                        page_number,
                    )

                    if consecutive_empty_pages >= 3:
                        raise RuntimeError(
                            "연속 세 페이지에서 리뷰 파싱에 실패했습니다. "
                            "저장된 debug HTML을 확인하세요."
                        )
                else:
                    consecutive_empty_pages = 0

                    if result.signature and result.signature in seen_page_signatures:
                        # 페이지 번호는 달라졌는데 같은 리뷰가 돌아온 경우는
                        # 리다이렉트 또는 세션 차단으로 판단한다.
                        self.logger.warning(
                            "%d페이지가 이전 페이지와 동일한 내용을 반환했습니다. "
                            "세션을 바꾸고 한 번 더 확인합니다.",
                            page_number,
                        )
                        self._create_session()
                        time.sleep(random.uniform(4.0, 6.0))
                        result = self._fetch_and_parse_page(current_url, page_number)

                        if result.signature in seen_page_signatures:
                            self._save_debug_html(
                                result.html,
                                page_number,
                                suffix="duplicate",
                            )
                            raise RuntimeError(
                                f"{page_number}페이지에서 이전 페이지와 동일한 "
                                "응답이 반복되었습니다."
                            )

                    if result.signature:
                        seen_page_signatures.add(result.signature)

                    added_count = 0
                    for review in result.reviews:
                        key = (
                            review["rating"],
                            review["date"],
                            review["review"],
                        )
                        if key in seen_reviews:
                            continue

                        seen_reviews.add(key)
                        self.reviews.append(review)
                        added_count += 1

                        if len(self.reviews) >= self.target_count:
                            break

                    self.logger.info(
                        "%d페이지에서 %d개 추가, 현재 총 %d개입니다.",
                        page_number,
                        added_count,
                        len(self.reviews),
                    )
                    self._save_checkpoint()

                if len(self.reviews) >= self.target_count:
                    break

                # 실제 HTML의 Older 링크를 우선 사용한다.
                next_url = result.next_url

                # 네비게이션 링크를 파싱하지 못한 경우에만 정형 URL을 사용한다.
                if next_url is None and result.reviews:
                    fallback_url = self._build_page_url(page_number + 1)
                    self.logger.warning(
                        "Older 링크를 찾지 못해 정형 URL을 사용합니다: %s",
                        fallback_url,
                    )
                    next_url = fallback_url

                if next_url is None:
                    self.logger.info("다음 페이지가 없어 크롤링을 종료합니다.")
                    break

                if next_url == current_url:
                    raise RuntimeError("다음 페이지 URL이 현재 URL과 같습니다.")

                current_url = next_url
                time.sleep(
                    random.uniform(
                        self.min_request_interval,
                        self.max_request_interval,
                    )
                )

        finally:
            self._close_session()

        if not self.reviews:
            raise RuntimeError(
                "리뷰를 한 개도 수집하지 못했습니다. "
                "저장된 debug HTML과 letterboxd_crawler.log를 확인하세요."
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
        """수집한 리뷰를 최종 CSV 파일로 저장한다."""
        if not self.reviews:
            raise RuntimeError(
                "저장할 리뷰가 없습니다. scrape_reviews()를 먼저 실행해야 합니다."
            )

        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, "reviews_letterboxd.csv")

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
                f"최종 저장 리뷰가 {len(dataframe)}개입니다. "
                f"과제 최소 조건인 {self.target_count}개를 충족하지 못했습니다."
            )