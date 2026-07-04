import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import json
import networkx as nx
from pyvis.network import Network
from neo4j import GraphDatabase
from config import GRAPH_DIR, OUTPUT_DIR, NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD

# ---------- ПОСТРОЕНИЕ ГРАФА В NEO4j ----------
def build_neo4j_graph():
    input_file = OUTPUT_DIR / "annotated_chunks.json"
    if not input_file.exists():
        print("⚠️ Файл annotated_chunks.json не найден. Сначала запустите nlp_pipeline.py")
        return

    with open(input_file, encoding='utf-8') as f:
        chunks = json.load(f)

    print(f"🔄 Загрузка {len(chunks)} документов в Neo4j...")

    driver = GraphDatabase.driver(NEO4J_URI, auth=(NEO4J_USER, NEO4J_PASSWORD))

    with driver.session() as session:
        session.run("MATCH (n) DETACH DELETE n")
        print("✅ Старый граф очищен")
        session.run("CREATE INDEX IF NOT EXISTS FOR (n:Entity) ON (n.name)")

        for chunk in chunks:
            doc_id = chunk.get('doc_id', 'unknown')
            session.run(
                "MERGE (d:Document {filename: $doc_id})",
                doc_id=doc_id
            )

            for cond in chunk.get('conditions', []):
                param = cond.get('parameter', '')
                op = cond.get('operator', '')
                value = cond.get('value', '')
                unit = cond.get('unit', '')
                session.run(
                    """
                    MERGE (c:Condition {parameter: $param, operator: $op, value: $value, unit: $unit})
                    WITH c
                    MATCH (d:Document {filename: $doc_id})
                    MERGE (d)-[:MENTIONS]->(c)
                    """,
                    param=param, op=op, value=value, unit=unit, doc_id=doc_id
                )

            for term in chunk.get('terms', []):
                term_name = term.get('canonical', '')
                if not term_name:
                    continue
                cat = term.get('category', 'unknown')
                session.run(
                    """
                    MERGE (e:Entity {name: $name, type: $type})
                    WITH e
                    MATCH (d:Document {filename: $doc_id})
                    MERGE (d)-[:MENTIONS]->(e)
                    """,
                    name=term_name, type=cat, doc_id=doc_id
                )

            for triple in chunk.get('triples', []):
                subj = triple.get('subject', '')
                pred = triple.get('predicate', '')
                obj = triple.get('object', '')
                if not subj or not obj:
                    continue
                session.run(
                    """
                    MERGE (s:Entity {name: $subj})
                    MERGE (o:Entity {name: $obj})
                    WITH s, o
                    MATCH (d:Document {filename: $doc_id})
                    MERGE (d)-[:MENTIONS]->(s)
                    MERGE (d)-[:MENTIONS]->(o)
                    MERGE (s)-[:REL {type: $pred}]->(o)
                    """,
                    subj=subj, obj=obj, pred=pred, doc_id=doc_id
                )

        print("✅ Граф успешно загружен в Neo4j")
    driver.close()


# ---------- СОЗДАНИЕ ВИЗУАЛИЗАЦИИ (HTML) ----------
def create_visualization(limit=500):
    """
    Генерирует интерактивную визуализацию графа.
    limit — максимальное число узлов (None — без ограничения).
    """
    input_file = OUTPUT_DIR / "annotated_chunks.json"
    if not input_file.exists():
        print("⚠️ Файл annotated_chunks.json не найден.")
        return

    with open(input_file, encoding='utf-8') as f:
        chunks = json.load(f)

    G = nx.DiGraph()

    for chunk in chunks:
        doc_id = chunk.get('doc_id', 'unknown')
        G.add_node(doc_id, label=doc_id, type='Document')

        for term in chunk.get('terms', []):
            term_name = term.get('canonical', '')
            if not term_name:
                continue
            G.add_node(term_name, label=term_name, type=term.get('category', 'entity'))
            G.add_edge(doc_id, term_name, label='MENTIONS')

        for triple in chunk.get('triples', []):
            subj = triple.get('subject', '')
            obj = triple.get('object', '')
            pred = triple.get('predicate', '')
            if subj and obj:
                G.add_node(subj, label=subj, type='entity')
                G.add_node(obj, label=obj, type='entity')
                G.add_edge(subj, obj, label=pred)

    if len(G.nodes) == 0:
        print("⚠️ Граф пуст. Нет данных для визуализации.")
        return

    # Ограничиваем число узлов, если задано
    if limit is not None and len(G.nodes) > limit:
        nodes_to_keep = list(G.nodes)[:limit]
        G = G.subgraph(nodes_to_keep)
        print(f"⚠️ Граф ограничен {limit} узлами (всего {len(G.nodes)})")

    net = Network(height="950px", width="100%", directed=True, bgcolor="#f8f9fa", font_color="black")
    net.from_nx(G)

    for node in net.nodes:
        node['size'] = 15
        node['font'] = {'size': 12}
    for edge in net.edges:
        edge['width'] = 1
        edge['color'] = '#2c3e50'

    GRAPH_DIR.mkdir(parents=True, exist_ok=True)
    output_html = GRAPH_DIR / "knowledge_graph.html"
    net.save_graph(str(output_html))
    print(f"✅ Визуализация сохранена: {output_html}")


# ---------- ГЛАВНАЯ ----------
if __name__ == "__main__":
    build_neo4j_graph()
    # Указываем лимит (можно изменить или передать None для отключения)
    create_visualization(limit=500)