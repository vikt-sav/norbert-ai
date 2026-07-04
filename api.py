from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Dict, Optional
import aiohttp
from elasticsearch import Elasticsearch, NotFoundError
from neo4j import GraphDatabase
from config import (
    ELASTIC_HOST, ELASTIC_INDEX,
    NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD,
    ENABLE_WEB_SEARCH, WEB_SEARCH_RESULTS
)
from utils import extract_conditions, extract_geography, extract_years
from web_search import web_search
from llm_client import get_llm_client

app = FastAPI(title="Knowledge Graph API + GitHub Models (GPT-4o)")

# ---------- Подключение к Elasticsearch (опционально) ----------
es_available = False
es = None
try:
    es = Elasticsearch(ELASTIC_HOST)
    if es.ping():
        es_available = True
        print("✅ Elasticsearch доступен")
    else:
        print("⚠️ Elasticsearch не отвечает на ping. Поиск в ES будет пропущен.")
except Exception as e:
    print(f"⚠️ Ошибка подключения к Elasticsearch: {e}. Поиск в ES будет пропущен.")

# ---------- Подключение к Neo4j (обязательно) ----------
try:
    neo4j_driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))
    # Проверка подключения
    with neo4j_driver.session() as session:
        session.run("RETURN 1")
    print("✅ Neo4j доступен")
except Exception as e:
    print(f"❌ Критическая ошибка: Neo4j недоступен: {e}")
    raise


class SearchRequest(BaseModel):
    query: str
    filters: Optional[Dict] = {}
    use_web: bool = True


class SearchResponse(BaseModel):
    answer: str
    documents: List[Dict]
    graph_nodes: List[Dict]
    graph_edges: List[Dict]
    sources: List[Dict]
    web_sources: List[Dict]


@app.post("/search", response_model=SearchResponse)
async def search(request: SearchRequest):
    print("🔥 API: search() вызвана")

    query_text = request.query
    filters = request.filters or {}

    # 1. Извлечение условий, географии, годов
    conditions = extract_conditions(query_text)
    geography = extract_geography(query_text)
    years = extract_years(query_text)

    # 2. Поиск в Elasticsearch (если доступен)
    documents = []
    if es_available:
        es_query = {"bool": {"must": [{"match": {"text": query_text}}]}}
        if conditions:
            es_query["bool"]["filter"] = es_query["bool"].get("filter", [])
            for cond in conditions:
                es_query["bool"]["filter"].append({
                    "nested": {
                        "path": "conditions",
                        "query": {
                            "bool": {
                                "must": [
                                    {"term": {"conditions.parameter": cond['parameter']}},
                                    {"range": {"conditions.value": {"lte": cond['value'] if cond['operator'] == '<=' else cond['value']}}}
                                ]
                            }
                        }
                    }
                })
        if geography:
            es_query["bool"]["filter"] = es_query["bool"].get("filter", [])
            es_query["bool"]["filter"].append({"term": {"geography": geography}})
        if years:
            es_query["bool"]["filter"] = es_query["bool"].get("filter", [])
            es_query["bool"]["filter"].append({"range": {"years": {"gte": min(years), "lte": max(years)}}})

        try:
            es_results = es.search(index=ELASTIC_INDEX, body={"query": es_query, "size": 20})
            hits = es_results['hits']['hits']
            documents = [hit['_source'] for hit in hits]
            print(f"✅ Elasticsearch: найдено {len(documents)} документов")
        except Exception as e:
            print(f"⚠️ Ошибка поиска в Elasticsearch: {e}")

    # 3. Получение графа из Neo4j (всегда)
    doc_ids = [doc['doc_id'] for doc in documents] if documents else []
    graph_nodes = []
    graph_edges = []
    with neo4j_driver.session() as session:
        if doc_ids:
            result = session.run(
                """
                MATCH (d:Document)-[:MENTIONS]->(n)
                WHERE d.filename IN $doc_ids
                RETURN n
                """,
                doc_ids=doc_ids
            )
            for record in result:
                node = record['n']
                graph_nodes.append({
                    'id': node.id,
                    'labels': list(node.labels),
                    'properties': dict(node.items())
                })
            result_edges = session.run(
                """
                MATCH (d:Document)-[:MENTIONS]->(a), (d)-[:MENTIONS]->(b)
                WHERE d.filename IN $doc_ids AND a <> b
                MATCH (a)-[r]->(b)
                RETURN a, r, b
                """,
                doc_ids=doc_ids
            )
            for record in result_edges:
                a = record['a']
                b = record['b']
                r = record['r']
                graph_edges.append({
                    'source': a.id,
                    'target': b.id,
                    'type': r.type,
                    'properties': dict(r.items())
                })

    # 4. Веб-поиск (гибридный: DuckDuckGo + Crossref)
    web_sources = []
    use_web = ENABLE_WEB_SEARCH and request.use_web
    print(f"🔍 DEBUG: ENABLE_WEB_SEARCH={ENABLE_WEB_SEARCH}, request.use_web={request.use_web}, use_web={use_web}")

    if use_web:
        print("🔍 DEBUG: Вызываем web_search...")
        try:
            web_results = web_search(query_text, num_results=WEB_SEARCH_RESULTS)
            print(f"🔍 DEBUG: web_results = {type(web_results)}")

            # Проверяем тип результата
            if isinstance(web_results, dict):
                # Новая версия — объединяем оба списка
                combined = web_results.get("web", []) + web_results.get("academic", [])
                print(f"🔍 DEBUG: объединено {len(combined)} результатов (web: {len(web_results.get('web', []))}, academic: {len(web_results.get('academic', []))})")
            elif isinstance(web_results, list):
                # Старая версия — просто список
                combined = web_results
            else:
                combined = []
                print(f"⚠️ Неожиданный тип web_results: {type(web_results)}")

            for item in combined:
                if isinstance(item, dict):
                    web_sources.append({
                        "title": item.get("title", ""),
                        "snippet": item.get("snippet", ""),
                        "url": item.get("url", ""),
                        "authors": item.get("authors", ""),
                        "source": item.get("source", ""),
                        "year": item.get("year", ""),
                        "source_type": "web"
                    })
                else:
                    print(f"⚠️ Пропущен не-словарь в результатах: {item}")

        except Exception as e:
            print(f"⚠️ Ошибка веб-поиска: {e}")
    else:
        print("ℹ️ Веб-поиск отключён (ENABLE_WEB_SEARCH=False или request.use_web=False)")

    # 5. Формирование контекста для LLM
    local_context = "\n".join([doc.get('text', '')[:500] for doc in documents[:3]])
    web_context = "\n".join([
        f"- [{s['title']}]({s['url']}): {s['snippet'][:200]}..."
        for s in web_sources[:3]
    ])
    full_context = local_context
    if web_context:
        full_context += f"\n\nДополнительные результаты из интернета:\n{web_context}"

    # 6. Генерация ответа через GitHub Models (GPT-4o)
    try:
        llm_client = get_llm_client()
        answer = llm_client.generate_answer(query_text, full_context)
    except Exception as e:
        print(f"❌ Ошибка генерации ответа через GitHub Models: {e}")
        answer = "⚠️ Ошибка генерации ответа. Проверьте GITHUB_TOKEN в .env\n\n"
        if local_context:
            answer += f"📚 Найдено в локальных документах:\n{local_context[:500]}"
        if web_context:
            answer += f"\n\n🌐 Результаты веб-поиска:\n{web_context}"

    # 7. Формирование источников
    sources = [
        {
            'filename': doc.get('doc_id'),
            'snippet': doc.get('text', '')[:300] + "...",
            'conditions': doc.get('conditions', []),
            'source_type': 'local'
        }
        for doc in documents[:5]
    ]
    all_sources = sources + web_sources

    return SearchResponse(
        answer=answer,
        documents=documents,
        graph_nodes=graph_nodes,
        graph_edges=graph_edges,
        sources=all_sources,
        web_sources=web_sources
    )


@app.on_event("shutdown")
def shutdown():
    neo4j_driver.close()