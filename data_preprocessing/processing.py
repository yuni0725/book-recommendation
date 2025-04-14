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


nest_asyncio.apply()

ERROR_COUNT = 0
error_books_df = pd.DataFrame(columns=["자료명"])

load_dotenv()
APIKey = os.getenv("KAKAO_API_KEY")
ttbkey = os.getenv("ALADIN_API_KEY2")


def create_default_aladin_info():
    return {
        "알라딘표지": None,
        "알라딘ISBN13": None,
        "알라딘설명": None,
        "알라딘카테고리ID": None,
        "알라딘카테고리명": None,
    }


async def search_kakao_book(isbn):
    base_url = "https://dapi.kakao.com/v3/search/book?target=isbn"
    headers = {"Authorization": f"KakaoAK {APIKey}"}
    params = {
        "query": str(isbn),
        "sort": "accuracy",
        "page": 1,
        "size": 10,
        "target": "ISBN",
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
    global ERROR_COUNT
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

    book_info_dict = book_info.to_dict("records")[0]

    combined_dict = {**book_info_dict, **kakao_book_info}

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
    kakao_book_info = await search_kakao_book(book_isbn)

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

    os.makedirs("dataset/errors", exist_ok=True)

    df = pd.read_csv(
        "dataset/drop_duplicates_book_data.csv",
        quoting=csv.QUOTE_ALL,
        escapechar="\\",
        encoding="utf-8",
    )
    all_results = []

    BATCH_SIZE = 100
    CHUNK_SIZE = 10

    for batch_start in range(0, len(df), BATCH_SIZE):

        batch_end = min(batch_start + BATCH_SIZE, len(df))
        current_batch = df[batch_start:batch_end]

        print(f"\n=== 배치 처리 시작: {batch_start+1}~{batch_end} ===")

        for i in range(0, len(current_batch), CHUNK_SIZE):
            chunk = current_batch[i : i + CHUNK_SIZE]

            tasks = [process_book(pd.DataFrame([book])) for _, book in chunk.iterrows()]
            chunk_results = await asyncio.gather(*tasks)

            all_results.extend(chunk_results)

            print(
                f"처리된 도서: {batch_start + i + len(chunk)}/{len(df)} "
                f"({((batch_start + i + len(chunk))/len(df)*100):.2f}%)"
            )

        interim_df = pd.concat(all_results, ignore_index=True)
        interim_df.to_csv(
            "dataset/kakao_info/add_kakao_info_interim.csv",
            index=False,
            quoting=csv.QUOTE_ALL,
            escapechar="\\",
            encoding="utf-8",
            lineterminator="\n",
        )

        if not error_books_df.empty:
            error_books_df.drop_duplicates(subset=["자료명"], inplace=True)
            error_books_df.to_csv(
                "dataset/errors/error_books.csv",
                index=False,
                encoding="utf-8-sig",
                quoting=csv.QUOTE_ALL,
            )
            print(f"\n현재까지 발생한 에러 도서 수: {len(error_books_df)}")

        if batch_end < len(df):
            print(f"=== 다음 배치 처리를 위해 2초 대기 중... ===")
            await asyncio.sleep(2)

    final_df = pd.concat(all_results, ignore_index=True)
    final_df.to_csv(
        "dataset/kakao_info/add_kakao_info.csv",
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
    asyncio.run(main())
