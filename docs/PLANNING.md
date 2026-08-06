# Knowledge Base RAG — Planlama Dokümanı

Temel: production-rag-platform'un kanıtlanmış çekirdek pipeline'ı (chunking, hybrid search, rerank, grounded generation, citation, tracing) taşınıyor — sıfırdan yazılmıyor.

Asıl fark: çoklu doküman tipi (PDF/Markdown/web/Notion/Confluence) + otomatik incremental re-sync (sadece değişen içerik yeniden indekslenir).

LLM stratejisi: provider-agnostic — ortak bir interface üzerinden Ollama (local-first, varsayılan) + Claude API/OpenAI (bulut) desteklenir.

UI: Streamlit, multi-page (`st.navigation`) — Chat / Sources / Sync Status ayrı sayfalar (dbt-feature-lineage'daki desenin aynısı; `st.tabs()` lazy olmadığı için pahalı işlemler sayfa olmalı, tab değil).

Connector modeli: Local filesystem, Notion, Confluence hepsi aynı `Connector` interface'ini implemente eder (`list_documents()`, `fetch_content()`, `get_content_hash()`). Filesystem connector en basit ve en kolay test edilebilir olduğu için önce o, incremental sync mantığı onun üzerinde doğrulanıp sonra uzak connector'lara uygulanır.

## Sprint 0 — Foundation + Core Port

Amaç: production-rag-platform'un çekirdek pipeline'ını yeni repoya taşıyıp adapte etmek.

Scope:

* Yeni repo iskeleti (`app/{connectors,parsing,ingestion,retrieval,reranker,llm,registry,sync,shared}/`, `tests/`, `docs/`)
* Taşınacaklar (adapte edilerek): PyMuPDF PDF parser, chunker, Qdrant hybrid store, hybrid search, cross-encoder reranker, grounding/citation mantığı, OpenTelemetry tracing setup
* Taşıma sırasında namespace/modül isimleri yeni projeye göre düzenlenir, ama mantık korunur
* Taşınan testlerin (uyarlanmış haliyle) hâlâ yeşil olduğu doğrulanır

Açık sorular:

* Citation formatı (`[s.page/paragraph]`) bu projede en baştan multi-source olacağı için (`[s.source_type:source_id/page/paragraph]`gibi), Sprint 0'da mı yoksa Sprint 7'de mi genişletilecek — öneri: Sprint 0'da placeholder olarak genişletilmiş formatla başla, tekrar refactor gerektirmesin

DoD: taşınan pipeline'ın testleri yeşil, tek bir dokümanla (PDF) uçtan uca eski davranış (embed→retrieve→rerank→generate→citation) çalışıyor.

### Kapanış notu

Repo iskeleti ve çekirdek pipeline production-rag-platform'dan taşındı (bkz. `docs/sprint-00-plan.md` taşıma tablosu). Citation formatı planlanan gibi Sprint 0'da genişletildi — Sprint 5'e ertelenmedi: `[s.<source_type>:<source_id>/<page>/<paragraph>]`, örn. `[s.pdf:handbook/2/0]`. Grounding kontrolü artık `(source_type, source_id, page, paragraph)` dörtlüsüne göre çalışıyor; production-rag-platform'daki doc-scoping bug'ının regression testi de (`tests/test_grounding.py::test_grounding_rejects_citation_whose_page_paragraph_matches_a_different_source`) ve source_type ayrımı için ek bir test daha (`..._even_with_same_source_id`) taşındı/eklendi.

`Chunk` modeline `source_type`/`source_id` alanları eklendi; `QdrantStore.upsert_chunks`'ın `source_filename` parametresi kaldırıldı — artık payload bilgisi doğrudan chunk üzerinden geliyor. `app/retrieval/filters.py`'deki `source_filenames` filtresi `source_types`/`source_ids`'e ayrıldı.

107 test yeşil (5'i gerçek Ollama/Qdrant servisleri gerektirdiği için bu makinede skip edildi — servisler ayağa kaldırılmadı). DoD'nin "tek dokümanla uçtan uca" kısmı `tests/test_pipeline_e2e_hermetic.py` ile hermetik olarak kanıtlandı: gerçek bir PDF, gerçek PyMuPDF parse + chunk + gerçek Qdrant (`:memory:`) hybrid search (RRF) + gerçek grounding/citation-highlight mantığı üzerinden uçtan uca çalışıyor; yalnızca Ollama embedding/chat çağrıları (ağ/model indirme gerektirdiği için) fake'lendi. Gerçek servislerle aynı senaryo `tests/test_ingest_e2e.py` ve `tests/test_generation_e2e.py`'de mevcut, servisler ayağa kalktığında otomatik çalışacak.

Python sürümü notu: sistemin varsayılan `python3` 3.9 idi (pyproject `>=3.11` istiyor); venv Homebrew'daki `python3.12` ile kuruldu.

## Sprint 1 — Provider Abstraction

Amaç: LLM sağlayıcısını config'den değiştirilebilir hale getirmek.

Scope:

* `LLMProvider` interface'i (embed, chat/stream_chat metodları)
* `OllamaProvider` (Sprint 0'dan taşınan client'ın interface'e uydurulmuş hali)
* `ClaudeProvider` (Anthropic API, streaming destekli)
* Config'den sağlayıcı seçimi, local-first varsayılan
* Embedding tarafı da aynı abstraction'a girer mi (Ollama embedding + Claude'un embedding sunmadığı gerçeği) — bu netleştirilecek

Açık sorular:

* Claude API'nin embedding endpoint'i yok — embedding her zaman Ollama'da mı kalacak, yoksa OpenAI embedding de bir seçenek mi olacak (muhtemelen: embedding ayrı bir abstraction, generation'dan bağımsız seçilebilir)

DoD: aynı soru, config değişikliğiyle hem Ollama hem Claude API üzerinden gerçekten cevaplanabiliyor, iki sağlayıcı arası fark (varsa) somut örnekle gösterilmiş.

## Sprint 2 — Document Registry

Amaç: Sync/incremental indexing'in üzerine oturacağı metadata temeli.

Scope:

* Metadata store (SQLite, production-rag-platform'da DB kullanılmamıştı - bu yeni bir bileşen): `documents` tablosu (`source_type, source_id, content_hash, last_synced_at, version, status`)
* CRUD katmanı: doküman kaydet/güncelle/sil, hash'e göre değişiklik sorgula

DoD: registry'ye kaydedilen bir dokümanın hash'i değiştiğinde "değişti" olarak tespit edilebiliyor, testlerle doğrulanmış.

## Sprint 3 — Filesystem Connector + Multi-format Parsers

Amaç: Klasör bazlı ingestion'ı PDF + Markdown ile çalışır hale getirmek.

Scope:

* `Connector` interface'i (`list_documents()`, `fetch_content()`, `get_content_hash()`)
* `LocalFilesystemConnector`: klasörü tarar, PDF (Sprint 0'dan taşınan parser) + yeni Markdown parser kullanır
* Markdown parser: başlık hiyerarşisini (paragraf yerine section/heading) metadata olarak korur
* Registry'ye entegrasyon: taranan her dosya registry'ye kaydedilir

DoD: bir klasördeki PDF+Markdown karışımı tek komutla ingest ediliyor, her doküman registry'de doğru `source_type` ile görünüyor.

## Sprint 4 — Incremental Sync (Filesystem üzerinde doğrulama)

Amaç: Hash-bazlı diffing ile sadece değişeni yeniden işlemek — önce filesystem'de, en kolay test edilebilir ortamda.

Scope:

* Sync fonksiyonu: registry'deki hash ile diskteki güncel hash'i karşılaştırır
* Değişmemiş doküman: atlanır
* Değişmiş doküman: yeniden parse+chunk+embed+upsert, eski chunk'lar temizlenir
* Silinmiş doküman: registry'den ve Qdrant'tan temizlenir

Açık sorular:

* Bir dokümanın chunk sayısı değişirse (örn. içerik kısaldı) eski fazladan chunk'ların Qdrant'ta yetim kalmaması nasıl garanti edilecek — muhtemel çözüm: doc_id bazlı "önce tüm eski chunk'ları sil, sonra yenilerini yaz" stratejisi

DoD: bir dosya değiştirildiğinde sadece o dosyanın chunk'ları güncelleniyor (diğerlerine dokunulmuyor), bir dosya silindiğinde Qdrant'ta hiçbir yetim chunk kalmıyor — gerçek bir senaryo ile (dosya değiştir → sync → Qdrant'ı kontrol et) kanıtlanacak.

## Sprint 5 — Multi-source Citations

Amaç: Citation formatını kaynak tipini gösterecek şekilde netleştirmek (Sprint 0'da placeholder bırakıldıysa burada kesinleştirilir).

Scope:

* Citation formatı: `[s.SOURCE_TYPE:SOURCE_ID/LOCATION]` (örn. `[s.pdf:handbook/2/0]`, `[s.markdown:readme/Kurulum]`)
* Grounding check'in (production-rag-platform'da doc-scoping bug'ından öğrenilen ders) `(source_type, source_id, location)`üçlüsüne göre çalıştığı doğrulanır — aynı hatayı tekrarlamamak için özellikle test edilir

DoD: karışık kaynaklı bir koleksiyonda (PDF+Markdown) citation'lar doğru kaynağa işaret ediyor, yanlış kaynağa sızma yok — production-rag-platform'daki bug'ın regression testi burada da var.

## Sprint 6 — Web Page Parser + İlk Uzak Connector (Notion)

Amaç: Uzak/canlı bir kaynağı sisteme bağlamak.

Scope:

* Web sayfası parser (trafilatura veya benzeri, ana içeriği nav/reklam/footer'dan ayıklayan)
* `NotionConnector`: Notion API ile sayfa listeleme + içerik çekme, `Connector` interface'ine uyumlu
* Notion API rate limit'lerine karşı basit bir backoff

DoD: bir Notion workspace'inden (test workspace) içerik gerçekten çekilip ingest ediliyor, registry'de `source_type=notion`olarak görünüyor.

## Sprint 7 — Sync Scheduler

Amaç: Periyodik ve manuel sync tetiklemeyi otomatikleştirmek.

Scope:

* Periyodik job (APScheduler veya basit bir asyncio loop - Celery'nin ek karmaşıklığına gerek olup olmadığı değerlendirilecek, M2'de hafif kalması tercih edilir)
* Her connector için ayrı sync sıklığı config edilebilir
* Manuel "sync now" tetikleyici (API endpoint)

DoD: connector'lar config'deki sıklığa göre otomatik sync oluyor, manuel tetikleme de çalışıyor, sync geçmişi (başarı/hata) kaydediliyor.

## Sprint 8 — Observability Extension

Amaç: Tracing'i sync/ingestion pipeline'ına genişletmek (query tarafı Sprint 0'dan zaten taşınmıştı).

Scope:

* Sync/ingestion adımları (`fetch`, `parse`, `chunk`, `embed`, `upsert`, `cleanup`) span olarak instrument edilir
* Connector bazlı sync süresi ve başarı/hata oranı span attribute'u olarak eklenir

DoD: bir sync koşumu Jaeger'da uçtan uca izlenebiliyor, hangi connector'ın ne kadar sürdüğü görülüyor.

## Sprint 9 — Evaluation

Amaç: Çoklu kaynak tipini kapsayan bir golden set ile kalite ölçümü.

Scope:

* Golden set: en az PDF + Markdown + (varsa Notion) kaynaklardan sorular
* production-rag-platform'daki DeepEval + 7B judge yaklaşımı taşınır
* Kaynak tipi bazında ayrı metrik kırılımı (örn. Notion sorularında mı, PDF sorularında mı daha zayıf)

DoD: golden set komutla çalıştırılabiliyor, kaynak tipi bazında kırılım raporlanıyor.

## Sprint 10 — UI (Multi-page Streamlit)

Amaç: Chat + kaynak yönetimi + sync durumunu ayrı sayfalarda sunmak.

Scope:

* `st.navigation` ile 3 sayfa: Chat (production-rag-platform'dan taşınan streaming+citation+trace paneli), Sources (bağlı connector'lar, manuel sync tetikleme, doküman listesi), Sync Status (son sync zamanları, başarı/hata geçmişi, kaynak başına doküman sayısı)
* Pahalı işlemler (sync tetikleme) ayrı sayfada, tab içinde değil (dbt-feature-lineage dersinden)

DoD: üç sayfa da çalışıyor, bir kaynağı UI'dan manuel sync tetikleyip sonucu Sync Status sayfasında gerçekten görebiliyorsun.

## Sprint 11 — Docker Compose Polish

Amaç: Tek komutla kurulum.

Scope:

* production-rag-platform'daki desen taşınır (Qdrant+Jaeger+backend container'da, Ollama native)
* Yeni bileşen: registry DB (SQLite dosya bazlı ise ek container gerekmez, PostgreSQL'e geçilirse eklenir — karar burada netleşir)

DoD: sıfırdan kurulum (`docker compose down -v` + `up`) uçtan uca çalışıyor, gerçekten test edilmiş.

## Sprint 12 (stretch) — İkinci Connector (Confluence)

Amaç: Connector abstraction'ının gerçekten genellenebilir olduğunu kanıtlamak.

Scope:

* `ConfluenceConnector`, `Connector` interface'ine uyumlu, minimum kod tekrarıyla eklenir
* Eğer interface'e uymayan bir şey çıkarsa (örn. Confluence'a özgü bir kavram), bu Sprint 6'daki abstraction tasarımının bir eksiği olarak not düşülür — düzeltme burada yapılır

DoD: iki connector aynı anda aktif, ikisinden de gerçek içerik ingest edilip sorgulanabiliyor.
