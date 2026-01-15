from langchain_openai import ChatOpenAI
from dotenv import load_dotenv
from langchain_openai.embeddings import OpenAIEmbeddings
from supabase import create_client
import json
import os

load_dotenv()

llm = ChatOpenAI(model="gpt-4o-mini", temperature=0.3)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

supabase = create_client(SUPABASE_URL, SUPABASE_KEY)


def retrieval(query):
    query_embedding = OpenAIEmbeddings(model="text-embedding-3-small").embed_query(
        query
    )

    response = (
        supabase.rpc(
            "match_book", {"query_embedding": query_embedding, "filter": json.dumps({})}
        )
        .execute()
        .data
    )

    context_texts = "\n\n".join(
        [
            f"[{doc.get('name', '제목 없음')}]\n{doc['description']}\nSimilarity:{doc['similarity']}"
            for doc in response
        ]
    )

    return context_texts


from langchain.prompts import ChatPromptTemplate

question_prompt = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """
            You are a professional book curator who recommends books by analyzing their summaries.
            You understand the reader's intent from their search query, and you provide thoughtful recommendations with clear reasoning.

            Below is the user's search query and a list of books whose summaries were retrieved based on that query.

            📌 User's query:
            "{query}"

            📚 Relevant book summaries:
            {context}

            Please recommend books from the context that best match the user's query.
            For each book, explain *why* it fits the query.

            Use the tone, format, and detail level of the following example recommendation as a model:

            ✨ Sample recommendation to imitate:
            {book_recommendation_sample}
    
            ALERT
            Please write in Korean.
            Your output should be markdown format.
            Do not use emojis.
            
            
            Now, generate your recommendation below in the same style:
            """,
        ),
    ]
)


from langchain_core.runnables import RunnablePassthrough

query = "파이썬"
book_recommendation_sample = """
    한때 유행했던 일만 시간의 법칙을 기억하는가? 어떤 분야에서 전문가가 되려면 최소한 일만 시간의 훈련이 필요하다는 개념이다. 
    하지만 단순히 연습의 양이 많다고 해서 모두가 전문가가 되는 것은 아니다. 이 책은 심리학자이자 다중언어 구사자, 테니스 선수로도 활약했던 저자가 학습과 훈련, 그리고 기량 향상의 상관관계를 연구한 결과를 담고 있다. 
    장 피아제, 노엄 촘스키, 그리고 일만 시간의 법칙을 제창한 심리학자 안데르스 에릭손 등 대가들의 이론 및 최신 연구 결과를 바탕으로, 뇌과학과 인지심리학적 관점에서 '제대로 연습하는 법'을 탐구한다. 
    아마추어 스포츠 선수, 유명 체스 선수, 다중언어 구사자, 피아노 연주자 등 다양한 사례 분석을 통해 연습의 물리적 양보다 중요한 것은 질적인 측면임을 강조한다. 적절한 휴식 속에서 배운 것을 재조합하고, 몰입 상태에서 연습할 때 비로소 '최고'라는 목표에 도달할 수 있는 것이다. 
    벌써 2025년이 100일 넘게 흘렀다. 완연한 봄을 맞이하여 새로운 기술을 배우고 싶거나, 그동안 노력에 비해 실력이 늘지 않는다고 느껴왔다면, 이 책을 길잡이 삼아 ‘제대로 연습하는 법’을 배워보면 어떨까?
"""
chain = RunnablePassthrough() | question_prompt | llm

result = chain.invoke(
    {
        "context": retrieval(query),
        "query": query,
        "book_recommendation_sample": book_recommendation_sample,
    }
)
