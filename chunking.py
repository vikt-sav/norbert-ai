import json
import os
from langchain_text_splitters import RecursiveCharacterTextSplitter
from config import OUTPUT_DIR   # импортируем только OUTPUT_DIR

# Задаём значения прямо здесь
MAX_CHUNK_SIZE = 1024
CHUNK_OVERLAP = 200

def chunk_text(text, chunk_size=MAX_CHUNK_SIZE, overlap=CHUNK_OVERLAP):
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=overlap,
        separators=["\n\n", "\n", ". ", " ", ""]
    )
    return splitter.split_text(text)

def main():
    input_path = os.path.join(OUTPUT_DIR, 'extracted_texts.json')
    if not os.path.exists(input_path):
        print(f"❌ Файл {input_path} не найден. Сначала запустите extract_text.py")
        return

    with open(input_path, 'r', encoding='utf-8') as f:
        docs = json.load(f)

    all_chunks = []
    for doc in docs:
        chunks = chunk_text(doc['full_text'])
        for idx, chunk in enumerate(chunks):
            all_chunks.append({
                'doc_id': doc['filename'],
                'chunk_index': idx,
                'text': chunk,
                'metadata': {
                    'source': doc['path'],
                    'filename': doc['filename']
                }
            })

    output_path = os.path.join(OUTPUT_DIR, 'chunks.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_chunks, f, ensure_ascii=False, indent=2)

    print(f"✅ Создано {len(all_chunks)} чанков. Сохранено в {output_path}")

if __name__ == '__main__':
    main()