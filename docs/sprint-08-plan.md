# Sprint 8 — Observability Extension

## Kör nokta taraması — kodu gerçekten okuyup bulundu, varsayılmadı

production-rag-platform'un dersi: lazy model yükleme hiçbir span'e sarılmamıştı. Burada model yükleme (`SparseEncoder`/`CrossEncoderReranker`) `__init__`'te EAGER (tembel değil) — ve zaten `embed_document()` çağrıları `embed_batch` span'i İÇİNDE yapılıyor, o yüzden bu spesifik bug burada YOK. Ama kodu satır satır okuyunca ÜÇ GERÇEK kör nokta bulundu:

1. **Bir sync koşumu tek trace DEĞİL — her doküman kendi trace'i.** `ingest_connector`'ın kendisi hiçbir üst span açmıyor; `tracer.start_as_current_span("ingest_document"/"delete_document")` doğrudan en üst seviyede çağrılıyor. OpenTelemetry'de bir span İÇİNDE başka bir span açılmazsa YENİ BİR TRACE ROOT'u olur. Sonuç: 3 dokümanlı bir klasörü sync etmek Jaeger'da 3 (+ silinen varsa daha fazla) AYRI, birbiriyle İLİŞKİSİZ trace üretiyor — DoD'nin "uçtan uca TEK trace" şartını doğrudan ihlal ediyor. Bu, kodu koşup Jaeger çıktısına bakmadan, salt trace/span ilişkilendirme kurallarını (child span'in PARENT context İÇİNDE açılması gerektiği) uygulayarak tespit edildi.
2. **Connector I/O (fetch) hiç span'lenmiyor.** `connector.list_documents()` (döngüden ÖNCE) ve her doküman için `connector.get_content_hash()` (`has_changed()` kontrolünden önce) span'siz çağrılıyor. Notion için bunlar GERÇEK ağ istekleri (+ 429 backoff sleep'leri) — şu an tamamen görünmez. `NotionConnector.fetch_content()` (yine ağ, sayfalanmış) ise `parse_and_chunk` span'inin İÇİNE gömülü — CPU-bound parse işiyle aynı span'de, ikisini birbirinden ayıramıyorsunuz (bir sync'in yavaş olması ağ mı yoksa parse mı diye Jaeger'a bakarak ANLAŞILAMIYOR — production-rag-platform'un "görünmeyen maliyet kaynağı" dersinin aynısı).
3. **Atlanan (skip edilen) dokümanlar tamamen görünmez.** `has_changed() == False` olan bir doküman için HİÇBİR span açılmıyor — sadece sayaç artıyor. Jaeger'da "52 dokümandan 50'si kontrol edildi ve değişmediği için atlandı" bilgisi YOK, sadece işlenen 2 doküman görünüyor. Bir sync'in NEDEN çalıştığı (ya da beklenenden uzun sürdüğü — 50 dokümanın hash'ini kontrol etmek bile zaman alır) trace'den anlaşılamıyor.

## Düzeltmeler

* `ingest_connector`'ın TÜM gövdesi yeni bir üst span'e (`ingest_connector`) sarıldı — `source_type` attribute'u ile. Artık aynı koşumdaki TÜM alt span'ler (silme, fetch, parse, embed, upsert) AYNI trace_id'yi paylaşıyor.
* Yeni `fetch_documents` span'i: `connector.list_documents()` çağrısını sarıyor (kaç doküman bulunduğu attribute olarak).
* Yeni `check_document` span'i: her doküman için `get_content_hash()` + `has_changed()` kontrolünü sarıyor — SKIP edilse bile (`sync.skipped` attribute'u `True`/`False`) — artık atlanan dokümanlar da trace'de GÖRÜNÜYOR, sadece "işlenmedi" diye işaretli.
* Notion'ın `fetch_content()`'ı `parse_and_chunk`'tan AYRILDI — kendi `fetch` span'i içinde çağrılıyor, `parse_and_chunk` artık sadece CPU-bound metin işlemeyi ölçüyor. PDF/Markdown için zaten dosya yolundan okunuyor (ayrı bir ağ maliyeti yok) — `parse_and_chunk` onlar için değişmedi.
* `ingest_document`/`delete_document` span'lerine (zaten vardı) `source_type` attribute'u zaten ekliydi, korunuyor.

## `sync_run` (SyncManager) — trace_id kararı

**Karar: EVET, `trace_id` `sync_runs` tablosuna yazılıyor.** `SyncManager.trigger_sync()` artık TÜM denemeyi (REDDEDİLEN durum DAHİL) saran bir `sync_run` span'i açıyor. Bu, Sprint 0'ın `generate.py::stream_answer`'ının zaten kurduğu presedansla AYNI desen: `format(span.get_span_context().trace_id, "032x")` ile trace_id çıkarılıp `SyncHistory.start_run()`'a geçiriliyor, `sync_runs` tablosuna yeni bir `trace_id TEXT` kolonu eklendi. Gerekçe: Sprint 10'un "Sync Status" sayfasında "bu sync neden yavaştı" sorusunun cevabı doğrudan Jaeger'a link olacak — `trace_id` olmadan kullanıcı Jaeger'da hangi trace'e bakacağını bulamaz. `start_run()` sırasında (henüz sync bitmeden) yazılıyor — hâlâ ÇALIŞAN bir sync'in trace'ine de erken erişilebilsin diye (bitmesini beklemeye gerek yok).

`ingest_connector`'ın kendi üst span'i `sync_run`'ın İÇİNDE açıldığı için (context propagation `await` sınırları arasında `contextvars` ile otomatik çalışıyor, Sprint 0'ın `generate.py` testlerinde zaten kanıtlanmış bir mekanizma) aynı trace_id'yi paylaşıyor — SyncManager'ın ayrıca bir tracer geçirmesine gerek yok.

## Yüksek kardinaliteli veri sızıntısı — test garantisi

production-rag-platform'un dersi tekrar test ediliyor: yeni `fetch_documents`/`check_document`/`sync_run` span'lerinin HİÇBİRİNE tam chunk metni, tam fetch edilen içerik (Notion blok metni, dosya içeriği) veya tam URL/response body yazılmıyor — sadece sayılar (`document_count`, `chunk_count`) ve kimlikler (`source_id`, `source_type`). Sprint 0'ın `test_ingest_path_spans_do_not_contain_chunk_text` deseniyle aynı, yeni span'ler için de tekrarlanıyor.

## Gerçek Jaeger doğrulaması

Bu makinede Docker çalışıyor ve `docker-compose.yml` zaten Jaeger+Qdrant tanımlıyor — Sprint 1/6'daki "API key yok, mock'la belgelendi" durumunun AKSİNE, burada gerçek doğrulama YAPILABİLİR. Plan: `docker compose up -d jaeger qdrant`, gerçek `setup_tracing()` + gerçek bir filesystem sync koşumu, Jaeger'ın HTTP API'sinden (`GET /api/traces?service=knowledge-base-rag`) trace'i gerçekten sorgulayıp TEK bir trace_id altında `sync_run → ingest_connector → fetch_documents/check_document/ingest_document → parse_and_chunk/embed_batch/upsert_batch` hiyerarşisinin göründüğünü kanıtlamak. Doğrulama sonrası container'lar durduruluyor (`docker compose down`) — geliştirme ortamını olduğu gibi bırakmak için.

## DoD doğrulama planı

1. `pytest -q` yeşil, `ruff check` temiz.
2. Yeni span'lerin unit testleri: doğru parent-child ilişkisi (tek trace_id), doğru attribute'lar, skip edilen dokümanlar için de span üretimi.
3. Yüksek kardinaliteli veri sızmadığı testle kanıtlı.
4. Gerçek Jaeger'a karşı GERÇEKTEN doğrulanmış (mock değil) — sonuç Sprint 8 kapanış notuna yazılacak.
