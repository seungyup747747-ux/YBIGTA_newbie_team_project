# Review Analysis

## Letterboxd

# 1. EDA (Exploratory Data Analysis)

Letterboxd에서 수집한 500개의 리뷰를 분석한 결과, 전처리 이후 총 478개의 리뷰가 최종 분석에 사용되었다.

### (1) 별점 분포

별점은 전체적으로 높은 점수에 집중되어 있었으며, 4점과 5점 리뷰가 가장 많은 비중을 차지하였다. 평균 별점은 약 **3.99점**으로 나타났으며, 전반적으로 긍정적인 평가가 많은 플랫폼임을 확인할 수 있었다.

<p align="center">
<img src="review_analysis/plots/letterboxd_rating_distribution.png" width="600">
</p>

---

### (2) 리뷰 길이 분포

리뷰 길이는 짧은 리뷰가 가장 많았으며, 일부 매우 긴 리뷰가 존재하였다. Boxplot을 통해 긴 리뷰가 이상치처럼 보였지만 실제 사용자 리뷰였기 때문에 제거하지 않고 유지하였다.

<p align="center">
<img src="review_analysis/plots/letterboxd_review_length_distribution.png" width="600">
</p>

<p align="center">
<img src="review_analysis/plots/letterboxd_review_length_boxplot.png" width="600">
</p>

---

### (3) 언어 분포

Letterboxd는 글로벌 플랫폼이기 때문에 영어뿐 아니라 스페인어, 포르투갈어, 프랑스어 등 다양한 언어의 리뷰가 존재하였다. 전처리 과정에서 언어를 자동으로 감지하여 저장하였다.

<p align="center">
<img src="review_analysis/plots/letterboxd_language_distribution.png" width="600">
</p>

---

### (4) 시계열 분포

리뷰 작성 시점을 연도 및 월 단위로 분석하였다. 최근 시기에 리뷰가 집중되어 있었으며, 이는 크롤링한 페이지의 특성과 최근 사용자 활동의 영향을 함께 반영한 결과로 판단된다.

<p align="center">
<img src="review_analysis/plots/letterboxd_yearly_review_count.png" width="600">
</p>

<p align="center">
<img src="review_analysis/plots/letterboxd_latest_year_monthly_count.png" width="600">
</p>

---

### (5) 주요 키워드

언어별 TF-IDF를 이용하여 주요 단어를 추출하였다. 영어, 스페인어, 포르투갈어 리뷰를 각각 분석하여 플랫폼에서 자주 등장하는 핵심 단어를 확인하였다.

<p align="center">
<img src="review_analysis/plots/letterboxd_top_terms_en.png" width="600">
</p>

<p align="center">
<img src="review_analysis/plots/letterboxd_top_terms_es.png" width="600">
</p>

<p align="center">
<img src="review_analysis/plots/letterboxd_top_terms_pt.png" width="600">
</p>

---

# 2. 전처리 및 Feature Engineering

## (1) 결측치 처리

다음 항목에 결측치가 존재하는 데이터는 제거하였다.

- rating
- review
- date

분석에 반드시 필요한 정보이므로 별도의 대체(imputation)는 수행하지 않았다.

---

## (2) 이상치 처리

다음과 같은 데이터를 제거하거나 수정하였다.

- Letterboxd의 정상 범위(0.5~5.0)를 벗어난 별점
- 미래 날짜
- 완전히 동일한 중복 리뷰
- 비정상적인 공백
- HTML 태그
- URL
- Zero-width 문자

반면 긴 리뷰는 실제 사용자 리뷰일 가능성이 높으므로 제거하지 않았다.

---

## (3) 텍스트 전처리

다음 과정을 수행하였다.

- HTML 제거
- URL 제거
- Zero-width 문자 제거
- Unicode 정규화
- 공백 정리
- Spoiler 문구 제거
- 원본 리뷰(raw_review)와 전처리 리뷰(cleaned_review)를 모두 저장

---

## (4) 파생 변수 생성

다음 Feature를 추가하였다.

- review_length
- word_count
- emoji_count
- exclamation_count
- question_count
- uppercase_ratio
- is_long_review
- year
- month
- day
- weekday
- is_weekend
- language
- language_probability
- is_positive
- is_negative

---

## (5) 텍스트 벡터화

텍스트는 Character N-gram 기반 TF-IDF를 사용하여 벡터화하였다.

Letterboxd에는 다양한 언어가 포함되어 있기 때문에 일반적인 Word TF-IDF보다 Character N-gram 방식이 여러 언어에 대해 안정적으로 동작하였다.

고차원의 TF-IDF 벡터는 Truncated SVD를 이용하여 차원을 축소한 뒤 Feature로 저장하였다.

---

## (6) 결과 저장

최종 결과는 아래 파일로 저장하였다.

```
database/preprocessed_reviews_letterboxd.csv
```

---

## Naver

# 1. EDA (Exploratory Data Analysis)

네이버 영화 관람평에서 수집한 500개의 리뷰를 분석하였다. 결측치, 비정상 별점, 날짜 이상치, 짧은 리뷰, 중복 리뷰를 점검한 결과 제거된 행 없이 총 500개의 리뷰가 최종 분석에 사용되었다.

### (1) 크롤링 데이터

네이버 통합검색 영화 관람평 영역에서 별점, 작성일, 리뷰 본문, 작성자 정보를 수집하였다. 네이버 리뷰 영역은 페이지 전체가 아니라 리뷰 박스 내부에서 추가 리뷰가 로드되는 구조이므로 Selenium으로 리뷰 리스트 영역을 스크롤하며 데이터를 수집하였다.

최종 원본 데이터는 아래 파일로 저장하였다.

```
database/reviews_naver.csv
```

---

### (2) 별점 분포

네이버 별점은 10점 만점 기준으로 수집되었다. 평균 별점은 약 **8.89점**, 중앙값은 **10점**으로 나타났으며, 전체 리뷰 중 약 **84.2%**가 8점 이상이었다. 따라서 네이버 관람평은 전반적으로 높은 평점에 집중된 분포를 보였다.

<p align="center">
<img src="review_analysis/plots/naver_rating_distribution.png" width="600">
</p>

---

### (3) 리뷰 길이 분포

리뷰 길이는 평균 약 **44.46자**, 중앙값 **26자**로 짧은 리뷰가 많은 편이었다. 다만 최대 길이는 324자로 일부 긴 감상평도 존재하였다. 긴 리뷰는 실제 사용자 리뷰로 판단하여 제거하지 않고 `is_long_review` 파생 변수로 별도 표시하였다.

<p align="center">
<img src="review_analysis/plots/naver_review_length_distribution.png" width="600">
</p>

---

### (4) 시계열 분포

리뷰 작성일은 2022년 12월 14일부터 2026년 3월 1일까지 분포하였다. 월별 리뷰 수를 확인하여 영화 개봉 이후 시점별 관심도 변화를 확인할 수 있도록 하였다.

<p align="center">
<img src="review_analysis/plots/naver_monthly_reviews.png" width="600">
</p>

---

### (5) 요일별 분포

요일별 리뷰 수를 비교한 결과 주말 리뷰 비중을 별도로 확인할 수 있었다. 이후 플랫폼 비교분석에서 사이트별 사용자 활동 시점 차이를 비교하는 기준으로 활용할 수 있다.

<p align="center">
<img src="review_analysis/plots/naver_weekday_reviews.png" width="600">
</p>

---

### (6) 주요 키워드

정제된 리뷰 텍스트에서 불용어와 숫자를 제외한 뒤 주요 단어 빈도를 확인하였다. 네이버 리뷰는 한국어 리뷰가 중심이므로 Word 기반 토큰을 사용하였다.

<p align="center">
<img src="review_analysis/plots/naver_top_words.png" width="600">
</p>

---

# 2. 전처리 및 Feature Engineering

## (1) 결측치 처리

다음 항목에 결측치 또는 형식 오류가 존재하는 데이터는 제거하도록 처리하였다.

- rating
- review
- date

이번 네이버 데이터에서는 해당 조건으로 제거된 행은 없었다.

---

## (2) 이상치 처리

다음과 같은 데이터를 제거하거나 별도 변수로 표시하였다.

- 네이버 정상 범위(0~10)를 벗어난 별점
- 미래 날짜 및 비정상적으로 오래된 날짜
- 너무 짧은 리뷰
- 완전히 동일한 중복 리뷰
- 매우 긴 리뷰(`is_long_review`)

---

## (3) 텍스트 전처리

다음 과정을 수행하였다.

- HTML 제거
- URL 제거
- Zero-width 문자 제거
- Unicode 정규화
- 공백 정리
- 원본 리뷰(raw_review)와 정규화 리뷰(normalized_review), 벡터화용 리뷰(cleaned_review)를 모두 저장

---

## (4) 파생 변수 생성

다음 Feature를 추가하였다.

- review_length
- word_count
- review_length_log1p
- is_long_review
- year
- month
- day
- weekday
- hour
- is_weekend
- time_period
- is_positive
- is_negative
- rating_centered

---

## (5) 텍스트 벡터화

텍스트는 Word 기반 TF-IDF를 사용하여 벡터화하였다. 생성된 TF-IDF 벡터는 고차원이므로 Truncated SVD를 이용해 10개의 축약 텍스트 Feature(`text_svd_01`~`text_svd_10`)로 변환하였다.

---

## (6) 결과 저장

최종 결과는 아래 파일로 저장하였다.

```
database/preprocessed_reviews_naver.csv
```

---

# 3. 사이트 비교분석

> 아래 내용은 팀원들의 전처리 결과를 모두 취합한 뒤 작성하였다.

## (1) 별점 분포 비교

Letterboxd, Naver, Metacritic의 별점 분포를 비교하였다.

(팀 데이터 추가 예정)

---

## (2) 리뷰 길이 비교

플랫폼별 평균 리뷰 길이를 비교하였다.

(팀 데이터 추가 예정)

---

## (3) 주요 키워드 비교

각 사이트에서 TF-IDF를 통해 추출한 주요 키워드를 비교하였다.

(팀 데이터 추가 예정)

---

## (4) 시계열 비교

플랫폼별 리뷰 작성 시기의 변화를 비교하였다.

(팀 데이터 추가 예정)
