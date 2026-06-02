# Medeniyet Üniversitesi AI Asistanı

**Medeniyet Üniversitesi AI Asistanı**, İstanbul Medeniyet Üniversitesi’nin public web kaynakları, akademik belgeleri, duyuruları ve ders içerikleri üzerinde çalışan RAG tabanlı, tool destekli bir yapay zekâ asistan platformudur.

> **Akademik not:** Bu proje İstanbul Medeniyet Üniversitesi’nin public web kaynakları kullanılarak geliştirilmiş akademik amaçlı bir bitirme projesi / lokal PoC çalışmasıdır. **Resmi bir İstanbul Medeniyet Üniversitesi uygulaması değildir.** Canlı OBS, öğrenci paneli veya kurumsal SSO entegrasyonu içermez.

---

## Proje Özeti

Üniversite bilgisini (yönetmelik, duyuru, akademik takvim, public web sayfaları) doğal dilde sorgulanabilir kılar. Cevaplar **indexlenmiş kaynaklara** dayanır; kaynak yoksa sistem kesin iddia yerine güvenli fallback kullanır.

**Konumlandırma:** Domain-specific, tool-augmented RAG assistant platformu — kaynaklı cevap, araç yönlendirme, crawler, hybrid retrieval, Redis önbellek, PostgreSQL logları ve **Yönetim Paneli** ile gözlemlenebilir bir mimari.

---

## Temel Özellikler

- Kaynaklı soru-cevap (citation)
- PDF, Markdown ve Web JSON ingestion
- Public web crawler (`scripts/crawl_website.py`)
- ChromaDB + BM25 hybrid retrieval
- LangGraph agent workflow ve intent routing
- Process Navigator (süreç rehberi)
- Open Library kaynak önerici
- Redis answer cache
- PostgreSQL: oturum, mesaj, feedback, agent run, tool call logları
- Streamlit arayüzü (sohbet + agent adımları)
- **Yönetim Paneli** (sistem ve veri hattı gözlemlenebilirliği)
- **Değerlendirme scripti** (`scripts/evaluate_rag.py`)
- Docker Compose ile lokal çalıştırma
- `INCLUDE_SAMPLE_DATA` ile örnek / gerçek kaynak ayrımı

---

## Mimari

### Chat ve agent

```text
Kullanıcı → Streamlit → FastAPI → LangGraph → Intent Router
  → RAG Search | Process Navigator | Resource Recommender
  → ChromaDB + BM25 / Open Library → LLM
  → PostgreSQL (log) + Redis (cache) → Yanıt + Kaynaklar + Agent Steps
```

### Veri hattı

```text
Public web / PDF / Markdown
  → crawl_website.py (opsiyonel)
  → data/raw/web, data/raw/pdf
  → ingest_data.py → data/chroma, data/bm25, chunks.jsonl
  → Hybrid search
```

**Not:** Vektör arama PostgreSQL’de değil; ChromaDB + BM25 dosya tabanlıdır.

---

## Teknoloji Yığını

| Bileşen | Teknoloji |
|---------|-----------|
| API | FastAPI |
| UI | Streamlit |
| Agent | LangGraph |
| Vektör arama | ChromaDB (`text-embedding-3-small`) |
| Anahtar kelime | BM25 (`rank-bm25`) |
| LLM | OpenAI `gpt-4o-mini` |
| Kalıcılık | PostgreSQL |
| Önbellek | Redis |
| Dış API | Open Library |
| Ops | Docker Compose |

---

## Veri Kaynakları

### Public / lokal kaynaklar

| Yol | İçerik |
|-----|--------|
| `data/raw/web/` | Crawler JSON çıktıları |
| `data/raw/pdf/` | İndirilen PDF’ler |
| `data/chroma/`, `data/bm25/`, `data/processed/` | Üretilen indeksler |
| `outputs/evaluation/` | Değerlendirme raporları |

### Örnek veri seti

`data/raw/samples/` — kurgu Markdown (yönetmelik, takvim, duyuru). Hızlı başlangıç için `INCLUDE_SAMPLE_DATA=true`.

**Gerçek üniversite kaynaklarıyla çalışırken** `INCLUDE_SAMPLE_DATA=false` **kullanılması uygundur**; aksi halde örnek metinler crawler/PDF kaynaklarıyla karışabilir.

### Değerlendirme soru seti

`data/evaluation/eval_questions.json` — public test seti (kişisel veri yok).

---

## Web Crawler / Public Source Collector

- **Betik:** `scripts/crawl_website.py`
- Yalnızca **public** HTML; izinli domain (`medeniyet.edu.tr`, `*.medeniyet.edu.tr`)
- Login, OBS, öğrenci paneli ve kapalı sistemlere **bağlanmaz**
- Çıktı: `data/raw/web/*.json`, `data/raw/pdf/*.pdf`
- Sonrası **mutlaka** `ingest_data.py`

Örnek seed URL’ler `.env.example` içinde (`UNIVERSITY_CRAWL_URLS`). Gerçek çalıştırma için aynı listeyi kendi `.env` dosyanıza kopyalayın.

| Kaynak türü | Örnek (public) |
|-------------|----------------|
| Genel site / duyurular | `www.medeniyet.edu.tr` |
| Akademik takvim (PDF) | Üniversite dokümanları |
| SSS, öğrenci işleri | Kayıt, harç, yatay geçiş, formlar |
| **Bilgisayar Mühendisliği (BM)** | Staj, MÜDEK, Bitirme Projesi, Mevzuat (`bm.medeniyet.edu.tr`) |
| **Fakülte** | Eğitim planları, **Ders Programları** (`muhendislikdogabilimleri.medeniyet.edu.tr`) |

`UNIVERSITY_ALLOWED_DOMAINS=medeniyet.edu.tr` — alt alan adları (`*.medeniyet.edu.tr`) crawler tarafından kapsanır.

---

## Ingestion Pipeline

```bash
source venv/bin/activate
export PYTHONPATH=.
python scripts/ingest_data.py
```

| `INCLUDE_SAMPLE_DATA` | Davranış |
|------------------------|----------|
| `true` | `data/raw/samples` dahil |
| `false` | Samples atlanır — Medeniyet crawl/PDF kaynakları için tercih edilir |

Desteklenen formatlar: `.pdf`, `.md`, `.txt`, `.json` (web crawler).

---

## Agent Araçları

| Intent | Araç | Görev |
|--------|------|--------|
| `rag_question` | `rag_search` | Yönetmelik, duyuru, takvim — kaynaklı cevap |
| `process_guidance` | `process_navigator` | Adım adım süreç rehberi |
| `resource_recommendation` | `resource_recommender` | Open Library kitap/kaynak önerisi |

**Process Navigator** dilekçe üretmez; kişisel veri toplamaz. Dilekçe/başvuru asistanı gelecek çalışmalar kapsamındadır.

---

## Redis Answer Cache

- Anahtar: `answer_cache:{intent}:{hash(normalized_question)}` — intent aynı kalır (farklı intent farklı cevap)
- Sorular cache key’e dönüştürülmeden önce **normalize edilir**: küçük harf, fazla boşluk ve noktalama (`. , ? !` vb.) farkları aynı anahtarı üretir
- Tekrarlayan sorularda agent/RAG atlanabilir; `agent_steps` içinde cache hit/miss görünür
- **Cache güvenliği:** kişisel bilgi, dilekçe/başvuru içeren sorular ve fallback / yetersiz kaynak cevapları cache’e **yazılmaz**; bu sorularda okuma da bypass edilir
- Crawl + ingest sonrası: `docker compose exec redis redis-cli FLUSHDB`

---

## PostgreSQL Persistence and Observability

- `chat_sessions`, `chat_messages`, `feedback`, `document_metadata`
- `agent_runs` — question, selected_tool, status, duration_ms
- `tool_calls` — tool_name, input/output_summary, status

---

## Yönetim Paneli

Streamlit sidebar: **Sohbet** | **Yönetim Paneli**

**Erişim:** Yönetim Paneli basit şifre koruması ile açılır (tam kullanıcı yönetimi / JWT değildir). Şifre `ADMIN_DASHBOARD_PASSWORD` ile `.env` üzerinden ayarlanır. Sohbet ekranı şifresiz kullanılmaya devam eder.

Bölümler: Sistem Durumu · Bilgi Tabanı Durumu · Veri Hattı Durumu · Önbellek Durumu · Agent Gözlemlenebilirliği · Operasyonel Hazırlık

- Endpoint: `GET /admin/diagnostics` (salt okunur, API anahtarı döndürmez)

---

## Değerlendirme Scripti

```bash
python scripts/evaluate_rag.py --base-url http://localhost:8000 --flush-cache
```

Metrikler: intent/tool eşleşmesi, keyword skoru, kaynak zorunluluğu, fallback, latency. Raporlar: `outputs/evaluation/` (gitignore). LLM cevapları **%100 deterministik değildir**.

---

## Kurulum

### Gereksinimler

- Docker Compose **veya** Python 3.11+, OpenAI API anahtarı

### Ortam değişkenleri

`cp .env.example .env` — `OPENAI_API_KEY` ve gerekirse PostgreSQL değerlerini doldurun. **Gerçek anahtarları repoya commit etmeyin.**

Ayrıntılı liste: [Environment Variables](#ortam-değişkenleri) ve `.env.example`.

---

## Local Çalıştırma

```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env

export PYTHONPATH=.
uvicorn backend.app.main:app --reload --port 8000

# Ayrı terminal
export BACKEND_URL=http://127.0.0.1:8000
streamlit run frontend/streamlit_app.py
```

| Adres | URL |
|-------|-----|
| Arayüz | http://localhost:8501 |
| API | http://localhost:8000/docs |

---

## Docker ile Çalıştırma

```bash
cp .env.example .env
docker compose up --build
```

---

## Sık Kullanılan Komutlar

```bash
source venv/bin/activate
export PYTHONPATH=.

python scripts/crawl_website.py
python scripts/ingest_data.py
docker compose exec redis redis-cli FLUSHDB
python scripts/evaluate_rag.py --base-url http://localhost:8000 --flush-cache
```

---

## Örnek Sorular

Normal sohbetten denenebilir (yönetim panelinde listelenmez):

| Soru | Beklenen davranış |
|------|-------------------|
| Ders seçimi nasıl yapılır? | Process Navigator |
| Harç ödeme işlemleri nasıl yapılır? | Process Navigator |
| Yatay geçiş için ne yapmam gerekiyor? | Process Navigator |
| Kayıt dondurma şartları nelerdir? | RAG |
| Mazeret sınavına kimler başvurabilir? | RAG |
| Veri yapıları için kaynak öner. | Open Library |
| Uzay madenciliği kulübü kayıt süreci nasıl? | Güvenli / sınırlı yanıt (safety) |

---

## Proje Sınırları

- Akademik bitirme projesi / lokal PoC kapsamında geliştirilmiştir
- **Resmi üniversite uygulaması değildir**
- Canlı OBS/API entegrasyonu yoktur
- Kişisel öğrenci verisi işlenmez; resmi başvuru yapılmaz
- Login gerektiren sistemlere girilmez
- Cevaplar yalnızca indexlenmiş kaynaklarla sınırlıdır
- Tam otonom genel amaçlı agent değildir

---

## Gelecek Çalışmalar

- Dilekçe / başvuru asistanı
- RAG reranker
- Zamanlanmış crawler
- Kaynak değişiklik izleme
- Feedback dashboard
- Rol tabanlı yetkilendirme
- Çoklu üniversite desteği
- OBS/API entegrasyonu

---

## Security / Privacy Notes

- `.env`, `context.md`, crawler çıktıları ve indeksler **commit edilmemeli**
- API anahtarları yalnızca lokal `.env` içinde
- Crawler yalnızca public sayfalar; kişisel veri toplanmaz
- Yönetim Paneli ve chat loglarında soru metinleri kısaltılarak gösterilir

---

## Ortam Değişkenleri

Özet (tam liste `.env.example`):

| Değişken | Açıklama |
|----------|----------|
| `OPENAI_API_KEY` | OpenAI (placeholder repoda) |
| `INCLUDE_SAMPLE_DATA` | Örnek belgeler; gerçek kaynaklar için `false` |
| `UNIVERSITY_CRAWL_URLS` | Crawler seed URL’leri |
| `UNIVERSITY_ALLOWED_DOMAINS` | İzinli domain |
| `ADMIN_DASHBOARD_PASSWORD` | Yönetim Paneli şifresi (Streamlit) |
| `REDIS_URL`, `ENABLE_REDIS_CACHE` | Answer cache |
| `DATABASE_URL` | PostgreSQL |

---

## Doğrulama ve Test Akışı

```bash
source venv/bin/activate
export PYTHONPATH=.

# Veri yenileme
python scripts/crawl_website.py
python scripts/ingest_data.py

# Servisler
docker compose down
docker compose up --build

# Önbellek
docker compose exec redis redis-cli FLUSHDB

# Değerlendirme
python scripts/evaluate_rag.py --base-url http://localhost:8000 --flush-cache

# Git güvenliği
git status
grep -R "sk-" . --exclude-dir=venv --exclude-dir=.venv --exclude-dir=.git
```

| Kontrol | URL |
|---------|-----|
| Arayüz | http://localhost:8501 |
| API | http://localhost:8000/docs |

---

## Klasör Yapısı

```text
backend/app/     API, agent, RAG, tools, db
frontend/        Streamlit (Sohbet + Yönetim Paneli)
data/
  raw/pdf, web/  Lokal crawl (gitignore)
  raw/samples/   Örnek Markdown belgeleri
  evaluation/    eval_questions.json
scripts/         crawl, ingest, evaluate_rag, test
outputs/evaluation/  Raporlar (gitignore)
```

Sürüm notları: [`CHANGELOG.md`](CHANGELOG.md)

---

## Lisans

Bu proje akademik amaçlı bir bitirme projesi / lokal PoC çalışmasıdır. Henüz açık kaynak lisansı eklenmemiştir.
