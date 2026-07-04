import json
import os
import asyncio
import aiohttp
from collections import defaultdict
from config import OUTPUT_DIR, ASYNC_CONCURRENCY
from utils import (
    extract_conditions, extract_numbers_with_units,
    extract_geography, extract_years,
    normalize_term, normalize_entity, normalize_predicate,
    split_text_into_fragments
)
from yandex_ai import YandexAIClientAsync

# Включаем LLM для извлечения триплетов (теперь с группировкой)
USE_LLM = True

async def process_document_async(session, yandex_client, doc_id, full_text, semaphore, doc_metadata=None):
    """
    Обрабатывает один документ: извлекает правила и генерирует триплеты 
    для всех его фрагментов (если USE_LLM = True).
    """
    async with semaphore:
        # 1. Извлечение правилами (делаем один раз для всего текста)
        conditions = extract_conditions(full_text)
        numbers = extract_numbers_with_units(full_text)
        geography = extract_geography(full_text)
        years = extract_years(full_text)

        # 2. Термины из глоссария
        found_terms = []
        from utils import GLOSSARY
        for category in ['materials', 'processes', 'equipment']:
            for term_ru, term_en in GLOSSARY.get(category, {}).items():
                if term_ru.lower() in full_text.lower() or term_en.lower() in full_text.lower():
                    found_terms.append({
                        'category': category,
                        'canonical': term_ru,
                        'english': term_en
                    })

        # 3. Триплеты через LLM (если включено)
        all_triples = []
        if USE_LLM and yandex_client:
            # Разбиваем текст на большие фрагменты (до 50k токенов)
            fragments = split_text_into_fragments(full_text)
            print(f"   Документ {doc_id}: {len(fragments)} фрагментов")
            for idx, fragment in enumerate(fragments):
                if len(fragment.strip()) < 100:  # пропускаем слишком короткие
                    continue
                try:
                    triples = await yandex_client.generate_triples_async(session, fragment, doc_id)
                    # Нормализуем и обогащаем метаданными
                    for t in triples:
                        t['subject'] = normalize_entity(t.get('subject', ''))
                        t['predicate'] = normalize_predicate(t.get('predicate', ''))
                        t['object'] = normalize_entity(t.get('object', ''))
                        t['source'] = doc_id
                        t['fragment_index'] = idx
                        t.setdefault('confidence', 0.7)
                    all_triples.extend(triples)
                except Exception as e:
                    print(f"   ⚠️ Ошибка LLM для фрагмента {idx} документа {doc_id}: {e}")

        # Формируем результат: один объект на документ (но мы сохраним как чанки для совместимости)
        # Чтобы не ломать остальной пайплайн, создадим один "чанк" на документ,
        # но сохраним весь текст и все триплеты.
        return {
            'doc_id': doc_id,
            'chunk_index': 0,   # будет только один чанк на документ
            'text': full_text[:500] + "..." if len(full_text) > 500 else full_text,  # сокращаем для хранения
            'full_text': full_text,  # сохраняем полный текст для индексации
            'conditions': conditions,
            'numbers': numbers,
            'geography': geography,
            'years': years,
            'terms': found_terms,
            'triples': all_triples,
            'metadata': doc_metadata or {}
        }


async def main_async():
    # Загружаем чанки, но будем группировать по doc_id
    input_path = os.path.join(OUTPUT_DIR, 'chunks.json')
    if not os.path.exists(input_path):
        print(f"❌ Файл {input_path} не найден. Сначала запустите chunking.py")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        chunks = json.load(f)

    print(f"📄 Всего чанков: {len(chunks)}")

    # Группируем чанки по doc_id
    docs = defaultdict(list)
    for chunk in chunks:
        docs[chunk['doc_id']].append(chunk['text'])

    print(f"📄 Всего документов: {len(docs)}")
    print(f"⚙️  Обрабатываем документы с параллелизмом {ASYNC_CONCURRENCY}")

    yandex_client = YandexAIClientAsync() if USE_LLM else None
    semaphore = asyncio.Semaphore(ASYNC_CONCURRENCY)

    annotated = []
    async with aiohttp.ClientSession() as session:
        tasks = []
        for idx, (doc_id, texts) in enumerate(docs.items()):
            full_text = "\n\n".join(texts)  # объединяем все чанки документа
            if idx % 50 == 0:
                print(f"  Запуск документа {idx+1}/{len(docs)}: {doc_id}")
            task = process_document_async(session, yandex_client, doc_id, full_text, semaphore)
            tasks.append(task)

        # Выполняем все задачи с прогресс-баром
        for i, coro in enumerate(asyncio.as_completed(tasks)):
            result = await coro
            annotated.append(result)
            if i % 20 == 0:
                print(f"  Обработано {i+1}/{len(tasks)} документов")

    # Сохраняем результат (каждый документ — один чанк)
    output_path = os.path.join(OUTPUT_DIR, 'annotated_chunks.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(annotated, f, ensure_ascii=False, indent=2)

    print(f"✅ Аннотировано {len(annotated)} документов. Сохранено в {output_path}")


def main():
    asyncio.run(main_async())


if __name__ == '__main__':
    main()