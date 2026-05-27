# University AI Assistant

Üniversite kaynakları, akademik belgeler ve ders içerikleri üzerinde çalışan RAG tabanlı, tool destekli yapay zekâ asistan platformu.

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
- PDF ve Markdown ingestion
- ChromaDB semantic / vector search
- BM25 keyword search (`rank-bm25`)
- Hybrid retrieval (vektör + anahtar kelime birleşimi)
- LangGraph tabanlı agent workflow
- Intent routing (soru türüne göre dal seçimi)
- Open Library ile akademik kaynak / kitap önerisi
- PostgreSQL ile kalıcı sohbet geçmişi, agent run ve tool call logları
- Redis answer cache (tekrarlayan sorularda LLM/retrieval maliyetini azaltır)
- Docker Compose ile tek komutla çalıştırma
- Modern Streamlit sohbet arayüzü (oturum geçmişi, silme, agent steps)
- API üzerinden ingestion ve chat uç noktaları

---

## Sistem Mimarisi

```text
Kullanıcı
  → Streamlit Frontend
  → FastAPI Backend
  → LangGraph Agent
  → Intent Router
  → RAG Search / Resource Recommender Tool
  → LLM Answer Generation
  → PostgreSQL (Logs & Chat History)
  → Response + Sources + Agent Steps
```

**Veri katmanı (retrieval):** ham belgeler → chunking → ChromaDB (embedding) + BM25 (keyword)  
**Uygulama katmanı (kalıcılık):** PostgreSQL — oturumlar, mesajlar, geri bildirim, agent ve tool logları

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

Ek: **pypdf** (PDF parsing), **SQLAlchemy** + **Alembic** (veritabanı), **httpx** (frontend → backend).

---

## Agent Tools

### RAG Search Tool

PDF ve Markdown kaynaklardan hybrid arama yapar; bulunan pasajlara dayanarak kaynaklı cevap üretir. Yönetmelik maddeleri, akademik takvim, duyuru metinleri ve benzeri indexlenmiş içerikler için kullanılır.

- `selected_tool`: `rag_search`
- Akış: analyze → intent → retrieve → grade → (rewrite) → generate → validate

### Resource Recommender Tool

Ders içeriği veya konu ifadesine göre [Open Library](https://openlibrary.org) üzerinden kitap / kaynak önerir; isteğe bağlı olarak RAG bağlamı ile zenginleştirilir.

- `selected_tool`: `resource_recommender`
- Akış: analyze → intent → (RAG context) → Open Library → LLM öneri

API yanıtında `agent_steps` ve `selected_tool` alanları döner; Streamlit arayüzünde **Agent adımları** expander’ında gösterilir.

### Gelecek tool’lar (planlanan)

- Web crawler (public duyuru / yönetmelik toplama)
- Dilekçe / form asistanı
- Reranker
- RAG evaluation
- Admin panel

---

## Veri Kaynakları

Public repoda **demo Markdown belgeleri** bulunur:

```text
data/raw/samples/
  sample_regulation.md
  sample_academic_calendar.md
  sample_announcement.md
```

Bu metinler tamamen kurgu/demo amaçlıdır (kayıt dondurma, mazeret sınavı, mezuniyet, ders kaydı vb. konuları kapsar).

Gerçek belgeler yalnızca **lokal ortamda** eklenir:

```text
data/raw/pdf/     # PDF dosyaları (.gitignore)
data/raw/web/     # Markdown, metin, JSON (.gitignore)
data/raw/faq/     # İsteğe bağlı Gold FAQ
```

**Üretilen indeksler** (GitHub’a dahil edilmez):

```text
data/chroma/      # ChromaDB vektör indeksi
data/bm25/        # BM25 pickle indeksi
data/processed/   # chunks.jsonl
```

Desteklenen ingestion formatları: `.pdf`, `.md`, `.txt`, `.json`

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

Belge kaynaklarını chunk’layıp ChromaDB ve BM25 indekslerini oluşturur.

**Docker:**

```bash
docker compose exec backend python scripts/ingest_data.py
```

**Yerel:**

```bash
source venv/bin/activate
export PYTHONPATH=.
python scripts/ingest_data.py
```

Yalnızca demo `samples` klasörü (hızlı deneme):

```bash
python scripts/ingest_data.py --samples-only
```

Mevcut `chunks.jsonl` ile indeks yenileme:

```bash
python scripts/ingest_data.py --skip-sources
```

Alternatif: `POST /ingest` API uç noktası (FastAPI docs).

Chroma metadata örnekleri: `source`, `source_type`, `title`, `content_type`, `page`, `section_title`, `indexed_at`

---

## Kullanım Örnekleri

**RAG / yönetmelik ve süreç soruları**

- Kayıt dondurma şartları nelerdir?
- Mazeret sınavına kimler başvurabilir?
- Mezuniyet için gerekli şartlar nelerdir?
- Ders kaydı süreci nasıl işler?

**Kaynak / kitap önerisi**

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

PostgreSQL **vektör arama için kullanılmaz**. Arama katmanı ayrıdır:

| Bileşen | Görev |
|---------|--------|
| **ChromaDB** | Semantic / vector search |
| **BM25** | Keyword search |
| **Hybrid retrieval** | İki kanalın birleştirilmesi |

Chroma ve BM25 indeksleri dosya tabanlıdır (`data/chroma`, `data/bm25`).

---

## Redis’in Rolü

Redis iki amaçla kullanılır:

- **Answer cache** — Aynı normalize edilmiş soru tekrar sorulduğunda cevap `answer_cache:{intent}:{hash}` anahtarıyla Redis’ten döner; agent, RAG, LLM ve tool akışı yeniden çalıştırılmaz. Yanıt süresi ve API maliyeti düşer.
- **Health / status** — `GET /health` yanıtında `redis: ready | unavailable` alanı.

Yapılandırma (`.env`):

```bash
ENABLE_REDIS_CACHE=true
REDIS_CACHE_TTL_SECONDS=3600
REDIS_URL=redis://localhost:6379/0
```

Redis kullanılamazsa sistem cache’siz devam eder; chat akışı etkilenmez.

Cache doğrulama:

```bash
docker compose exec redis redis-cli keys '*answer_cache*'
```

---

## Projenin Sınırları

- Bu proje **lokal PoC / demo** olarak geliştirilmiştir; production hardening kapsamı dışındadır.
- Canlı üniversite API entegrasyonu (OBS, e-Devlet vb.) **içermez**.
- Kişisel öğrenci verisi (not, borç, gerçek transkript) **işlemez**.
- Kimlik doğrulama veya kurumsal SSO **yoktur**.
- Cevaplar **yalnızca indexlenmiş kaynaklarla** sınırlıdır; kaynak yoksa kesin iddia üretilmez.
- Resmi işlem yapmaz; bilgilendirme ve asistanlık amacı taşır.
- Hava durumu, dilekçe üretimi gibi henüz desteklenmeyen intent’ler için dürüst bilgi mesajı döner.

---

## Yol Haritası

- Web crawler ile public duyuru / yönetmelik toplama
- Dilekçe / form asistanı
- Reranker entegrasyonu
- RAG evaluation ve kalite metrikleri
- Admin panel (belge ve indeks yönetimi)
- Kimlik doğrulama (auth)
- Çoklu üniversite / çoklu koleksiyon desteği

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

---

## Klasör Yapısı

```text
backend/app/     FastAPI, agent, RAG, tools, db, services
frontend/        Streamlit UI
data/            Ham veri, işlenmiş chunk, indeksler
scripts/         Ingestion ve test betikleri
alembic/         Veritabanı migration
docker-compose.yml
```

Detaylı mimari notlar: [`context.md`](context.md) · Sürüm notları: [`CHANGELOG.md`](CHANGELOG.md)

---

## Lisans

Repoda henüz bir `LICENSE` dosyası tanımlı değildir. Projeyi dağıtırken uygun bir açık kaynak lisansı (ör. MIT) eklemeniz önerilir.
