# University AI Assistant

**University AI Assistant**, üniversite kaynakları, akademik belgeler, duyurular ve ders içerikleri üzerinde çalışan RAG tabanlı, tool destekli bir yapay zekâ asistan platformudur.

---

## Proje Amacı

Bu proje, üniversite ortamında dağınık duran bilgiyi — yönetmelikler, duyurular, akademik takvimler, ders notları ve benzeri kaynakları — doğal dilde sorgulanabilir hale getirmeyi hedefler. Temel hedefler:

- Üniversiteye ait yönetmelik, duyuru, akademik takvim, ders içeriği ve benzeri kaynakları daha erişilebilir kılmak
- Kullanıcının doğal dilde sorduğu sorulara **kaynaklı** ve **bağlama dayalı** cevap üretmek
- Yalnızca LLM çıktısına güvenmek yerine **RAG**, **hybrid search** ve **tool routing** ile kontrollü yanıt üretmek
- Lokal ortamda çalışan, tekrarlanabilir bir **PoC / demo mimarisi** sunmak

Kaynak bulunamadığında sistem kesin cevap vermek yerine güvenli bir fallback mesajı döner (*“Kaynak yoksa cevap yok”* prensibi).

---

## Temel Özellikler

- Kaynaklı soru-cevap (citation ile)
- PDF, Markdown ve Web JSON ingestion
- Public web crawler (`scripts/crawl_website.py`)
- PDF link discovery ve download
- Direct PDF URL handling (crawler)
- ChromaDB semantic / vector search
- BM25 keyword search (`rank-bm25`)
- Hybrid retrieval (vektör + anahtar kelime)
- LangGraph agent workflow
- Intent routing (soru türüne göre dal seçimi)
- University Process Navigator (adım adım süreç rehberi)
- Open Library resource recommender
- Redis answer cache
- PostgreSQL chat history, agent run ve tool call logları
- Streamlit chat UI (oturum geçmişi, agent steps gösterimi)
- Docker Compose ile tek komutla çalıştırma
- `INCLUDE_SAMPLE_DATA` ile demo / gerçek kaynak ingestion ayrımı
- API üzerinden ingestion ve chat uç noktaları

---

## Sistem Mimarisi

### Chat ve agent akışı

```text
Kullanıcı
  → Streamlit Frontend
  → FastAPI Backend
  → LangGraph Agent
  → Intent Router
  → RAG Search / Process Navigator / Resource Recommender
  → ChromaDB + BM25 / Open Library
  → LLM Answer Generation
  → PostgreSQL (Logs & Chat History)
  → Redis Answer Cache
  → Response + Sources + Agent Steps
```

### Ingestion ve crawler akışı

```text
Public Web Sources / PDFs / Markdown
  → crawl_website.py (opsiyonel; public web için)
  → data/raw/web (JSON) + data/raw/pdf
  → ingest_data.py
  → ChromaDB + BM25
  → RAG Search
```

**Kalıcılık:** PostgreSQL — oturumlar, mesajlar, geri bildirim, agent ve tool logları (vektör arama burada yapılmaz).

---

## Teknoloji Stack’i

| Teknoloji | Rol |
|-----------|-----|
| **FastAPI** | REST API, chat, ingestion, health ve OpenAPI dokümantasyonu |
| **Streamlit** | Sohbet arayüzü, oturum yönetimi, kaynak ve agent adımlarının gösterimi |
| **LangGraph** | Agent workflow: analiz, intent, retrieval, grading, üretim, doğrulama |
| **ChromaDB** | Semantic / vector search; `text-embedding-3-small` embedding’leri |
| **BM25** (`rank-bm25`) | Keyword tabanlı arama; hybrid retrieval’ın ikinci bileşeni |
| **PostgreSQL** | Chat session, mesaj, feedback, agent run, tool call logları |
| **Redis** | Answer cache (`answer_cache:*`) ve `/health` status kontrolü |
| **OpenAI** | `gpt-4o-mini` (cevap üretimi), `text-embedding-3-small` (embedding) |
| **Open Library API** | Ders / konu bazlı kitap ve kaynak önerisi (API key gerekmez) |
| **Docker Compose** | Backend, frontend, PostgreSQL, Redis tek komutla ayağa kalkar |

Ek: **pypdf** (PDF parsing), **BeautifulSoup** (crawler HTML), **SQLAlchemy** + **Alembic** (veritabanı), **httpx** (frontend → backend).

---

## Agent Tools

### RAG Search Tool

Indexlenmiş PDF, Markdown ve web JSON kaynaklarında hybrid arama yapar; bulunan pasajlara dayanarak kaynaklı cevap üretir.

- `selected_tool`: `rag_search`
- Akış: analyze → intent → retrieve → grade → (rewrite) → generate → validate

### Process Navigator Tool

Kullanıcının üniversite süreçleriyle ilgili sorularını algılar; indexlenmiş kaynaklara göre adım adım süreç rehberi, gerekli belgeler/bilgiler, dikkat edilmesi gerekenler, ilgili birim (kaynakta geçiyorsa) ve sonraki aksiyon üretir. Dilekçe üretmez; kişisel veri toplamaz.

- `selected_tool`: `process_navigator`
- Intent: `process_guidance`
- Akış: analyze → intent → hybrid search → süreç planı → Markdown rehber + kaynaklar

Örnek sorular: *Ders seçimi nasıl yapılır?*, *Harç ödeme işlemleri nasıl yapılır?*, *Yatay geçiş için ne yapmam gerekiyor?*

Genel şart soruları (`Kayıt dondurma şartları nelerdir?`) **RAG Search** ile yanıtlanır; süreç soruları Process Navigator ile ayrılır.

### Resource Recommender Tool

Ders içeriği veya konu ifadesine göre [Open Library](https://openlibrary.org) üzerinden kitap / kaynak önerir; isteğe bağlı olarak RAG bağlamı ile zenginleştirilir.

- `selected_tool`: `resource_recommender`
- Akış: analyze → intent → (RAG context) → Open Library → LLM öneri

API yanıtında `agent_steps` ve `selected_tool` alanları döner; Streamlit arayüzünde **Agent adımları** expander’ında gösterilir.

### Planlanan (henüz yok)

- Petition / Application Assistant (dilekçe/form üretimi — v0.5.0 Process Navigator bunu **içermez**)
- Reranker
- RAG evaluation
- Admin panel

---

## Veri Kaynakları

### Demo sample veriler (GitHub’da kalır)

Public repoda **demo Markdown belgeleri** bulunur; repoyu klonlayan herkes hızlı deneme yapabilir:

```text
data/raw/samples/
  sample_regulation.md
  sample_academic_calendar.md
  sample_announcement.md
```

Bu dosyalar kurgu/demo amaçlıdır (örnek yönetmelik, akademik takvim, duyuru). **GitHub’da kalırlar**; production veya gerçek okul verisi testlerinde ingestion dışında bırakılabilir (`INCLUDE_SAMPLE_DATA=false`).

| `INCLUDE_SAMPLE_DATA` | Davranış |
|----------------------|----------|
| `true` (varsayılan) | `data/raw/samples` indexlenir — hızlı demo / GitHub deneyimi |
| `false` | Samples atlanır — crawler/PDF ile toplanan gerçek kaynaklar için **önerilir** |

Gerçek okul verisiyle çalışırken `false` kullanılmazsa demo akademik takvim, duyuru veya yönetmelik metinleri crawler/PDF kaynaklarıyla **karışabilir**; agent yanlış kaynaktan cevap verebilir.

### Gerçek üniversite verileri (lokal)

Crawler veya manuel PDF ile **lokal ortamda** toplanır; repoya commit edilmemelidir:

```text
data/raw/web/     # Crawler JSON çıktıları (generated/local, .gitignore)
data/raw/pdf/     # İndirilen PDF’ler (generated/local, .gitignore)
data/raw/faq/     # İsteğe bağlı Gold FAQ
```

`UNIVERSITY_CRAWL_URLS` ve `UNIVERSITY_ALLOWED_DOMAINS` kullanıcının `.env` dosyasında tanımlanır (örnekler `.env.example` içinde).

**Üretilen indeksler** (repoda tutulmaz):

```text
data/chroma/      # ChromaDB vektör indeksi
data/bm25/        # BM25 pickle indeksi
data/processed/   # chunks.jsonl
```

Desteklenen ingestion formatları: `.pdf`, `.md`, `.txt`, `.json` (web crawler çıktısı)

---

## Kurulum

### Gereksinimler

- Docker ve Docker Compose **veya**
- Python 3.11+, `pip`, çalışan bir OpenAI API anahtarı

### Docker (önerilen)

```bash
git clone <repo-url>
cd uni-agent-project
cp .env.example .env
# .env içinde OPENAI_API_KEY ve gerekirse POSTGRES_* değerlerini doldurun

docker compose up --build
```

| Servis | Adres |
|--------|--------|
| Streamlit UI | http://localhost:8501 |
| FastAPI | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| Health | http://localhost:8000/health |

### Yerel geliştirme (opsiyonel)

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

---

## Ingestion

Belge kaynaklarını chunk’layıp ChromaDB ve BM25 indekslerini oluşturur (`scripts/ingest_data.py`). Terminalde sample modu açıkça loglanır (*Sample data ingestion enabled/disabled*).

### Demo mod (GitHub hızlı deneme)

`.env` içinde:

```bash
INCLUDE_SAMPLE_DATA=true
```

```bash
source venv/bin/activate
export PYTHONPATH=.
python scripts/ingest_data.py
```

Yalnızca demo samples (`INCLUDE_SAMPLE_DATA` ayarından bağımsız):

```bash
python scripts/ingest_data.py --samples-only
```

### Gerçek okul verisi modu (önerilen)

`.env` içinde:

```bash
INCLUDE_SAMPLE_DATA=false
```

Ardından crawler → ingestion:

```bash
export PYTHONPATH=.
python scripts/crawl_website.py
python scripts/ingest_data.py
```

**Docker:**

```bash
docker compose exec backend python scripts/crawl_website.py
docker compose exec backend python scripts/ingest_data.py
```

### Diğer

Mevcut `chunks.jsonl` ile indeks yenileme:

```bash
python scripts/ingest_data.py --skip-sources
```

Alternatif: `POST /ingest` API uç noktası (FastAPI docs).

Chroma metadata örnekleri: `source`, `source_type`, `title`, `url`, `date`, `content_type`, `page`, `section_title`, `indexed_at`

---

## Web Crawler / Public Source Collector

`scripts/crawl_website.py`, **yalnızca public** üniversite web sayfalarından metin ve PDF toplar. Canlı okul API’si, OBS, öğrenci paneli, login veya kişisel veri içeren kapalı sistemlere **bağlanmaz**.

| Özellik | Açıklama |
|---------|----------|
| HTML okuma | Sayfa metni `data/raw/web/` altında JSON olarak kaydedilir |
| PDF | Sayfadaki linkler ve doğrudan PDF URL’leri `data/raw/pdf/` altına indirilebilir |
| Domain kısıtı | `UNIVERSITY_ALLOWED_DOMAINS` (ör. `medeniyet.edu.tr` → `*.medeniyet.edu.tr`) |
| İndeksleme | Crawler sonrası **mutlaka** `ingest_data.py` çalıştırılmalı |
| Kapsam | `CRAWLER_MAX_PAGES` toplam ziyaret ve link keşfini sınırlar; yalnızca seed URL’lerle sınırlı kalmak için değeri düşük tutulabilir |

**Yerel:**

```bash
source venv/bin/activate
# .env: UNIVERSITY_CRAWL_URLS, UNIVERSITY_ALLOWED_DOMAINS (örnekler .env.example)

export PYTHONPATH=.
python scripts/crawl_website.py
python scripts/ingest_data.py
```

**Docker:**

```bash
docker compose exec backend python scripts/crawl_website.py
docker compose exec backend python scripts/ingest_data.py
```

İlgili ortam değişkenleri: `UNIVERSITY_CRAWL_URLS`, `UNIVERSITY_ALLOWED_DOMAINS`, `CRAWLER_OUTPUT_DIR`, `CRAWLER_PDF_DIR`, `CRAWLER_MAX_PAGES`, `CRAWLER_REQUEST_TIMEOUT`, `CRAWLER_DELAY_SECONDS`, `CRAWLER_DOWNLOAD_PDFS` — ayrıntılar `.env.example`.

Örnek public kaynaklar (İstanbul Medeniyet Üniversitesi PoC): ana site, duyurular, akademik takvim PDF, SSS, ders seçimi/kayıt yenileme, harç ödeme, yatay geçiş, eğitim planları, formlar, iletişim — tam URL listesi `.env.example` içinde.

---

## Kullanım Örnekleri

**RAG — genel bilgi / şartlar**

- Kayıt dondurma şartları nelerdir?
- Akademik takvim hakkında bilgi ver.

**Process Navigator — süreç rehberi** (crawl + ingest sonrası)

- Ders seçimi nasıl yapılır?
- Harç ödeme işlemleri nasıl yapılır?
- Yatay geçiş için ne yapmam gerekiyor?
- Akademik takvimde ders kayıt süreci nasıl ilerliyor?
- Kayıt dondurma süreci nasıl ilerler?

*Public web soruları için önce crawler + ingestion; Redis cache eski cevap döndürebilir (aşağıya bakın).*

**Kaynak önerisi (Open Library)**

- Veri yapıları için kaynak öner.
- Algoritma dersi için kitap öner.

Örnek yanıt alanları: `answer`, `citations`, `agent_steps`, `selected_tool`, `session_id`

---

## PostgreSQL’in Rolü

PostgreSQL, **kalıcı uygulama verisini** tutar:

- `chat_sessions` — sohbet oturumları
- `chat_messages` — kullanıcı ve asistan mesajları
- `feedback` — kullanıcı geri bildirimi
- `agent_runs` — agent çalışma kayıtları
- `tool_calls` — tool çağrı logları

PostgreSQL **vektör arama için kullanılmaz**. Arama katmanı:

| Bileşen | Görev |
|---------|--------|
| **ChromaDB** | Semantic / vector search |
| **BM25** | Keyword search |
| **Hybrid retrieval** | İki kanalın birleştirilmesi |

Chroma ve BM25 indeksleri dosya tabanlıdır (`data/chroma`, `data/bm25`).

---

## Redis’in Rolü

Redis iki amaçla kullanılır:

- **Answer cache** — Aynı normalize edilmiş soru tekrar sorulduğunda cevap `answer_cache:{intent}:{hash}` anahtarıyla Redis’ten dönebilir. Agent, RAG, LLM ve tool akışı yeniden çalıştırılmaz; yanıt süresi ve API maliyeti azalır.
- **Health / status** — `GET /health` yanıtında `redis: ready | unavailable` alanı.

Yapılandırma (`.env`):

```bash
ENABLE_REDIS_CACHE=true
REDIS_CACHE_TTL_SECONDS=3600
REDIS_URL=redis://localhost:6379/0
```

Redis kullanılamazsa sistem cache’siz devam eder; chat akışı etkilenmez.

**Crawler + ingest sonrası test:** Eski cevaplar cache’de kalabilir. Yeni indekslenmiş içeriği görmek için cache temizleyin veya soruyu farklı ifadeyle sorun:

```bash
docker compose exec redis redis-cli keys '*answer_cache*'
docker compose exec redis redis-cli FLUSHDB
```

`FLUSHDB` seçili Redis veritabanındaki tüm anahtarları siler; yalnızca geliştirme ortamında kullanın.

---

## Projenin Sınırları

- Bu proje **lokal PoC / demo** olarak geliştirilmiştir; production hardening kapsamı dışındadır.
- Canlı üniversite API entegrasyonu (OBS, e-Devlet vb.) **içermez**.
- OBS, login veya öğrenci paneli gibi sistemlere **bağlanmaz**.
- Kişisel öğrenci verisi (not, borç, gerçek transkript) **işlemez**.
- Kimlik doğrulama veya kurumsal SSO **yoktur**.
- Cevaplar **yalnızca indexlenmiş kaynaklarla** sınırlıdır; kaynak yoksa kesin iddia üretilmez.
- Resmi işlem yapmaz; bilgilendirme ve asistanlık amacı taşır.
- Crawler **yalnızca public web** kaynakları içindir; güncel içerik için crawl + ingest periyodik tekrarlanmalıdır.
- Demo sample veriler gerçek crawler/PDF kaynaklarıyla **aynı anda** indexlenirse cevaplar karışabilir; gerçek kaynak testlerinde `INCLUDE_SAMPLE_DATA=false` önerilir.
- Petition/Application Assistant ve benzeri intent’ler **henüz desteklenmez**; dürüst bilgi mesajı döner.

---

## Yol Haritası

Sıradaki planlar:

- Petition / Application Assistant
- Reranker
- RAG evaluation
- Admin panel
- Feedback dashboard
- Semantic cache improvements
- Auth / role-based access
- Çoklu üniversite desteği

---

## Test Scriptleri

```bash
export PYTHONPATH=.

python scripts/test_vector_search.py "tek ders sınavı"
python scripts/test_bm25_search.py "tek ders sınavı"
python scripts/test_hybrid_search.py
python scripts/test_intent_routing.py
python scripts/demo_questions.py
```

Crawler + ingestion sonrası UI testinde Redis cache’i temizlemeyi unutmayın.

---

## Klasör Yapısı

```text
backend/app/     FastAPI, agent, RAG, tools, db, services
frontend/        Streamlit UI
data/            Ham veri, işlenmiş chunk, indeksler
scripts/         crawl_website.py, ingest_data.py, test betikleri
alembic/         Veritabanı migration
docker-compose.yml
```

Sürüm notları: [`CHANGELOG.md`](CHANGELOG.md)

---

## Lisans

Repoda henüz bir `LICENSE` dosyası tanımlı değildir. Projeyi dağıtırırken uygun bir açık kaynak lisansı (ör. MIT) eklemeniz önerilir.
