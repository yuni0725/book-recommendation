import pandas as pd
import asyncio
import nest_asyncio
from bs4 import BeautifulSoup, Comment
from playwright.async_api import async_playwright
import csv

# nest-asyncio 설정
nest_asyncio.apply()

# 전역 변수로 에러 카운트 설정
ERROR_COUNT = 0


def search_aladin_book(title):
    import requests
    import os
    from dotenv import load_dotenv

    # .env 파일에서 API 키 로드
    load_dotenv()
    ttbkey = os.getenv("ALADIN_API_KEY")

    base_url = "http://www.aladin.co.kr/ttb/api/ItemSearch.aspx"
    params = {
        "TTBKey": ttbkey,
        "Query": title,
        "QueryType": "Keyword",
        "MaxResults": 10,
        "start": 1,
        "SearchTarget": "Book",
        "output": "js",
        "Version": "20131101",
        "Sort": "Accuracy",
    }

    try:
        response = requests.get(base_url, params=params)
        result = response.json()

        # 검색 결과가 있는 경우
        if "item" in result and result["item"]:
            book = result["item"][0]  # 첫 번째 검색 결과

            # 필요한 정보만 추출하여 새로운 딕셔너리 생성
            book_info = {
                # 기본 정보
                "알라딘제목": book.get("title", ""),
                "알라딘원제": book.get("originalTitle", ""),
                "알라딘저자": book.get("author", ""),
                "알라딘출판사": book.get("publisher", ""),
                "알라딘출판일": book.get("pubDate", ""),
                # ISBN 정보
                "ISBN13": book.get("isbn13", ""),
                "ISBN": book.get("isbn", ""),
                # 상세 정보
                "알라딘책 설명": book.get("description", "").replace("\n", ""),
                "알라딘목차": book.get("toc", ""),
                "알라딘부가제목": book.get("subTitle", ""),
                # 분류 정보
                "알라딘카테고리ID": book.get("categoryId", ""),
                "알라딘카테고리명": book.get("categoryName", ""),
                # 이미지 정보
                "알라딘표지 이미지(작은버전)": book.get("coverSmallUrl", ""),
                "알라딘표지 이미지(중간버전)": book.get("cover", ""),
                "알라딘표지 이미지(큰버전)": book.get("coverLargeUrl", ""),
                # 부가 정보
                "알라딘상품 링크": book.get("link", ""),
            }
            return book_info
        else:
            return {"error": "검색 결과가 없습니다."}

    except Exception as e:
        return {"error": f"에러 발생: {str(e)}"}


def scrape_after_comment(html_content, target_comment):
    soup = BeautifulSoup(html_content, "html.parser")

    # 모든 주석을 찾습니다
    comments = soup.find_all(string=lambda text: isinstance(text, Comment))

    for comment in comments:
        if target_comment in comment.string:
            # 주석 노드의 다음 형제 요소들을 찾습니다
            next_elements = comment.find_next_siblings()

            # 결과를 저장할 리스트
            content_after_comment = []

            for element in next_elements:
                # 다른 주석을 만나면 중단
                if isinstance(element, Comment):
                    break
                content_after_comment.append(element)
            return content_after_comment

    return None


async def scrape_aladin_book_with_selenium(url):
    global ERROR_COUNT  # 전역 변수 사용 선언
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url)

            # 페이지의 절반 높이까지 스크롤
            await page.evaluate(
                """
                () => {
                    const totalHeight = document.body.scrollHeight;
                    window.scrollTo(0, totalHeight / 2);
                }
            """
            )
            await asyncio.sleep(1)
            target_element = await page.wait_for_selector(
                ".Ere_prod_middlewrap", timeout=10000
            )
            html_content = await target_element.inner_html()
            result = scrape_after_comment(html_content, "책소개")
            if result is None:
                return None
            return (
                result[1]
                .find("div", class_="Ere_prod_mconts_R")
                .text.replace("\n", "")
                .strip()
            )
        except Exception as e:
            ERROR_COUNT += 1
            print(f"스크래핑 중 오류 발생: {str(e)}")
            return None
        finally:
            await browser.close()


async def combine_book_info_with_description(book_info, aladin_book_info, url):
    book_description = await scrape_aladin_book_with_selenium(url)
    aladin_book_info["알라딘책소개"] = book_description

    # book_info를 딕셔너리로 변환
    book_info_dict = book_info.to_dict("records")[0]

    # aladin_book_info와 book_info_dict를 합침
    combined_dict = {**book_info_dict, **aladin_book_info}

    # 하나의 행을 가진 데이터프레임으로 변환
    return pd.DataFrame([combined_dict])


def create_default_aladin_info():
    return {
        "알라딘제목": None,
        "알라딘원제": None,
        "알라딘저자": None,
        "알라딘출판사": None,
        "알라딘출판일": None,
        "ISBN13": None,
        "ISBN": None,
        "알라딘책 설명": None,
        "알라딘목차": None,
        "알라딘부가제목": None,
        "알라딘카테고리ID": None,
        "알라딘카테고리명": None,
        "알라딘표지 이미지(작은버전)": None,
        "알라딘표지 이미지(중간버전)": None,
        "알라딘표지 이미지(큰버전)": None,
        "알라딘상품 링크": None,
        "알라딘책소개": None,
    }


async def process_book(book_info):
    global ERROR_COUNT

    book_title = book_info["자료명"]
    aladin_book_info = search_aladin_book(book_title)

    if "error" in aladin_book_info:
        ERROR_COUNT += 1
        print(f"검색 실패: {book_title} - {aladin_book_info['error']}")
        default_info = create_default_aladin_info()
        return pd.DataFrame([{**book_info.to_dict("records")[0], **default_info}])

    try:
        url = aladin_book_info["알라딘상품 링크"]
        return await combine_book_info_with_description(
            book_info, aladin_book_info, url
        )

    except Exception as e:
        ERROR_COUNT += 1
        print(f"처리 중 에러 발생: {book_title} - {str(e)}")
        default_info = create_default_aladin_info()
        return pd.DataFrame([{**book_info.to_dict("records")[0], **default_info}])


async def main():
    global ERROR_COUNT
    import time

    # 데이터 로드 시 quoting 파라미터 추가
    df = pd.read_csv(
        "dataset/processed_book_info_data_1.csv",
        quoting=csv.QUOTE_ALL,  # 모든 필드를 따옴표로 감싸기
        escapechar="\\",  # 이스케이프 문자 설정
        encoding="utf-8",  # 인코딩 명시
    )

    # 결과를 저장할 리스트
    all_results = []

    # 100개씩 처리하기 위한 설정
    BATCH_SIZE = 100
    CHUNK_SIZE = 3

    # 전체 데이터를 100개씩 나누어 처리
    for batch_start in range(0, len(df), BATCH_SIZE):
        batch_start_time = time.time()  # 배치 시작 시간 기록

        batch_end = min(batch_start + BATCH_SIZE, len(df))
        current_batch = df[batch_start:batch_end]

        print(f"\n=== 배치 처리 시작: {batch_start+1}~{batch_end} ===")

        # 현재 배치를 청크로 나누어 처리
        for i in range(0, len(current_batch), CHUNK_SIZE):
            chunk = current_batch[i : i + CHUNK_SIZE]

            # 현재 청크의 모든 책을 동시에 처리
            tasks = [process_book(pd.DataFrame([book])) for _, book in chunk.iterrows()]
            chunk_results = await asyncio.gather(*tasks)

            # 결과 저장
            all_results.extend(chunk_results)

            # 진행 상황 출력
            print(
                f"처리된 도서: {batch_start + i + len(chunk)}/{len(df)} "
                f"({((batch_start + i + len(chunk))/len(df)*100):.2f}%)"
            )

            # API 서버 부하 방지를 위한 딜레이
            await asyncio.sleep(1)

        # 현재까지의 결과를 중간 저장
        interim_df = pd.concat(all_results, ignore_index=True)
        interim_df.to_csv(
            "dataset/add_aladin_info_interim.csv",
            index=False,
            quoting=csv.QUOTE_ALL,
            escapechar="\\",
            encoding="utf-8",
            lineterminator="\n",
        )

        # 배치 처리 시간 계산 및 출력
        batch_end_time = time.time()
        batch_duration = batch_end_time - batch_start_time
        minutes = int(batch_duration // 60)
        seconds = int(batch_duration % 60)
        print(f"\n=== 배치 처리 완료. 소요 시간: {minutes}분 {seconds}초 ===")

        # 마지막 배치가 아닌 경우 3분 대기
        if batch_end < len(df):
            print(f"=== 다음 배치 처리를 위해 1분 대기 중... ===")
            await asyncio.sleep(60)

    # 모든 결과를 하나의 데이터프레임으로 합치기
    final_df = pd.concat(all_results, ignore_index=True)

    # 최종 결과를 CSV 파일로 저장
    final_df.to_csv(
        "dataset/add_aladin_info_1.csv",
        index=False,
        quoting=csv.QUOTE_ALL,
        escapechar="\\",
        encoding="utf-8",
        lineterminator="\n",
    )

    print("\n모든 처리가 완료되었습니다.")
    print(f"총 처리된 도서 수: {len(final_df)}")
    print(f"총 에러 발생 횟수: {ERROR_COUNT}")

    return final_df


if __name__ == "__main__":
    # 비동기 실행
    asyncio.run(main())
