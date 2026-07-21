from typing import Dict, List, Optional

from bs4 import BeautifulSoup
from selenium import webdriver
from selenium.webdriver.chrome.webdriver import WebDriver
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from selenium.common.exceptions import WebDriverException
from webdriver_manager.chrome import ChromeDriverManager

from review_analysis.crawling.base_crawler import BaseCrawler
from utils.logger import setup_logger

import os
import pandas as pd
import time


class MetacriticCrawler(BaseCrawler):
    """Metacritic에서 영화 리뷰를 수집하는 크롤러.
    
    영화: 아바타 물의 길
    대상 페이지: https://www.metacritic.com/movie/avatar-the-way-of-water/user-reviews/
    페이지가 아닌 스크롤 방식으로, 평점, 날짜, 내용을 가져옴
    각 카드 박스가 'data-testid': 'review-card'로 있고, 
    평점(rate): {'class':'c-siteReviewScore'}, 
    날짜(date): {'class':'review-card-date'}
    본문(review): {'data-testid': 'review-quote-text'}
     - [SPOILER ALERT: This review contains spoilers.]: 본문 내용이 스포일러가 될 때 다음과 같이 나타남.
     - read more botton을 클릭 후 리뷰 내용 크롤링.
     - 모달 창을 ESC로 닫고 진행 
    """

    def __init__(self, output_dir: str):
        """Metacritic 크롤러를 초기화한다.

        Args:
            output_dir: 크롤링 결과 CSV 파일을 저장할 디렉터리 경로.
        """
        super().__init__(output_dir)

        self.base_url = ""
        self.target_count = 500

        self.driver: Optional[WebDriver] = None
        self.reviews: List[Dict[str, str]] = []
        self.logger = setup_logger("metacritic_crawler.log")

    def start_browser(self) -> None:
        """Selenium Chrome WebDriver를 실행한다."""
        chrome_options = Options()

        chrome_options.add_experimental_option("detach", True)
        chrome_options.add_experimental_option("excludeSwitches", ["enable-logging"])

        self.driver = webdriver.Chrome(
            service=Service(ChromeDriverManager().install()),
            options=chrome_options
        )

    def _scroll_down_with_page_down(
        self,
        driver: WebDriver,
        presses: int = 6,
        pause: float = 0.3,
    ) -> None:
        """한 번에 맨 아래로 점프하지 않고, PAGE_DOWN 키를 여러 번 눌러 스크롤한다.

        execute_script로 좌표를 계산해 점프하는 방식은 (1) 한 번에 점프하면
        봇 탐지/스로틀링에 걸리기 쉽고, (2) 잘게 쪼개면 JS 호출이 과도하게
        늘어나 렌더러가 크래시하는 문제가 있었다. 키 입력은 실제 사용자
        스크롤과 동일한 이벤트라 렌더러 부담도 적고 더 자연스럽다.
        """
        body = driver.find_element(By.TAG_NAME, 'body')
        for _ in range(presses):
            body.send_keys(Keys.PAGE_DOWN)
            time.sleep(pause)

    def scrape_reviews(self) -> None:
        """Metacritic에서 별점, 날짜, 리뷰 본문을 수집한다."""
        self.start_browser()
        driver = self.driver
        url = 'https://www.metacritic.com/movie/avatar-the-way-of-water/user-reviews/'
        driver.get(url)
        driver.implicitly_wait(2)
        try:
            driver.maximize_window()
        except:
            pass

        time.sleep(2) # 첫 로딩 대기

        
        # 페이지 스크롤 하는 법
        # - 로드된 리뷰 개수가 전체 개수(total_review_count)에 도달하면 종료
        # - 또는 스크롤을 여러번 해도 개수가 더 이상 늘어나지 않으면 종료 (안전장치)

        interval = 2 #리뷰 로드 시간
        max_wait = 8 # 한 번의 스크롤에서 새 콘텐츠가 뜰 때까지 기다릴 최대 시간(초)
        max_scroll_count = 200
        scroll_count = 0 # 현재 스크롤 횟수
        no_change_count = 0
        max_no_chage = 6

        # 현재 로드된 리뷰 카드 개수를 가져와서 저장
        # (document.body.scrollHeight는 리뷰가 많아지면 브라우저의 엘리먼트
        # 최대 높이 한계(2^24px)에 걸려 더 이상 증가하지 않는 경우가 있어
        # 종료 판단 기준으로 쓰기에 부적합함 — 실제 로드된 카드 개수로 판단한다.)
        prev_count = len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="review-card"]'))

        #반복 수행
        while scroll_count < max_scroll_count:
                try:
                    self._scroll_down_with_page_down(driver)

                    # 고정 대기 대신, 카드 개수가 늘어날 때까지 최대 max_wait초 동안 폴링한다.
                    # DOM이 커질수록 다음 배치 로딩이 느려져서 고정 sleep으로는
                    # 아직 로딩 중인 걸 '더 이상 안 늘어남'으로 오판할 수 있다.
                    curr_count = prev_count
                    waited = 0.0
                    while waited < max_wait:
                        time.sleep(interval)
                        waited += interval
                        curr_count = len(driver.find_elements(By.CSS_SELECTOR, '[data-testid="review-card"]'))
                        if curr_count != prev_count:
                            break
                except WebDriverException as e:
                    self.logger.error(f"스크롤 중 세션 오류 발생, 재시도: {e}")
                    time.sleep(interval)
                    continue  # 세션이 살아있으면 다음 루프에서 이어감

                self.logger.info(
                    "[scroll %d/%d] prev_count=%s curr_count=%s waited=%.1fs no_change_count=%d",
                    scroll_count + 1, max_scroll_count, prev_count, curr_count, waited, no_change_count,
                )

                if curr_count == prev_count:
                    no_change_count += 1
                    if no_change_count >= max_no_chage:
                        self.logger.warning(
                            "리뷰 개수 변화 없음이 %d회 연속 발생하여 스크롤 종료 (scroll_count=%d, count=%s)",
                            max_no_chage, scroll_count, curr_count,
                        )
                        break
                else:
                    no_change_count = 0
                    prev_count = curr_count

                scroll_count += 1

        self.logger.info("스크롤 반복 종료: scroll_count=%d, 최종 리뷰 카드 개수=%s", scroll_count, prev_count)

        columns = ['rate', 'date', 'review']
        values = []

        # 드라이버 접근 > 페이지 소스 가져오기
        soup = BeautifulSoup(driver.page_source, 'html.parser')
        data_rows = soup.find_all('div', attrs={'data-testid': 'review-card'})

        for i, row in enumerate(data_rows):
            blank = []

            rate = row.find('div', attrs={'class':'c-siteReviewScore'}) # 리뷰 점수 가져오기
            if rate:
                rate = rate.get_text().strip()
                blank.append(rate)
            else:
                blank.append('Someting is wrong')
                print('{}번째 리뷰 평점 가져올 때 문제 발생'.format(i+1))
                continue

            date = row.find('div', attrs={'data-testid':'review-card-date'}) # 리뷰 날짜 가져오기
            if date:
                date = date.get_text().strip()
                blank.append(date)
            else:
                blank.append('Something is wrong')
                print('{}번째 리뷰 날짜 가져올 때 문제 발생'.format(i+1))
                continue

            review = row.find('div', attrs={'data-testid': 'review-quote-text'})
            if review:
                review = review.get_text().strip()
            else:
                blank.append('Someting is wrong')
                print('{}번째 리뷰 본문 가져올 때 문제 발생'.format(i+1))
                continue

            if '[SPOILER ALERT: This review contains spoilers.]' in review:
                try:
                    card = driver.find_elements(By.CSS_SELECTOR, '[data-testid="review-card"]')[i]
                    read_more_btn = card.find_element(By.XPATH, './/*[@data-testid="review-quote-read-more"]')
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", read_more_btn)
                    driver.execute_script("arguments[0].click();", read_more_btn)

                    modal_quote = WebDriverWait(driver, 5).until(
                        EC.visibility_of_element_located((By.XPATH, '//*[@class="review-read-more-modal__quote"]'))
                    )
                    review = modal_quote.text.strip() # 모달창에 표시된 전체 리뷰

                    driver.find_element(By.TAG_NAME, 'body').send_keys(Keys.ESCAPE) #ESC로 모달창 닫기
                    time.sleep(0.5)
                except Exception as e:
                    self.logger.error(
                        "%d번째 리뷰 스포일러 전체 내용 가져올때 문제발생: %s: %s",
                        i + 1, type(e).__name__, e,
                    )
            
            blank.append(review)
            values.append(blank)
            print('---------------------------------------------------')

        self.df = pd.DataFrame(values, columns=columns)

        try:
            driver.quit()
        except Exception as e:
            self.logger.warning(f"드라이버 종료 중 오류 (세션이 이미 끊겼을 수 있음): {e}")


    def save_to_database(self) -> None:
        """수집한 리뷰를 CSV 파일로 저장한다."""
        os.makedirs(self.output_dir, exist_ok=True)
        output_path = os.path.join(self.output_dir, "reviews_metacritic.csv")

        df = self.df.reset_index(drop=True)
        df.index = df.index + 1
        df.to_csv(output_path, encoding="utf-8-sig")