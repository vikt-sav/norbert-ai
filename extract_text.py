import os
import json
import pdfplumber
import PyPDF2  # правильный импорт
from docx import Document
from config import DATA_DIR, OUTPUT_DIR

os.makedirs(OUTPUT_DIR, exist_ok=True)


def extract_text_from_pdf(filepath):
    text = ""
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                page_text = page.extract_text()
                if page_text:
                    text += page_text + "\n"
    except:
        # fallback на PyPDF2
        try:
            with open(filepath, 'rb') as f:
                reader = PyPDF2.PdfReader(f)
                for page in reader.pages:
                    page_text = page.extract_text()
                    if page_text:
                        text += page_text + "\n"
        except Exception as e:
            print(f"   ⚠️ Не удалось извлечь текст из PDF: {e}")
    return text


def extract_text_from_docx(filepath):
    doc = Document(filepath)
    return "\n".join([p.text for p in doc.paragraphs])


def extract_text_from_txt(filepath):
    with open(filepath, 'r', encoding='utf-8', errors='ignore') as f:
        return f.read()


def process_file(filepath):
    ext = os.path.splitext(filepath)[1].lower()
    if ext == '.pdf':
        text = extract_text_from_pdf(filepath)
    elif ext == '.docx':
        text = extract_text_from_docx(filepath)
    elif ext == '.txt':
        text = extract_text_from_txt(filepath)
    else:
        return None
    return {
        'filename': os.path.basename(filepath),
        'path': filepath,
        'full_text': text,
        'pages': text.count('\f') + 1
    }


def main():
    all_docs = []
    for root, dirs, files in os.walk(DATA_DIR):
        for file in files:
            if file.lower().endswith(('.pdf', '.docx', '.txt')):
                path = os.path.join(root, file)
                print(f"Обработка: {path}")
                doc = process_file(path)
                if doc:
                    all_docs.append(doc)

    output_path = os.path.join(OUTPUT_DIR, 'extracted_texts.json')
    with open(output_path, 'w', encoding='utf-8') as f:
        json.dump(all_docs, f, ensure_ascii=False, indent=2)

    print(f"Извлечено {len(all_docs)} документов. Сохранено в {output_path}")


if __name__ == '__main__':
    main()