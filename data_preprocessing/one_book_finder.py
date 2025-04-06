import requests
import os
from dotenv import load_dotenv
import asyncio
from bs4 import BeautifulSoup, Comment
from playwright.async_api import async_playwright

# .env 파일에서 API 키 로드
load_dotenv()
ttbkey = os.getenv("ALADIN_API_KEY1")


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
            print(f"스크래핑 중 오류 발생: {str(e)}")
            return None
        finally:
            await browser.close()


async def get_book_by_itemid(item_id):
    base_url = "http://www.aladin.co.kr/ttb/api/ItemLookUp.aspx"
    params = {
        "TTBKey": ttbkey,
        "ItemId": item_id,
        "ItemIdType": "ItemId",
        "Output": "js",
        "Version": "20131101",
    }

    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()

        if not data.get("item"):
            return None

        book = data["item"][0]

        # 책 소개 정보를 비동기적으로 가져오기
        book_intro = await scrape_aladin_book_with_selenium(book.get("link", ""))

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
            "알라딘책소개": book_intro,
        }

        return book_info

    except requests.exceptions.RequestException as e:
        print(f"API 요청 중 오류 발생: {e}")
        return None


# 사용 예시
if __name__ == "__main__":
    item_id = input("책")

    # 비동기 함수 실행을 위한 이벤트 루프 생성
    async def main():
        result = await get_book_by_itemid(item_id)
        if result:
            print(",".join([f'"{str(value)}"' for value in result.values()]))

    # 이벤트 루프 실행
    asyncio.run(main())
