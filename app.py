import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

import streamlit as st
import requests
import json
import pandas as pd
import sqlite3
from datetime import datetime
import re

# Импортируем конфиг
from config import PROFILES_DIR

# ---------- ФУНКЦИЯ ДЛЯ ИЗВЛЕЧЕНИЯ ПРОБЕЛОВ ----------
def extract_gaps(text: str) -> str:
    if not text:
        return ""
    markers = [
        r'\*\*Пробелы в знаниях[:\s]*\*\*',
        r'###\s*Пробелы в знаниях',
        r'Пробелы в знаниях[:\s]*',
        r'Gaps in knowledge[:\s]*',
        r'Пробелы и ограничения[:\s]*',
        r'\*\*Пробелы[:\s]*\*\*',
        r'###\s*Пробелы',
    ]
    for marker in markers:
        match = re.search(marker, text, re.IGNORECASE)
        if match:
            start = match.end()
            end_match = re.search(r'\n\s*(?:\*\*|###|\d+\.)', text[start:], re.IGNORECASE)
            end = start + end_match.start() if end_match else len(text)
            gaps_text = text[start:end].strip()
            if gaps_text:
                return gaps_text
    patterns = [
        r'(?:недостаточно|отсутствуют|не изучены|мало данных|пробелы|не освещены)\s*[:\s]+([\s\S]*?)(?=\n\s*(?:\*\*|###|\d+\.|$))',
        r'(?:рекомендации|предложения)\s*[:\s]+([\s\S]*?)(?=\n\s*(?:\*\*|###|\d+\.|$))'
    ]
    for pat in patterns:
        match = re.search(pat, text, re.IGNORECASE | re.DOTALL)
        if match:
            gaps_text = match.group(1).strip()
            if gaps_text:
                return gaps_text
    lines = text.split('\n')
    gap_lines = []
    for line in lines:
        stripped = line.strip()
        if stripped and (stripped.startswith('-') or stripped.startswith('*')):
            if any(word in stripped.lower() for word in ['недостаточно', 'отсутствуют', 'пробел', 'не изучены', 'мало данных', 'не освещены']):
                gap_lines.append(stripped)
    if gap_lines:
        return '\n'.join(gap_lines)
    return ""


# ---------- НАСТРОЙКИ СТРАНИЦЫ ----------
st.set_page_config(page_title="🔬 Норберт — научный консультант", layout="wide", page_icon="🔬")

st.title("🔬 Норберт — научный консультант")
st.subheader("Семантический поиск + граф знаний + LLM + веб-поиск + Crossref")
st.caption("Гибридный поиск: локальные данные, веб-поиск (DuckDuckGo) и академические публикации (Crossref)")

st.info("🚀 Используется GitHub Models (DeepSeek-R1) для генерации ответов и гибридный веб-поиск (DuckDuckGo + Crossref)")

# ---------- БАЗА ДАННЫХ ----------
PROFILES_DIR.mkdir(parents=True, exist_ok=True)
DB_PATH = PROFILES_DIR / "queries.db"

conn = sqlite3.connect(str(DB_PATH), check_same_thread=False)
c = conn.cursor()
c.execute("""
    CREATE TABLE IF NOT EXISTS query_history (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        timestamp TEXT,
        query TEXT,
        answer TEXT,
        sources TEXT
    )
""")
conn.commit()

# ---------- ФУНКЦИИ ИСТОРИИ ----------
def save_query(query, answer, sources):
    c.execute(
        "INSERT INTO query_history (timestamp, query, answer, sources) VALUES (?, ?, ?, ?)",
        (datetime.now().isoformat(), query, answer, json.dumps(sources))
    )
    conn.commit()

def load_history(limit=100):
    df = pd.read_sql_query(
        "SELECT timestamp, query, answer, sources FROM query_history ORDER BY timestamp DESC LIMIT ?",
        conn, params=(limit,)
    )
    return df

def clear_history():
    c.execute("DELETE FROM query_history")
    conn.commit()

# ---------- СЕССИЯ ----------
if 'last_gaps' not in st.session_state:
    st.session_state.last_gaps = ""
if 'last_answer' not in st.session_state:
    st.session_state.last_answer = ""

# ---------- БОКОВАЯ ПАНЕЛЬ ----------
page = st.sidebar.radio(
    "Разделы",
    ["💬 Чат с знаниями", "🌐 Обозреватель графа", "🔍 Пробелы в данных", "📊 История запросов"]
)

# ---------- ЧАТ ----------
if page == "💬 Чат с знаниями":
    st.subheader("Задайте вопрос по горно-металлургической тематике")

    query = st.text_area(
        "Вопрос:",
        placeholder="Какие методы обессоливания воды подходят при концентрации сульфатов 200–300 мг/л?",
        height=100
    )

    col1, col2 = st.columns([1, 3])

    with col1:
        st.subheader("Фильтры")
        geo = st.selectbox("География", ["Все", "Россия", "Зарубеж"])
        year_min = st.number_input("Год от", min_value=1900, max_value=2030, value=2000)
        year_max = st.number_input("Год до", min_value=1900, max_value=2030, value=2026)
        use_web = st.checkbox("Включить веб-поиск", value=True)
        search_btn = st.button("🔍 Поиск", type="primary")

    if search_btn and query.strip():
        filters = {}
        if geo != "Все":
            filters['geography'] = "RU" if geo == "Россия" else "foreign"
        if year_min and year_max:
            filters['year_range'] = {'min': year_min, 'max': year_max}

        payload = {
            "query": query,
            "filters": filters,
            "use_web": use_web
        }

        with st.spinner("Поиск в графе знаний + интернете + генерация через DeepSeek-R1..."):
            try:
                response = requests.post("http://localhost:8000/search", json=payload, timeout=120)
                if response.status_code == 200:
                    data = response.json()
                    answer = data.get('answer', 'Нет ответа')

                    st.session_state.last_answer = answer
                    st.session_state.last_gaps = extract_gaps(answer)

                    with col2:
                        st.subheader("📝 Ответ")
                        st.markdown(answer)

                        # --- ВЕБ-ИСТОЧНИКИ ---
                        web_sources = data.get('web_sources', [])
                        if web_sources:
                            ddg = [s for s in web_sources if s.get('source') == 'DuckDuckGo']
                            academic = [s for s in web_sources if s.get('source') == 'Crossref']
                            other = [s for s in web_sources if s.get('source') not in ['DuckDuckGo', 'Crossref']]

                            if ddg:
                                st.subheader("🌐 Веб-результаты (DuckDuckGo)")
                                for src in ddg:
                                    with st.expander(f"🔗 {src.get('title', 'Ссылка')}"):
                                        st.write(src.get('snippet', ''))
                                        st.write(f"**URL:** [{src.get('url', '')}]({src.get('url', '')})")

                            if academic:
                                st.subheader("📄 Академические публикации (Crossref)")
                                for src in academic:
                                    with st.expander(f"📄 {src.get('title', 'Статья')}"):
                                        st.write(src.get('snippet', ''))
                                        if src.get('authors'):
                                            st.write(f"**Авторы:** {src.get('authors')}")
                                        if src.get('year'):
                                            st.write(f"**Год:** {src.get('year')}")
                                        st.write(f"**DOI:** [{src.get('url', '')}]({src.get('url', '')})")

                            if other:
                                st.subheader("🌐 Другие источники")
                                for src in other:
                                    with st.expander(f"🔗 {src.get('title', 'Ссылка')}"):
                                        st.write(src.get('snippet', ''))
                                        st.write(f"**URL:** [{src.get('url', '')}]({src.get('url', '')})")

                        # --- ЛОКАЛЬНЫЕ ИСТОЧНИКИ ---
                        st.subheader("📚 Локальные источники")
                        sources = data.get('sources', [])
                        local_sources = [s for s in sources if s.get('source_type') == 'local']
                        if local_sources:
                            for src in local_sources[:5]:
                                with st.expander(f"📄 {src.get('filename', 'Документ')}"):
                                    st.write(src.get('snippet', '')[:500] + "...")
                                    st.write("**Условия:**", src.get('conditions', []))
                        else:
                            st.info("Локальные источники не найдены")

                        save_query(query, answer, sources + web_sources)

                        if data.get('graph_nodes'):
                            st.subheader("📊 Визуализация графа")
                            try:
                                import networkx as nx
                                from pyvis.network import Network
                                from streamlit.components.v1 import html

                                G = nx.Graph()
                                for node in data['graph_nodes']:
                                    label = node['properties'].get('name', node['properties'].get('filename', str(node['id'])))
                                    G.add_node(node['id'], label=label, type=node['labels'][0])
                                for edge in data['graph_edges']:
                                    G.add_edge(edge['source'], edge['target'], label=edge['type'])

                                net = Network(height="500px", width="100%", directed=True)
                                for node in G.nodes(data=True):
                                    net.add_node(node[0], label=node[1]['label'], title=node[1]['type'])
                                for edge in G.edges(data=True):
                                    net.add_edge(edge[0], edge[1], label=edge[2]['label'])

                                net.save_graph("graph.html")
                                with open("graph.html", 'r', encoding='utf-8') as f:
                                    html(f.read(), height=550)
                            except Exception as e:
                                st.warning(f"Не удалось построить граф: {e}")

                else:
                    st.error(f"Ошибка API: {response.text}")
            except Exception as e:
                st.error(f"Ошибка: {e}")

# ---------- ОБОЗРЕВАТЕЛЬ ГРАФА ----------
elif page == "🌐 Обозреватель графа":
    st.subheader("Визуализация Knowledge Graph")
    if st.button("Обновить и показать граф", type="primary"):
        graph_path = Path("data/graph/knowledge_graph.html")
        if graph_path.exists():
            with open(graph_path, 'r', encoding='utf-8') as f:
                st.components.v1.html(f.read(), height=950)
        else:
            st.warning("Граф ещё не построен. Запустите python build_graph.py")

# ---------- ПРОБЕЛЫ ----------
elif page == "🔍 Пробелы в данных":
    st.subheader("Анализ пробелов в знаниях (на основе последнего ответа)")
    gaps = st.session_state.get('last_gaps', '')
    if gaps:
        st.markdown(gaps)
    else:
        st.info("Пробелы не найдены. Возможно, в последнем ответе нет информации о пробелах.")

# ---------- ИСТОРИЯ ----------
elif page == "📊 История запросов":
    st.subheader("История запросов")
    df = load_history(limit=100)
    if df.empty:
        st.info("История пуста. Задайте несколько вопросов в чате.")
    else:
        st.dataframe(df, use_container_width=True)
        col1, col2 = st.columns(2)
        with col1:
            if st.button("🗑️ Очистить историю"):
                clear_history()
                st.success("История очищена")
                st.rerun()
        with col2:
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button(
                label="📥 Скачать историю (CSV)",
                data=csv,
                file_name=f"query_history_{datetime.now().strftime('%Y%m%d')}.csv",
                mime="text/csv",
            )

# ---------- ПОДВАЛ ----------
st.caption("🔬 Норберт • Норникель AI Hackathon • GitHub Models (DeepSeek-R1) + Crossref")