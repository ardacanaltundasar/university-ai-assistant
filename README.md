# University AI Agent

Üniversite öğrenci işleri için **Agentic RAG** tabanlı, kaynak gösteren, lokal çalışan **PoC demo** asistanı.

Detaylı mimari ve kurallar: [`context.md`](context.md).

## Proje özeti

Öğrenciler yönetmelik, sınav, kayıt, belge ve kampüs süreçleri hakkında soru sorar. Sistem:

- Hybrid search (ChromaDB + BM25) ile kaynak arar
- LangGraph ajan akışı ile cevap üretir
- CRAG ile kaynakları doğrular
- Citation ile kaynak gösterir
- **Kaynak yoksa kesin cevap vermez**

## Mimari

```text
Streamlit (frontend)  →  FastAPI (backend)  →  LangGraph Agent
                                              ↓
                                    Hybrid Search (Chroma + BM25)
                                              ↓
                                    PDF / Markdown / FAQ veri katmanı
```

**Ajan akışı:** analyze → route → retrieve → grade → (rewrite) → generate → validate → (fallback)

## Teknolojiler

| Katman | Teknoloji |
|--------|-----------|
| API | FastAPI, Uvicorn |
| UI | Streamlit |
| Agent | LangGraph |
| Vektör DB | ChromaDB |
| Keyword | rank-bm25 |
| LLM / Embedding | OpenAI GPT-4o mini, text-embedding-3-small |
| PDF | pypdf |
| Opsiyonel | Redis, Docker Compose |

## Kurulum (yerel)

### 1. Bağımlılıklar

```bash
cd /path/to/uni-agent-project
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

### 2. Ortam dosyası

```bash
cp .env.example .env
# .env içine OPENAI_API_KEY değerinizi yazın
```

### 3. Demo Data

Public repoda **gerçek üniversite PDF’leri veya özel veriler bulunmaz**. Bunun yerine demo Markdown belgeleri vardır:

```text
data/
  raw/
    pdf/          # .gitkeep — gerçek PDF’ler yalnızca lokal eklenir (gitignore)
    web/          # .md, .txt, .json duyurular (opsiyonel, lokal)
    samples/      # Demo belgeler (repoda)
      sample_regulation.md
      sample_academic_calendar.md
      sample_announcement.md
  chroma/         # vektör indeksi (gitignore)
  bm25/           # BM25 indeksi (gitignore)
  processed/      # chunks.jsonl (gitignore)
```

**Demo belgeler** kayıt dondurma, mazeret sınavı, mezuniyet şartları, ders kayıt süreci ve akademik takvim konularını içerir (tamamen kurgu metin).

Gerçek PDF veya web içeriği eklemek için dosyaları `data/raw/pdf/` veya `data/raw/web/` altına koyun; ardından ingestion çalıştırın.

İsteğe bağlı Gold FAQ: `data/raw/faq/gold_faq.json`

### 4. Ingestion (PDF / Markdown → chunks → Chroma + BM25)

Desteklenen formatlar: `.pdf`, `.md`, `.txt`, `.json`  
Okunan klasörler: `data/raw/pdf/`, `data/raw/web/`, `data/raw/samples/`

**Yerel (venv):**

```bash
source venv/bin/activate
export PYTHONPATH=.
python scripts/ingest_data.py
```

Yalnızca demo samples (API anahtarı ile tam indeks):

```bash
python scripts/ingest_data.py --samples-only
```

Sadece mevcut `chunks.jsonl` ile indeks yenileme:

```bash
python scripts/ingest_data.py --skip-sources
```

**Docker:**

```bash
docker compose exec backend python scripts/ingest_data.py
```

Chroma metadata alanları: `source`, `source_type`, `title`, `content_type`, `page`, `section_title`, `indexed_at`

### 5. Backend

```bash
export PYTHONPATH=.
uvicorn backend.app.main:app --reload --port 8000
```

- API: http://127.0.0.1:8000  
- Docs: http://127.0.0.1:8000/docs  
- Health: http://127.0.0.1:8000/health  

### 6. Frontend (yeni terminal)

```bash
export BACKEND_URL=http://127.0.0.1:8000
streamlit run frontend/streamlit_app.py
```

- UI: http://localhost:8501  

## Docker ile çalıştırma

```bash
cp .env.example .env
# OPENAI_API_KEY doldurun
docker compose up --build
```

## Test scriptleri

```bash
export PYTHONPATH=.

python scripts/test_vector_search.py "tek ders sınavı"
python scripts/test_bm25_search.py "tek ders sınavı"
python scripts/test_hybrid_search.py

# Demo stabilizasyon testi (12 soru)
python scripts/demo_questions.py
```

## Demo soruları

Jüri demosu için örnek sorular (Streamlit sidebar + `scripts/demo_questions.py`):

1. Kayıt dondurma şartları nelerdir?
2. Tek ders sınavına kimler girebilir?
3. Yaz okulunda en fazla kaç kredi alabilirim?
4. ÇAP yapmak için not ortalamam kaç olmalı?
5. Transkriptimi nereden alabilirim?
6. OBS şifremi unuttum, ne yapmalıyım?
7. Kampüs kartımı kaybettim, ne yapmalıyım?
8. Mazeret sınavı için sağlık raporu yeterli mi?
9. Danışman onayı olmadan ders seçimi tamamlanır mı?
10. Harç ödemesini nasıl yapabilirim?

**Kapsam dışı** (güvenli fallback beklenir):

11. Bugün hava nasıl?
12. Bana gerçek transkriptimi çıkarır mısın?

## Sistem sınırları

Bu PoC **yapmaz**:

- Canlı OBS / e-Devlet entegrasyonu
- Kişisel not, borç, transkript sorgulama
- Resmi işlem veya belge üretme
- Canlı hava durumu gibi kaynak dışı sorular

## Temel prensip

```text
Kaynak yoksa cevap yok.
```

Yanlış bilgi vermektense güvenli fallback mesajı döner:

> Bu konuda elimdeki doğrulanmış kaynaklarda yeterli bilgi bulamadım…

## Hızlı demo kontrol listesi

```bash
# 1) Ortam
cp .env.example .env

# 2) Paketler
pip install -r requirements.txt

# 3) İndeks (PDF'ler yüklüyse)
export PYTHONPATH=.
python scripts/ingest_data.py

# 4) Backend
uvicorn backend.app.main:app --reload --port 8000

# 5) Frontend (ayrı terminal)
streamlit run frontend/streamlit_app.py

# 6) Otomatik test
python scripts/demo_questions.py
```

## Klasör yapısı

```text
backend/app/     FastAPI, agent, RAG, services
frontend/        Streamlit UI
data/            Ham veri, işlenmiş chunk, indeksler
scripts/         Ingest ve test betikleri
```
