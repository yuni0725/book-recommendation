import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
import csv
import requests
import os
from dotenv import load_dotenv

# .env 파일에서 API 키 로드
load_dotenv()
APIKey = os.getenv("KAKAO_API_KEY")


def search_kakao_book(title):
    try:
        isbn = int(title)
        base_url = "https://dapi.kakao.com/v3/search/book?target=isbn"
        headers = {"Authorization": f"KakaoAK {APIKey}"}
        params = {
            "query": isbn,
            "sort": "accuracy",
            "page": 1,
            "size": 10,
            "target": "isbn",
        }
    except:
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
        response = requests.get(base_url, params=params, headers=headers)
        result = response.json()
        book_result = result["documents"][0]

        processed_book = {
            "제목": book_result["title"],
            "저자": ", ".join(book_result["authors"]),
            "번역자": (
                ", ".join(book_result["translators"])
                if book_result["translators"]
                else None
            ),
            "ISBN": book_result["isbn"],
            "출판사": book_result["publisher"],
            "출간일": pd.to_datetime(book_result["datetime"]).strftime("%Y-%m-%d"),
            "썸네일": book_result["thumbnail"],
            "URL": book_result["url"],
        }

        if processed_book:
            return processed_book
        else:
            return {"error": "검색 결과가 없습니다."}

    except Exception as e:
        return {"error": f"에러 발생: {str(e)}"}


def scrape_kakao_book_with_playwright(url):
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        try:
            page.goto(url)

            target_element = page.wait_for_selector(
                ".desc:not(:empty)", state="visible", timeout=10000
            )
            html_content = target_element.inner_html()
            soup = BeautifulSoup(html_content, "html.parser")

            book_description = soup.text.replace("\n", "").strip()
            return book_description
        except Exception as e:
            print(f"스크래핑 중 오류 발생: {str(e)}")
            return None
        finally:
            browser.close()


def combine_book_info_with_description(book_info, kakao_book_info, url):
    book_description = scrape_kakao_book_with_playwright(url)
    kakao_book_info["책소개"] = book_description

    book_info_dict = book_info.to_dict("records")[0]
    combined_dict = {**book_info_dict, **kakao_book_info}

    combined_df = pd.DataFrame([combined_dict])
    return combined_df


def create_default_kakao_info():
    return {
        "제목": None,
        "저자": None,
        "번역자": None,
        "ISBN": None,
        "출판사": None,
        "출간일": None,
        "썸네일": None,
        "URL": None,
    }


def process_book(book_info, title):
    kakao_book_info = search_kakao_book(title)

    url = kakao_book_info["URL"]
    return combine_book_info_with_description(book_info, kakao_book_info, url)


def main():
    df = pd.read_csv(
        "dataset/drop_duplicates_book_data.csv",
        quoting=csv.QUOTE_ALL,  # 모든 필드를 따옴표로 감싸기
        escapechar="\\",  # 이스케이프 문자 설정
        encoding="utf-8",  # 인코딩 명시
    )

    error_df = pd.read_csv(
        "dataset/errors/error_books.csv",
        quoting=csv.QUOTE_ALL,
        escapechar="\\",
        encoding="utf-8",
        columns=["자료명"],
    )

    final_df = pd.read_csv(
        "dataset/kakao_info/add_kakao_info_interim.csv",
        quoting=csv.QUOTE_ALL,
        escapechar="\\",
        encoding="utf-8",
    )

    error_df = error_df["자료명"].tolist()

    for book in error_df:
        df = df[df["자료명"] == book]
        print(df["자료명"])
        print(book)
        title = input("제목 : ")

        if title == "0":
            continue
        elif title == "exit":
            break

        processed_book = process_book(df, title)

        # final_df에서 해당 도서 행을 찾아 processed_book으로 교체
        final_df.loc[final_df["자료명"] == book] = processed_book

        # error_df에서 해당 도서 삭제
        error_df.remove(book)

        # 변경된 데이터프레임 저장
        final_df.to_csv(
            "dataset/kakao_info/add_kakao_info_interim.csv",
            index=False,
            encoding="utf-8",
            quoting=csv.QUOTE_ALL,
            escapechar="\\",
        )
        # 에러 목록 업데이트
        pd.DataFrame(error_df, columns=["자료명"]).to_csv(
            "dataset/errors/error_books.csv",
            index=False,
            encoding="utf-8",
            quoting=csv.QUOTE_ALL,
            escapechar="\\",
        )

        print("\n모든 처리가 완료되었습니다.")


if __name__ == "__main__":
    main()
