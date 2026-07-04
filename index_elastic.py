import json
import os
from elasticsearch import Elasticsearch, helpers
from config import OUTPUT_DIR, ELASTIC_HOST, ELASTIC_INDEX


def create_index(es):
    if es.indices.exists(index=ELASTIC_INDEX):
        es.indices.delete(index=ELASTIC_INDEX)

    mapping = {
        "mappings": {
            "properties": {
                "doc_id": {"type": "keyword"},
                "chunk_index": {"type": "integer"},
                "text": {"type": "text", "analyzer": "standard"},
                "geography": {"type": "keyword"},
                "years": {"type": "integer"},
                "conditions": {
                    "properties": {
                        "parameter": {"type": "keyword"},
                        "operator": {"type": "keyword"},
                        "value": {"type": "float"},
                        "unit": {"type": "keyword"}
                    }
                },
                "terms": {
                    "properties": {
                        "category": {"type": "keyword"},
                        "canonical": {"type": "keyword"}
                    }
                },
                "metadata": {
                    "properties": {
                        "source": {"type": "keyword"},
                        "filename": {"type": "keyword"}
                    }
                }
            }
        }
    }
    es.indices.create(index=ELASTIC_INDEX, body=mapping)


def index_chunks(annotated_chunks):
    es = Elasticsearch(ELASTIC_HOST)
    create_index(es)

    actions = []
    for chunk in annotated_chunks:
        doc = {
            "_index": ELASTIC_INDEX,
            "_source": {
                "doc_id": chunk['doc_id'],
                "chunk_index": chunk['chunk_index'],
                "text": chunk['text'],
                "geography": chunk.get('geography'),
                "years": chunk.get('years', []),
                "conditions": chunk.get('conditions', []),
                "terms": chunk.get('terms', []),
                "metadata": chunk.get('metadata', {})
            }
        }
        actions.append(doc)

    success, errors = helpers.bulk(es, actions, chunk_size=100)
    print(f"Индексировано {success} чанков. Ошибок: {len(errors) if errors else 0}")


def main():
    input_path = os.path.join(OUTPUT_DIR, 'annotated_chunks.json')
    with open(input_path, 'r', encoding='utf-8') as f:
        annotated = json.load(f)
    index_chunks(annotated)


if __name__ == '__main__':
    main()