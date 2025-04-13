import pandas as pd
import asyncio
import nest_asyncio
from bs4 import BeautifulSoup
from playwright.async_api import async_playwright
import csv
from datetime import datetime
import aiohttp
import os
from dotenv import load_dotenv

# nest-asyncio 설정
nest_asyncio.apply()

# 전역 변수로 에러 카운트와 에러 발생 책 리스트 설정
ERROR_COUNT = 0
error_books_df = pd.DataFrame(columns=["자료명"])  # 에러 도서를 저장할 데이터프레임

# .env 파일에서 API 키 로드
load_dotenv()
APIKey = os.getenv("KAKAO_API_KEY")
ttbkey = os.getenv("ALADIN_API_KEY2")


def create_default_aladin_info():
    """알라딘 API 응답이 실패했을 때 사용할 기본값을 반환하는 함수"""
    return {
        "알라딘표지": None,
        "알라딘ISBN13": None,
        "알라딘설명": None,
        "알라딘카테고리ID": None,
        "알라딘카테고리명": None,
    }


async def search_kakao_book(title):
    base_url = "https://dapi.kakao.com/v3/search/book?target=title"
    headers = {"Authorization": f"KakaoAK {APIKey}"}
    params = {
        "query": str(title),
        "sort": "accuracy",
        "page": 1,
        "size": 10,
        "target": "title",
    }

    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(
                base_url, params=params, headers=headers
            ) as response:
                result = await response.json()
                book_result = result["documents"][0]

                isbn = book_result["isbn"].split(" ")[1]

                processed_book = {
                    "카카오제목": book_result["title"],
                    "카카오작가": ", ".join(book_result["authors"]),
                    "카카오번역자": (
                        ", ".join(book_result["translators"])
                        if book_result["translators"]
                        else None
                    ),
                    "카카오ISBN": isbn,
                    "카카오출판사": book_result["publisher"],
                    "카카오출간일": pd.to_datetime(book_result["datetime"]).strftime(
                        "%Y-%m-%d"
                    ),
                    "카카오썸네일": book_result["thumbnail"],
                    "카카오URL": book_result["url"],
                }

                if processed_book:
                    return processed_book
                else:
                    return {"error": "검색 결과가 없습니다."}

    except Exception as e:
        return {"error": f"에러 발생: {str(e)}"}


async def scrape_kakao_book_with_playwright(url):
    global ERROR_COUNT  # 전역 변수 사용 선언
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        page = await browser.new_page()
        try:
            await page.goto(url)

            target_element = await page.wait_for_selector(".desc", timeout=3000)
            html_content = await target_element.inner_html()
            soup = BeautifulSoup(html_content, "html.parser")

            book_description = soup.text.replace("\n", "").strip()
            return book_description
        except Exception as e:
            ERROR_COUNT += 1
            print(f"스크래핑 중 오류 발생: {str(e)}")
            return None
        finally:
            await browser.close()


async def combine_book_info_with_description(book_info, kakao_book_info, url):
    book_description = await scrape_kakao_book_with_playwright(url)
    kakao_book_info["책소개"] = book_description

    # book_info를 딕셔너리로 변환
    book_info_dict = book_info.to_dict("records")[0]

    # kakao_book_info와 book_info_dict를 합침
    combined_dict = {**book_info_dict, **kakao_book_info}

    # 하나의 행을 가진 데이터프레임으로 변환
    return pd.DataFrame([combined_dict])


def create_default_kakao_info():
    return {
        "카카오제목": None,
        "카카오작가": None,
        "카카오번역자": None,
        "카카오ISBN": None,
        "카카오출판사": None,
        "카카오출간일": None,
        "카카오썸네일": None,
        "카카오URL": None,
    }


def save_error_books():
    """오류가 발생한 책들을 CSV 파일로 저장하는 함수"""
    if error_books_df.empty:
        print("에러가 발생한 도서가 없습니다.")
    else:
        current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
        error_books_df.to_csv(
            f"dataset/errors/error_books_{current_time}.csv",
            index=False,
            encoding="utf-8-sig",
            quoting=csv.QUOTE_ALL,
        )
        print(
            f"\n에러가 발생한 도서 목록이 저장되었습니다: error_books_{current_time}.csv"
        )


async def process_book(book_info):
    global ERROR_COUNT, error_books_df
    book_title = book_info["자료명"].iloc[0]
    book_isbn = book_info["ISBN"].iloc[0]
    kakao_book_info = await search_kakao_book(book_title)

    if "error" in kakao_book_info:
        ERROR_COUNT += 1
        error_books_df = pd.concat(
            [error_books_df, book_info[["자료명"]]], ignore_index=True
        )
        print(f"검색 실패: {book_title}")
        default_info = create_default_kakao_info()
        return pd.DataFrame([{**book_info.to_dict("records")[0], **default_info}])

    try:
        url = kakao_book_info["카카오URL"]
        return await combine_book_info_with_description(book_info, kakao_book_info, url)

    except Exception as e:
        ERROR_COUNT += 1
        error_books_df = pd.concat(
            [error_books_df, book_info[["자료명"]]], ignore_index=True
        )
        print(f"처리 중 에러 발생: {book_title}")
        default_info = create_default_kakao_info()
        return pd.DataFrame([{**book_info.to_dict("records")[0], **default_info}])


async def main():
    global ERROR_COUNT, error_books_df

    # errors 디렉토리 생성
    os.makedirs("dataset/errors", exist_ok=True)

    # 데이터 로드 시 quoting 파라미터 추가
    df = pd.read_csv(
        "dataset/errors/카카오없음.csv",
        quoting=csv.QUOTE_ALL,  # 모든 필드를 따옴표로 감싸기
        escapechar="\\",  # 이스케이프 문자 설정
        encoding="utf-8",  # 인코딩 명시
    )

    # 결과를 저장할 리스트
    all_results = []

    # 100개씩 처리하기 위한 설정
    BATCH_SIZE = 100
    CHUNK_SIZE = 10

    # 전체 데이터를 100개씩 나누어 처리
    for batch_start in range(0, len(df), BATCH_SIZE):

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

        # 현재까지의 결과를 중간 저장
        interim_df = pd.concat(all_results, ignore_index=True)
        interim_df.to_csv(
            "dataset/errors/error_books_interim.csv",
            index=False,
            quoting=csv.QUOTE_ALL,
            escapechar="\\",
            encoding="utf-8",
            lineterminator="\n",
        )

        # 현재까지의 에러 도서 목록 저장
        if not error_books_df.empty:
            # 중복 제거
            error_books_df.drop_duplicates(subset=["자료명"], inplace=True)
            error_books_df.to_csv(
                "dataset/errors/에러_도서목록.csv",
                index=False,
                encoding="utf-8-sig",
                quoting=csv.QUOTE_ALL,
            )
            print(f"\n현재까지 발생한 에러 도서 수: {len(error_books_df)}")

        # 마지막 배치가 아닌 경우 대기
        if batch_end < len(df):
            print(f"=== 다음 배치 처리를 위해 2초 대기 중... ===")
            await asyncio.sleep(2)

    # 최종 결과를 CSV 파일로 저장
    final_df = pd.concat(all_results, ignore_index=True)
    final_df.to_csv(
        "dataset/errors/에러_도서목록.csv",
        index=False,
        quoting=csv.QUOTE_ALL,
        escapechar="\\",
        encoding="utf-8",
        lineterminator="\n",
    )

    print("\n모든 처리가 완료되었습니다.")
    print(f"총 처리된 도서 수: {len(final_df)}")
    print(f"총 에러 발생 횟수: {ERROR_COUNT}")
    print(f"에러가 발생한 도서 수: {len(error_books_df)}")

    return final_df


if __name__ == "__main__":
    # 비동기 실행
    asyncio.run(main())
