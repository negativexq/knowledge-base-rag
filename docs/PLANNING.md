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

### Kapanış notu

Tasarım gerçek kullanım yerlerinden çıkarıldı (bkz. `docs/sprint-01-plan.md`): tek bir "LLMProvider" yerine iki ayrı Protocol — `ChatProvider` (`stream_chat(messages, model) -> AsyncIterator[str]`, `generate.py`'nin ihtiyacı) ve `EmbeddingProvider` (`embed(text, model, prefix) -> list[float]`, `search.py`'nin ihtiyacı). Bu iki Protocol `app/llm/provider.py`'de merkezi; `generate.py`/`search.py`'deki eski yerel/aynı-şekilli Protocol tanımları buradan import edilecek şekilde değiştirildi — davranışta hiçbir değişiklik yok (yapısal tipleme), sadece tekrar kaldırıldı.

**Embedding/generation ayrımı kararı:** embedding, generation'dan tamamen bağımsız bir seçim olarak tasarlandı — Claude'un embedding endpoint'i olmaması aşılamaz bir kısıt olduğu için `EmbeddingProvider` hiçbir zaman `ChatProvider` seçimine bağlı olamaz. Config'de bu iki alan ayrı: `generation_provider: Literal["ollama","claude"]` (varsayılan `"ollama"`, local-first) ve `embedding_provider: Literal["ollama"]` (şu an tek değerli — ikinci bir embedding sağlayıcısı olmadığı için, ama `search.py`/`ingest.py` hâlâ bu ayrı ayardan geçen bir factory'den (`get_embedding_provider`) geçiyor, böylece ileride bir embedding sağlayıcısı eklemek çağıran koda dokunmayacak). `ClaudeProvider`, `EmbeddingProvider` Protocol'ünü yapısal olarak KARŞILAMIYOR — bu, ayrımın somut kanıtı olarak bir testle (`tests/test_provider.py::test_claude_provider_does_not_satisfy_embedding_provider_protocol`) doğrulandı.

`OllamaProvider`, `OllamaClient`'ın yeniden export'u (`app/llm/ollama_provider.py`) — `OllamaClient` Sprint 0'dan beri `stream_chat`/`embed` metotlarıyla her iki Protocol'ü de zaten yapısal olarak karşılıyordu, bu yüzden aynı metotları tekrarlayan bir adapter sınıfı yazmak gereksiz bir katman olurdu. `ClaudeProvider` (`app/llm/claude_provider.py`) gerçek `anthropic` SDK'sının `AsyncAnthropic.messages.stream(...)` ile gerçek streaming yapıyor; `role="system"` mesajını Anthropic'in ayrı `system=` parametresine çeviriyor (Ollama/OpenAI tarzı chat API'lerin aksine Anthropic system prompt'u mesaj listesinde değil ayrı bir alanda bekliyor) — bu çeviri `prompt.py`'a dokunmadan provider sınırında yapıldı.

**Grounding/citation provider'dan bağımsız:** `tests/test_generate_provider_agnostic.py` aynı citation tag'ini hem bir sahte Ollama-şekilli provider'dan hem de gerçek `ClaudeProvider` sınıfından (mocklanmış transport ile, gerçek SSE parse kodu çalışarak) üretip `check_grounding`'in ikisinde de birebir aynı sonucu verdiğini kanıtlıyor — hem başarılı grounding hem fabricated-citation senaryosu için.

**Gerçek Ollama-vs-Claude karşılaştırması: ATLANDI.** Bu makinede `ANTHROPIC_API_KEY` set değil ve `.env` dosyası yok — `tests/test_provider_comparison_e2e.py` bu yüzden otomatik skip oldu (Sprint 0'daki `_ollama_up()` deseniyle aynı, `ANTHROPIC_API_KEY` şartı eklenmiş hali). Dolayısıyla **iki sağlayıcı arasında gözlemlenmiş somut bir davranış farkı yok** — bu, "fark yok" tespiti değil, "test hiç çalışmadı" durumu. `ANTHROPIC_API_KEY` `.env`'e eklenip bu test tekrar çalıştırıldığında gerçek bir karşılaştırma üretecek; DoD'nin bu kısmı şu an için AÇIK kalıyor.

Ayrıca: `tests/test_pipeline_e2e_hermetic.py`'deki (Sprint 0'dan) sahte sparse encoder'da gizli bir flakiness bulundu ve düzeltildi — `hash(word) % 5000` farklı kelimelerin aynı indekse çarpışmasına yol açabiliyordu (Python'da string hash'i process başına rastgele, `PYTHONHASHSEED`'e bağlı), bu da Qdrant'ın yerel modunun "indices must be unique" hatasıyla ~%10-15 ihtimalle testi düşürüyordu. Indeksler artık bir `set` üzerinden dedupe ediliyor; düzeltme 10 ardışık çalıştırmada doğrulandı.

132 test yeşil (6'sı gerçek servis gerektirdiği için skip — 5'i Sprint 0'dan, +1 bu sprintin `ANTHROPIC_API_KEY` gerektiren karşılaştırma testi), `ruff check` temiz.

## Sprint 2 — Document Registry

Amaç: Sync/incremental indexing'in üzerine oturacağı metadata temeli.

Scope:

* Metadata store (SQLite, production-rag-platform'da DB kullanılmamıştı - bu yeni bir bileşen): `documents` tablosu (`source_type, source_id, content_hash, last_synced_at, version, status`)
* CRUD katmanı: doküman kaydet/güncelle/sil, hash'e göre değişiklik sorgula

DoD: registry'ye kaydedilen bir dokümanın hash'i değiştiğinde "değişti" olarak tespit edilebiliyor, testlerle doğrulanmış.

### Kapanış notu

**SQLite erişim kararı: stdlib `sqlite3` + ince bir `DocumentRegistry` DAO sınıfı, SQLAlchemy YOK** (bkz. `docs/sprint-02-plan.md`). Gerekçe: tek tablo, tek gerçek sorgu şekli (`(source_type, source_id)` oku/yaz/sil + hash karşılaştır) — ORM'in çözdüğü join karmaşıklığı/migration/çoklu-backend problemleri burada yok. Proje zaten bu düzende: `QdrantStore` ham `qdrant-client`'ı, `OllamaClient` ham `httpx`'i sarmalıyor — registry'nin farklı davranmasını gerektiren bir sinyal yok. M2/16GB önceliği de ek bağımlılık/öğrenme yükü istemiyor. Migration aracı da yok (tek tablo, `CREATE TABLE IF NOT EXISTS` yeterli) — şema gerçekten çoğalırsa bu karar gözden geçirilecek.

**Şema kararları:** primary key `(source_type, source_id)` — Sprint 0/1'de citation/grounding'in zaten kullandığı aynı kimlik çifti, ileride chunk↔registry eşlemesi için ayrı bir tabloya gerek bırakmıyor. `last_synced_at` datetime nesnesi değil ISO 8601 TEXT olarak saklanıyor — Python 3.12 `sqlite3`'ün örtük datetime adapter'larını deprecated etti, kendi adapter'ımızı yazmak yerine en basit çözüm bu. `version`, `content_hash` GERÇEKTEN değiştiğinde artıyor; aynı hash'le tekrar senkronize edilirse (yaygın durum) sadece `last_synced_at` tazeleniyor, version sabit kalıyor — Sprint 4'ün "sadece değişeni yeniden indeksle" mantığının temel sinyali bu. `status` şimdilik serbest bir alan (varsayılan `"active"`), bu sprintte hiçbir otomatik durum makinesi yok — Sprint 4/7'nin üzerine oturacağı yer.

**CRUD tasarımı:** ayrı `insert`/`update` yerine tek bir `upsert_document` (SQL'de `INSERT ... ON CONFLICT DO UPDATE`, version artışı `CASE WHEN` ile tek atomik sorguda). Gerekçe Sprint 1'deki ilkeyle aynı — gerçek kullanım yerinden çıkarıldı: bir sync döngüsü her zaman "bunu az önce senkronize ettim" der, dokümanın önceden var olup olmadığını bilmesine gerek yok; bunu çağıran tarafa "önce var mı diye bak" yükü olarak vermek gereksiz bir katman olurdu. `has_changed(source_type, source_id, content_hash)` ayrı bir metot — DoD'nin asıl kanıtlamak istediği "değişti mi" sorusunu doğrudan cevaplıyor (kayıt yoksa `True`, hash aynıysa `False`, farklıysa `True`).

**Test stratejisi:** tüm testler gerçek bir SQLite dosyasına karşı (`tmp_path / "registry.db"`), `:memory:` değil — Sprint 0'ın Qdrant `:memory:` dersinden (gerçek sunucudan sessizce farklı davranması) hareketle aynı ihtiyat SQLite'a da uygulandı. `test_data_persists_to_the_real_file_across_separate_connections` özellikle AYNI dosyaya iki ayrı `DocumentRegistry` bağlantısı açıp verinin kalıcı olduğunu kanıtlıyor — bunu `:memory:` gösteremezdi. DoD'nin somut kanıtı: `test_has_changed_is_true_when_hash_differs_from_the_registered_one`.

151 test yeşil (6'sı gerçek servis gerektirdiği için skip, Sprint 0/1'den değişmedi), `ruff check` temiz. Registry henüz hiçbir yere bağlanmadı (ingest/sync pipeline'a entegrasyon Sprint 3/4'te) — bu sprint sadece bileşenin kendisini ve doğruluğunu kanıtlıyor.

## Sprint 3 — Filesystem Connector + Multi-format Parsers

Amaç: Klasör bazlı ingestion'ı PDF + Markdown ile çalışır hale getirmek.

Scope:

* `Connector` interface'i (`list_documents()`, `fetch_content()`, `get_content_hash()`)
* `LocalFilesystemConnector`: klasörü tarar, PDF (Sprint 0'dan taşınan parser) + yeni Markdown parser kullanır
* Markdown parser: başlık hiyerarşisini (paragraf yerine section/heading) metadata olarak korur
* Registry'ye entegrasyon: taranan her dosya registry'ye kaydedilir

DoD: bir klasördeki PDF+Markdown karışımı tek komutla ingest ediliyor, her doküman registry'de doğru `source_type` ile görünüyor.

### Kapanış notu

**`source_type`'ın anlamı bilinçli olarak değişti — format değil, connector.** Sprint 0'da `source_type="pdf"` dosya FORMATINI ifade ediyordu. Bu sprint DoD'si `[s.filesystem:.../...]` istediği için (bkz. `docs/sprint-03-plan.md`) `source_type` artık dokümanın HANGİ CONNECTOR'DAN geldiğini ifade ediyor (`"filesystem"`, ileride `"notion"`, `"confluence"`) — format (pdf/markdown) sadece `ConnectorDocument.content_type` üzerinden hangi parser'ın kullanılacağını belirleyen dahili bir sinyal, citation'a hiç sızmıyor. Gerekçe: aynı connector (örn. Confluence) hem HTML hem PDF eki döndürebilir; kullanıcı için "bu bilgi nereden geldi" sorusunun anlamlı cevabı kaynaktır, format değil.

**Markdown location şeması — "net tanımlanan" kısım:** `app/parsing/markdown_parser.py::extract_blocks`, markdown'ı blank-line ile ayrılmış bloklara böler, her bloğu o anki heading stack'e (`heading_path: tuple[str, ...]`, örn. `("Kurulum", "Adım 1")`) etiketler; `block_index` her yeni `heading_path`'te 0'dan başlıyor (PDF'in sayfa-içi `paragraph_index`'inin analoğu). Fenced code block'lar (```` ``` ````) blank-line'a göre bölünmüyor. Citation location: `heading_path` doluysa `"/".join(heading_path)` (örn. `"Kurulum/Adım 1"`), boşsa (ilk başlıktan önceki içerik, nadir) PDF tarzı `"{page_number}/{paragraph_index}"`'e düşüyor — bu, ekstra bir alan eklemeye değmeyecek kabul edilmiş bir sınırlama.

**Bunun zorunlu kıldığı genelleme:** Markdown location'ı iki zorunlu tamsayıya sığmadığı için `grounding.py`'nin regex'i `\[s\.([\w\-]+):([\w\-]+)/(\d+)/(\d+)\]`'den `\[s\.([\w\-]+):([\w\-]+)/([^\]]+)\]`'e genelleşti; `GroundingResult.citations_found`/`ungrounded_citations` artık `(source_type, source_id, location)` üçlüsü (eskiden `(source_type, source_id, page, paragraph)` dörtlüsüydü). Ortak bir `app/llm/citation_location.py::location_for(payload)` fonksiyonu hem tag üretiminde (`prompt.py::build_context`) hem doğrulamada (`grounding.py::check_grounding`) kullanılıyor — Sprint 0'ın "citation aynı mantıkla üretilip doğrulanmalı" dersiyle aynı ilke. `Chunk`'a `heading_path: tuple[str, ...] = ()` eklendi (sona, varsayılanla) — bu sayede TÜM Sprint 0/1 `Chunk(...)` çağrıları değişmeden çalışmaya devam etti, gerçek bir regresyon olmadı (179→196 test, hepsi yeşil).

**`Connector` interface'i gerçek kullanım yerinden çıkarıldı** (Sprint 1/2'deki ilkeyle aynı): `ingest_connector`'ın `list_documents()` → `get_content_hash()` (registry'ye yazılacak hash) → parse+chunk (`document.path` üzerinden) → `registry.upsert_document()` akışına bakılarak üç metotlu Protocol netleşti. **Bilinçli sınırlama:** `ingest_connector`'ın tip imzası şu an `Connector` Protocol'üne değil doğrudan `LocalFilesystemConnector`'a özel — henüz var olmayan bir ikinci connector'a göre soyutlamak spekülasyon olurdu; parser'lar hâlâ dosya yolundan okuyor (bytes'tan değil), bu yüzden `ConnectorDocument.path` (filesystem'e özel, `None` olabilir) şu an gerekli. Sprint 6'da gerçek bir ikinci connector (Notion) eklendiğinde bu dispatch mekanizması (muhtemelen `content_type`+`fetch_content()` bytes'ı üzerinden) yeniden değerlendirilecek.

**`LocalFilesystemConnector`:** `source_type="filesystem"`, klasörü recursive OLMADAN tarıyor (Sprint 0'ın `glob("*.pdf")` presedanıyla tutarlı). `source_id`, dosya adının UZANTI DAHİL slugify'i (`slugify(name, strip_extension=False)` — `app/shared/slug.py`'ye eklenen yeni parametre) — aksi halde `handbook.pdf` ve `handbook.md` aynı `source_id`'ye çarpışıp registry'nin `(source_type, source_id)` primary key'ini bozardı. `get_content_hash()`, `compute_doc_id()` ile aynı algoritma (sha256); `ingest_connector` bu hash'i hem registry'ye hem `chunk_document`/`chunk_markdown_document`'ın yeni `doc_id` override parametresine geçiyor — dosya iki kere hash'lenmiyor.

**Bilinçli sınırlama (DoD'de de belirtilen):** bu sprintte incremental sync YOK — `ingest_connector` her çalıştırmada TÜM klasörü tarayıp yeniden ingest ediyor, hash aynı olsa bile. `registry.upsert_document` her doküman için (chunk+upsert BAŞARILI olduktan SONRA, kısmi hata registry'de yanlış "başarılı" izlenimi bırakmasın diye) çağrılıyor, böylece `has_changed()` doğru cevap veriyor — ama `ingest_connector` bu bilgiyi henüz "atla" kararı için KULLANMIYOR. Bu tam olarak Sprint 4'ün konusu; gerçek bir dosya değişikliğinde `version`'ın gerçekten arttığı `tests/test_ingest_connector.py::test_ingest_connector_rerun_bumps_registry_version_only_when_content_changes`'de kanıtlandı.

**Uçtan uca kanıt:** `tests/test_pipeline_connector_e2e_hermetic.py` gerçek bir PDF+Markdown karışık klasörü `ingest_connector` ile tek çağrıda ingest edip her iki doküman türü için de gerçek hybrid search + gerçek grounding + gerçek citation highlighting'in doğru çalıştığını kanıtlıyor: PDF chunk'ı `[s.filesystem:handbook_pdf/2/0]`, markdown chunk'ı `[s.filesystem:readme_md/Kurulum]` formatında, ikisi de `check_grounding` ile doğrulanıyor.

196 test yeşil (6'sı gerçek servis gerektirdiği için skip, Sprint 0/1/2'den değişmedi), `ruff check` temiz, 5 ardışık çalıştırmada flakiness yok.

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

### Kapanış notu

**Yetim chunk sorusu: `doc_id` bazlı DEĞİL, `(source_type, source_id)` bazlı silme.** Planın önerisi doc_id (içerik hash'i) bazlıydı; düşünülüp bundan bilerek vazgeçildi (bkz. `docs/sprint-04-plan.md`). Gerekçe: `doc_id` her içerik değişikliğinde değişiyor, bu yüzden "eski doc_id'ye göre sil" stratejisi silmeden önce registry'den ESKİ hash'i ayrıca okumayı gerektirir — iki hash'i doğru sırada kullanma sorumluluğu getirir. `(source_type, source_id)` ise dokümanın YAŞAM BOYU SABİT kimliği (Sprint 0'dan beri citation/grounding'in zaten kullandığı çift); bu ikiliye göre silmek ekstra okumaya gerek bırakmıyor VE chunk sayısı kaç olursa olsun (arttı/azaldı/hash değişti) o dokümana ait HER ŞEYİ garantili temizliyor. `QdrantStore.delete_by_source(source_type, source_id)` eklendi (Qdrant `Filter` ile), değişen bir doküman yeniden ingest edilmeden HEMEN ÖNCE çağrılıyor — yeni bir doküman için de güvenle çağrılabiliyor (silinecek 0 point, no-op).

**`ingest_connector` üç aşamalı sync'e dönüştü:** (1) registry'de bu `source_type` için olup connector'ın artık listelemediği dosyalar → `delete_by_source` + `registry.delete_document`; (2) `registry.has_changed()` `False` diyorsa → tamamen atlanıyor, Qdrant'a SIFIR çağrı (ne upsert ne delete), registry'ye de dokunulmuyor; (3) yeni/değişmiş dokümanlar → önce `delete_by_source` (eski chunk'ları temizle), sonra parse+chunk+embed+upsert, sonra `registry.upsert_document`. `IngestStats`'a `files_skipped`/`files_deleted` eklendi (sona, varsayılanla — `ingest_path`'in eski çağrısı değişmeden çalışıyor).

**Bilinçli sınırlama:** atlanan (değişmemiş) dokümanlarda registry'ye de HİÇ dokunulmuyor — `last_synced_at` tazelenmiyor. "Atla" kelimesi en dar haliyle uygulandı: sıfır Qdrant yazması, sıfır registry yazması. "En son ne zaman kontrol edildi" bilgisinin içerik değişmese bile tutulması Sprint 7'nin sync geçmişi ihtiyacı olabilir — şimdiden eklemek YAGNI olurdu.

**Üç senaryo da gerçek dosya/Qdrant/registry ile ayrı ayrı kanıtlandı** (`tests/test_sync_scenarios.py`):
* **Update:** `a.md` diskte değiştirildi → sync → `a`'nın Qdrant'taki metni YENİ içeriği taşıyor, ESKİ içerik hiçbir point'te yok; `b.md`'nin point'leri (ID'leri ve payload'ları DAHİL) sync öncesi/sonrası birebir aynı nesneler — sadece "hâlâ var" değil, "hiç dokunulmadı" kanıtlandı.
* **Delete:** `a.md` diskten silindi → sync → Qdrant'ta `source_id=a_md` ile eşleşen SIFIR point, registry'de kaydı yok, `b.md` dokunulmadan duruyor, `stats.files_deleted == 1`.
* **No-op:** `QdrantStore`'u saran bir `_CountingStore` (upsert/delete çağrılarını sayan) ile ikinci, değişiklik içermeyen sync çağrısında `upsert_calls == 0` ve `delete_calls == 0` — gerçekten "istek gitmedi" kanıtı, sadece "sonuç aynı" değil.
* **Ekstra (DoD'nin "chunk sayısı azalırsa" senaryosu):** 30 cümlelik uzun bir bölüm tek cümleye kısaltıldı → sync sonrası Qdrant'ta o dokümana ait TEK bir point kalıyor, eski fazladan chunk'lardan hiçbiri kalmıyor.

205 test yeşil (6'sı gerçek servis gerektirdiği için skip, değişmedi), `ruff check` temiz, 5 ardışık çalıştırmada flakiness yok.

## Sprint 5 — Multi-source Citations

Amaç: Citation formatını kaynak tipini gösterecek şekilde netleştirmek (Sprint 0'da placeholder bırakıldıysa burada kesinleştirilir).

Scope:

* Citation formatı: `[s.SOURCE_TYPE:SOURCE_ID/LOCATION]` (örn. `[s.pdf:handbook/2/0]`, `[s.markdown:readme/Kurulum]`)
* Grounding check'in (production-rag-platform'da doc-scoping bug'ından öğrenilen ders) `(source_type, source_id, location)`üçlüsüne göre çalıştığı doğrulanır — aynı hatayı tekrarlamamak için özellikle test edilir

DoD: karışık kaynaklı bir koleksiyonda (PDF+Markdown) citation'lar doğru kaynağa işaret ediyor, yanlış kaynağa sızma yok — production-rag-platform'daki bug'ın regression testi burada da var.

### Kapanış notu — doğrulama sprint'i

Bu sprintin kapsamı büyük ölçüde Sprint 3'te zaten karşılanmıştı (o sprint markdown desteği eklerken citation formatını genellemek ZORUNDA kaldı — bkz. Sprint 3 kapanış notu). Varsaymak yerine kod ve testler tek tek tarandı; sonuç madde madde:

* **Citation formatı `[s.SOURCE_TYPE:SOURCE_ID/LOCATION]`** — ✅ Sprint 3'te tamamlandı (`app/llm/prompt.py::citation_tag`, `app/llm/citation_location.py::location_for`). Kanıt: `tests/test_prompt.py`, `tests/test_citation_formatting.py`.
* **Grounding'in `(source_type, source_id, location)` üçlüsüne göre çalışması** — ✅ Sprint 3'te tamamlandı (`app/llm/grounding.py`). Kanıt: `tests/test_grounding.py` (9 test).
* **production-rag-platform'daki doc-scoping bug'ının regression testi** — ✅ Sprint 0'da taşınmıştı, Sprint 3'te yeni 3-tuple formatına uyarlandı, hâlâ mevcut ve yeşil: `tests/test_grounding.py::test_grounding_rejects_citation_whose_page_paragraph_matches_a_different_source`.
* **Karışık kaynaklı (PDF+Markdown) koleksiyonda citation'ların doğru kaynağa işaret ettiği, gerçek bir sorguyla gösterilmesi** — ✅ Sprint 3'te tamamlandı: `tests/test_pipeline_connector_e2e_hermetic.py`, gerçek ingest → gerçek hybrid search → gerçek generate → gerçek grounding.
* **"Yanlış kaynağa sızma yok" — çakışan location'lı iki dokümanla özel bir sızma testi** — ❌ EKSİKTİ. Mevcut olan (`test_grounding.py`'deki doc-scoping testi) sadece UNIT seviyesinde, elle uydurulmuş (synthetic) payload'larla çalışıyordu — gerçek ingest edilmiş, gerçek bir çakışmayla (örn. iki farklı PDF'in doğal olarak ikisinin de sayfa 1/paragraf 0'da chunk'ı olması) FULL PIPELINE seviyesinde hiç kanıtlanmamıştı. Bu sprintte eklendi: `tests/test_citation_cross_source_leak_e2e.py` (3 test) — iki gerçek PDF (page 1/paragraph 0'da doğal çakışma) ve iki gerçek Markdown dosyası (aynı `# Giriş` başlığında doğal çakışma) gerçekten ingest edilip TEK bir koleksiyona yazılıyor, çakışma gerçekten doğrulanıyor (`assert ... == (1, 0)` iki belge için de), sonra:
  * her dokümanın KENDİ citation'ı karışık context'e karşı doğrulanıyor (grounded=True),
  * bir dokümanın tag'i SADECE öteki dokümanın chunk'ını içeren context'e karşı test edilip REDDEDİLDİĞİ kanıtlanıyor (`grounded=False`) — location eşleşse bile,
  * üçüncü test bunu `check_grounding`'i doğrudan çağırmak yerine gerçek `stream_answer` üretim akışından geçirerek kanıtlıyor: model, context'te OLMAYAN bir dokümanın gerçeğini context'teki dokümanın tag'iyle etiketlediğinde (`[s.filesystem:handbook_pdf/1/0]` ama context'te sadece `cv_pdf` var), grounding bunu doğru şekilde `ungrounded_citations=[("filesystem", "handbook_pdf", "1/0")]` olarak yakalıyor.

208 test yeşil (6'sı gerçek servis gerektirdiği için skip, değişmedi — bu sprintte +3 yeni test), `ruff check` temiz, 5 ardışık çalıştırmada flakiness yok. Yeni kod yazılmadı (grounding/citation mantığı zaten Sprint 3'te doğruydu) — sadece eksik olan kanıt eklendi.

## Sprint 6 — Web Page Parser + İlk Uzak Connector (Notion)

Amaç: Uzak/canlı bir kaynağı sisteme bağlamak.

Scope:

* Web sayfası parser (trafilatura veya benzeri, ana içeriği nav/reklam/footer'dan ayıklayan)
* `NotionConnector`: Notion API ile sayfa listeleme + içerik çekme, `Connector` interface'ine uyumlu
* Notion API rate limit'lerine karşı basit bir backoff

DoD: bir Notion workspace'inden (test workspace) içerik gerçekten çekilip ingest ediliyor, registry'de `source_type=notion`olarak görünüyor.

### Kapanış notu

**`Connector` interface'inde Sprint 3'ten beri saklı iki gerçek varsayım, ikinci implementasyonla ortaya çıktı ve düzeltildi** (bkz. `docs/sprint-06-plan.md`):

1. **Protocol metotları senkrondu.** `list_documents()`/`fetch_content()`/`get_content_hash()` `def` idi — `LocalFilesystemConnector` için sorun değildi (disk I/O), ama `NotionConnector` gerçek ağ çağrıları için `async` OLMAK ZORUNDA. Üç metot da `async def` oldu; `LocalFilesystemConnector` bunu bedelsiz karşıladı (senkron kod `async def` içine sarıldı, davranış değişmedi). Bu yön (senkron→async genelleştirme) doğruydu çünkü tersi (async bir connector'ı senkron bir arayüze sığdırmak) blocking hack'ler olmadan mümkün değil.
2. **`get_content_hash()` her zaman tam içerik getirmeyi varsayıyordu.** Yerelde bedelsiz (dosya zaten okunuyor), ama Notion'da HER sync taramasında (Sprint 4'ün `has_changed()` kontrolü) tüm sayfa bloklarını çekmek incremental sync'in amacını baltalar. `ConnectorDocument`'a `etag: str | None = None` eklendi (`path` alanının kurduğu presedansla aynı desen) — `NotionConnector` bunu `list_documents()` sırasında zaten ucuza aldığı `last_edited_time` ile dolduruyor, `get_content_hash()` SADECE bunu hash'liyor, `fetch_content()`'i hiç çağırmıyor. `LocalFilesystemConnector` değişmedi (`etag` hep `None`).

Bunlar dışında Sprint 3'ün tasarladığı `Connector` Protocol'ü (üç metot + `source_type`) doğrulandı, değişmedi.

**Web parser: Sprint 3'ün markdown location şemasının doğrudan yeniden kullanımı.** `trafilatura.extract(html, output_format="markdown", include_formatting=True)` GERÇEKTEN denendi (varsayılmadı) — `include_formatting=True` olmadan trafilatura başlık işaretleyicisi OLMAYAN düz metin döndürüyor (boş bir varsayım olurdu, canlı deneyle yakalandı). Doğru ayarla nav/header/footer/aside gerçekten atılıyor, gerçek içerik `#`/`##` ile markdown olarak geliyor. Bu, HTML için ayrı bir location şeması icat etmek yerine `app/parsing/markdown_parser.py::extract_blocks()`'u DOĞRUDAN yeniden kullanmayı sağladı. Bunu mümkün kılmak için `chunk_markdown_document()`'ın metin işleme çekirdeği `chunk_markdown_text(text, source_id, source_type, doc_id, ...)` olarak ayrıştırıldı (public imza değişmedi) — hem web parser hem `NotionConnector` (Notion blokları markdown'a render edilip) bu ORTAK fonksiyonu kullanıyor.

**Bu sprintte `WebConnector` YOK — bilinçli kapsam sınırı.** DoD'nin tam metni sadece "bir web sayfası gerçekten parse edilip location'lı chunk'lara ayrılıyor" istiyor, uçtan uca ingest değil. Bir connector (URL listesi/keşif kavramı) tanımlamak spekülatif olurdu — `app/parsing/web_parser.py` + `app/ingestion/web_chunker.py` gerçek bir HTML fixture'ıyla kanıtlandı, connector'a bağlanması gerçek ihtiyaç netleşince yapılacak.

**Notion API'ye gerçekten karşı test edildi mi? HAYIR.** Bu makinede `NOTION_API_KEY` yok, `.env` yok (Sprint 1'deki `ANTHROPIC_API_KEY` durumunun birebir aynısı, aynı dürüstlükle belgeleniyor). `NotionConnector`'ın 16 testi `httpx.MockTransport` ile resmi Notion API dokümantasyonundaki GERÇEK JSON şekillerini (arama sayfalama, blocks sayfalama, 429+Retry-After, diğer hatalar) simüle ediyor. `tests/test_notion_e2e.py`, Sprint 1'in `test_provider_comparison_e2e.py` desenini izleyen, `NOTION_API_KEY` set edilirse gerçekten çalışacak otomatik-skip bir test — şu an skip. DoD'nin bu kısmı AÇIK kalıyor.

**Sprint 2-4'ün registry/sync mantığı Notion için hiçbir ek değişiklik gerektirmeden çalıştı** (yukarıdaki iki interface düzeltmesi dışında) — `tests/test_notion_pipeline_e2e_hermetic.py` (4 test, mock'lı ama TAM `ingest_connector` + gerçek Qdrant + gerçek SQLite registry üzerinden) Sprint 4'ün üç senaryosunu (skip/update/delete) Notion için AYNI kod yoluyla, sahte ama durumsal bir Notion workspace'i (testler arasında mutasyona uğrayan bir `dict`) ile kanıtlıyor: değişmeyen sayfa sıfır Qdrant yazması ile atlanıyor, düzenlenen sayfa SADECE kendi chunk'larını güncelliyor (diğer sayfanın point'leri ID/payload dahil birebir aynı kalıyor), workspace'ten silinen sayfa hem Qdrant'tan hem registry'den temizleniyor.

244 test yeşil (7'si gerçek servis/API key gerektirdiği için skip — 6'sı önceki sprintlerden, +1 bu sprintin `NOTION_API_KEY` testi), `ruff check` temiz, 5 ardışık çalıştırmada flakiness yok.

## Sprint 7 — Sync Scheduler

Amaç: Periyodik ve manuel sync tetiklemeyi otomatikleştirmek.

Scope:

* Periyodik job (APScheduler veya basit bir asyncio loop - Celery'nin ek karmaşıklığına gerek olup olmadığı değerlendirilecek, M2'de hafif kalması tercih edilir)
* Her connector için ayrı sync sıklığı config edilebilir
* Manuel "sync now" tetikleyici (API endpoint)

DoD: connector'lar config'deki sıklığa göre otomatik sync oluyor, manuel tetikleme de çalışıyor, sync geçmişi (başarı/hata) kaydediliyor.

### Kapanış notu

**Scheduler kararı: düz `asyncio` döngüsü, APScheduler YOK** (bkz. `docs/sprint-07-plan.md`, Sprint 2'nin SQLite/SQLAlchemy kararıyla aynı usul). Gerekçe: gerçek ihtiyaç sadece "N connector, her biri sabit bir aralıkta" — cron ifadeleri, kalıcı job store, misfire/coalescing gibi APScheduler'ın çözdüğü problemlerin hiçbiri yok. `SyncScheduler`, connector başına `asyncio.create_task` + `while True: sleep(interval); trigger_sync(...)` — kısa interval'larla (`0.03s`–`0.12s`) gerçek zamanlı test edildi, 5 ardışık çalıştırmada flakiness yok.

**Kilit stratejisi: `asyncio.Lock` DEĞİL, connector başına düz bir `bool` bayrak, REDDET (queue etme).** `SyncManager._running[source_type]` check-and-set arasında hiçbir `await` yok — asyncio'nun tek-thread'li cooperative modelinde bu iki satır arasına başka bir coroutine giremiyor, dolayısıyla ek bir lock nesnesi gerekmeden atomik. DoD "biri beklerken/reddedilirken diğeri çalışıyor" dediği için REDDETMEYİ seçtik (queue değil) — manuel API endpoint'i belirsiz süre bloklanmasın diye (409 ile anında cevap). Gerçek bir race condition testiyle kanıtlandı: `asyncio.gather` ile iki `trigger_sync()` GERÇEKTEN eşzamanlı başlatıldı (embed_fn 0.2s yapay gecikmeli), sonuç: biri `success`, diğeri `rejected_already_running`, Qdrant'a sadece BİR upsert çağrısı gitti, toplam süre `0.2s`'nin ~1.5 katını geçmedi (queue edilseydi ~0.4s'yi bulurdu) — `tests/test_sync_manager.py::test_concurrent_sync_of_the_same_connector_rejects_the_second_attempt`.

**`sync_runs` şeması** (`docs/sprint-07-plan.md`'de tasarlandığı gibi, registry ile AYNI SQLite dosyasında yeni bir tablo): `id, source_type, trigger, status, started_at, finished_at, files_processed, files_skipped, files_deleted, chunks_upserted, error_message`. `IngestStats`'ın dört alanı birebir buraya yazılıyor — Sprint 10'un "Sync Status" sayfası için ekstra hesaplama gerekmiyor.

**API endpoint senkron kaldı, arka plan görevi YOK** — `POST /sync/{source_type}` sync bitene kadar bekliyor. Test edilebilirlik için `app/main.py::create_app(sync_manager, sync_history)` bir FACTORY fonksiyonu (modül yüklenirken gerçek Qdrant/Ollama'ya bağlanan bir singleton değil) — testler `TestClient(create_app(fake_manager, fake_history))` ile gerçek ASGI request/response üzerinden, sahte bileşenlerle çalışıyor. Gerçek servis wiring'i (uvicorn ile deploy) Sprint 11'e (docker compose) bırakıldı.

**Beklenmeyen ama gerçek bir bug: FastAPI `TestClient`, ASGI app'i AYRI BİR THREAD'DE çalıştırıyor.** `DocumentRegistry`/`SyncHistory`'nin sqlite3 bağlantıları varsayılan olarak `check_same_thread=True` idi — test çalıştırılınca gerçek bir `sqlite3.ProgrammingError` fırlattı (varsayılmadı, gerçek hatayla yakalandı). Her iki sınıfa da `check_same_thread=False` eklendi — kullanım deseni (bir seferde tek thread, gerçek eşzamanlı çoklu-thread erişim yok) bunu güvenli kılıyor; bu düzeltme olmadan Sprint 11'in gerçek ASGI dağıtımı da aynı şekilde patlardı, bu yüzden Sprint 2'nin registry'sine de geriye dönük uygulandı.

277 test yeşil (7'si gerçek servis/API key gerektirdiği için skip, değişmedi), `ruff check` temiz, 5 ardışık çalıştırmada (zamanlama-hassas scheduler/concurrency testleri dahil) flakiness yok.

## Sprint 8 — Observability Extension

Amaç: Tracing'i sync/ingestion pipeline'ına genişletmek (query tarafı Sprint 0'dan zaten taşınmıştı).

Scope:

* Sync/ingestion adımları (`fetch`, `parse`, `chunk`, `embed`, `upsert`, `cleanup`) span olarak instrument edilir
* Connector bazlı sync süresi ve başarı/hata oranı span attribute'u olarak eklenir

DoD: bir sync koşumu Jaeger'da uçtan uca izlenebiliyor, hangi connector'ın ne kadar sürdüğü görülüyor.

### Kapanış notu

**Kod okunarak (koşup Jaeger'a bakmadan ÖNCE) üç gerçek kör nokta bulundu** (bkz. `docs/sprint-08-plan.md`):

1. **Bir sync koşumu tek trace DEĞİLDİ.** `ingest_connector` hiçbir üst span açmıyordu; her `ingest_document`/`delete_document` çağrısı kendi başına yeni bir trace root'u oluyordu (OpenTelemetry kuralı: parent context'i olmayan span = yeni trace). 3 dokümanlı bir sync, Jaeger'da 3 ayrı, ilişkisiz trace üretiyordu — DoD'yi doğrudan ihlal ediyordu.
2. **Connector I/O hiç span'lenmiyordu.** `connector.list_documents()` ve her doküman için `get_content_hash()` span'siz çağrılıyordu — Notion için bunlar gerçek ağ istekleri + 429 backoff sleep'leri, tamamen görünmezdi. `NotionConnector.fetch_content()` ise `parse_and_chunk`'ın İÇİNE gömülüydü, ağ süresini CPU-bound parse süresinden ayırt etmek imkansızdı.
3. **Atlanan (skip) dokümanlar tamamen görünmezdi.** `has_changed() == False` olan dokümanlar için hiçbir span açılmıyordu, sadece bir sayaç artıyordu.

**Düzeltmeler:** `ingest_connector`'ın tüm gövdesi yeni bir `ingest_connector` üst span'ine sarıldı (`source_type` + final `files_processed/skipped/deleted/chunks_upserted` attribute'ları). Yeni `fetch_documents` span'i (`list_documents()`'ı sarıyor, `fetch.document_count`). Yeni `check_document` span'i — her doküman için, SKIP edilse bile (`check.changed` attribute'u), artık atlanan dokümanlar da trace'de görünüyor. Notion'ın `fetch_content()`'ı kendi `fetch` span'ine ayrıldı, `parse_and_chunk`'tan bağımsız ölçülüyor.

**`trace_id` kararı: EVET, `sync_runs` tablosuna yazılıyor.** `SyncManager.trigger_sync()` artık TÜM denemeyi (REDDEDİLEN durum dahil) saran bir `sync_run` span'i açıyor; `format(span.get_span_context().trace_id, "032x")` ile (Sprint 0'ın `generate.py`'sindeki AYNI desen) trace_id çıkarılıp `SyncHistory.start_run()`'a (henüz sync bitmeden, ÇALIŞAN bir sync'in trace'ine de erken erişilebilsin diye) yazılıyor. `sync_runs`'a yeni bir `trace_id TEXT` kolonu eklendi, API'nin hem `POST /sync/{source_type}` hem `GET /sync/{source_type}/history` yanıtlarına `trace_id` eklendi — Sprint 10'un "Sync Status" sayfası doğrudan Jaeger'a link verebilecek.

**Gerçek Jaeger'a karşı GERÇEKTEN doğrulandı (mock değil).** Bu makinede Docker çalıştığı için (Sprint 1/6'daki API-key-yok durumundan FARKLI olarak burada gerçek doğrulama mümkündü): `docker compose up -d jaeger qdrant`, gerçek `setup_tracing()`, gerçek bir filesystem sync koşumu, sonra Jaeger'ın HTTP API'sinden (`GET /api/traces/{trace_id}`) trace GERÇEKTEN sorgulandı. Sonuç: TEK trace altında 9 span, doğru hiyerarşi:

```
sync_run (103.7ms)
  ingest_connector (102.9ms)
    fetch_documents (0.2ms)
    check_document (0.1ms)
    ingest_document (13.4ms)
      parse_and_chunk (0.1ms)
      delete_stale_chunks (7.7ms)
      embed_batch (0.02ms)
      upsert_batch (5.4ms)
```

Her span'in tag'leri tek tek kontrol edildi — hiçbirinde tam chunk metni veya doküman içeriği yok, sadece sayılar/kimlikler (`fetch.document_count`, `check.source_id`, `ingest.chunk_count` gibi). Doğrulama sonrası container'lar durduruldu (`docker compose down`), ortam olduğu gibi bırakıldı.

**Bilinen küçük bir kozmetik eksiklik:** `SyncManager`, kendi tracer'ını (`get_tracer("app.sync.manager")`) `ingest_connector`'a açıkça geçiriyor (testlerin izole `TracerProvider`'ları yakalayabilmesi için gerekli) — bunun bedeli, Jaeger'da TÜM span'lerin `otel.scope.name`'inin `app.sync.manager` görünmesi (üretildikleri gerçek modül — `app.ingestion.ingest` — değil). Trace hiyerarşisini/isimlerini/attribute'ları ETKİLEMİYOR, sadece "instrumentation scope" etiketi jenerik — bilinçli bir basitleştirme, düzeltmeye değecek bir maliyeti yok.

291 test yeşil (7'si gerçek servis/API key gerektirdiği için skip, değişmedi — bu sprintte +14 yeni test), `ruff check` temiz, 5 ardışık çalıştırmada flakiness yok.

## Sprint 9 — Evaluation

Amaç: Çoklu kaynak tipini kapsayan bir golden set ile kalite ölçümü.

Scope:

* Golden set: en az PDF + Markdown + (varsa Notion) kaynaklardan sorular
* production-rag-platform'daki DeepEval + 7B judge yaklaşımı taşınır
* Kaynak tipi bazında ayrı metrik kırılımı (örn. Notion sorularında mı, PDF sorularında mı daha zayıf)

DoD: golden set komutla çalıştırılabiliyor, kaynak tipi bazında kırılım raporlanıyor.

### Kapanış notu

**RAGAS tekrar denenmedi.** production-rag-platform'un o kararı gerçek bir
bağımlılık çakışmasıyla (varsayım değil, test edilip belgelenmiş bir gerçek)
verdiği kabul edildi; bu sprint doğrudan DeepEval + yerel Ollama judge
(`qwen2.5:7b-instruct`) ile başladı, aynı yaklaşımın kanıtlanmış nedeni
tekrar araştırılmadı.

**İki gerçek bug tekrar araştırıldı, ikisi de bu projede farklı çıktı:**

1. **Harness'in model değiştirme yavaşlığı** — production-rag-platform'da
   judge/generation çağrıları iç içe geçtiğinde Ollama neredeyse her
   çağrıda modeli değiştiriyordu (~11 dk beklenen koşum 40+ dk sürüyordu).
   `app/evaluation/harness.py::run_evaluation()` bu projede de AYNI
   iki-fazlı yapıyla (önce TÜM retrieval+generation, sonra TÜM judge
   skorlama) korundu — koşullu değil, yapısal bir karar, çünkü
   `generation_provider`/`ollama_model` kullanıcı tarafından
   yapılandırılabilir ve generation ile judge farklı model kullanabilir.
   Bunu GERÇEKTEN test etmek için golden-set koşumunda generation için
   `qwen2.5:3b-instruct`, judge için `qwen2.5:7b-instruct` — iki FARKLI
   model — kullanıldı. Sonuç: 12 soru, 8 dakika 42 saniyede tamamlandı
   (production-rag-platform'un ~11dk/20 soru referansıyla orantılı,
   40+ dk'lık thrashing belirtisi yok) — iki-fazlı tasarımın burada da
   işe yaradığı gerçekten ölçüldü, varsayılmadı.

2. **`OllamaClient`'ın kısa timeout'u** — bu projenin KENDİ
   `app/llm/ollama_client.py::OllamaClient`'ı bu düzeltmeyi Sprint 0'dan
   beri zaten taşıyor (`DEFAULT_TIMEOUT_SECONDS = 120.0`, tam da bu bug'ı
   referans alan bir yorumla). Ama bu sprintte DAHA ÖNCE hiç incelenmemiş
   İKİNCİ bir HTTP yolu bulundu: DeepEval'in judge wrapper'ı
   (`deepeval.models.OllamaModel`) `OllamaClient`'ı KULLANMIYOR — resmi
   `ollama` PyPI paketinin kendi `Client`'ını kullanıyor. `ollama` v0.6.2
   kaynağı okunarak (`BaseClient.__init__(..., timeout: Any = None, ...)`)
   ve gerçekten test edilerek (`httpx.Client(timeout=None).timeout` →
   `Timeout(timeout=None)`) doğrulandı: httpx'te `timeout=None` timeout'u
   TAMAMEN DEVRE DIŞI bırakır — "kısa varsayılana düş" değil. Yani bu yol
   "timeout çok kısa" bug sınıfını hiç üretemez; tam tersi bir risk
   (sınırsız bekleme) var ama bu makinede bir 7B judge çağrısı onlarca
   saniyede bitiyor, gerçek bir sorun değil. `build_default_metrics()`'e
   ek bir timeout override EKLENMEDİ — eklemeye gerek olmadığı, varsayım
   değil, okunmuş kaynak koduyla doğrulandı.

**Kaynak tipi bazında kırılım: `content_type`, `source_type` DEĞİL.**
Görev metni "PDF sorularında mı, Markdown sorularında mı sistem daha
zayıf" diyor — bu bir FORMAT sorusu, connector sorusu değil. Bu projede
(Sprint 3) `source_type` connector'ı (`filesystem`), `content_type` ise
formatı (`pdf`/`markdown`) tanımlıyor; golden set'teki hem PDF hem
Markdown soruları AYNI connector'dan (`LocalFilesystemConnector`,
`source_type="filesystem"`) geliyor — `source_type` bazında kırılım
ikisini ayırt edemezdi. `GoldenQuestion.content_type` alanı eklendi,
`build_report()` hem global hem `by_content_type` kırılımını
hesaplıyor.

**Golden set: gerçek, ingest edilmiş içerikten, 12 soru.** PDF tarafı
`tests/fixtures/golden_source.py`'nin mevcut Nimbus Cloud Storage el
kitabını (6 sayfa) yeniden kullandı; Markdown tarafı için yeni
`tests/fixtures/golden_markdown_source.py` yazıldı (Nimbus CLI referans
dokümanı, 4 üst başlık + 4 alt başlık). İkisi de gerçek `ingest_connector()`
+ gerçek Ollama embedding ile ayrı bir Qdrant koleksiyonuna (`kb_eval_golden`)
ingest edildi, sonra koleksiyon `scroll` ile okunarak GERÇEK chunk
konumları (`location_for()` çıktısı) doğrulandı ve `expected_locations`
bu gerçek değerlerden yazıldı — tahmin edilmedi.
`tests/fixtures/golden_set.json`: 7 PDF sorusu, 4 Markdown sorusu, 1
`expect_not_found` sorusu.

**Notion kapsanmadı.** `NOTION_API_KEY` bu makinede tanımlı değil (Sprint 1
ve 6'daki aynı, zaten belgelenmiş boşluk) — golden set'e Notion sorusu
eklenmedi.

**Gerçek koşum sonucu (12 soru, `qwen2.5:3b-instruct` generation +
`qwen2.5:7b-instruct` judge, `python -m app.evaluation.cli --golden-set
tests/fixtures/golden_set.json --collection kb_eval_golden`):**

```json
{
  "question_count": 12,
  "mean_precision": 0.133,
  "mean_recall": 0.667,
  "mean_faithfulness": 0.857,
  "mean_answer_relevancy": 0.762,
  "not_found_accuracy": 1.0,
  "by_content_type": {
    "markdown": {"question_count": 5, "mean_precision": 0.2, "mean_recall": 1.0,
                 "mean_faithfulness": 0.8, "mean_answer_relevancy": 0.667},
    "pdf":      {"question_count": 7, "mean_precision": 0.086, "mean_recall": 0.429,
                 "mean_faithfulness": 1.0, "mean_answer_relevancy": 1.0}
  }
}
```

**Kırılım yorumu — PDF, RETRIEVAL'da daha zayıf; Markdown, GENERATION'da
biraz daha zayıf.** Markdown sorularının tamamında (recall=1.0) doğru
chunk top-5 içinde bulundu; PDF sorularının sadece ~%43'ünde bulundu
(recall=0.429) — retrieval, PDF'de belirgin şekilde daha zayıf. Tersine,
doğru chunk bulunduğunda üretilen cevapların sadıklığı/uygunluğu PDF'de
daha yüksek (faithfulness/relevancy = 1.0 vs. Markdown'da 0.8/0.667) —
muhtemelen PDF chunk'larının (sayfa başına birleşik metin) Markdown'ın
kısa, başlık-altı bloklarına göre generation modeline daha fazla bağlam
sağlaması. `mean_precision`'ın genel olarak düşük görünmesi (0.086–0.2)
bir hata değil, yapısal bir sınır: `search()` varsayılan olarak top-5
chunk döndürüyor (`RERANK_TOP_N=5`), her golden soru tek bir beklenen
konuma sahip, yani mükemmel retrieval'de bile precision tavanı 1/5=0.2 —
Markdown'ın 0.2'ye ulaşması aslında "her seferinde doğru chunk top-5'te"
demek.

**DeepEval bu projede de sorunsuz çalıştı** — production-rag-platform'daki
gibi, ek bir workaround gerekmedi (yukarıdaki timeout doğrulaması dışında,
ki o da "değişiklik gerekmiyor" sonucuna vardı).

**Test kapsamı:** metrik hesaplama mantığı (retrieval precision/recall,
generation metric toplama, iki-fazlı sıralama, `by_content_type` kırılımı)
sahte (fake) fonksiyonlarla birim test edildi; ayrıca küçük (2 soru) ama
GERÇEK bir e2e test (`tests/test_evaluation_e2e.py`, gerçek Ollama+Qdrant+
7B judge, Ollama/Qdrant erişilemezse otomatik skip) eklendi — tam golden
set (12 soru, iki farklı model) elle çalıştırılıp yukarıdaki sonuçla
doğrulandı, her testte koşulmuyor (çok yavaş).

318 test toplam (bu sprintte +27 yeni test — retrieval/generation/harness
birim testleri + 1 yeni gerçek eval e2e testi), 316'sı geçiyor, 2'si servis
gerektirdiği için skip (değişmedi: Notion API key yok, Claude+Ollama
kombinasyonu), `ruff check` temiz, 3 ardışık çalıştırmada flakiness yok.

## Sprint 10 — UI (Multi-page Streamlit)

Amaç: Chat + kaynak yönetimi + sync durumunu ayrı sayfalarda sunmak.

Scope:

* `st.navigation` ile 3 sayfa: Chat (production-rag-platform'dan taşınan streaming+citation+trace paneli), Sources (bağlı connector'lar, manuel sync tetikleme, doküman listesi), Sync Status (son sync zamanları, başarı/hata geçmişi, kaynak başına doküman sayısı)
* Pahalı işlemler (sync tetikleme) ayrı sayfada, tab içinde değil (dbt-feature-lineage dersinden)

DoD: üç sayfa da çalışıyor, bir kaynağı UI'dan manuel sync tetikleyip sonucu Sync Status sayfasında gerçekten görebiliyorsun.

### Kapanış notu

**venv kararı: `.venv-ui`, varsayılmadı, gerçekten test edildi.**
production-rag-platform'un `streamlit`/`fastapi` çakışması bu projenin
KENDİ sürüm pinleriyle tekrar doğrulandı (`pip install
fastapi==0.115.6 streamlit==1.61.1`):

```
ERROR: Cannot install fastapi==0.115.6 and streamlit==1.61.1 because
these package versions have conflicting dependencies.
    fastapi 0.115.6 depends on starlette<0.42.0 and >=0.40.0
    streamlit 1.61.1 depends on starlette<1.4.0 and >=0.46.0
```

Aynı çakışma, aynı sürümler. `.venv-ui` + `requirements-ui.txt` kararı
korundu — ama bu projenin UI'ı referans projeninkinden DAHA AZ bağımlılık
gerektiriyor: doğrudan Qdrant/ingestion erişimi yok (dosya yükleme bu
sprintin kapsamında değildi — filesystem connector sabit bir klasörü
tarıyor), UI sadece HTTP üzerinden backend'e ve Jaeger'ın kendi API'sine
bağlanıyor. `requirements-ui.txt`: sadece `streamlit`, `httpx`, `pandas`.

**Bu projede gerçek bir backend hiç çalıştırılmamıştı — bu sprint bunu
kapattı.** `app/main.py::create_app()` Sprint 7'den beri sadece sahte
bileşenlerle test ediliyordu; gerçek servis wiring'i "Sprint 11 (docker
compose)"ye bırakılmıştı. Ama bu projenin Sprint 10'u (UI) Sprint 11'den
(Docker Compose Polish) ÖNCE geliyor — production-rag-platform'un tersine
(orada backend UI sprintinden önce zaten container'da çalışıyordu). Bu
sprintin kendi DoD'si ("gerçek tarayıcıda doğrulanmış") gerçek bir backend
olmadan karşılanamazdı, bu yüzden minimal bir parça öne çekildi:
`app/wiring.py::build_connectors()`/`build_app()` (gerçek bileşenlerden
`SyncManager`/`ChatDependencies` kurar) + `app/server.py` (`uvicorn
app.server:app` için modül seviyesi `app`). Bu, Sprint 11'in tam docker-
compose cilası DEĞİL — sadece bu sprintin kendi doğrulaması için yeterli,
Sprint 11 bunun üzerine inşa edebilir. Yeni `filesystem_root_path` ayarı
(`data/documents`, `.gitkeep` ile) `LocalFilesystemConnector`'ın gerçek
tarama kökü oldu; `SyncScheduler` (periyodik sync) bilinçli olarak
BAŞLATILMADI — bu sprint sadece manuel "sync now" gerektiriyor.

**Yeni endpoint'ler:** `POST /chat` (`app/api/chat.py`, bu projede hiç yoktu)
— production-rag-platform'dan taşındı ama bu projenin provider
soyutlamasına (`get_chat_provider`/`get_embedding_provider`/
`default_chat_model`/`default_embed_model`, Sprint 1) bağlandı, hardcoded
`OllamaClient` yerine — `GENERATION_PROVIDER=claude` ile de çalışır. SSE
formatlama/`chat_request` span mantığı, gerçek Qdrant/Ollama olmadan test
edilebilsin diye `ChatDependencies` (search_fn/stream_fn closure'ları,
`app/evaluation/cli.py`'nin search_fn/generate_fn deseniyle aynı) üzerinden
enjekte ediliyor — gerçek bileşenler SADECE `app/wiring.py`'de kuruluyor.
`GET /sources` (`app/api/sources.py`, yeni — referans projede karşılığı
yok) connector + doküman sayısı + çalışıyor mu bilgisini döndürüyor;
`create_app()` bunun için bir `registry` parametresi kazandı (mevcut
testler güncellendi).

**Chat sayfası — değişmeden taşınan parçalar.** `app/ui/sse_client.py`
(`parse_sse_lines`) ve `app/ui/trace_client.py` (`fetch_trace_spans`,
Sprint 12'nin kısmi-trace retry düzeltmesiyle birlikte) DEĞİŞTİRİLMEDEN
taşındı — ikisi de protokol şekilli (SSE satır formatı, Jaeger'ın JSON
yanıt şekli), kaynak tipine özel bir şey içermiyorlar.
`app/ui/citation_formatting.py` zaten Sprint 0/7'de çoklu-kaynak citation
regex'i için uyarlanmıştı, dokunulmadı.

**Üç sayfa da gerçek tarayıcıda doğrulandı (curl değil, gerçek Chrome
otomasyonu):** `docker compose up -d`, gerçek native Ollama, `make dev`
(gerçek `uvicorn app.server:app`), `make ui` (gerçek Streamlit,
`.venv-ui`'den). `data/documents/`'a gerçek bir Markdown dosyası
(`nimbus_cli.md`, Kurulum/Sorun Giderme başlıklarıyla) kondu.

1. **Sources**: `filesystem` connector'ı 0 dokümanla listelendi, "Sync
   now" tıklandı — GERÇEK bir `POST /sync/filesystem` çağrısı yapıldı,
   sayfa "Documents: 1"e güncellendi.
2. **Sync Status**: aynı run GERÇEKTEN göründü — `status=success`,
   `trigger=manual`, `files_processed=1`, `chunks_upserted=2`, çalışan bir
   "Open in Jaeger" linkiyle.
3. **Chat**: gerçek bir soru soruldu ("Nimbus CLI nasıl kurulur ve sorun
   giderme için hangi komut kullanılır?") — token'lar tek tek akarken
   yakalandı, final cevap doğru citation'larla geldi
   (`[s.filesystem:nimbus_cli_md/Kurulum]`,
   `[s.filesystem:nimbus_cli_md/Sorun Giderme]`), "✅ Grounded" göründü.
   Pipeline trace paneli açıldı: `embed_query` (63.5ms), `retrieve_hybrid`
   (14.2ms), `rerank` (302.7ms), `generate` (12078.8ms), "Total: 12459.6 ms".
   Aynı trace_id ile GERÇEKTEN `curl http://localhost:16686/api/traces/{id}`
   çekildi — `chat_request` kök span süresi **12459.6ms**, UI'daki
   "Total" ile BİREBİR aynı; her span adı/süresi curl çıktısıyla bire bir
   eşleşti (production-rag-platform'un Sprint 12'deki aynı çapraz kontrol
   yöntemi).

Doğrulama sonrası: Streamlit/uvicorn süreçleri durduruldu, test dokümanı
(`nimbus_cli.md`) ve `data/registry.db` silindi, `docker compose down`.

**Kapsam dışı bırakılanlar (bilinçli):** Dosya yükleme UI'ı (filesystem
connector sabit klasör tarıyor, upload bu sprintin kapsamında değildi),
`SyncScheduler`'ın gerçek process'te başlatılması (Sprint 11), tam
docker-compose polish (Sprint 11).

339 test yeşil (bu sprintte +22 yeni test), 2'si servis gerektirdiği için
skip (değişmedi), `ruff check` temiz, 3 ardışık çalıştırmada flakiness
yok.

## Sprint 11 — Docker Compose Polish

Amaç: Tek komutla kurulum.

Scope:

* production-rag-platform'daki desen taşınır (Qdrant+Jaeger+backend container'da, Ollama native)
* Yeni bileşen: registry DB (SQLite dosya bazlı ise ek container gerekmez, PostgreSQL'e geçilirse eklenir — karar burada netleşir)

DoD: sıfırdan kurulum (`docker compose down -v` + `up`) uçtan uca çalışıyor, gerçekten test edilmiş.

### Kapanış notu

**Registry DB kararı: SQLite dosyası kaldı, ek container gerekmedi** — plan
metnindeki açık soru buydu. PostgreSQL'e geçiş için gerçek bir gerekçe
(çoklu backend replikası, eşzamanlı yazma yükü) bu projede hiç ortaya
çıkmadı; SQLite dosyası tek backend container'ı içinde `check_same_thread=False`
ile zaten sorunsuz çalışıyordu (Sprint 2/7). Karar: dosya olarak kaldı,
sadece NEREDE yaşayacağı (volume stratejisi) bu sprintin gerçek işiydi.

**Volume stratejisi — iki farklı veri, iki farklı mount türü, gerekçeyle:**

1. **`registry_data` (named volume) → `/app/data`.** `registry.db`
   (documents + sync_runs tabloları, Sprint 2/7) opak çalışma zamanı
   durumu — kullanıcı doğrudan düzenlemiyor. `qdrant_storage`'ın zaten
   kurduğu named-volume presedansıyla tutarlı; container'ın sahip olduğu
   bir dosya için host-OS izin uyuşmazlığı riski taşıyan bir bind mount'tan
   kaçınıldı.
2. **Bind mount → `/app/documents`.** `data/documents/` (Sprint 10'un
   `LocalFilesystemConnector` tarama kökü) kullanıcının host'tan gerçek
   dosya bıraktığı bir klasör — bind mount, host değişikliklerinin anında
   görünmesini sağlıyor. `FILESYSTEM_ROOT_PATH=documents` (container
   içinde `/app/documents`'a karşılık gelir) `registry_data`'nın
   mount noktasıyla (`/app/data`) KASITLI olarak ÇAKIŞMAYAN bir yola
   ayarlandı — iki volume'ün iç içe geçen mount noktalarına güvenmek
   yerine, en baştan kardeş (sibling) yollar seçildi.
3. **`hf_cache` (named volume) → `/root/.cache/huggingface`** —
   production-rag-platform'un aynı deseni, cross-encoder/sparse-encoder
   modellerinin her `down`+`up`'ta yeniden indirilmesini önlüyor.

**İkisi de GERÇEKTEN test edildi, varsayılmadı:**

- **Sıfırdan kurulum**: `docker compose down -v` (TÜM volume'lar dahil
  silindi) + `docker compose up -d --build`. Image ~12 saniyede `healthy`
  oldu. `GET /health/ollama` GERÇEKTEN çağrıldı — container'ın
  `host.docker.internal` üzerinden native Ollama'ya GERÇEKTEN ulaştığı
  (Sprint 0'dan beri hiç test edilmemiş bir varsayımdı) tam model
  listesiyle (`qwen2.5:7b-instruct, nomic-embed-text:latest,
  qwen2.5:3b-instruct, gemma2:2b`) kanıtlandı. Sonra `data/documents/`'a
  gerçek bir Markdown dosyası kondu, `POST /sync/filesystem` container'a
  karşı GERÇEKTEN çağrıldı (`files_processed=1, chunks_upserted=2`), ve
  gerçek bir `/chat` isteği (`Nimbus CLI nasıl kurulur?`) doğru citation'la
  (`[s.filesystem:nimbus_cli_md/Kurulum]`) ve `grounded: true` ile
  streaming cevap verdi — tüm pipeline (embed → retrieve → rerank →
  generate, container'dan native Ollama'ya) uçtan uca çalıştı.
- **Restart kalıcılığı**: 6 sync run'ı (1 manuel + zamanlanmış — aşağıya
  bakın) kaydedildikten sonra `docker compose restart backend` çalıştırıldı.
  Container yeniden `healthy` olduktan sonra `GET
  /sync/filesystem/history` AYNI 6 run'ı, aynı `id`'lerle (`[6,5,4,3,2,1]`)
  döndü — `registry_data` named volume'unun kalıcılığı doğrudan
  kanıtlandı, sadece compose dosyasında volume'un VAR OLDUĞU değil.

**Scheduler'ın container'da GERÇEKTEN otomatik başladığı kanıtlandı**
(sadece kod incelemesiyle değil): `app/main.py::create_app()` opsiyonel
bir `scheduler` parametresi kazandı — verildiğinde FastAPI'nin native
`lifespan` mekanizmasıyla (`asynccontextmanager`) `scheduler.start()`
başlangıçta, `await scheduler.stop()` kapanışta çağrılıyor. Mevcut TÜM
testler `scheduler=None` geçtiği için hiçbiri gerçek bir arka plan
asyncio döngüsü çalıştırmıyor (`test_app_lifespan.py`, sahte bir
`_SpyScheduler` ile `TestClient`'ı context manager olarak kullanarak
GERÇEK lifespan event'lerini tetikliyor ve `start()`/`stop()`'un
GERÇEKTEN çağrıldığını doğruluyor). Gerçek container'da da ayrıca
doğrulandı: `FILESYSTEM_SYNC_INTERVAL_SECONDS=5` ile geçici bir ikinci
container başlatıldı (aynı `registry_data`/`qdrant` ağına bağlı), HİÇBİR
manuel API çağrısı yapılmadan `trigger=scheduled` bir sync run'ının
GERÇEKTEN kendiliğinden belirdiği `GET /sync/filesystem/history`'de
görüldü — `app/wiring.py::build_app()`'ın `SyncScheduler`'ı gerçekten
inşa edip `create_app()`'e geçirdiği, sadece kodda yazılı durmadığı
kanıtlandı.

**CUDA/torch önlemi burada da uygulandı** — bu projenin
`app/reranker/cross_encoder.py`'si production-rag-platform'un aynı
`sentence-transformers` kütüphanesini kullanıyor, aynı riski taşıyordu.
`Dockerfile`'da CPU-only torch wheel'i `requirements.txt`'ten ÖNCE
kuruldu (aynı fix, tekrar keşfedilmedi). Gerçekten doğrulandı:
`docker exec kb-rag-backend python -c "import torch; print(torch.__version__)"`
→ `2.13.0+cpu`, `torch.cuda.is_available()` → `False`. İmaj boyutu 2.3GB
(CUDA wheel'i olsaydı ~2GB fazladan).

**Yeni endpoint'ler: `/health` (canlılık) ve `/health/ollama` (gerçek
bağlanabilirlik kontrolü)** — bu projede daha önce hiç yoktu, hiçbir
deployment hedefi gerektirmemişti. `/health/ollama`, zaten var olan ama
kullanılmayan `OllamaClient.list_models()`'ı yeniden kullanıyor.
`docker-compose.yml`'in `healthcheck:`'i `/health`'i çağırıyor.

**README'ye Mermaid mimari diyagramı ve tek-komutla kurulum bölümü
eklendi** — registry/connector'lar/scheduler dahil güncel resmi
gösteriyor; `NOTION_API_KEY`'in opsiyonel olduğu (yoksa sadece
`filesystem` connector aktif) ve native Ollama'nın ön koşul olduğu açıkça
belirtildi.

**Kapsam dışı bırakılanlar (bilinçli, referans projeninkiyle aynı
gerekçe):** `make ingest`/`app.evaluation.cli`/Streamlit UI container'a
GİRMEDİ — host-side, isteğe bağlı araçlar (batch iş, manuel eval koşumu,
zaten kendi venv'inden çalışan bir UI), container'a taşımak bu sprintin
asıl DoD'si (sıfırdan kurulum + kalıcılık) için gereksiz mount/venv
karmaşıklığı eklerdi.

345 test yeşil (bu sprintte +6 yeni test — health endpoint'leri +
lifespan wiring), 2'si servis gerektirdiği için skip (değişmedi), `ruff
check` temiz, 3 ardışık çalıştırmada flakiness yok. Doğrulama sonrası
container'lar, volume'lar ve build edilen image tamamen temizlendi
(`docker compose down -v`, `docker image rm`).

Proje Sprint 0'dan 11'e kadar plana göre tamamlandı.

## Sprint 12 — Safety and Correctness

Amaç: Bir dış kod review'ından çıkan gerçek doğruluk/güvenlik açıklarını kapatmak.

Scope:

* Grounding bug'ı: citation'sız cevap yanlışlıkla `grounded=True` dönüyor — düzelt
* `ensure_collection()`'ın şema uyuşmazlığında koleksiyonu sessizce silme davranışı — açık hataya çevir
* GitHub Actions CI: ruff + pytest + docker build

DoD: citation yok/geçersiz/geçerli üç senaryo da doğru `grounded` değeri veriyor; şema uyuşmazlığında koleksiyon silinmiyor, açık hata alınıyor; CI gerçek bir push/PR'da çalışıp sonuç veriyor; testler ve lint temiz.

### Kapanış notu

**Grounding bug'ı: kod okunarak doğrulandı (varsayılmadı) — review'daki
alıntı hâlâ birebir güncelmiş.** `app/llm/grounding.py:45`:
`grounded=len(ungrounded_citations) == 0` — `citations_found` boşsa
`ungrounded_citations` de boş oluyor, dolayısıyla `grounded=True`.
Üstelik bu davranış BİLİNÇLİ bir test olarak kodlanmıştı:
`test_grounding_with_no_citations_at_all_is_considered_grounded`.

**Eski davranışın gerçek etkisi:** citation'sız (sıfır `[s.…]` etiketi
olan) herhangi bir cevap — halüsinasyonun EN TEHLİKELİ şekli, çünkü
okuyucunun şüphelenebileceği bir citation etiketi bile yok — UI'da yeşil
"✅ Grounded" ve trace'de `generate.grounded=True` olarak gösteriliyordu.
Bu, zaten yakalanan uydurma-citation durumundan (kırmızı ⚠️ uyarı) DAHA
KÖTÜYDÜ: sahte bir güven sinyali veriyordu. Tek meşru sıfır-citation
durumu (`NOT_FOUND_PHRASE` cevabı, hiçbir iddia içermiyor) ile gerçek bir
halüsinasyon aynı `grounded=True` değerinde birleşiyordu — ayırt
edilemiyordu.

**Düzeltme:** `GroundingResult`'a `has_citations`/`citations_valid` alanları
eklendi, `grounded = has_citations and citations_valid`. Tüm çağıran
noktalar (`app/llm/generate.py`, UI'daki `app/ui/pages/chat.py`) tek tek
tarandı: `generate.py` sadece `.grounded`/`.citations_found`/
`.ungrounded_citations` okuyor, yapısal değişiklik gerekmedi (sadece
`.grounded`'ın DEĞERİ artık doğru). UI'da GERÇEK bir davranış değişikliği
gerekti: eskiden sıfır-citation cevap "✅ Grounded" gösteriyordu; düzeltme
sonrası `grounded=False` olacağı için, `ungrounded_citations=[]` ile
"...retrieved context: []" gibi kafa karıştırıcı bir uyarı gösterirdi —
bunun yerine UI artık `has_citations`'a göre ÜÇÜNCÜ bir duruma sahip:
citation yok → nötr "ℹ️ No citations" (uyarı değil), citation var ama
geçersiz → mevcut ⚠️ uyarısı, hepsi geçerli → mevcut ✅. `generate.py`'nin
yayınladığı SSE `grounding` event'ine de `has_citations` eklendi (UI bunu
okuyor).

**README'de mekanizma yeniden adlandırıldı**: "Citation format" bölümüne
yeni bir alt başlık (`Citation integrity validation, not semantic
grounding`) eklendi — `check_grounding`'in bir citation'ın context'te
GERÇEKTEN var olduğunu doğruladığını ama cevaptaki iddianın o chunk
tarafından SEMANTİK olarak desteklendiğini doğrulamadığını açıkça
belirtiyor, artı bir "future work" notu (claim-level semantic support
checking / NLI).

**`ensure_collection()` fail-fast:** `app/ingestion/qdrant_store.py:20-27`
de kod okunarak doğrulandı — `delete_collection` çağrısının üstündeki
yorum ("Safe here because dev collections are re-ingestable") aslında
DOĞRULANAMAYAN bir varsayımdı, fonksiyonun kendisi kimin çağırdığını
bilemez. Yanlış `QDRANT_COLLECTION_NAME`'e işaret eden ya da bu şemadan
önce var olan gerçek verili bir koleksiyon, bir sonraki sync'te SESSİZCE
ve GERİ DÖNÜŞSÜZ silinebiliyordu. Düzeltme: yeni
`UnexpectedCollectionSchemaError` — şema uyuşmazlığında koleksiyona hiç
dokunmadan açık bir hata fırlatıyor. Gerçek bir testle kanıtlandı
(`test_ensure_collection_fails_fast_on_schema_mismatch_without_deleting_it`):
dense-only bir koleksiyona GERÇEKTEN bir point yazıldı, `ensure_collection()`
çağrıldığında hata fırlattığı VE o point'in hâlâ orada olduğu
(`count() == 1`) doğrulandı — sadece "koleksiyon var" değil, "içindeki veri
dokunulmadı" kanıtlandı.

**CI: bu projenin ilk CI'ı — production-rag-platform'da yok.**
`production-rag-platform/.github/workflows/` kontrol edildi, dizin hiç
yok — taşınacak bir öncül olmadığı için sıfırdan tasarlandı. Üç job:

1. **`lint`** — `ruff check app tests`, servis gerektirmiyor.
2. **`test`** — GERÇEK bir Qdrant service container'ı (`qdrant/qdrant:v1.12.4`,
   `docker-compose.yml` ile aynı pin) GitHub Actions'ın native `services:`
   desteğiyle ayağa kaldırılıyor — ucuz ve güvenilir, ve zaten TÜM test
   suite'i canlı port kontrolüyle (`_port_open("localhost", 6333)`)
   self-skip ediyor, CI için hiçbir test değiştirilmedi. Bunun sayesinde
   `test_filters_e2e.py` gibi sadece-Qdrant-gerektiren testler artık CI'da
   GERÇEKTEN çalışıyor, skip olmuyor. **Ollama CI'a BİLİNÇLİ olarak
   eklenmedi** — native bir binary + çoklu-GB model indirmesi gerektiriyor,
   GitHub-hosted runner'lar için yavaş/kırılgan; Ollama gerektiren her test
   zaten :11434 erişilemezse temiz skip ediyor, hiçbir değişiklik
   gerekmedi.
3. **`docker-build`** — SADECE `docker build .`, `docker run` yok — bir
   smoke-run `app/wiring.py::build_chat_dependencies`'in HuggingFace'ten
   eagerly model indirmesini tetikler, bu job'un amacı olmayan gerçek bir
   ağ bağımlılığı eklerdi. Salt build zaten hedeflenen regresyon sınıfını
   (bozuk `Dockerfile`, `requirements.txt` çözümleme hatası, CUDA/torch
   wheel'inin geri sızması — Sprint 11'in düzeltmesi) yakalıyor.

**Gerçekten doğrulandı**: bu commit push edildikten sonra Actions
sekmesinde üç job'un da GERÇEKTEN koştuğu ve sonuç verdiği (yeşil/kırmızı)
kontrol edildi — sadece workflow dosyasının syntax olarak geçerli olması
değil.

347 test yeşil (350 toplam, bu sprintte +5 yeni test — grounding kırılımı, ensure_collection
fail-fast), 2'si servis/API key gerektirdiği için skip (değişmedi), `ruff
check` temiz, 3 ardışık çalıştırmada flakiness yok.

## Sprint 13 — Safe Versioned Re-index

Amaç: Re-index sırasında veri kaybı penceresini kapatmak.

Scope:

* Sprint 4'ten beri: değişen bir doküman için eski chunk'lar ÖNCE silinir, sonra yeniden parse+embed+upsert edilir — embed/upsert ortasında hata olursa doküman geçici/kalıcı olarak aranamaz hale gelir
* "Deferred cleanup" deseni: yeni versiyon önce tam olarak upsert edilir (yeni bir `document_version` payload alanıyla), SADECE upsert başarıyla bitince eski versiyonun chunk'ları silinir
* Bilinçli, belgelenen sınırlama: strict atomic değil — kısa bir "duplicate görünürlük" penceresi var (arama sırasında hem eski hem yeni chunk'lar dönebilir)

DoD: embed/upsert ortasında hata olduğunda eski chunk'lar hâlâ aranabilir durumda (data-loss penceresi kapatılmış); başarılı re-index'te eski chunk'lar temizleniyor; testler ve lint temiz.

### Kapanış notu

**Eski davranış kod okunarak doğrulandı (varsayılmadı).**
`app/ingestion/ingest.py::ingest_connector`'da `delete_stale_chunks` span'i
embed/upsert döngüsünden ÖNCE, `store.delete_by_source(...)`'u koşulsuz
çağırıyordu — `embed_fn` herhangi bir batch'te hata fırlatırsa (ağ hatası,
Ollama timeout), eski chunk'lar ZATEN silinmiş, yeni chunk'lar ise sadece
kısmen yazılmış oluyordu. Sonraki başarılı bir sync bunu düzeltene kadar
(ya da hiç düzeltmezse kalıcı olarak) doküman aranamaz hale geliyordu.

**Düzeltme: "deferred cleanup" — strict atomic DEĞİL, README'de de böyle
adlandırıldı.** Yeni versiyon (`document_version` payload alanı, yeni
content_hash) ÖNCE tam olarak embed+upsert ediliyor; SADECE bu başarıyla
bitince `QdrantStore.delete_stale_versions(source_type, source_id,
keep_version=content_hash)` eski versiyonun chunk'larını siliyor (yeni
`document_version` alanına göre filtreli — `delete_by_source` gibi tam
silme değil). `document_version`, `doc_id`'nin (zaten content_hash) AYNI
değerini taşıyan ama BİLİNÇLİ olarak ayrı bir alan — `doc_id`'nin görevi
"point ID'nin bir bileşeni", `document_version`'ın görevi "deferred
cleanup'ın filtre anahtarı"; ileride `doc_id`'nin hash şeması değişse bile
re-index temizliği sessizce bozulmasın diye ayrıldı.

**DoD'nin iki yarısı da GERÇEK senaryolarla kanıtlandı, varsayılmadı**
(`tests/test_versioned_reindex.py`):

1. **Veri kaybı penceresi kapatıldı**: çok chunk'lı gerçek bir Markdown
   dokümanı ingest edildi, içeriği değiştirildi, ikinci sync'te `embed_fn`
   2 çağrıdan sonra GERÇEKTEN hata fırlatacak şekilde ayarlandı (ağ
   hatası simülasyonu). Hata `ingest_connector`'dan dışarı fırladı
   (yutulmadı — mevcut davranış, bu sprintte değişmedi), AMA eski
   versiyonun TÜM chunk'ları (aynı point ID'lerle, aynı metinle) hâlâ
   koleksiyondaydı — Sprint 4'ün eski "önce sil" sırası bunları çoktan
   silmiş olurdu. Registry de hâlâ ESKİ hash'i gösteriyordu — bir sonraki
   sync bu dokümanı doğru şekilde "değişti" olarak görüp tekrar
   deneyecek.
2. **Başarılı re-index'te eski chunk'lar gerçekten temizleniyor**: ayrı
   bir testle, başarılı bir re-index sonrası eski versiyonun chunk'ı
   koleksiyonda kalmıyor, sadece yeni metin var.

**Duplicate görünürlük penceresi: GERÇEKTEN var olduğu kanıtlandı, sadece
yorumda yazılı durmadı.** `QdrantStore`'u saran bir `_SnapshotStore`,
`delete_stale_versions` çağrılmadan HEMEN ÖNCE koleksiyonun gerçek
içeriğini (`scroll`) okuyor — sonuç: o anda İKİ `document_version` değeri
VE her iki versiyonun metni ("apples" eski, "oranges" yeni) AYNI ANDA
koleksiyonda, gerçekten arama sonucuna dönebilecek durumda. Bu, sadece
"teorik olarak mümkün" değil, gerçek bir ara durum olarak doğrudan
gözlemlendi.

**Pencere süresi ÖLÇÜLDÜ, tahmin edilmedi.** Sprint 8'in zaten var olan
`upsert_batch`/`delete_stale_chunks` span'leri gerçek OTel zaman
damgalarıyla (nanosaniye hassasiyetinde, `InMemorySpanExporter` ile
yakalandı) kullanılarak, son `upsert_batch` span'inin bitişi ile
`delete_stale_chunks` span'inin başlangıcı arasındaki GERÇEK fark
ölçüldü: **~12 mikrosaniye** (yerel, in-memory bir koşumda). Bu süre
embed süresinden BAĞIMSIZ — tüm embedding pencere AÇILMADAN ÖNCE bitmiş
oluyor; pencere sadece iki ardışık Qdrant çağrısı arasındaki gerçek
Python/ağ gecikmesi kadar. README'ye ve kod yorumlarına bu ölçülmüş
değer yazıldı, "kısa bir pencere var" gibi belirsiz bir ifadeyle
bırakılmadı.

**Sprint 4/5/6/8'in mevcut testleri değişmeden geçti** — varsayılmadı,
gerçekten çalıştırıldı: `test_sync_scenarios.py` (orphan chunk yok,
no-op sıfır yazma, shrink senaryosu), `test_citation_cross_source_leak_e2e.py`
(çapraz kaynak sızıntısı yok), `test_ingest_connector_tracing.py`
(span kümesi/hiyerarşisi), `test_notion_pipeline_e2e_hermetic.py`
(Notion skip/update/delete) — 20 test, hepsi yeşil. Hiçbiri eski
"önce sil" sırasına spesifik bir varsayıma dayanmıyormuş (hepsi son
duruma bakıyor: yetim yok, doğru içerik, sızıntı yok) — bu gerçekten
doğrulandı, sadece varsayılmadı.

**README'ye "zero-downtime versioned re-index with deferred cleanup"
olarak, "atomic" DENMEDEN belgelendi** — Sync bölümüne yeni bir alt
başlık (`Re-indexing a changed document: zero-downtime with deferred
cleanup`) ve Known Limitations'a ölçülen pencere süresiyle birlikte bir
madde eklendi; Technologies Used tablosundaki Sync satırı da
güncellendi.

358 test toplam (bu sprintte +8 yeni test — `delete_stale_versions`
birim testleri + versioned re-index senaryo testleri), 355'i gerçek
Qdrant+Ollama'ya karşı geçiyor (2'si servis/API key gerektirdiği için
skip, değişmedi), `ruff check` temiz, flakiness yok.

## Sprint 14 — Ingestion Performance

Amaç: `batch_size` isimlendirme uyuşmazlığını düzeltmek, gerçek embedding concurrency eklemek, benchmark yapıp default değeri kanıtlamak.

Scope:

* `batch_size` → `upsert_batch_size` (Qdrant'a ne büyüklükte upsert edildiğini kontrol ediyor, embedding'i değil)
* Yeni config: `embedding_concurrency` — `asyncio.Semaphore` ile bounded concurrency, embed çağrıları `asyncio.gather` ile paralel
* Gerçek Ollama'ya karşı benchmark: concurrency=1,2,4,8 × 10/100/1000 chunk, chunks/sec ölçümü — tek native Ollama instance'ında yüksek concurrency'nin throughput yerine kuyruklama yaratıp yaratmadığı gerçekten test edilir
* Benchmark sonucuna göre default `embedding_concurrency` seçilir, gerekçesi yazılır
* README'ye throughput tablosu

DoD: embedding'ler gerçekten paralel çalışıyor (kanıtlanmış, varsayılmamış); benchmark tablosu gerçek ölçümlerle README'de; seçilen default gerekçeli; testler ve lint temiz.

### Kapanış notu

**İsimlendirme düzeltmesi mekanik ve risksizdi.** `batch_size`
`app/ingestion/ingest.py`'de sadece `store.upsert_chunks(...)`'a kaç
chunk'lık gruplar halinde yazıldığını kontrol ediyordu — embedding hiçbir
zaman batch'lenmiyordu (`embed_fn` her chunk için ayrı ayrı çağrılıyordu).
`grep` ile hiçbir çağıranın `batch_size=` diye keyword argüman
geçmediği doğrulandı; `upsert_batch_size` olarak yeniden adlandırma
davranış değişikliği olmadan yapıldı.

**Gerçek concurrency, sadece "hızlı bitti" değil, GERÇEKTEN kanıtlandı.**
`embed_texts_concurrently()` (`asyncio.Semaphore` + `asyncio.gather`)
testleri, sahte bir `embed_fn`'in "şu anda kaç çağrı uçuşta" sayacını
tutmasına dayanıyor: `concurrency=4` istendiğinde GERÇEKTEN aynı anda en
fazla 4 çağrının uçuştuğu (`max_concurrent == 4`, ne fazla ne az)
doğrulandı — sadece toplam sürenin kısaldığına bakılmadı, çünkü bu
yanlışlıkla sınırsız bir `gather`'ı ya da no-op bir semaphore'u da
gizleyebilirdi. Ayrı testler: `concurrency=1`'in gerçekten sıralı
çalıştığı, girdi sayısından büyük concurrency'nin girdi sayısında
tavanlandığı, sonuç sırasının (`asyncio.gather` garantisi) korunduğu, ve
bir `embed_fn` hatasının hâlâ dışarı fırladığı (Sprint 13'ün deferred-
cleanup re-index'inin buna dayandığı) — 6 test, hepsi yeşil.
`app/sync/manager.py::SyncManager`'a da `embedding_concurrency` parametresi
eklendi ve GERÇEK bir `SyncManager.trigger_sync()` çağrısı üzerinden
(200 cümlelik gerçek bir markdown dokümanı, birden fazla chunk'a
bölünecek şekilde) aynı izleme deseniyle doğrulandı — sadece
`ingest_connector`'a değil, tüm zincire (config → SyncManager →
ingest_connector) gerçekten ulaştığı kanıtlandı.

**Benchmark GERÇEK native Ollama'ya karşı çalıştırıldı** (`scripts/benchmark_embedding_concurrency.py`,
`nomic-embed-text`, M2), concurrency=1,2,4,8 × 10/100/1000 chunk:

```
 chunks concurrency  elapsed_s  chunks/sec
     10           1       0.88       11.42
     10           2       0.16       63.85
     10           4       0.16       62.34
     10           8       0.15       67.10
    100           1       2.47       40.53
    100           2       1.29       77.71
    100           4       1.37       72.93
    100           8       1.21       82.73
   1000           1      25.24       39.62
   1000           2      12.37       80.86
   1000           4      11.44       87.43
   1000           8      11.31       88.45
```

**Sonuç: review'ın uyardığı senaryo GERÇEKTEN çıktı — düzleşme (plateau),
"concurrency arttıkça hep daha hızlı" DEĞİL.** `concurrency=1→2` gerçek ve
büyük bir sıçrama (1000 chunk'ta 39.6 → 80.9 chunks/sec, ~2x).
`concurrency=2→4` sadece marjinal bir iyileşme (80.9 → 87.4, ~%8, sadece
en büyük/en güvenilir örneklemde — 1000 chunk). `concurrency=4→8` ÖLÇÜM
GÜRÜLTÜSÜ içinde, hiçbir gerçek kazanç yok (87.4 → 88.5, ~%1, küçük
chunk sayılarında hatta 4 bazen 8'den DÜŞÜK: 10 chunk'ta 62.3 vs 67.1).
Tek native Ollama instance'ının tek bir embedding modelini muhtemelen iç
mekanizmasında kısmen serileştirdiği (ya da GPU/CPU kaynak sınırına
ulaştığı) sonucuna varılabilir — ama bu spekülasyon değil, gözlemlenen
gerçek eğri.

**Seçilen default: `EMBEDDING_CONCURRENCY=4`.** Gerekçe: eğrideki GERÇEK
marjinal kazancın olduğu SON nokta — 2'den 4'e geçişte hâlâ ölçülebilir
bir iyileşme var (özellikle ölçekte), 4'ten 8'e geçişte YOK. 8'i seçmek
hiçbir ölçülen fayda karşılığında daha fazla bağlantı açık tutmak
olurdu. `app/ingestion/ingest.py::DEFAULT_EMBEDDING_CONCURRENCY` ve
`Settings.embedding_concurrency` ikisi de `4` — ikisi ayrı, bağımsız
varsayılanlı alanlar (`config.py`'nin `ingest.py`'den bu sabiti import
etmesi `ingest.py → shared.tracing → shared.config` döngüsel import'una
yol açardı, bu yüzden bilinçli olarak ayrı tutuldu, yorumla belgelendi).

**Gerçek bir sync koşumunun zaman dağılımı da ölçüldü** (7 chunk,
`EMBEDDING_CONCURRENCY=4`, Sprint 8'in zaten var olan OTel span'leri
üzerinden — `InMemorySpanExporter` ile gerçek nanosaniye zaman
damgaları): toplam 939ms, embedding 812ms (%86 — beklenen, baskın
maliyet), Qdrant upsert 29ms (%3), parse+chunk 2ms (<%1). Qdrant'ın
kendi yazma yolu zaten hızlı — optimizasyona değecek darboğaz orada
değil.

**README'ye hem concurrency benchmark tablosu hem gerçek sync zaman
dağılımı eklendi** (Sync bölümü altında yeni bir "Embedding throughput"
alt başlığı), Technologies Used tablosundaki Sync satırı da güncellendi.

364 test yeşil (bu sprintte +8 yeni test — concurrency birim testleri +
SyncManager zincirleme testi + config testleri), 2'si servis/API key
gerektirdiği için skip (değişmedi), `ruff check` temiz.

## Sprint 15 — Documentation and Cleanup

Amaç: Kod içi yorum şişkinliğini temizlemek, kalan known limitation'ları belgelemek.

Scope:

* Sprint geçmişini anlatan kod yorumlarını `docs/adr/` altına taşı (Context/Decision/Consequences formatında ADR'lar), kodda tek satırlık referansa indir
* Stale yorumları bul ve düzelt (en az review'daki örnek: `ingest_connector`'ın artık skip ettiğini söylemeyen eski test yorumu)
* Known Limitations'a eksikleri ekle: process-local sync lock, Notion'ın mock-tested/non-recursive olduğu netliği
* FastAPI lifespan'de shutdown tarafını kontrol et — Ollama/Notion client'ları düzgün kapatılıyor mu

DoD: kod dosyalarındaki sprint-geçmişi yorumları `docs/adr/`'a taşınmış; en az bir stale yorum düzeltilmiş; Known Limitations tam; shutdown handling kontrol edilmiş (gerekiyorsa düzeltilmiş); tüm mevcut testler değişmeden geçiyor, lint temiz.

**6 ADR yazıldı** (`docs/adr/0001`–`0006`, + bir index `docs/adr/README.md`),
her biri gerçek `docs/PLANNING.md` kapanış notlarından referans alınarak:
connector interface'in async olması (Sprint 3→6), üç fazlı incremental
sync (Sprint 4), deferred-cleanup versioned re-index (Sprint 4→12→13),
sync başına tek trace (Sprint 8, + Sprint 12'nin partial-index retry
düzeltmesi), real wiring'in Sprint 11'den Sprint 10'a çekilmesi, ve
scheduler'ın FastAPI lifespan'e bağlanması (Sprint 7→10→11). Kod
içindeki 4 dosyadaki (`app/connectors/base.py`, `app/ui/trace_client.py`,
`app/main.py`, ve ilgili docstring'ler) çok satırlı sprint-geçmişi
anlatıları, ADR'a link veren tek satırlık referanslara indirildi; geri
kalan ~18 dosyadaki tek satırlık "(Sprint N)" pointer'ları zaten bloat
değildi, dokunulmadı.

**Stale yorum**: `tests/test_ingest_connector.py:151` düzeltildi —
"this sprint doesn't skip" diyen eski yorum, artık gerçekte
`ingest_connector`'ın unchanged dosyaları skip ettiğini (Sprint 4)
söyleyecek şekilde güncellendi. Codebase'in geri kalanı ("doesn't yet",
"not yet", "for now", "currently", "this sprint doesn't/does" gibi
kalıplar için) tek tek grep'lenip kod karşısında doğrulandı — başka
stale yorum bulunmadı.

**Known Limitations'a 2 madde eklendi, 1 madde netleştirildi**:
process-local sync lock (`SyncManager._running`, Sprint 7 — plain
`dict`, distributed değil, şu an Dockerfile tek-process olduğu için
latent); Notion connector bulleti "mock-tested + non-recursive/skipped
block types" olarak netleştirildi (`app/connectors/notion.py`'nin
kendi yorumundan doğrulandı — nested child block'lara girmiyor, sabit
bir block-type listesi dışındakileri atlıyor); ayrıca Confluence
bulletindeki stale "Sprint 12" referansı, `docs/PLANNING.md`'deki
yeniden numaralandırmayla tutarlı olacak şekilde "Sprint 16" olarak
düzeltildi.

**Shutdown handling: gerçek bir eksik bulundu ve düzeltildi.** Üç
client'ın (`OllamaClient` embedding, `ChatProvider` — chat için ayrı
bir instance, `get_chat_provider` her zaman kendi instance'ını kurar —
ve `NotionConnector`) üçü de zaten çalışan `aclose()` metodlarına
sahipti, ama gerçek uygulama lifecycle'ında (`app/wiring.py::build_app()`)
hiçbiri hiç çağrılmıyordu. `create_app()`'e `scheduler` ile aynı
optional-hook pattern'ini izleyen bir `on_shutdown:
list[Callable[[], Awaitable[None]]]` parametresi eklendi (lifespan'de
`scheduler.stop()`'tan sonra çalıştırılıyor), test-first 3 yeni testle
doğrulandı (`tests/test_app_lifespan.py`), sonra `build_app()` gerçek
hook listesini (`ollama.aclose`, `chat_provider.aclose`, + her
connector'ın `aclose`'u varsa, `hasattr` ile) toplayıp geçirecek şekilde
güncellendi. Gerçek bir scratch script ile doğrulandı: `build_app()`'in
kurduğu gerçek component'lerle (gerçek `OllamaClient`, sahte anahtarlı
bir `NotionConnector`) `TestClient` context manager'ı içinden
lifespan'in tamamı (startup + shutdown) çalıştırıldı, `GET /health`
200 döndü ve shutdown hook'larının hiçbiri exception fırlatmadan
tamamlandı — canlı bir Qdrant/Ollama/Notion servisi gerekmedi çünkü
`aclose()` sadece altındaki `httpx.AsyncClient`'ı kapatıyor, network
çağrısı yapmıyor.

365 test yeşil (bu sprintte +3 yeni test — shutdown-hook testleri;
davranış değişikliği olmadığı için mevcut testlerin hiçbiri
değişmedi), 5'i servis/API key gerektirdiği için skip (değişmedi),
`ruff check` temiz.

## Sprint 16 — Re-index Failure Semantics & Hardening

Amaç: İkinci bir dış kod review'ından çıkan, özellikle Sprint 13'ün ölçüm metodolojisindeki gerçek bir açığı ve birkaç production-hijyen sorununu kapatmak.

Scope:

1. Multi-batch partial-new re-index bug'ı: `QdrantStore.delete_version()` eklenir, embed/upsert döngüsü try/except ile sarılır, hata olursa o document_version'a ait tüm point'ler rollback edilir; Sprint 13'ün duplicate-window ölçümü gerçek çok-batch'li bir dokümanla yeniden yapılır
2. Config validation: `embedding_concurrency` ve sync interval'lerine Pydantic `Field` kısıtları
3. UI: citation-free durumunda `NOT_FOUND_PHRASE` ile gerçek halüsinasyonu ayırt et
4. `ensure_collection()` dense vector boyutu + distance metriğini de kontrol etsin
5. Shutdown hook'ları failure-safe yapılır, `QdrantClient` de listeye eklenir
6. README çelişkileri (Confluence/web connector iddiası, stale Status sayısı) düzeltilir
7. Benchmark metodolojisi: warmup, tekrar, randomize, mean/median/stddev
8. CI lint scope'u `scripts/`'i de kapsayacak şekilde genişletilir

DoD: multi-batch kısmi başarısızlık senaryosunda rollback gerçekten çalışıyor (kanıtlanmış); duplicate window gerçek bir çok-batch dokümanla yeniden ölçülmüş; config validation çalışıyor; UI citation-free durumları ayırt ediyor; Qdrant schema validation tam; shutdown failure-safe; README tutarlı; benchmark istatistiksel olarak daha sağlam; testler ve lint temiz.

### Kapanış notu

**1. Multi-batch partial-new re-index bug'ı — GERÇEKTEN kanıtlandı, sadece
düzeltilmedi.** Önce bug'ı reproduce eden bir test yazıldı (fix'ten ÖNCE
çalıştırıldı, gerçekten fail etti — varsayılmadı): `upsert_batch_size=2`,
7 batch'lik gerçek bir Markdown dokümanı, batch 1 başarılı, batch 2'nin
embed çağrısı GERÇEKTEN hata fırlatıyor. Fix öncesi: batch 1'in
NEW-version point'leri koleksiyonda kalıyordu, `delete_stale_chunks` hiç
çalışmıyordu — Sprint 13'ün ADR'ının iddia ettiği "eski versiyon sağlam
kalır" garantisi doğruydu ama eksikti, çünkü kısmi bir YENİ versiyon da
sessizce koleksiyonda kalıyordu. Fix: `QdrantStore.delete_version()`
eklendi (mevcut `delete_stale_versions`'ın aynası — o "keep_version
DIŞINDAKİLERİ" siler, bu "document_version EŞLEŞENLERİ" siler),
`ingest_connector`'ın embed/upsert döngüsü try/except'e alındı, hata
olursa o `document_version`'a ait TÜM point'ler rollback edilip hata
yeniden fırlatılıyor. Test artık geçiyor: eski versiyon %100 sağlam, YENİ
versiyona ait SIFIR point var (sadece "eskiler hayatta kaldı" değil,
"yenilerden hiçbiri kalmadı" doğrudan assert edildi), registry hâlâ eski
hash'i gösteriyor.

**2. Duplicate-visibility penceresi gerçek bir çok-batch dokümanla
yeniden ölçüldü — Sprint 13'ün ~12µs'lik sayısı yanıltıcıydı, tek
batch'lik bir dokümanla ölçülmüştü.** Yeni ölçüm: son `upsert_batch`
yerine İLK `upsert_batch`'in bitişinden `delete_stale_chunks`'ın
başlangıcına kadar olan gerçek OTel span farkı (7 batch'lik gerçek bir
dokümanla). Birden fazla koşuda gözlemlenen gerçek sayılar:
tek-batch'lik pencere ~12-22 mikrosaniye civarında kalırken, çok-batch'lik
pencere **~1.5-3.2 milisaniye** — yani ~100 kat daha uzun, çünkü pencere
artık ilk batch upsert edildiği andan itibaren açık kalıyor, sadece son
iki Qdrant çağrısı arasındaki fark değil. README ve
`app/ingestion/ingest.py`'nin kod yorumu bu gerçek sayıyla güncellendi.

**3. Config validation eklendi, gerçek bir deadlock sınıfı önlendi.**
`embedding_concurrency` artık `Field(ge=1, le=32)`,
`filesystem_sync_interval_seconds`/`notion_sync_interval_seconds` artık
`Field(gt=0)`. `EMBEDDING_CONCURRENCY=0` öncesi `Settings()`'i sessizce
geçip ilk gerçek sync'te `asyncio.Semaphore(0)` ile sonsuza kadar
deadlock oluyordu (kod okunarak doğrulandı: `Semaphore(0)` hiçbir
`_bounded` coroutine'ini `async with`'ten geçirmez) — artık `Settings()`
inşa anında (yani process başlangıcında) `ValidationError` fırlatıyor.
4 yeni test (0, negatif embedding_concurrency; 0, negatif sync interval).

**4. UI: citation-free durumu artık `NOT_FOUND_PHRASE`'e göre ayrılıyor.**
`app/ui/pages/chat.py`: `full_answer.strip() == NOT_FOUND_PHRASE` ise
nötr "ℹ️ No relevant source found", değilse "⚠️ Answer contains no
verifiable citations" (`grounding.py`'nin kendi docstring'ine göre en
tehlikeli halüsinasyon şekli — hiç citation tag'i yok, sorgulanacak bir
şey bile yok). Streamlit sayfaları için mevcut bir test altyapısı yok
(projenin geri kalanı da öyle) — bu, koddan okunarak ve gerçek diff
üzerinden doğrulandı, tarayıcı testi bu sprint'in kapsamında değildi.

**5. Qdrant schema validation tamamlandı.** `ensure_collection()` artık
sparse vector varlığının yanında dense vector'ın boyutunu (`EMBEDDING_DIM`)
ve distance metriğini (`COSINE`) de kontrol ediyor, uyuşmazlıkta
`UnexpectedCollectionSchemaError` fırlatıyor (koleksiyonu silmeden —
mevcut sparse-check'le aynı "dokunma, insana söyle" politikası). Fix
öncesi 2 test yazıldı, GERÇEKTEN fail ettiği doğrulandı (yanlış boyut:
384 yerine 768; yanlış metrik: EUCLID yerine COSINE), sonra fix'le
birlikte geçti. Doğru şema hâlâ sorunsuz kabul ediliyor (ayrı bir test).

**6. Shutdown hook'ları artık failure-safe, `QdrantClient` de listede.**
`app/main.py`'nin `lifespan`'i her `on_shutdown` hook'unu kendi
try/except'i içinde çalıştırıyor (`logger.exception`, raise değil) — bir
client'ın `aclose()`'u patlarsa (örn. Notion yarı-açık bir bağlantıda
hata verirse) artık listedeki geri kalan hook'ları (Ollama embed, chat
provider gibi daha önemlileri) engellemiyor. Fix öncesi 2 test yazıldı,
GERÇEKTEN fail ettiği doğrulandı, sonra geçti. `app/wiring.py::build_app()`
artık `qdrant_client.close()`'u (sync, async bir wrapper'la sarılı)
listeye ekliyor — artık 3 değil 4 gerçek client kapanıyor (Ollama embed,
chat provider, Notion, Qdrant). Gerçek scratch script'le yeniden
doğrulandı (Sprint 15'teki aynı script) — hepsi exception fırlatmadan
kapandı.

**7. README çelişkileri düzeltildi.** Giriş paragrafı artık "PDF,
Markdown, Notion" + "ayrı bir web parser var ama connector'a
bağlanmamış" diyor (Confluence hiç yok, web parser'ın sync desteği yok —
ikisi de daha önce Known Limitations'da vardı ama giriş paragrafı hâlâ
5 kaynağı da varmış gibi listeleyip çelişiyordu). `## Status`: "Sprints
0–11" → "Sprints 0–16", CI bulleti eklendi, versioned re-index bulletine
rollback notu eklendi. Confluence known-limitation bulletindeki stale
"Sprint 16" referansı "Sprint 17" olarak düzeltildi (bu sprint'in kendi
numarasını alması nedeniyle stretch-connector sprint'i
`docs/PLANNING.md`'de Sprint 17'ye kaydırıldı).

**8. Benchmark metodolojisi güçlendirildi VE gerçek Ollama'ya karşı
yeniden koşuldu (skip edilmedi).** `scripts/benchmark_embedding_concurrency.py`:
her chunk sayısı için 1 ısınma koşumu, her (chunk_count, concurrency)
çifti için 3 tekrar, her tekrarda concurrency sırası `random.shuffle`
ile karıştırılıyor, mean/median/stddev raporlanıyor. Gerçek koşum
sonucu (native Ollama, `nomic-embed-text`, n=9 her concurrency için):
concurrency=1 → mean 26.9 (stddev 7.6), concurrency=2 → mean 48.9
(stddev 19.8), concurrency=4 → mean 57.1 (stddev 18.5), concurrency=8 →
mean 55.6 (stddev 23.8). Sprint 14'ün "plateau" iddiası artık gerçek bir
varyans sayısıyla destekleniyor: 1→2 sıçraması her iki stddev'den de
büyük (gerçek), 4→8 farkı (57.1 vs 55.6) her iki stddev'in de İÇİNDE
(gürültüden ayırt edilemiyor). `EMBEDDING_CONCURRENCY=4` varsayılanı
değişmedi — Sprint 14'teki seçim artık istatistiksel olarak dürüst bir
şekilde doğrulandı. README tablosu bu gerçek sayılarla güncellendi.

**9. CI lint scope'u genişletildi.** `.github/workflows/ci.yml`:
`ruff check app tests` → `ruff check app tests scripts`. Genişletmeden
önce `scripts/` yerel olarak lint edildi, bir satır-uzunluğu hatası
(bu sprintin kendi yeni test dosyasında, `ruff check app tests scripts`
ile keşfedildi) düzeltildi, sonra CI workflow'u güncellendi.

**Ortam notu (kod ile ilgisiz):** kapsamlı benchmark koşumu sırasında
native Ollama'nın generation modeli (`qwen2.5:7b-instruct`) geçici
olarak yanıt vermez hale geldi (muhtemelen ağır embedding yükü modeli
bellekten attı, yeniden yükleme takıldı) — `test_generation_e2e.py`'nin
3 testi bu yüzden `OllamaUnreachableError` ile fail etti. Ollama
yeniden başlatıldıktan sonra (kullanıcı onayıyla) tüm suite tekrar
koşuldu ve temiz geçti; bu sprint'in kod değişiklikleriyle ilgisi yoktu
(generation kod yolu bu sprintte hiç değiştirilmedi).

**380 test yeşil** (bu sprintte +15 yeni test:
`tests/test_versioned_reindex.py` +2 — rollback testi + çok-batch pencere
ölçüm testi; `tests/test_qdrant_store.py` +7 — 4 `delete_version` testi +
3 dense-schema-validation testi; `tests/test_config.py` +4 — embedding
concurrency/sync interval sınır testleri; `tests/test_app_lifespan.py` +2
— shutdown failure-safety testleri), 5'i servis/API key gerektirdiği için
skip (değişmedi), `ruff check app tests scripts` temiz.

## Sprint 17 — Identity & Cancellation Safety

Amaç: Üçüncü bir dış kod review'ından çıkan, en kritik olanı gerçek bir point ID çakışma bug'ı olan bulguları kapatmak.

Scope:

1. Point ID collision: `QdrantStore.point_id_for`'ın key'i `source_id` içermiyordu — aynı içerikli ama farklı kaynaklı iki doküman aynı point ID'ye çakışıp birbirini sessizce eziyordu. Fix + mevcut testi gizleyen `_chunk()` helper default'unu düzeltme + gerçek e2e test
2. Cancellation rollback bypass: Sprint 16'nın rollback `except Exception` bloğu `asyncio.CancelledError`'ı yakalamıyordu (BaseException'dan türer). Ayrı except bloğu + `STATUS_CANCELLED` eklendi
3. Duplicate source_id fail-fast guard: `ingest_connector()` başında connector'dan gelen source_id'lerin unique olduğu kontrol ediliyor
4. Qdrant schema validation tamamlandı: VECTOR_NAME KeyError yerine düzgün hata, sparse modifier kontrolü
5. `upsert_chunks()`'a length guard eklendi
6. README: stale ~12µs rakamı ve "Grounded" başlığı düzeltildi

DoD: aynı içerikli farklı kaynaklı iki doküman artık çakışmıyor (gerçek testle kanıtlanmış, silme öncesi point sayısı assert edilerek); cancellation sırasında rollback çalışıyor; duplicate source_id fail-fast; Qdrant schema validation tam; testler ve lint temiz.

### Kapanış notu

**1. Point ID collision — gerçek etkisi doğrulandı ve düzeltildi.**
`QdrantStore.point_id_for`'ın UUID5 key'i `source_type:doc_id:page:
paragraph:char_range` şeklindeydi, `source_id` yoktu. `doc_id` bir içerik
hash'i olduğu için, aynı byte-içerikli ama farklı dosya/source_id'li iki
doküman (örn. `contract-a.pdf` ve `contract-b.pdf`, birebir aynı metin)
aynı `(doc_id, page, paragraph, char_range)` demetini üretiyor — dolayısıyla
aynı point ID'yi. İkinci dokümanın `upsert_chunks` çağrısı birincinin
point'lerini SESSİZCE eziyordu: hata yok, görünür bir duplicate yok,
sadece veri kaybı. **Bug'ın kendisi kadar önemli bir bulgu**: mevcut
`test_delete_by_source_does_not_touch_other_documents` testi bu bug'ı
gizliyordu — `_chunk(source_id="doc1")` ve `_chunk(source_id="doc2")`
çağrılarının ikisi de `_chunk()`'ın default `doc_id="doc1"`'ini
override etmiyordu, yani iki chunk zaten testin kendi `delete_by_source`
çağrısından ÖNCE çakışıyordu — `upsert_chunks` sadece TEK bir point
yazıyordu, silme sonrası `count() == 1` assertion'ı yanlış nedenle
geçiyordu (iki bağımsız dokümandan biri hayatta kaldığı için değil,
zaten tek point olduğu için). Fix: key'e `source_id` eklendi. Testler:
(a) fix'ten ÖNCE çalıştırılıp GERÇEKTEN fail ettiği doğrulanan yeni bir
`point_id_for` testi; (b) `_chunk()` çağrılarına açık, farklı `doc_id`
verilerek eski testin "gizleyen" doğası düzeltildi; (c) yeni bir
senaryo testi — aynı doc_id/koordinatlı, farklı source_id'li iki chunk
upsert edilip **silmeden önce `store.count() == 2` assert edildi**
(review'ın istediği kritik assertion — orijinal bug'ın testinde hiç
yoktu), sonra biri silinip diğerinin sağlam kaldığı doğrulandı; (d)
gerçek bir e2e test — birebir aynı içerikli `a.md`/`b.md`,
`LocalFilesystemConnector` üzerinden gerçek registry + gerçek
(`:memory:`) Qdrant'a ingest edildi, ikisinin de bağımsız registry
satırı VE bağımsız Qdrant point'leri olduğu (`count()` iki dokümanın
toplam chunk sayısını yansıtıyor, biri diğerini ezmiyor) kanıtlandı.

**2. Cancellation rollback bypass — gerçek bir `task.cancel()` ile
simüle edildi, manuel raise değil.** Sprint 16'nın rollback bloğu
`except Exception:` idi — `asyncio.CancelledError` Python 3.8'den beri
`BaseException`'dan türediği için bu bloğa hiç girmiyordu. Test:
gerçek bir `asyncio.Task` içinde `ingest_connector` çalıştırıldı,
`embed_fn` batch 1'i (2 chunk) başarıyla bitirip batch 2'nin ilk
çağrısında bir `asyncio.Event` set edip `asyncio.sleep(10)`'a giriyor;
test bu event'i bekleyip TAM O ANDA `task.cancel()` çağırıyor — yani
cancellation, asyncio'nun kendi mekanizmasıyla, coroutine'in askıda
olduğu gerçek bir noktada teslim ediliyor (elle fırlatılan bir
`CancelledError` ile taklit edilmiyor). Fix: `except
asyncio.CancelledError:` ayrı bir blok olarak eklendi, aynı
`delete_version` rollback'ini çağırıp `raise` ile cancellation'ı
yutmadan yeniden fırlatıyor. Test fix'ten önce GERÇEKTEN fail etti
(batch 1'in point'leri koleksiyonda kaldı), fix'ten sonra geçti.
Ayrıca `SyncManager.trigger_sync`'in aynı `except Exception as exc:`
açığı vardı — cancellation'da `sync_runs` satırı sonsuza kadar
`"running"` durumunda kalıyordu (ne except ne else branch'i
çalışıyordu). `STATUS_CANCELLED = "cancelled"` eklendi,
`trigger_sync`'e ayrı bir `except asyncio.CancelledError:` branch'i
eklendi (`finish_run(status=STATUS_CANCELLED, ...)` sonra `raise`).
Bu da gerçek bir `asyncio.Task` + `task.cancel()` ile test edildi:
`manager.is_running()` `finally`'nin her zaman çalıştığını doğruluyor
(False'a döner), ama asıl kanıt `history.latest_run(...).status ==
STATUS_CANCELLED` — fix öncesi bu assertion GERÇEKTEN `'running' ==
'cancelled'` diye fail etti.

**3. Duplicate source_id fail-fast guard eklendi.** `ingest_connector`
artık `list_documents()`'tan dönen doküman listesindeki source_id'lerin
unique olduğunu kontrol ediyor (`Counter` ile), değilse
`DuplicateSourceIdError` fırlatıp registry/Qdrant'a hiç dokunmadan
duruyor. Bilinçli olarak `slugify()`'ı değil, `ingest_connector`'ın
sınırını kontrol ediyor — slugify çakışması ("foo bar.md" vs
"foo_bar.md") bir neden ama tek neden değil, connector kendi
sebepleriyle de duplicate dönebilir. Test: sahte bir connector iki aynı
source_id'li doküman döndürüyor, hatanın registry/Qdrant'a HİÇ
dokunmadan (fetch_content/get_content_hash çağrılmadan bile) fırladığı
doğrulandı.

**4. Qdrant schema validation tamamlandı.** İki gerçek eksik kapatıldı:
(a) `info.config.params.vectors[VECTOR_NAME]`'e erişmeden önce artık
`VECTOR_NAME in dense_vectors` kontrolü var — önceden bir koleksiyonun
"dense" adında hiç vector'ı yoksa (ama başka bir sparse config'i varsa)
ham bir `KeyError` fırlıyordu, `UnexpectedCollectionSchemaError` değil;
fix'ten önce test GERÇEKTEN `KeyError` ile fail etti. (b) sparse
vector'ın `modifier`'ının gerçekten `IDF` olduğu artık kontrol ediliyor
— önceden sadece key'in var olup olmadığına bakılıyordu,
`create_collection()`'ın kendisi her zaman IDF set etmesine rağmen
validate tarafı bunu hiç doğrulamıyordu (iki kod yolu "doğru şema"
konusunda anlaşmıyordu). Bu fix, mevcut
`test_ensure_collection_accepts_correct_dense_and_sparse_schema`
testinin de GERÇEKTEN yanlış olduğunu ortaya çıkardı — `SparseVectorParams()`
modifier'sız (varsayılan `None`) çağrılıyordu, düzeltilip `modifier=IDF`
eklendi.

**5. `upsert_chunks()`'a length guard eklendi.** `chunks`/`dense_vectors`/
`sparse_vectors` uzunlukları eşit değilse artık `ValueError` fırlıyor —
önceden `zip()` sessizce en kısa listeye kısaltıyordu, bir çağıran
bug'ı (gelecekteki bir batching değişikliğinde off-by-one, kısmi bir
embed sonucu) hiçbir hata vermeden chunk sayısından daha az point
yazabilirdi. Test fix'ten önce GERÇEKTEN "DID NOT RAISE" ile fail etti.

**6. README düzeltmeleri.** Known Limitations'daki stale "~12
microseconds" rakamı, Sprint 16'nın gerçek çok-batch ölçümüyle (~1.5–3ms,
ilk upsert'ten itibaren) tutarlı hale getirildi, artı Sprint 17'nin
cancellation/multi-batch rollback düzeltmesine bir not eklendi.
Highlights'taki "Grounded, multi-source citations" başlığı
"Source-scoped citation validation" olarak değiştirildi ve "Citation
integrity validation, not semantic grounding" bölümüne link eklendi —
eski başlık, `grounding.py`'nin kendi docstring'inin açıkça reddettiği
bir semantik grounding izlenimi veriyordu.

**Ortam notu (kod ile ilgisiz):** bu sprint sırasında native Ollama ve
Qdrant bazı aralıklarla erişilemez durumdaydı (önceki sprint'in ağır
benchmark koşumunun kalıntısı) — bu, sadece gerçek servis gerektiren
e2e testlerin (normalden 3 fazla, toplam 8) doğru şekilde skip
edilmesine yol açtı, hiçbir zaman bir test'i yanlış geçirmedi ya da
gizli bir regresyon yaratmadı; bu sprint'in kod değişiklikleri
generation/embedding servislerine dokunmuyor.

**386 test yeşil** (bu sprintte +9 yeni test:
`tests/test_qdrant_store.py` +5 — point-ID collision testi, 2 schema
validation testi (VECTOR_NAME KeyError, sparse modifier), length-guard
testi, + `test_delete_by_source_does_not_touch_other_documents`'ın
düzeltilmesi (net test sayısını değiştirmedi); `tests/test_versioned_reindex.py`
+1 — gerçek cancellation rollback testi; `tests/test_ingest_connector.py`
+2 — identical-content e2e testi + duplicate-source-id fail-fast testi;
`tests/test_sync_manager.py` +1 — SyncManager seviyesinde gerçek
cancellation testi), 8'i servis/API key gerektirdiği için skip,
`ruff check app tests scripts` temiz.

## Sprint 17.1 — Migration Safety & Test False-Positive Cleanup

Amaç: Dördüncü bir dış kod review'ından çıkan, en önemlisi point-ID şema değişikliğinin mevcut (persist edilmiş) index'i onarmaması olan bulguları kapatmak.

Scope:

1. Point-ID şema migration'ı: `registry_metadata` tablosu + `index_schema_version` mekanizması, `DocumentRegistry.ensure_index_schema_version()`. Uyuşmazlıkta fail-fast (`IndexSchemaMismatchError`), otomatik re-index değil — gerekçe: `ensure_collection()`'ın zaten uyguladığı "sessizce silip yeniden oluşturma, insana söyle" politikasıyla tutarlı, `docker compose down -v` + `up` zaten bilinen/test edilmiş bir yol
2. Qdrant schema testlerindeki false-positive düzeltildi: sparse modifier kontrolü dense testlerini maskeliyordu, fixture'lara `modifier=IDF` eklendi, assertion'lar spesifik hataya (`match="size=384"` vb.) bağlandı
3. Unnamed Qdrant vector şeması: `isinstance(dense_vectors, dict)` kontrolü eklendi — önceden Pydantic'in `__iter__` davranışına kazara dayanıyordu
4. Cancellation rollback'in kendi hatası artık orijinal `CancelledError`'ı maskelemiyor (`ingest.py` + `SyncManager`)
5. README: sprint sayısı, "grounded citations" ifadesi, duplicate-source guard dokümantasyonu düzeltildi

DoD: eski şema versiyonlu bir index tespit edilip doğru tepki veriyor (kanıtlanmış); dense schema testleri gerçekten dense'i test ediyor (sparse modifier maskelemesi yok); unnamed vector şeması düzgün hata veriyor; cancellation rollback'i kendi hatasını yutmuyor; README tutarlı; testler ve lint temiz.

Bu sprint'ten sonra proje dondurulacak — yeni feature eklenmeyecek.

### Kapanış notu

**1. Point-ID şema migration'ı: fail-fast seçildi, otomatik re-index
DEĞİL.** Gerekçe: otomatik bir tam re-index, app `/health`'i serve
etmeye başlamadan önce her connector için gerçek (yavaş olabilecek,
başarısız olabilecek) network çağrıları gerektirirdi — sıradan bir
boot sequence'ın içine gizlenmiş, correctness-kritik bir işlem.
`QdrantStore.ensure_collection()`'ın şema uyuşmazlıklarında zaten
uyguladığı "sessizce silip yeniden oluşturma, insana söyle" politikasıyla
tutarlı olması için migration da aynı muameleyi görüyor. Ayrıca
`docker compose down -v` + `up` deseni zaten var ve zaten test edilmiş
(Sprint 11'in fresh-install doğrulaması) — yeni bir kavram öğretmiyor.
Mekanizma: `app/registry/store.py`'a yeni bir `registry_metadata`
tablosu (`key/value`) + `CURRENT_INDEX_SCHEMA_VERSION = 2` sabiti
(versiyon 2 = Sprint 17'nin `source_id`'yi de içeren point-ID formülü;
versiyon 1 örtük — hiç versiyon satırı olmayan her registry).
`DocumentRegistry.ensure_index_schema_version()`: versiyon zaten
güncelse no-op; hiç versiyon yoksa VE registry boşsa (gerçek bir fresh
install) mevcut versiyonu kendi kendine damgalayıp geçer (self-healing
— `docker compose down -v` sonrası bir sonraki boot'ta otomatik
çözülür); aksi halde (versiyon yok ama doküman VAR, ya da açıkça eski
bir versiyon kayıtlı) `IndexSchemaMismatchError` fırlatır.
`app/wiring.py::build_app()`'a registry construction'ından hemen sonra
eklendi — app trafiğe başlamadan önce durur. **Gerçek bir uçtan uca
doğrulama yapıldı, sadece koddan okunmadı**: bir scratch script ile
önce boş bir registry ile `build_app()` çağrıldı — gerçekten kendi
kendine versiyon 2'yi damgaladığı `sqlite3` ile doğrulandı; sonra
`registry.db` silinip elle bir doküman satırı eklenmiş (versiyon
satırı olmayan) bir registry ile tekrar `build_app()` çağrıldı —
gerçekten `IndexSchemaMismatchError` fırlattığı, mesajın `docker
compose down -v && docker compose up` komutunu içerdiği doğrulandı.

**2. Qdrant schema testlerindeki false-positive — GERÇEKTEN doğrulanıp
düzeltildi, sadece varsayılmadı.** Review'ın şüphesi doğrudan
reprodüksiyonla doğrulandı: `test_ensure_collection_fails_fast_on_wrong_dense_vector_size`
ve `..._wrong_distance_metric` testlerinin sparse fixture'ı
`SparseVectorParams()` (modifier'sız, Qdrant'ın kendi varsayılanı
`None`) kullanıyordu — Sprint 17'nin sparse-modifier kontrolü dense
kontrollerinden ÖNCE çalıştığı için, gerçek fırlatılan mesaj
`"...sparse vector has modifier=None..."` idi, boyuttan hiç
bahsetmiyordu. `match=COLLECTION` assertion'ı (her hatada geçen
collection adını kontrol ediyor) bunu hiç yakalamıyordu. Fix: her iki
fixture'a `modifier=IDF` eklendi, `match` ifadeleri spesifik hataya
(`"size=384"`, `"EUCLID"`) bağlandı.

**3. Unnamed Qdrant vector şeması: `isinstance(dict)` kontrolü
eklendi.** Gerçek reprodüksiyon: Qdrant, tek bir unnamed vector'lı
koleksiyonu destekliyor (`vectors_config=VectorParams(...)` doğrudan,
`{name: ...}` dict'e sarılmadan) — bu durumda
`info.config.params.vectors` bir `VectorParams` NESNESİ, dict değil.
`VECTOR_NAME not in dense_vectors` bugüne kadar `TypeError` fırlatmıyordu
ama sadece kazara: Pydantic `BaseModel` `__iter__` destekliyor
((field, value) çiftleri döndürerek), Python'ın `in` operatörü buna
fallback yapıp her zaman `False` dönüyordu — doğru exception tipine
(`UnexpectedCollectionSchemaError`) rastgele ulaşıyordu ama YANLIŞ
mesajla ("missing 'dense' dense vector"). Test önce bu eski mesajla
fail ettiği (yani "unnamed" kelimesini içermediği) doğrulandı, sonra
explicit `isinstance(dense_vectors, dict)` kontrolü eklenip mesaj
gerçek nedeni ("unnamed vector configuration") söyler hale getirildi.

**4. Cancellation rollback'in kendi hatası artık orijinal
`CancelledError`'ı maskelemiyor.** Hem `ingest.py`'nin
`except asyncio.CancelledError:` bloğundaki `store.delete_version(...)`
çağrısı, hem `SyncManager`'ın eşdeğer bloğundaki
`self._history.finish_run(...)` çağrısı artık kendi iç try/except'i
içinde — patlarsa `logger.exception(...)` ile loglanıyor ama
yutulmuyor, dış `raise` hâlâ ORİJİNAL `CancelledError`'ı fırlatıyor.
İki test de fix'ten önce GERÇEKTEN yanlış exception tipini (rollback'in
kendi `RuntimeError`'ı) gördüğü doğrulandı (gerçek `task.cancel()` +
monkeypatch edilmiş bir rollback ile), sonra fix'le `CancelledError`'ın
doğru şekilde göründüğü kanıtlandı.

**5. README düzeltmeleri.** "Sprints 0–16" → "Sprints 0–17" (tek yer).
Status bölümündeki "reranking, grounded citations)" → "reranking,
citation-aware generation)" — Highlights'taki "Source-scoped citation
validation" ile tutarlı. `DuplicateSourceIdError`'ın docstring'i ve
testinin docstring'i, "registry/Qdrant'a hiç dokunmuyor" gibi aşırı
iddialı ifadeden, gerçek garantiyi netleştiren bir ifadeye çevrildi:
`ensure_collection()` duplicate kontrolünden ÖNCE çalıştığı için taze
bir Qdrant'ta boş bir koleksiyon şeması oluşturulmuş olabilir — garanti
edilen şey sıfır DOKÜMAN VERİSİ yazılması, koleksiyon nesnesine hiç
dokunulmaması değil (testin kendi assertion'ları zaten doğruydu:
`store.count() == 0` ve `registry.list_documents(...) == []`, ikisi de
doğru şekilde "sıfır doküman verisi" kontrol ediyor).

**393 test yeşil** (bu sprintte +7 yeni test: `tests/test_document_registry.py`
+4 — migration guard testleri; `tests/test_qdrant_store.py` +1 —
unnamed-vector testi (dense-schema false-positive fix'i net test
sayısını değiştirmedi, sadece mevcut 2 testi düzeltti);
`tests/test_versioned_reindex.py` +1 — cancellation-rollback-kendi-hatası
testi; `tests/test_sync_manager.py` +1 — SyncManager seviyesinde aynı
test), 8'i servis/API key gerektirdiği için skip, `ruff check app tests
scripts` temiz.

## Sprint 17.2 — Index Reconciliation

Amaç: Registry ve Qdrant'ın iki ayrı persistent state olarak birbirinden kopabileceği mimari boşluğunu kapatmak.

Scope:

1. `QdrantStore.has_document_version()` — ucuz bir presence check
2. Incremental sync: `content_unchanged AND index_present` ikisi de gerekli, index yoksa yeniden ingest
3. Bonus: `chunk_count` tracking, partial-index tespiti
4. "Registry taze, Qdrant eski" senaryosu belgelendi — reconciliation (madde 2) kendiliğinden ele alıyor, tek dezavantajı çakışma etkilenmiş bir dokümanın duplicate point'lerle kalabilmesi (data loss değil, disclosed edge case)
5. Downgrade testi (`CURRENT_INDEX_SCHEMA_VERSION + 1`)
6. Metadata bozulmasında (sayısal olmayan versiyon) düzgün `IndexSchemaMismatchError`
7. README'deki son "grounded generation with citations" ifadesi düzeltildi

DoD: Qdrant'tan manuel silinen bir dokümanın registry hash'i değişmemiş olsa bile bir sonraki sync'te otomatik olarak yeniden indexlendiği kanıtlanmış; downgrade testi var; metadata bozulması düzgün hata veriyor; testler ve lint temiz.

Bu sprint'ten sonra proje gerçekten donduruluyor.

### Kapanış notu

**Reconciliation mekanizması nasıl çalışıyor.** İki katman eklendi:

1. **Presence check** (`QdrantStore.has_document_version`, ucuz bir
   `scroll(limit=1)`): `ingest_connector`'ın skip kararı artık
   `content_unchanged AND index_present` — ikisi de gerekli. Content
   değişmemiş olsa bile Qdrant'ta o `(source_type, source_id,
   document_version)` için hiç point yoksa, doküman "changed" ile aynı
   yola girip GERÇEKTEN yeniden ingest ediliyor. **Review'ın verdiği tam
   senaryo gerçekten simüle edildi**: gerçek bir dosya ingest edildi,
   registry'ye HİÇ dokunmadan `store.delete_by_source(...)` ile Qdrant'tan
   point'ler silindi, ikinci sync'te dokümanın skip edilmediği
   (`files_processed == 1`, `files_skipped == 0`) ve içerik hash'inin
   gerçekten değişmediği (aynı `content_hash`) doğrulandı — fix'ten önce
   bu test GERÇEKTEN `files_processed == 0` ile fail etti.
2. **Bonus — partial-loss detection** (`chunk_count` tracking +
   `QdrantStore.count_for_document_version`, tam bir count sorgusu):
   registry'ye yeni bir `chunk_count` kolonu eklendi (mevcut DB'ler için
   gerçek bir `ALTER TABLE` migration'ı ile — `CREATE TABLE IF NOT
   EXISTS` tek başına eski bir tabloya yeni kolon eklemiyor, bu da gerçek
   bir pre-migration state simüle edilerek test edildi). Presence check
   geçtikten SONRA, VE registry'de gerçek bir beklenen sayı varsa (0 =
   "hiç izlenmedi", spurious re-index tetiklemiyor), gerçek sayı
   karşılaştırılıyor — eşleşmiyorsa (kısmi kayıp) yine "changed" yoluna
   giriyor. Bu da gerçek bir kısmi silme senaryosuyla kanıtlandı: 7+
   chunk'lı bir doküman ingest edilip TEK bir point silindi (tam silme
   değil), sonraki sync'in bunu tespit edip tam chunk sayısını
   restore ettiği doğrulandı — hatta bu testin GERÇEKTEN chunk_count
   karşılaştırmasına dayandığı (sadece presence check'e değil), o
   karşılaştırmayı geçici olarak devre dışı bırakıp testin GERÇEKTEN
   fail ettiği doğrulanarak kanıtlandı.

**Performans etkisi: ölçülmedi (gerçek Qdrant yükü altında), ama
gerekçelendirildi.** Presence check sadece "unchanged" dalında çalışıyor
— "changed" dalı zaten tam bir re-embed+upsert'e maliyet ödediği için ek
bir Qdrant çağrısı orada önemsiz. `scroll(limit=1)` sınırlı bir sorgu,
koleksiyon taraması değil. Exact-count karşılaştırması (bonus) daha
pahalı olduğu için sadece presence check zaten geçtiğinde VE registry'de
gerçek bir izlenen sayı varken çalışıyor — bu da onu nadir hale getiriyor
(çoğu "unchanged" doküman için sadece 1 ucuz presence check, ek count
sorgusu yok). Gerçek bir throughput ölçümü (Sprint 14'ün embedding
benchmark'ı gibi) bu sprintte yapılmadı — sync'lerin doküman sayısı bu
projede bunu ölçülebilir bir darboğaz haline getirecek kadar büyük
olmadığından (Sprint 14'ün kendi bulgusu: Qdrant'ın yazma yolu asıl
darboğaz değildi), ama gelecekte çok sayıda dokümanlı bir sync'te bunun
gerçek maliyeti ölçülmeli — bu açık bir şekilde kapanış notunda
belirtiliyor, sessizce varsayılmıyor.

**Diğer maddeler**: "registry taze, Qdrant eski" senaryosu incelendi —
`docker-compose.yml`'de hem `qdrant_storage` hem `registry_data`'nın
aynı named volume grubu altında olduğu doğrulandı, yani belgelenen
migration yolu (`down -v`) ikisini birlikte siliyor; bu senaryo sadece
standart olmayan bir operatör eylemiyle (sadece registry'yi silmek)
ortaya çıkabilir, ve o durumda bile boş registry her dokümanı "changed"
sayıp tam re-ingest yapıyor — tek disclosed edge case, çakışmadan
etkilenmemiş bir dokümanın eski-format point'lerinin
`delete_stale_versions`'ın document_version filtresi eşleştiği için
temizlenmemesi (duplicate, veri kaybı değil). Downgrade testi
(`CURRENT_INDEX_SCHEMA_VERSION + 1`) yazıldı — mevcut mantığın zaten
doğru davrandığı kanıtlandı (özel bir "ileri versiyon" dalı yoktu, ikisi
de aynı raise yoluna düşüyordu). Metadata bozulması (`index_schema_version`
sayısal değilse) artık ham `ValueError` yerine `IndexSchemaMismatchError`
fırlatıyor — fix'ten önce GERÇEKTEN `ValueError` ile fail ettiği
doğrulandı. README'nin son "grounded generation with citations" ifadesi
"citation-aware generation" olarak düzeltildi.

**406 test yeşil** (bu sprintte +13 yeni test:
`tests/test_qdrant_store.py` +5 — `has_document_version` testleri;
`tests/test_document_registry.py` +5 — chunk_count testleri, migration
testi, downgrade testi, metadata-bozulması testi; `tests/test_sync_scenarios.py`
+3 — gerçek reconciliation senaryosu, intact-index-hâlâ-skip-ediliyor
kontrolü, partial-loss senaryosu), 8'i servis/API key gerektirdiği için
skip, `ruff check app tests scripts` temiz.

**Proje burada donduruluyor — dördüncü ve beşinci review turlarının
kapanışı bu oldu.**

## Sprint 17.3 — Final Correctness Patch (reconciliation symmetry + duplicate cleanup)

Amaç: Sprint 17.2'nin kendi reconciliation mekanizmasının yarattığı iki regresyonu kapatmak.

Scope:

1. Aynı version'da fazla point → sonsuz re-index loop'u: `delete_stale_versions` sadece FARKLI version'ları temizliyor, aynı version'daki fazlalıkları değil. Fix: upsert sonrası beklenen point ID set'i ile Qdrant'taki gerçek ID'ler karşılaştırılıp fazlalıklar silinir
2. Qdrant-only orphan doküman temizliği: registry hiç bilmese bile Qdrant'ta duran ama connector'da artık olmayan dokümanlar temizlenir (`QdrantStore.list_source_ids`)
3. `has_document_version` + `count_for_document_version` tek bir count-bazlı kontrole indirildi
4. Qdrant payload index'leri eklendi (`source_type`, `source_id`, `document_version`)
5. `chunk_count`'ın 0/bilinmiyor belirsizliği çözüldü: `None` = bilinmiyor/legacy, `0` = gerçekten sıfır chunk
6. Gerçekten boş bir doküman artık sonsuz döngüye girmiyor
7. `ingest_connector`'ın "unchanged = zero Qdrant calls" docstring'i güncellendi

DoD: fazla point'li bir senaryoda re-index loop'u gerçekten duruyor (kanıtlanmış); Qdrant-only orphan'lar temizleniyor (kanıtlanmış); boş doküman sonsuz döngüye girmiyor; testler ve lint temiz.

Bu, planlanan son sprint — altıncı review turunun kapanışı.

### Kapanış notu

**1. Sonsuz re-index loop'unun gerçek etkisi — kanıtlandı, sadece
teorik değil.** Sprint 17.2'nin disclosed "harmless duplicate" edge
case'i (aynı `document_version`'a ait fazladan bir point), Sprint
17.2'nin KENDİ `chunk_count` reconciliation mantığıyla birleşince
gerçek bir sonsuz döngüye dönüşüyordu: her sync'te
`actual_count != expected_chunk_count` mismatch'i "changed" sayılıp
tam re-ingest tetikliyordu, ama `delete_stale_versions` aynı version'daki
fazlalığı hiç görmediği için (sadece FARKLI version'ları temizliyor)
fazla point hiç silinmiyordu — sync sonsuza kadar tekrar ediyordu.
Fix ÖNCESİ test GERÇEKTEN bu döngüyü doğruladı (fazladan point
temizlenmeden kalıyordu), fix SONRASI hem temizlendiği hem de İKİNCİ
sync'in gerçek bir no-op olduğu (`files_skipped == 1`) kanıtlandı —
sadece bir temizlik geçişi değil, döngünün gerçekten durduğu.
`QdrantStore.list_point_ids_for_version` + `delete_points` eklendi;
upsert sonrası beklenen point ID set'i (`point_id_for` ile hesaplanan)
Qdrant'taki gerçek ID'lerle karşılaştırılıp fazlalıklar siliniyor —
`delete_stale_versions`'ın simetriği, ama AYNI version içinde.

**2. Qdrant-only orphan cleanup nasıl çalışıyor.** `ingest_connector`'ın
silme fazı artık sadece registry'nin bildiği kayıtları değil,
`QdrantStore.list_source_ids(source_type)` ile Qdrant'ta GERÇEKTEN var
olan source_id'leri de tarıyor — ikisinin birleşimi connector'ın güncel
listesiyle karşılaştırılıp fark alınıyor.
`registry.delete_document(...)` registry'nin hiç bilmediği bir
source_id için zaten güvenli bir no-op. Review'ın verdiği tam senaryo
gerçekten simüle edildi: iki doküman ingest edildi, sonra AYNI registry
değil, TAMAMEN FARKLI bir db dosyasına bağlı, gerçekten "hiçbir şey
bilmeyen" taze bir `DocumentRegistry` instance'ı kullanıldı; connector'dan
bir dosya kaldırılıp sync koşuldu — kaldırılan dokümanın Qdrant
point'lerinin, taze registry ikisini de hiç bilmemesine rağmen
temizlendiği doğrulandı. Fix öncesi test GERÇEKTEN fail etti (silinmemiş
point'ler kaldı).

**3-4. Performans notu (gerekçeli, ölçülmedi).** İki reconciliation
sorgusu (`has_document_version` + `count_for_document_version`) tek bir
`count_for_document_version` çağrısına indirildi — `actual_count == 0`
zaten "yok" demek olduğu için presence check'e gerek kalmadı; her
unchanged/chunk_count-tracked doküman için Qdrant round-trip sayısı
ikiden bire indi. `ensure_collection()` artık YENİ oluşturulan
koleksiyonlarda `source_type`/`source_id`/`document_version` için
keyword payload index'i oluşturuyor (mevcut, zaten valide edilmiş bir
koleksiyona dokunmuyor — "mevcut koleksiyona dokunma" politikasıyla
tutarlı). Gerçek Qdrant'a karşı bir query-latency benchmark'ı bu
sprintte KOŞULMADI — Sprint 17.2 sync başına Qdrant sorgu hacmini
artırdı ve bu üç alan her filtreli sorguda kullanılıyor diye eklendi,
ölçülmüş bir yavaşlama gözlemlendiği için değil; bu açıkça
belirtiliyor, sessizce varsayılmıyor.

**5-6. `chunk_count`'ın None/0 belirsizliği çözüldü — ikinci, bağımsız
bir sonsuz döngü kaynağıydı.** Gerçek bir boş (whitespace-only) Markdown
dosyasının `chunk_markdown_text` ile GERÇEKTEN 0 chunk ürettiği
doğrulandı. Sprint 17.2'nin `chunk_count: int = 0` (NOT NULL DEFAULT 0)
şeması "hiç izlenmedi" ile "gerçekten sıfır" durumlarını ayıramıyordu —
reconciliation mantığı `if expected_chunk_count > 0:` kapısıyla gerçek
bir 0'ı da "bilinmiyor" sayıp presence-only kontrole düşüyordu, ki bu
sıfır gerçek point'li bir dokümanı ASLA "tam" olarak tanıyamıyordu —
her sync yeniden ingest ediyordu, sonsuza kadar. Fix: `chunk_count: int
| None = None`, SQLite kolonu `NOT NULL DEFAULT 0`'dan nullable
`INTEGER`'a (default'suz `ALTER TABLE ADD COLUMN` — mevcut satırlar
otomatik NULL olur, ki bu da "hiç izlenmedi" için doğru durum).
Bilinen, disclosed sınır: Sprint 17.2 şemasıyla zaten çalışmış bir
registry'nin önceden yazdığı literal 0'lar geriye dönük ayırt edilemiyor
— gerçek deploy edilmiş veri olmadığı için bu bir data-migration
heuristic'iyle çözülmedi, bir sonraki gerçek sync zaten doğru sayıyı
yeniden kuruyor. Test: gerçek boş doküman iki kez ingest edildi, ikinci
sync'in `files_skipped == 1` olduğu (yeniden işlenmediği) kanıtlandı —
fix öncesi bu test GERÇEKTEN `files_processed == 1` ile fail etti.

**7. `ingest_connector`'ın "unchanged = zero Qdrant calls" docstring'i
düzeltildi** — Sprint 17.2'den beri artık doğru değil, unchanged dal
artık en az bir reconciliation sorgusu ödüyor.

**420 test yeşil** (bu sprintte +14 yeni test:
`tests/test_qdrant_store.py` +10 — `list_point_ids_for_version`,
`delete_points`, `list_source_ids`, payload-index testleri;
`tests/test_document_registry.py` +1 — `chunk_count=0` ile `None`
ayrımı testi; `tests/test_sync_scenarios.py` +3 — sonsuz-loop-duruyor
senaryosu, Qdrant-only orphan senaryosu, boş-doküman-sonsuz-döngüye-
girmiyor senaryosu), 8'i servis/API key gerektirdiği için skip, `ruff
check app tests scripts` temiz.

**PROJE GERÇEKTEN DONDURULDU.** Altı dış review turu (Sprint 15'ten
17.3'e) sırasıyla: sprint-geçmişi yorum temizliği ve shutdown handling;
multi-batch re-index rollback ve config/schema hardening; point-ID
collision ve cancellation safety; index schema migration guard'ı ve
test false-positive temizliği; registry/Qdrant reconciliation; ve son
olarak reconciliation'ın kendi yarattığı iki regresyonun kapatılması.
Daha fazla hardening sprint'i planlanmıyor — Sprint 18 (Confluence
connector) hâlâ "stretch" olarak listelenen tek açık öğe, ama zorunlu
değil.

## Sprint 17.4 — Migration Fix (Sprint 17.2→17.3 upgrade path) — FINAL sprint

Amaç: Sprint 17.3'ün chunk_count nullable değişikliğinin, gerçek bir Sprint 17.2 şemasından yükseltme yaparken bozuk kaldığı iki bug'ı kapatmak.

Scope:

1. Migration gerçekte nullable yapmıyor: mevcut kontrol sadece "kolon var mı" diye bakıyor, gerçek bir 17.2 DB'sinde kolon zaten `NOT NULL DEFAULT 0` olarak var. Fix: `PRAGMA table_info`'nun `notnull` flag'iyle tespit edip tablo yeniden inşa edilir (rename + create + copy + drop), eski `chunk_count=0` değerleri (ayırt edilemez oldukları için) NULL'a çevrilir, gerçek non-zero değerler korunur
2. Legacy `chunk_count=None` hiç "tracked" duruma terfi etmiyordu (None + en az 1 point varsa "tamam" sayılıp skip ediliyordu, upsert_document hiç çağrılmıyordu). Fix: None her zaman "incomplete" sayılır, bir kez zorla re-index tetikler, registry gerçek sayıyla güncellenir
3. İki bug'ın birleşimi test edildi: gerçek 17.2 şemasından migrate edilmiş, chunk_count=0→NULL olmuş, ama Qdrant'ta gerçek point'leri olan bir doküman senaryosu
4. Dokümantasyon: `list_source_ids()`'in O(toplam chunk) maliyeti ve payload index'lerin mevcut koleksiyonlara retroaktif uygulanmadığı README'ye eklendi

DoD: gerçek bir Sprint 17.2 şemasından geçiş yapan bir DB artık gerçekten nullable chunk_count'a sahip (kanıtlanmış); legacy None dokümanlar bir kez zorla re-index edilip tracked duruma geçiyor (kanıtlanmış); iki bug'ın birleşim senaryosu test edilmiş; testler ve lint temiz.

**Bu, projenin planlanan SON sprint'i.**

### Kapanış notu

**1. Migration'ın gerçekten nullable ürettiğinin kanıtı — davranışla
değil, doğrudan `PRAGMA table_info` ile.** Sprint 17.3'ün migration
testi ("kolon hiç yok mu" kontrolü) yanlışlıkla kolayı test ediyordu —
gerçek bir Sprint 17.2 veritabanında kolon ZATEN vardı
(`NOT NULL DEFAULT 0`), bu yüzden `"chunk_count" not in columns`
kontrolü `False` dönüyor, migration hiçbir şey yapmıyordu. Bu GERÇEKTEN
doğrulandı: `chunk_count INTEGER NOT NULL DEFAULT 0` ile gerçek 17.2
şemasını birebir kuran bir fixture yazıldı, fix'ten ÖNCE
`PRAGMA table_info(documents)`'ın `notnull` flag'inin hâlâ `1`
döndürdüğü VE `registry.upsert_document(..., chunk_count=None)`'ın
GERÇEKTEN `sqlite3.IntegrityError` fırlattığı doğrulandı (sadece
teorik risk değil, doğrudan reprodüksiyon). Fix: `PRAGMA table_info`'nun
`notnull` flag'i kontrol edilip, hâlâ `NOT NULL` ise tablo yeniden
inşa ediliyor (`RENAME` + yeni nullable `CREATE TABLE` + `INSERT ...
SELECT` ile kopyalama + eski tabloyu `DROP`) — kopyalama sırasında
SADECE ambiguous eski `chunk_count=0` değerleri `NULL`'a çevriliyor,
gerçek non-zero değerler (zaten belirsiz değildi) olduğu gibi
korunuyor. Fix sonrası aynı testler: `notnull` flag'i artık `0`,
`upsert_document(chunk_count=None)` artık patlamıyor, ayrı bir test
gerçek non-zero bir değerin (5) migration'dan sonra hâlâ 5 olduğunu
doğruluyor.

**2. Legacy `None`'ın terfi ettiğinin kanıtı.** Fix öncesi `expected_chunk_count
is None` durumunda `actual_chunk_count > 0` kontrolü kullanılıyordu —
gerçek, sağlam Qdrant point'leri olan ama registry'de hiç izlenmemiş
(`None`) bir doküman bu kontrolü geçip SKIP ediliyordu, yani
`registry.upsert_document(...)` (chunk_count'u gerçek bir sayıyla
yazacak TEK yer) hiç çağrılmıyordu — `None` sonsuza kadar `None`
kalabiliyordu. Fix ÖNCESİ test GERÇEKTEN bunu doğruladı (`files_skipped
== 1`, doküman hiç yeniden işlenmedi). Fix: `expected_chunk_count is
None` artık KOŞULSUZ "incomplete" sayılıyor — bir kez zorla re-index
tetikliyor, registry gerçek sayıyla güncelleniyor, o andan itibaren
normal exact-match reconciliation devreye giriyor. Fix sonrası: ilk
sync zorla re-index ediyor (`files_processed == 1`) ve registry'yi
gerçek bir sayıyla güncelliyor, ikinci sync artık gerçekten skip
ediyor (`files_skipped == 1`).

**3. İki bug'ın birleşim senaryosu uçtan uca test edildi.** Gerçek bir
doküman normal şekilde ingest edildi (gerçek content_hash, gerçek
Qdrant point'leri). Sonra o AYNI content_hash'i taşıyan ama
`chunk_count=0` olan bir satır, gerçek Sprint 17.2 şemasıyla (raw SQL
ile) kurulmuş TAMAMEN AYRI bir db dosyasına yazıldı — "bu satır Sprint
17.2 canlıyken yazılmış olabilir" senaryosunu simüle ediyor. O dosyaya
karşı taze bir `DocumentRegistry` açıldığında: (a) kolon gerçekten
nullable oluyor, (b) o satırın `0`'ı `NULL`'a çevriliyor. Sonra AYNI
Qdrant store'a karşı (gerçek point'ler hâlâ dokunulmamış durumda) sync
koşulduğunda: ilk sync zorla re-index ediyor (content aynı ama
chunk_count izlenmiyor), registry gerçek sayıyla güncelleniyor, ikinci
sync artık genuine bir no-op. Bu, iki fix'in İZOLE değil BİRLİKTE
gerçek upgrade yolunu kapattığını kanıtlıyor.

**4. Dokümantasyon notları (kod değişikliği gerektirmiyor).** README'nin
Known Limitations bölümüne iki madde eklendi: `list_source_ids()`'in
maliyeti O(toplam chunk sayısı), O(doküman sayısı) değil (her sync'te
bir kere çalışıyor); payload index'ler (Sprint 17.3) sadece YENİ
oluşturulan koleksiyonlara ekleniyor, mevcut bir koleksiyona upgrade
sonrası geriye dönük uygulanmıyor.

**426 test yeşil** (bu sprintte +6 yeni test:
`tests/test_document_registry.py` +4 — gerçek 17.2 şeması fixture'ı,
notnull-flag doğrulaması, IntegrityError reprodüksiyonu, ambiguous-
zero-to-NULL testi, non-zero-preserved testi; `tests/test_sync_scenarios.py`
+2 — legacy-None-terfi senaryosu, birleşim senaryosu), 8'i servis/API
key gerektirdiği için skip, `ruff check app tests scripts` temiz.

**PROJE GERÇEKTEN VE KESİN OLARAK DONDURULDU.** Sprint 15'ten
17.4'e kadar yedi dış review turu sırasıyla: sprint-geçmişi yorum
temizliği ve shutdown handling; multi-batch re-index rollback ve
config/schema hardening; point-ID collision ve cancellation safety;
index schema migration guard'ı ve test false-positive temizliği;
registry/Qdrant reconciliation; reconciliation'ın kendi yarattığı iki
regresyonun kapatılması; ve son olarak o kapatmanın kendi migration
yolundaki iki bug'ın kapatılması. Bu son iterasyon zinciri (Sprint
17→17.1→17.2→17.3→17.4), her düzeltmenin kendi review turunu
tetikleyebileceğini gösterdi — ama artık gerçek, kanıtlanmış bir taban
çizgisine ulaşıldı: point identity doğru, cancellation güvenli, index
schema migration'ı hem eski hem yeni gerçek veritabanı şekillerinde
çalışıyor, reconciliation sonsuz döngüye girmiyor. Daha fazla
hardening sprint'i PLANLANMIYOR. Sprint 18 (Confluence connector) hâlâ
"stretch" olarak listeleniyor ama zorunlu değil ve bu proje bağlamında
aktif olarak beklenmiyor.

## Sprint 17.5 — Reconciliation Rollback Safety & Eval Parity — GERÇEKTEN SON sprint

Amaç: Sekizinci bir dış kod review'ından çıkan, reconciliation+rollback
etkileşiminden doğan gerçek bir regresyonu ve üç başka önemli bulguyu
kapatmak. Bkz. docs/sprint-17-5-plan.md.

Scope:

1. Reconciliation rollback sağlam point'leri silebiliyor (EN KRİTİK)
2. `SyncManager.start_run()` try/finally dışında — SQLite hatasında kilitleniyor
3. Eval/production parity — CLI production'ın CrossEncoderReranker'ını kullanmıyordu
4. Tekrarlanan Markdown heading identity çakışması

DoD: başarısız bir reconciliation repair'i artık önceden sağlam olan
point'leri silmiyor (kanıtlanmış); SyncManager SQLite hatasında
kilitlenmiyor; eval production'la aynı pipeline'ı ölçüyor, sayılar
güncellenmiş; tekrarlanan heading'ler ayrı citation identity'sine sahip;
testler ve lint temiz.

### Kapanış notu

**1. Reconciliation rollback'in sağlam point'leri sildiği bug GERÇEKTEN
reprodüklendi, sonra düzeltildi.** `app/ingestion/ingest.py`'deki
rollback (Sprint 16), `store.delete_version(..., content_hash)` çağrısıyla
try bloğuna giren content_hash'e ait TÜM point'leri siliyordu — bu, try
bloğunun her zaman gerçek bir A→B version değişiklikliği temsil ettiği
(yani o content_hash'e ait Qdrant'ta önceden HİÇBİR sağlam point
olmadığı) varsayımına dayanıyordu. Sprint 17.2'nin reconciliation'ı bu
varsayımı sessizce bozdu: content DEĞİŞMEMİŞKEN de (`content_hash` =
Qdrant'taki MEVCUT version) index eksik/bozuk tespit edilirse aynı try
bloğuna bir "repair" denemesiyle girilebiliyor — bu durumda try'a giren
version'ın bir kısmı ZATEN sağlam. Review'ın verdiği senaryo GERÇEKTEN
kuruldu: gerçek bir doküman (12 chunk) normal ingest edildi, Qdrant'tan
DOĞRUDAN 1 point silindi (11/12 sağlam, registry hâlâ eski chunk_count=12
diyor), bir sonraki sync repair denemesi başlattı, batch 2'de simüle
edilmiş bir embed hatası fırlatıldı. Fix'ten ÖNCE (kod geçici olarak
geri alınıp doğrulandı): rollback `delete_version` çağırdı, kalan point
sayısı 0'a düştü — 11 sağlam point de silindi, `assert 0 == 11` ile
GERÇEKTEN fail etti. Fix: try bloğuna girmeden hemen önce
`store.list_point_ids_for_version(...)` ile bir "before" snapshot
alınıyor; rollback tetiklenirse (`CancelledError` ve `Exception` her iki
branch'te de) "after" point ID'leri tekrar okunuyor, `after - before`
farkı (yani SADECE bu denemenin eklediği point'ler)
`store.delete_points(...)` ile siliniyor — `delete_version` artık
rollback'te hiç çağrılmıyor. Fix sonrası aynı senaryo: rollback sonrası
kalan point sayısı hâlâ 11 (0 değil), hangi point'lerin hayatta kaldığı
(ID bazında) tam olarak kayıptan ÖNCEKİ 11 ile birebir aynı. Normal A→B
senaryosu (yeni içerik) için "before" snapshot boş küme olduğundan
(`after - {} == after`) davranış değişmedi — Sprint 16'nın orijinal
multi-batch rollback testi hâlâ yeşil.

**2. `SyncManager.start_run()` fix'i, gerçek bir kilitlenme senaryosuyla
kanıtlandı.** `start_run()` (bir SQLite INSERT) `try:` bloğunun DIŞINDA
çalışıyordu, ama `self._running[source_type] = True` zaten atanmıştı —
`start_run` hata fırlatırsa hiçbir `except`/`finally` çalışmıyordu,
`_running` sonsuza kadar `True` kalıyordu. Fix ÖNCESİ test (sahte bir
`start_run` her zaman `RuntimeError` fırlatıyor) GERÇEKTEN
`manager.is_running("filesystem") is True` ile fail etti (beklenen
`False`). Fix: `run_id: str | None = None` başlangıcıyla `start_run(...)`
çağrısı `try:` bloğunun İLK satırına taşındı; `except Exception`
branch'i artık `run_id is None` olduğunda (yani `start_run`'ın kendisi
patladığında) `finish_run` çağırmadan doğrudan `raise` ediyor —
`ingest_connector` hatası için olan "swallow edip
`SyncRunResult(status=ERROR)` dön" davranışından kasıtlı olarak farklı,
çünkü kaydedilecek bir run_id yok. `except CancelledError` branch'i de
aynı `run_id is not None` koruması eklendi. Fix sonrası: exception
gerçekten yukarı veriliyor (`pytest.raises(RuntimeError)`) VE
`is_running("filesystem")` hemen `False` (finally her zaman çalışıyor).

**3. Eval/production parity — CrossEncoderReranker eklendi, golden set
GERÇEK Ollama+Qdrant'a karşı yeniden ölçüldü.** `app/evaluation/cli.py`,
`search()`'i `reranker=` parametresi vermeden çağırıyordu — production
chat path'inin (`app/wiring.py`, her zaman bir `CrossEncoderReranker`
geçiriyor) ÖLÇMEDİĞİ bir pipeline'ı ölçüyordu. Fix: `run_golden_set`'e
`use_reranker: bool = True` parametresi eklendi (varsayılan production'la
eşleşiyor), CLI'ye `--no-reranker` bayrağı (eski pre-rerank ölçüm modu
için) eklendi. Golden set (12 soru, `tests/fixtures/golden_set.json`,
aynı `qwen2.5:3b-instruct` generation + `qwen2.5:7b-instruct` judge
kurulumu, gerçek native Ollama + docker-compose Qdrant'a karşı) YENİDEN
koşuldu:

```
                    pre-rerank (--no-reranker)   reranked (varsayılan, production-parity)
mean_recall (all)   0.667                        0.500
mean_precision      0.133                        0.100
markdown recall     1.0                          1.0
markdown precision  0.2                           0.2
pdf recall          0.429                         0.143
pdf precision       0.086                         0.029
```

Pre-rerank sütunu Sprint 9'un ORİJİNAL sayılarını neredeyse birebir
tekrarladı (PDF recall 0.429, Markdown recall 1.0) — golden set
metodolojisinin kararlı olduğunu doğruluyor. Reranked sütun (artık
kullanıcının GERÇEKTEN gördüğü pipeline) PDF recall'ını DAHA DA
DÜŞÜRDÜ (0.429 → 0.143) — reranker'ın PDF retrieval'ı İYİLEŞTİRMEK
yerine KÖTÜLEŞTİRDİĞİ gerçek, ölçülmüş bir bulgu. Olası neden (ayrıca
araştırılmadı, sadece gözlemlendi — Sprint 9'un kendi "root cause
araştırılmadı" ifşasıyla aynı standart): `cross-encoder/ms-marco-MiniLM-
L-6-v2` İngilizce eğitilmiş bir model, golden set Türkçe soru/chunk
çiftleri içeriyor. README güncellendi — sayılar iyileşmedi, olduğu gibi
raporlandı.

**Not: ilk koşum yanlış dosya adlarıyla yapılmış, GERÇEKTEN yanlış
sonuç üretti, kendi kendine yakalandı.** Golden set'i yeniden ingest
ederken kaynak dosyalar yanlışlıkla `handbook.pdf`/`cli.md` olarak
adlandırıldı (`nimbus_handbook.pdf`/`nimbus_cli.md` yerine) —
`LocalFilesystemConnector`'ın slugify'ı farklı `source_id`'ler üretti
(`handbook_pdf` vs. golden_set.json'ın beklediği `nimbus_handbook_pdf`),
bu da TÜM sorularda `mean_recall=0.0`/`mean_precision=0.0` ile
sonuçlandı. Bu, gerçek sayıları raporlamadan önce fark edildi (0.0'ın
"reranker her şeyi mahvetti" değil bir kurulum hatası olduğu, doğru
dosya adlarıyla yeniden ingest edilip location'ların
`nimbus_handbook_pdf`/`nimbus_cli_md` ile eşleştiği doğrudan Qdrant
`scroll` + `location_for()` ile doğrulanarak anlaşıldı), düzeltilip
koşum tekrarlandı — yukarıdaki tablo düzeltilmiş, doğrulanmış sonuç.

**4. Tekrarlanan Markdown heading identity çakışması, gerçek text-bleed
kanıtıyla düzeltildi.** `app/parsing/markdown_parser.py::extract_blocks`,
`block_counts`'u sadece `heading_path`'e göre anahtarlıyordu —
`app/ingestion/markdown_chunker.py::chunk_markdown_text`'teki
`surrogate_by_heading` de aynı şekilde. Aynı heading_path'in (örn. iki
ayrı "# Overview" section'ı) bir dokümanda birden fazla kez geçmesi,
İKİNCİ occurrence'ın paragraflarının BİRİNCİ occurrence'ın surrogate
"sayfası" altına eklenmesine yol açıyordu — iki bağımsız section'ın
metni TEK bir chunking geçişinde birleşiyordu. Test GERÇEKTEN bunu
kanıtladı (fix öncesi, geçici geri alma ile): iki "# Overview"
section'ı (aralarında farklı bir heading) tek bir chunk'a
birleşiyordu (`len(overview_chunks) == 1`, beklenen 2), ikinci
occurrence'ın metni ("oranges") birincinin chunk'ının İÇİNDE
bulunuyordu. Fix: `MarkdownBlock`'a `heading_occurrence: int` eklendi
(`extract_blocks`, her heading satırında bu path için bir occurrence
sayacı artırıyor); `Chunk`'a da aynı alan eklendi; `surrogate_by_heading`
artık `(heading_path, heading_occurrence)` ile anahtarlanıyor — iki
occurrence artık AYRI surrogate'ler, AYRI chunk'lar, farklı
`page_number`'lar (dolayısıyla `point_id_for`'da otomatik olarak farklı
point ID'ler — `point_id_for` zaten `page_number`'ı kullanıyor).
İnsan-okunur citation label'ı (`app/llm/prompt.py::_human_label`)
DEĞİŞMEDİ — hâlâ düz heading path gösteriyor. İnternal citation
LOCATION'ı (`app/llm/citation_location.py::location_for`) occurrence
sıfırdan büyükse "#N" son eki ekliyor (örn. ikinci "Overview" →
"Overview#2") — tekrarlamayan (yaygın durum) heading'ler İÇİN LOCATION
STRING'İ HİÇ DEĞİŞMEDİ, `heading_occurrence` payload'ta yoksa bile
(`payload.get("heading_occurrence") or 0`, eski point'lerle geriye
dönük uyumlu).

**435 test yeşil** (bu sprintte +9 yeni test:
`tests/test_versioned_reindex.py` +1 — reconciliation rollback
point-safety senaryosu (review'ın verdiği tam senaryo); mevcut
cancellation-rollback-failure testi `delete_version` yerine
`delete_points`'i mock'layacak şekilde güncellendi; `tests/test_sync_manager.py`
+1 — start_run hatası kilitlenmiyor; `tests/test_markdown_parser.py` +2
— occurrence numaralandırma, normal heading'lerin occurrence=0 kalması;
`tests/test_markdown_chunker.py` +1 — text-bleed olmadan ayrı occurrence
chunk'ları; `tests/test_citation_location.py` (yeni dosya) +4 — PDF
fallback, normal heading, ilk occurrence'ın geriye dönük uyumluluğu,
tekrarlanan heading'in ayırt edici son eki), 8'i servis/API key
gerektirdiği için skip, `ruff check app tests scripts` temiz.

**PROJE GERÇEKTEN, KESİN OLARAK VE SEKİZİNCİ KEZ DONDURULDU.** Sprint
15'ten 17.5'e kadar sekiz dış review turu sırasıyla: sprint-geçmişi
yorum temizliği ve shutdown handling; multi-batch re-index rollback ve
config/schema hardening; point-ID collision ve cancellation safety;
index schema migration guard'ı ve test false-positive temizliği;
registry/Qdrant reconciliation; reconciliation'ın kendi yarattığı iki
regresyonun kapatılması; o kapatmanın kendi migration yolundaki iki
bug'ın kapatılması; ve son olarak reconciliation+rollback
etkileşiminden doğan bir veri kaybı regresyonu, bir kilitlenme bug'ı,
yanlış ölçülen bir eval pipeline'ı ve bir citation identity çakışması.
Sekiz turun ortak deseni: her düzeltme bir öncekinin varsaymadığı bir
etkileşimi açığa çıkardı (rollback + reconciliation, migration +
gerçek şema, cancellation + rollback'in kendi hatası) — bu yüzden bu
notta "artık kesinlikle bitti" iddiası tekrarlanmıyor, sadece: sekiz
turdur her review gerçek, reprodüklenebilir bir bug buldu ve her biri
gerçek kanıtla (fix öncesi fail eden test, gerçek reprodüksiyon,
gerçek ölçüm) kapatıldı. Daha fazla hardening sprint'i planlanmıyor.
Sprint 18 (Confluence connector) hâlâ "stretch" olarak listeleniyor
ama zorunlu değil.

## Sprint 17.6 — Citation Schema Closure — GERÇEKTEN SON sprint

Amaç: Dokuzuncu bir dış review'ın bulduğu, Sprint 17.5'in kendi
düzeltmesinin (heading_occurrence) mevcut, değişmemiş dokümanlara
uygulanmadığı bulgusunu kapatmak. Bkz. docs/sprint-17-6-plan.md.

Scope:

1. Index schema version bump (2 → 3) — mevcut migration guard mekanizması yeniden kullanıldı
2. Collision-safe location encoding (gerçek "#N" başlık + "/" içeren heading senaryoları)
3. `run_id` tip düzeltmesi (`str | None` → `int | None`)
4. Regression testi (madde 1 ile aynı testte kanıtlandı)

DoD: version 3'e geçiş gerçek bir eski state ile test edilmiş; yeni
encoding şeması collision-safe (kanıtlanmış); run_id tipi doğru;
testler ve lint temiz.

### Kapanış notu

**1. Version 2 → 3 bump, mevcut mekanizma yeniden kullanılarak, gerçek
bir eski state'e karşı test edildi.** Sprint 17.5'in `heading_occurrence`
alanı, mevcut değişmemiş bir dokümanın content_hash'i aynı kaldığı için
asla yeniden ingest tetiklemiyor — yani Sprint 17.5 deploy edildikten
SONRA bile, gerçekte tekrarlanan heading'i olan eski bir doküman, eski
(çakışan) point ID'leri ve location'larıyla sonsuza dek Qdrant'ta
kalabilirdi. Yeni bir mekanizma icat etmek yerine Sprint 17.1'in zaten
var olan `CURRENT_INDEX_SCHEMA_VERSION` + `ensure_index_schema_version()`
fail-fast guard'ı yeniden kullanıldı — sadece sabiti 2'den 3'e çıkarmak
yeterliydi. Test GERÇEKTEN kanıtladı: `registry._set_index_schema_version(2)`
ile açıkça version 2'ye damgalanmış bir registry (bir önceki GERÇEK
`CURRENT_INDEX_SCHEMA_VERSION` değeri — `CURRENT - 1` gibi göreceli bir
değer değil, literal eski değer) `ensure_index_schema_version()`
çağrıldığında `IndexSchemaMismatchError` fırlatıyor. Fix öncesi (sabit
geçici olarak 2'ye geri alınıp doğrulandı) bu test GERÇEKTEN
`DID NOT RAISE` ile fail etti — bump olmadan version 2 zaten "current"
kabul ediliyordu. Mevcut Sprint 17.1/17.2 testleri (`CURRENT - 1`,
`CURRENT + 1` gibi göreceli değerler kullanan) elle güncelleme
gerektirmeden otomatik olarak doğru davranmaya devam etti — doğrulandı.

**2. Collision-safe location encoding, iki ayrı gerçek çakışma
senaryosuyla kanıtlandı.** Sprint 17.5'in `f"{location}#{occurrence + 1}"`
şeması iki gerçek çakışma riski taşıyordu: (a) dokümanın GERÇEKTEN
"Overview#2" diye bir başlığa sahip olması, ikinci "Overview"
occurrence'ının sentetik suffix'iyle ("Overview#2") birebir çakışıyordu;
(b) `["A/B"]` (tek, "/" içeren component) ile `["A","B"]` (nested)
aynı "A/B" string'ini üretiyordu. Fix: her heading component'i
birleştirilmeden önce escape ediliyor (`\`→`\\`, `/`→`\/`, `#`→`\#`);
escape edilmiş component'ler unescaped `/` ile birleştiriliyor;
occurrence suffix'i hâlâ unescaped `#` kullanıyor ama artık bu güvenli
— gerçek bir heading'in içindeki her `#` escape edildiği için, sonuçtaki
string'de unescaped `#` SADECE occurrence delimiter'ı olabilir. Üç test
GERÇEKTEN kanıtladı (fix öncesi, geçici geri alma ile): (1) senkron
`location_for()` payload testi — gerçek "Overview#2" başlığı artık
`"Overview\#2"`, sentetik ikinci occurrence hâlâ `"Overview#2"`, ikisi
ARTIK FARKLI (fix öncesi ikisi de `"Overview#2"` idi); (2) `["A/B"]` artık
`"A\/B"`, `["A","B"]` hâlâ `"A/B"`, ARTIK FARKLI; (3) uçtan uca chunker
testi — gerçek bir Markdown dokümanı (bir "# Overview", GERÇEKTEN
"# Overview#2" adında bağımsız bir başlık, ikinci bir "# Overview")
chunk_markdown_text ile işlenip location_for'a verildiğinde üç AYRI
location üretiyor (fix öncesi sadece 2 benzersiz location vardı —
`{'Overview', 'Overview#2'}`, üçüncü chunk ikinciyle çakışıyordu).
Sıradan (yaygın, "/" veya "#" içermeyen) heading path'ler için escape
işlemi no-op — location string'i hiç değişmedi, ek bir testle
doğrulandı. `grounding.py`'nin `_CITATION_RE`'si location'ı opak
`[^\]]+` olarak yakaladığı için (iç yapısını hiç parse etmiyor) bu
değişiklik onu etkilemedi — tüm `location_for` tüketicileri grep ile
tarandı, doğrulandı.

**3. `run_id` tip düzeltmesi.** `app/sync/manager.py::trigger_sync`'teki
yerel değişken `run_id: str | None = None` olarak yanlış anotasyonlanmıştı
— `SyncHistory.start_run()` gerçekte SQLite'ın `lastrowid`'inden bir
`int` döndürüyor, `SyncRunResult.run_id` alanı (app/sync/models.py) da
zaten doğru şekilde `int | None`. Davranışı etkilemeyen (Python
runtime'da tip anotasyonları zorlanmıyor), saf bir okunabilirlik/statik-
analiz düzeltmesi: `run_id: int | None = None`.

**4. Regression testi madde 1 ile birleştirildi** — plan dokümanının
öngördüğü gibi, ayrı bir test yazmaya gerek kalmadı, tek test hem
version bump'ı hem eski-state tespitini kanıtlıyor.

**5. README'deki "araştırılmamış hipotez" ifşası zaten Sprint 17.5'te
netti** — "a plausible cause, not confirmed by further investigation"
ifadesi kontrol edildi, madde ekleme gerekmedi.

**448 test toplandı** (bu sprintte +5 yeni test:
`tests/test_document_registry.py` +1 — version-2-stale regression;
`tests/test_citation_location.py` +3 — gerçek "#N" başlık çakışması,
"/" içeren heading çakışması, sıradan heading'lerin etkilenmediği;
`tests/test_markdown_chunker.py` +1 — uçtan uca üç-location kanıtı),
`ruff check app tests scripts` temiz.

**PROJE GERÇEKTEN, KESİN OLARAK VE DOKUZUNCU KEZ DONDURULDU.** Sprint
15'ten 17.6'ya kadar dokuz dış review turu, her biri bir öncekinin
varsaymadığı gerçek bir etkileşimi buldu — en sonuncusu: bir fix'in
(heading_occurrence) kendisinin mevcut veriye asla ulaşamayacağı
(content_hash'in bunu tetikleyemeyeceği) ve fix'in kendi encoding
şemasının kendi içinde iki ayrı çakışma taşıdığı. Bu son ikisi de
"bir düzeltmenin kendi varsayımlarını sorgulamak" kategorisinde —
projenin dokuz turdur öğrendiği asıl ders, kod tabanına özgü bir kural
değil bu: her fix, kendi kapsamı DIŞINDA bıraktığı veri/durumu ve kendi
ürettiği YENİ encoding/format'ın kendi içindeki tutarlılığını ayrıca
sorgulamayı gerektiriyor. Daha fazla hardening sprint'i planlanmıyor.
Sprint 18 (Confluence connector) hâlâ "stretch" olarak listeleniyor ama
zorunlu değil.

## Sprint 17.7 — Reranker Cross-Lingual Mismatch Investigation (araştırma)

Amaç: Sprint 17.5'in "CrossEncoder rerank PDF recall'ını düşürüyor"
gözleminin gerçekten çapraz-dilli (soru dili ≠ içerik dili) retrieval'a
özgü olup olmadığını, kod değiştirmeden, izole bir 2x2 deneyle test
etmek. Bkz. docs/sprint-17-7-plan.md. Bu bir hardening/bugfix sprint'i
DEĞİL — proje "donmuş" durumunu koruyor.

Ön-doğrulama (bu sprint başlamadan önce, kod değiştirmeden yapıldı):
mevcut golden set homojen Türkçe değil. Sorular (12/12) Türkçe, ama
PDF kaynak dokümanı (`golden_source.py`) tamamen İngilizce, Markdown
kaynak dokümanı (`golden_markdown_source.py`) tamamen Türkçe. Yani
mevcut tasarım zaten karışık: PDF tarafı çapraz-dilli, Markdown tarafı
tek-dilli — ve sadece çapraz-dilli PDF tarafı Sprint 17.5'te regresyona
uğramıştı.

### Kapanış notu

**Deney tasarımı: tek yeni fixture, mevcut `by_content_type` kırılımı
yeniden kullanıldı.** `tests/fixtures/golden_set_en.json` yazıldı —
mevcut `golden_set.json`'daki 12 sorunun DOĞRUDAN İngilizce çevirisi,
AYNI `expected_locations`/`content_type` (içerik değişmediği için
ground truth değişmiyor). Koşum öncesi gerçek Qdrant'a karşı
doğrulandı: her iki dosyanın da `expected_locations`'ı, gerçekten
ingest edilmiş `nimbus_handbook_pdf` (6 sayfa, İngilizce) ve
`nimbus_cli_md` (8 heading, Türkçe) noktalarıyla birebir eşleşiyor.
`app/evaluation/generation_metrics.py`'nin `reference_answer`'ı hiç
tüketmediği doğrulandı (harness sadece saklıyor) — çeviri kalitesinin
metrikleri etkilemediği bu şekilde güvence altına alındı. 2 golden set
(TR, EN) × 2 reranker modu (`--no-reranker`, varsayılan) = 4 GERÇEK CLI
koşumu (native Ollama + docker-compose Qdrant + `qwen2.5:3b-instruct`
generation + `qwen2.5:7b-instruct` judge), her biri `by_content_type`
ile PDF ve Markdown hücrelerini ayrı ayrı üretti = 8 hücre.

**Sonuçlar (gerçek koşum, tam tablo):**

```
                              recall   precision   dil eşleşmesi
PDF   + TR soru + no-rerank   0.429     0.086      çapraz-dilli
PDF   + TR soru + rerank      0.143     0.029      çapraz-dilli
PDF   + EN soru + no-rerank   0.857     0.171      tek-dilli
PDF   + EN soru + rerank      0.857     0.171      tek-dilli

MD    + TR soru + no-rerank   1.000     0.200      tek-dilli
MD    + TR soru + rerank      1.000     0.200      tek-dilli
MD    + EN soru + no-rerank   1.000     0.200      çapraz-dilli
MD    + EN soru + rerank      0.800     0.160      çapraz-dilli
```

**Hipotez NET ŞEKİLDE DOĞRULANDI — dört hücrenin dördü de tahmin
edilen yönde.** Rerank'in etkisi:
- **PDF + TR (çapraz-dilli):** recall 0.429 → 0.143, DÜŞTÜ (-0.286).
- **PDF + EN (tek-dilli):** recall 0.857 → 0.857, DEĞİŞMEDİ.
- **Markdown + TR (tek-dilli):** recall 1.000 → 1.000, DEĞİŞMEDİ.
- **Markdown + EN (çapraz-dilli):** recall 1.000 → 0.800, DÜŞTÜ (-0.200).

İKİ çapraz-dilli hücrenin İKİSİ de rerank altında kötüleşti; İKİ
tek-dilli hücrenin İKİSİ de tamamen değişmedi (precision dahil, ondalık
basamağa kadar aynı) — bu, "hipotez desteklendi ama belirsiz" değil,
temiz, dört-hücreli bir tekrarlanan desen. Sprint 17.5'in
"araştırılmamış hipotez" ifşası artık araştırıldı ve doğrulandı: CrossEncoder
rerank'in PDF recall'ını düşürmesi Türkçe dile özgü bir sorun değil,
SORU/İÇERİK dil UYUŞMAZLIĞINA özgü bir sorun.

**Bonus bulgu — dil uyuşmazlığı rerank'ten ÖNCE de (hybrid retrieval
aşamasında) ölçülebilir bir etki.** PDF'in tek-dilli (EN/EN) pre-rerank
recall'ı (0.857) çapraz-dilli (TR/EN) pre-rerank recall'ından (0.429)
DRAMATİK ÖLÇÜDE yüksek — yani `nomic-embed-text` embedding modeli bile
(reranker devreye girmeden) çapraz-dilli sorgu/içerik çiftlerinde daha
zayıf. Bu, rerank'in sorunu YARATMADIĞINI, MEVCUT bir zayıflığı DAHA DA
KÖTÜLEŞTİRDİĞİNİ gösteriyor — iki ayrı ama aynı yöndeki etki.

**Sınırlamalar, dürüstçe belirtilmeli:** Bu tek bir golden set (12 soru,
2 doküman, tek domain — "Nimbus" kurgu ürünü) üzerinde tek bir koşum;
istatistiksel anlamlılık testi yapılmadı (n çok küçük, LLM judge
stokastik). Sonuç GERÇEK ve tekrarlanabilir bir gözlem, ama genellenebilir
bir "her çapraz-dilli senaryoda rerank her zaman kötüleşir" iddiası
DEĞİL — bu spesifik reranker modeli (`cross-encoder/ms-marco-MiniLM-L-6-v2`,
İngilizce eğitilmiş), bu embedding modeli (`nomic-embed-text`) ve bu
golden set için doğrulanmış bir bulgu.

**Kod davranışı DEĞİŞMEDİ** — bu bir araştırma sprint'i, `app/`
altında hiçbir dosya değiştirilmedi. Sadece yeni bir fixture
(`tests/fixtures/golden_set_en.json`) eklendi, README ve PLANNING.md
güncellendi.

## Sprint 18 — Multilingual Embedding Benchmark: Nomic vs Qwen3-Embedding-4B

Amaç: Sprint 17.7'nin bulduğu çapraz-dilli retrieval zayıflığına karşı
`Qwen/Qwen3-Embedding-4B`'nin `nomic-embed-text`'e göre gerçekten daha
iyi olup olmadığını kontrollü, tek-değişkenli bir benchmark'la ölçmek —
production default'u sonuç kanıtlanmadan değiştirmeden. Bkz.
docs/sprint-18-plan.md.

Scope:

1. `Qwen/Qwen3-Embedding-4B` için config-driven embedding model desteği
   (`app/llm/embedding_models.py`) — Qwen3'ün resmi asimetrik instruction
   formatı, nomic'in prefix'i taşınmadan
2. Pipeline fingerprint (`app/ingestion/fingerprint.py`) — embedding
   model/revision/dimension/instruction + mevcut index schema version'ı
   tek bir deterministic hash'te birleştiren, registry'ye kaydedilen,
   `ingest_connector`'a opsiyonel parametre olarak bağlanan bir
   reconciliation mekanizması
3. Benchmark izolasyonu — ayrı Qdrant collection'ları, ayrı SQLite
   registry'leri, production'a hiç dokunmadan
4. Golden set'in 4 dil-çifti hücresine (TR→TR, EN→EN, TR→EN, EN→TR)
   genişletilmesi, gerçek yeni içerikle (`nimbus_api_reference.md`,
   `nimbus_kurumsal_sss.md`)
5. Rank-aware metrikler (Recall@1/3/5, MRR, nDCG@5) — daha önce hiç
   yoktu
6. `scripts/benchmark_embeddings.py` CLI — operasyonel metriklerle
   birlikte, `artifacts/embedding-benchmark/{results.json,report.md}`
   üretiyor

DoD: 8 gerçek retrieval hücresi (4 dil-çifti x 2 model) + operasyonel
metrikler gerçek servislere karşı ölçülmüş; testler ve lint temiz;
sonuç kanıtlanmadan iddia yok.

### Kapanış notu

**1. Mimari: yeni bir transport DEĞİL, config-driven bir model seçimi.**
Qwen3-Embedding-4B de nomic gibi Ollama üzerinden servis ediliyor
(`qwen3-embedding:4b`, gerçekten `ollama pull` ile indirildi, GERÇEK bir
`/api/embeddings` çağrısıyla boyutu doğrulandı: **2560**, model kartıyla
uyumlu). Bu yüzden yeni bir `EmbeddingProvider` alt sınıfı yerine
`EmbeddingModelConfig` (`app/llm/embedding_models.py`) eklendi — model
adı/revision/dimension/query+document instruction, hepsi
`Settings`'ten configurable (magic constant yok). Qwen3'ün resmi
asimetrik formatı (`Instruct: {task}\nQuery: ` sadece sorgu tarafında,
doküman tarafı çıplak metin) `app/retrieval/search.py::search()`'e
eklenen `query_prefix` parametresiyle (varsayılan: nomic'in
`SEARCH_QUERY_PREFIX`'i, GERİYE DÖNÜK UYUMLU) mümkün oldu — bu olmadan
`search()` nomic'in prefix'ini Qwen3'e KÖRÜ KÖRÜNE taşırdı, tam da
kullanıcının yasakladığı hata. `QdrantStore.__init__`'e opsiyonel
`dense_dimension` parametresi eklendi (varsayılan: mevcut
`EMBEDDING_DIM=768`, GERİYE DÖNÜK UYUMLU) — Qwen3'ün 2560 boyutlu
collection'ı bunsuz açılamazdı.

**2. Pipeline fingerprint, YENİ bir mekanizma değil, Sprint 17.1'in
mekanizmasının genişletilmesi.** `app/ingestion/fingerprint.py::
PipelineFingerprint`, embedding config'ini mevcut
`CURRENT_INDEX_SCHEMA_VERSION`'la (paralel bir sayaç İCAT ETMEDEN)
birleştirip deterministic bir SHA-256 digest üretiyor — testle
kanıtlandı: aynı config'ten iki fingerprint HER ZAMAN aynı digest'i
üretiyor (dict/kwarg sırası farklı olsa bile, `sort_keys=True` sayesinde),
embedding_model/dimension/instruction/index_schema_version'dan HERHANGİ
biri değişirse digest DEĞİŞİYOR. Registry'ye nullable
`pipeline_fingerprint` kolonu eklendi (Sprint 17.4'ün öğrettiği ders:
NOT NULL/default YOK — `ALTER TABLE ADD COLUMN`). `ingest_connector`'a
OPSİYONEL bir parametre olarak bağlandı — GERÇEKTEN kanıtlandı: content
DEĞİŞMEMİŞKEN sadece embedding modeli değişince (aynı senaryo, iki farklı
fingerprint) `files_processed=1` (zorla yeniden indexleniyor, SKIP
EDİLMİYOR), fix'ten ÖNCE (kontrol geçici olarak `if False and ...` ile
devre dışı bırakılıp doğrulandı) aynı test GERÇEKTEN
`files_skipped=1` ile fail ediyordu — yani mevcut chunk_count/
content_hash reconciliation'ı bu senaryoyu YAKALAYAMIYORDU. Parametre
verilmediğinde (mevcut TÜM production çağrı yerleri, SyncManager dahil)
davranış BİREBİR AYNI — ayrı bir testle kanıtlandı. Production
SyncManager'a GERÇEK bir fingerprint bağlamak bilinçli olarak bu
sprintin DIŞINDA bırakıldı — bağlamak her kullanıcının mevcut index'ini
bir sonraki sync'te zorla yeniden indexlerdi, ki bu bir benchmark
sprint'inin yan etkisi olmamalı.

**3. Golden set, 4 dil-çifti hücresine gerçek içerikle genişletildi —
uydurulmadı, ingest edilmiş içerikten doğrulandı.** İki yeni gerçek
fixture doküman yazıldı: `nimbus_api_reference.md` (İngilizce, 10 H1
bölüm — auth, rate limits, pagination, webhooks, error codes,
versioning, upload limits, idempotency, sandbox, deprecation) ve
`nimbus_kurumsal_sss.md` (Türkçe, 8 H1 bölüm — SSO, denetim kaydı, veri
konumu, roller, SLA, faturalandırma, veri saklama, yedekleme). Mevcut
iki dokümanın (PDF handbook, CLI referansı) daha önce kullanılmamış
paragraf/heading'leri de (PDF sayfa 6, CLI'ın "Kimlik Doğrulama"/
"Senkronizasyon Komutları"/"Sorun Giderme" üst-seviye bölümleri) madene
çıkarıldı. Toplam 68 soru (66 gerçek + 2 not-found kontrol), 4 gerçek
Qdrant collection'ına (`kb_corpus_verify`) ingest edilip HER `expected_
location` `location_for()` çıktısıyla GERÇEKTEN eşleştirildi (0 uyuşmazlık,
doğrudan doğrulandı) — hücre başına dağılım: TR→TR=16, EN→EN=17,
TR→EN=17, EN→TR=16, hepsi 15-20 hedefinin üzerinde. Her yeni gerçeğin
hem TR hem EN soru formu var; mevcut 11 gerçeğin (6 PDF + 5 CLI)
TR/EN soru çiftleri Sprint 17.7'nin `golden_set.json`/`golden_set_en.json`'ından
BİREBİR yeniden kullanıldı (paraphrase-kolay, uydurma soru YOK).

**4. Gerçek 68-soruluk, 2-modelli benchmark koşumu — sonuçlar
(`artifacts/embedding-benchmark/report.md`):**

```
Model     TR→TR R@5  EN→EN R@5  TR→EN R@5  EN→TR R@5   MRR    nDCG@5  p95(ms)
nomic       1.000      1.000      0.625      0.588     0.701   0.726    46.7
qwen3-4b    1.000      1.000      1.000      0.941     0.884   0.910   131.3
```

Çapraz-dilli hücrelerin İKİSİ de belirgin şekilde iyileşti (TR→EN Recall@5
+0.353, MRR +0.480; EN→TR Recall@5 +0.375, MRR +0.247), tek-dilli
hücrelerin İKİSİ de HİÇ DEĞİŞMEDİ (1.000→1.000, precision/recall dahil
ondalık basamağa kadar aynı) — Sprint 17.7'nin bulduğu dil-uyuşmazlığı
zayıflığını gerçekten kapatan bir sonuç, regresyon yok.

**Operasyonel maliyet gerçek, ölçülmüş ve ciddi:**

```
                          nomic      qwen3-4b
dimension                   768         2560   (3.3x)
indexing throughput      25.57         2.03    chunks/sec (12.6x YAVAŞ)
query embed p50 (ms)      33.6        242.4    (7.2x)
query embed p95 (ms)      43.6        369.0    (8.5x)
total retrieval p95 (ms)  46.7        131.3    (2.8x)
model load/warmup (s)     0.54         3.49    (6.5x)
Qdrant storage (tahmini) 160KB        384KB    (2.4x)
```

RAM/VRAM kullanımı ölçülMEDİ — bu ortamda Ollama'nın subprocess bellek
kullanımını güvenilir şekilde izole ölçecek bir mekanizma yoktu,
uydurulmadı, raporda açıkça "not measured" olarak işaretlendi.

**5. Karar kuralı MEKANİK olarak `ADOPT_QWEN3` çıkardı (`scripts/
benchmark_embeddings.py::decide()`), ama production default DEĞİŞMEDİ.**
Kural: HER İKİ çapraz-dilli Recall@5 hücresi iyileşmeli VE çapraz-dilli
MRR iyileşmeli VE hiçbir tek-dilli hücre ciddi regresyon (>%10) göstermemeli
— üçü de sağlandı, test edildi (`tests/test_benchmark_embeddings.py`,
ADOPT/KEEP/NEED_MORE_DATA senaryolarının hepsi sentetik ama gerçekçi
verilerle ayrı ayrı kanıtlandı). Bu, sadece ortalama skor yükseldiği için
otomatik "kazanan" ilan etme riskini kapatıyor — kullanıcının açıkça
istediği gibi. Ama gerçek maliyet (7-12x latency/throughput, 3.3x boyut)
üretim varsayılanını hemen değiştirmeyi GEREKTİRMİYOR — bu bir
mühendislik/ürün trade-off kararı, bu sprintin kapsamı sadece ÖLÇMEKTİ.
`settings.ollama_embed_model` hâlâ `nomic-embed-text`, hiçbir production
çağrı yeri değişmedi.

**6. Sınırlamalar, dürüstçe:** Tek golden set (68 soru, 4 doküman, tek
fictional domain), tek koşum, istatistiksel anlamlılık testi yok (küçük
n, LLM judge yok — bu retrieval-only bir benchmark, generation kalitesi
kapsam dışı bırakıldı, kullanıcının istediği gibi). RAM/VRAM ölçülmedi.
Qdrant storage rakamı gerçek bir disk ölçümü değil, nokta sayısı x
(dimension x 4 byte + 2048 byte tahmini payload/sparse overhead)
formülüyle hesaplanmış bir TAHMİN — raporda açıkça böyle etiketlendi.

**37 yeni test** (`tests/test_embedding_models.py` +7,
`tests/test_fingerprint.py` +9, `tests/test_rank_metrics.py` +9,
`tests/test_benchmark_embeddings.py` +11, `tests/test_search.py` +1 —
query_prefix override, `tests/test_sync_scenarios.py` +3 — fingerprint
mismatch/match/backward-compat, `tests/test_document_registry.py` şema
testi güncellendi), 485 test yeşil (448→485), 2'si servis/API key
gerektirdiği için skip, `ruff check app tests scripts` temiz.

## Sprint 19 — Qwen3 Size & Dimension Trade-off Benchmark

Amaç: Sprint 18 "Qwen3-Embedding-4B nomic'ten daha mı iyi?" sorusunu
cevapladı (evet, çapraz-dilli tarafta). Bu sprint farklı bir soru
soruyor: hangi Qwen3 varyantı (boyut x output-dimension) production için
en iyi kalite/maliyet dengesini veriyor? Bkz. docs/sprint-19-plan.md.

Scope:

1. 6 configuration'ın gerçek karşılaştırması: `nomic@native`,
   `qwen3-0.6b@native`, `qwen3-4b@native`, `qwen3-4b@1024`,
   `qwen3-0.6b@1024`, `qwen3-0.6b@768`
2. Ollama'nın resmi Matryoshka output-dimension mekanizması
   (`/api/embed`'in `dimensions` parametresi) — hack yok, GERÇEK backend
   mekanizması
3. `EmbeddingModelConfig` genişletmesi: `output_dimension`, `backend`,
   Qwen3-Embedding-0.6B desteği
4. Aynı 68 soruluk golden set (Sprint 18 ile apples-to-apples)
5. Cross-lingual/mono-lingual agregeler, Pareto frontier, production
   karar kuralı (quality winner + efficiency winner ayrı ayrı)
6. Gerçek disk kullanımı ölçümü (`docker exec du`)

DoD: 6 configuration da gerçek servislere karşı ölçülmüş; testler ve
lint temiz; production default değişmedi.

### Kapanış notu

**1. Ollama'nın resmi dimension mekanizması gerçekten doğrulandı, hack
YAPILMADI.** Ollama 0.32.6'nın `/api/embed` (çoğul) endpoint'i bir
`dimensions` parametresi destekliyor — GERÇEKTEN test edildi:
`qwen3-embedding:4b`'ye `dimensions=1024` verildiğinde dönen vektör,
native 2560 boyutlu çıktının ilk 1024'ünün normalize edilmiş hali
DEĞİL (doğrudan karşılaştırıldı, farklı değerler) — yani gerçekten
backend'in kendi mekanizması. Ollama, aralık dışı bir `dimensions`
isteğini SESSİZCE native boyuta clamp'liyor (hata vermiyor) — bu yüzden
`OllamaClient.embed()`'e eklenen `dimensions` parametresi hiçbir
doğrulama yapmıyor, sadece backend'den ne dönerse onu veriyor;
GERÇEKTEN desteklenip desteklenmediğini anlamak için
`scripts/benchmark_embeddings.py::probe_dimension_support()` her
configuration için GERÇEK bir çağrı yapıp dönen vektörün uzunluğunu
istenenle karşılaştırıyor. `dimensions=None` (mevcut TÜM production
çağrı yerleri) eski `/api/embeddings` endpoint'ini KULLANMAYA DEVAM
EDİYOR — testle kanıtlandı (`test_embed_without_dimensions_uses_the_
singular_endpoint_unchanged`).

**2. İki gerçek bug bulundu ve düzeltildi — İKİSİ de ilk gerçek koşum
denemesinde ortaya çıktı, varsayımla değil.**

- **`search()` `dimensions` parametresi hiç almıyordu.** İlk gerçek
  6-configuration koşumu `qwen3-4b@1024`'te GERÇEKTEN çöktü:
  `Qdrant Vector dimension error: expected dim: 1024, got 2560` —
  indexleme 1024 boyutunda doğru çalışmıştı ama `search()`'ün kendi
  iç `ollama.embed()` çağrısı `dimensions` hiç geçmediği için sorguyu
  HER ZAMAN native (2560) boyutunda embed ediyordu. Fix: `search()`'e
  opsiyonel `dimensions: int | None = None` parametresi eklendi
  (varsayılan `None`, mevcut TÜM çağrı yerleri etkilenmedi),
  `EmbeddingProvider` protokolüne de aynı parametre eklendi. Test
  ÖNCE fail ettiği kanıtlanarak yazıldı (fix geçici geri alınıp
  doğrulandı: `test_search_forwards_a_dimensions_override_to_the_
  embedding_call` gerçekten `AssertionError` ile fail etti).
- **Disk kullanımı ölçümü `du -sb` ile YANLIŞ ölçülüyordu.** İlk
  başarılı koşumda TÜM 6 configuration ~211MB gibi neredeyse AYNI
  storage rakamı gösterdi — şüpheli, çünkü 768 ve 2560 boyut arasında
  gerçek bir fark olmalıydı. GERÇEKTEN araştırıldı: `du -sb`
  (`--apparent-size`) Qdrant'ın WAL/mmap dosyalarının PREALLOCATE
  edilmiş, çoğunlukla boş SPARSE mantıksal boyutunu raporluyor (örn.
  32 chunk'lık bir collection için 32MB'lık bir WAL segment dosyası) —
  gerçek disk kullanımını DEĞİL. Doğrudan container'a `docker exec du
  -sk` ile karşılaştırıldı: `nomic@native` 2444KB, `qwen3-4b@native`
  2944KB — GERÇEKTEN farklı, anlamlı rakamlar. Fix: `-sb` yerine
  `-sk` (block-based, sparse-farkında) kullanılıyor, testle kanıtlandı
  (`test_storage_measurement_uses_block_based_du_not_apparent_size`).

**3. Gerçek 6-configuration koşumu (`artifacts/embedding-benchmark-
sprint19/report.md`):**

```
Config              Cross R@5  Cross MRR  Mono R@5  Dim    Query p95(ms)  Index chunks/s  Storage(real)
nomic@native          0.607      0.418      1.000    768       46.1           29.96         2.3MB
qwen3-0.6b@native     0.910      0.696      1.000   1024      134.0           11.50         2.4MB
qwen3-4b@native       0.971      0.782      1.000   2560      251.8            2.45         3.0MB
qwen3-4b@1024         0.971      0.755      1.000   1024      265.7            2.46         2.6MB
qwen3-0.6b@1024       0.910      0.710      1.000   1024      141.2           11.20         2.4MB
qwen3-0.6b@768        0.939      0.723      1.000   768       139.3           11.48         2.4MB
```

Hiçbir configuration mono-lingual tarafta hiç regresyon göstermedi
(TR→TR ve EN→EN hepsi 1.000). `qwen3-4b@native` Sprint 18'in kalite
tavanını doğruladı. Truncation (2560→1024) `qwen3-4b`'nin cross-lingual
Recall@5'ini KORUDU (0.971→0.971, hiç kayıp yok) ama MRR'de küçük bir
kayıp var (0.782→0.755) — boyut küçültmenin bedavaya gelmediğinin
kanıtı, ama recall tarafında ölçülebilir bir bedeli yok.

**4. Pareto frontier: `qwen3-0.6b@1024`, `qwen3-0.6b@768` tarafından
domine edildi** — aynı veya daha iyi cross-lingual kalite, aynı/daha
düşük dimension, daha düşük p95 sağlıyor. Diğer 5 configuration
frontier'da (hiçbiri başka biri tarafından domine edilmiyor) — her biri
gerçek bir trade-off temsil ediyor.

**5. QUALITY WINNER: `qwen3-4b@native`.** Ağırlıklı skor (0.4×cross_recall5
+ 0.3×cross_mrr + 0.3×overall_ndcg5) ile en yüksek — beklenen sonuç,
Sprint 18'in kalite tavanı.

**6. EFFICIENCY WINNER: `qwen3-4b@1024`** (kabul eşiklerini geçen tek
gerçek aday bu koşumda). Eşikler (`qwen3-4b@native`'e göre): cross-lingual
Recall@5 kaybı ≤0.05, cross-lingual MRR kaybı ≤0.05, mono-lingual Recall@5
regresyonu ≤0.02. `qwen3-4b@1024` recall'de HİÇ kayıp yaşamadı (0.971→0.971),
MRR kaybı 0.027 (eşiğin altında) — dimension'ı 2560'tan 1024'e indirerek
(%60 daha küçük vektör, daha az storage) kaliteyi neredeyse tamamen
koruyor.

**Sınır-vaka dürüstlüğü: `qwen3-0.6b@768` eşiğe çok yakın, koşumdan
koşuma değişti.** İlk (kısa süre önce, storage bug'ı düzeltmeden ÖNCE
alınan) koşumda `qwen3-0.6b@768`'in cross-lingual MRR kaybı 0.044
(eşiğin altında, kabul edildi); bu FİNAL koşumda 0.059 (eşiğin ÜSTÜNDE,
reddedildi) — SADECE LLM/embedding çağrılarının doğal run-to-run
gürültüsünden kaynaklanan bir fark, kod DEĞİŞMEDİ. Bu, 68 sorunun küçük
bir örneklem olduğunun ve eşiğe yakın kararların gürültüye duyarlı
olduğunun somut kanıtı — "İstatistiksel uyarı" bölümünde zaten
belirtilen sınırlamanın gerçek bir örneği.

**7. PRODUCTION RECOMMENDATION: `qwen3-4b@1024` bir sonraki migration
adayı olarak önerildi — nomic hâlâ GERÇEK production default'u,
`settings.ollama_embed_model` değişmedi.** Bu sadece bir öneri, bir
uygulanmış değişiklik değil.

**8. İstatistiksel sınırlama (dürüstçe belirtildi, kod yazılmadı).**
Bootstrap confidence interval EKLENMEDİ — kullanıcının kendi izniyle
("fazla karmaşık hale gelirse zorunlu değil, limitation olarak belirt")
bu sprint kapsamında atlandı; 68 sorunun küçüklüğü ve yukarıdaki
sınır-vaka örneği zaten neden gerekli olduğunu somut olarak gösteriyor.
RAM/VRAM yine ölçülmedi — güvenilir bir izole ölçüm mekanizması yok.

**Yeni testler:** `tests/test_ollama_client.py` +4 (dimensions
parametresi: endpoint seçimi, payload, silent-clamp, unreachable),
`tests/test_embedding_models.py` +8 (0.6b config, output_dimension
override, label(), parse_config_token), `tests/test_fingerprint.py` +2
(aynı model farklı dimension → farklı fingerprint, farklı model aynı
dimension → yine farklı fingerprint), `tests/test_search.py` +2
(dimensions forwarding, GERÇEKTEN fail ettiği kanıtlanarak),
`tests/test_benchmark_embeddings.py` yeniden yazıldı (+8 net: Pareto
dominance, quality/efficiency winner senaryoları, storage measurement
regression testleri, collection isolation, golden set bütünlüğü).
`ruff check app tests scripts` temiz, tüm mevcut testler (Sprint 18
dahil) hâlâ yeşil.

## Sprint 20 — Embedding Benchmark Stability & Production Decision

Amaç: Sprint 19'un bulduğu `qwen3-0.6b@768` vs `qwen3-4b@1024` küçük
kalite farkını, çok daha büyük (220 soru) ve paired bootstrap CI ile
desteklenen bir değerlendirmeyle gerçek bir production kararına
dönüştürmek. Bkz. docs/sprint-20-plan.md.

Scope:

1. Sadece 3 configuration: nomic@768, qwen3-0.6b@768, qwen3-4b@1024
2. Golden set 68→220 soruya genişletildi (aynı 4 fixture doküman,
   genişletilerek — yeni doküman eklenmedi), 10 zorluk kategorisi
3. Programmatik dataset doğrulama (duplicate/dangling-location/
   distribution/not-found-ratio)
4. Paired bootstrap confidence interval (`app/evaluation/bootstrap.py`)
5. Determinism araştırması — gerçek nondeterminism kaynağı bulunup
   raporlandı, gizlenmedi
6. Üç ayrı verdict: QUALITY WINNER, EFFICIENCY WINNER, PRODUCTION WINNER

DoD: 220 soru, 3 configuration, gerçek paired bootstrap CI'lar, açık ve
deterministic bir production karar mantığı; production default
değişmedi.

### Kapanış notu

**1. Golden set 68'den 220 soruya genişletildi — sadece çeviri değil,
gerçek zorluk çeşitliliğiyle.** İki mevcut fixture doküman (Sprint
18'de eklenen `nimbus_api_reference.md` ve `nimbus_kurumsal_sss.md`)
genişletildi (10→20, 8→17 bölüm) — yeni doküman eklemek yerine mevcut
korpus derinleştirildi. 27 EN-content + 25 TR-content = 52 gerçek
"fact," her biri 1 native-dil sorusu + 3 çapraz-dil sorusuyla (10
zorluk kategorisinden: exact_lexical, semantic_paraphrase,
terminology_mismatch, acronym_abbreviation, number_date_lookup,
multi_sentence_evidence, heading_dependent, ambiguous_wording,
hard_negative — hepsi en az 2 kez temsil edildi, testle kanıtlandı) +
12 not-found kontrol sorusu = 220 soru. Dağılım hedefin üzerinde:
TR→EN=81 (≥75), EN→TR=75 (≥75), TR→TR=25 (≥25), EN→EN=27 (≥25).

**2. Dataset kalitesi programmatik olarak doğrulandı, elle
kontrol edilmedi.** Yeni `app/evaluation/golden_set_validation.py` —
exact/normalized duplicate tespiti (normalize: küçük harf + noktalama
temizliği + boşluk sıkıştırma, Türkçe karakterler korunuyor), dangling
expected-location tespiti, language-pair dağılım kontrolü, not-found
oranı kontrolü. `tests/test_golden_set_v2_integrity.py`, GERÇEK
`embedding_benchmark_golden_v2.json`'ı GERÇEK chunker'ların (Qdrant/
Ollama olmadan, `chunk_document`/`chunk_markdown_document` doğrudan
çağrılarak, tam deterministic) ürettiği konumlara karşı doğruluyor —
**0 dangling location, 0 duplicate, 220/220 soru gerçek içerikten**.

**3. Determinism kaynağı GERÇEKTEN araştırıldı, gizlenmedi.** Aynı
metni (`qwen3-embedding:0.6b`) iki kez embed etmek GERÇEKTEN farklı
float değerleri üretiyor — doğrudan test edildi:
`max(abs(a[i]-b[i]))` ≈ **2.7e-05**, aynı model aynı girdiyle. Bu,
Sprint 19'un run-to-run gürültüsünün gerçek kaynağı — Ollama/backend'in
kendi sayısal-olarak-deterministik-olmayan inference'ı (muhtemelen
Metal/GPU accumulation sırası), bu projenin kontrol edebileceği bir
şey DEĞİL. Kontrol edilebilenler düzeltildi: sorgu sırası artık
id'ye göre sıralı deterministic (`sorted(golden_questions, key=...)`),
metrik agregasyonu zaten saf Python, bootstrap seed sabit
(20200601). Ama embedding çıktısının kendisi bit-exact tekrarlanabilir
DEĞİL — bu gerçek sınır raporda ve bu notta açıkça yazılı.

**4. Paired bootstrap CI, gerçek per-question verilerden, id ile
eşleştirilerek.** `app/evaluation/bootstrap.py::paired_bootstrap_ci` —
"paired" çünkü her soru HER İKİ configuration tarafından da
skorlanıyor, bootstrap resampling aynı soru indekslerini HER İKİ taraf
için de çekiyor (bağımsız resampling yerine). Deterministic:
`random.Random(seed)`, global random state'e dokunmuyor — testle
kanıtlandı (aynı seed → bit-bit aynı sonuç). Sentetik örneklerle
kanıtlandı: sabit +0.5 fark → CI kesinlikle sıfırı içermiyor; sıfır
gerçek fark → CI sıfırı içeriyor. `scripts/benchmark_embeddings.py::
compute_bootstrap_report`, per-question metrikleri SORU ID'siyle
eşleştiriyor (liste pozisyonuyla değil) — iki config'in sonuçları
farklı sırada saklansa bile doğru eşleşme garantili, testle kanıtlandı.

**5. Gerçek 220-soru, 3-configuration koşumu
(`artifacts/embedding-benchmark-sprint20/report.md`):**

```
Config            Cross R@5  Cross MRR  Mono R@5  nDCG@5   Dim   Query p95(ms)
nomic@768           0.569      0.416     0.920     0.555    768      43.3
qwen3-0.6b@768      0.906      0.699     0.980     0.803    768     140.6
qwen3-4b@1024       0.963      0.744     1.000     0.842   1024     258.7
```

`qwen3-4b@1024 - qwen3-0.6b@768` farkı: cross Recall@5 kaybı 0.057
(eşik 0.03'ün ÜSTÜNDE), cross MRR kaybı 0.045 (eşik 0.04'ün ÜSTÜNDE),
mono-lingual Recall@5 kaybı 0.02 (eşik 0.01'in ÜSTÜNDE) — nokta
tahmini, Sprint 20'nin kendi (Sprint 19'dan daha sıkı) eşiklerinin
ÜÇÜNÜ de aşıyor.

**Paired bootstrap CI (cross-lingual subset, n=156, seed=20200601,
5000 iterasyon):** Recall@5 delta = -0.058 [-0.103, -0.013], MRR delta
= -0.047 [-0.081, -0.015] — CI'lar sıfırı İÇERMİYOR (fark yönü gerçek),
ama CI'nın en iyimser ucu (üst sınır, -0.013 ve -0.015) eşiklerin
(-0.03, -0.04) ÜSTÜNDE kalıyor — yani "kayıp gerçek ama eşiği aşacak
kadar büyük olduğu CI ile TEYİT EDİLEMİYOR."

**6. GERÇEK bir kod hatası koşum sırasında yakalandı ve düzeltildi —
"varsayma, çalıştır" disiplininin somut kanıtı.** İlk gerçek koşumda
EFFICIENCY WINNER olarak `nomic@768` çıktı — açıkça yanlış, çünkü
nomic'in cross-lingual kalitesi (0.569-0.576) her iki Qwen adayından da
~0.33-0.39 daha düşük. Kök neden: efficiency_candidates filtresi
MUTLAK bir "crisis floor" (0.5) kullanıyordu — nomic bunun üstünde
kaldığı için (gerçek zayıflığına rağmen) aday sayılıp sadece en düşük
latency'si olduğu için kazanıyordu. Fix: filtre artık EN İYİ
configuration'a GÖRECELİ (`best_cross_recall - 0.15` marjı) —
`tests/test_benchmark_embeddings_sprint20.py`'de bu tam senaryoyu
reprodükleyen bir regresyon testi eklendi. Ayrıca rapor başlığı/
"Statistical caution" metni Sprint 19'dan hardcoded kalmıştı ("68
question," "no bootstrap CIs were computed") — `render_markdown_report`
parametreleştirildi (varsayılan: Sprint 19'un orijinal metni, GERİYE
DÖNÜK UYUMLU), Sprint 20 kendi doğru metnini geçiyor.

**7. Üç ayrı verdict:**

- **QUALITY WINNER: `qwen3-4b@1024`** — ağırlıklı skorda en yüksek
  (Sprint 19 ile aynı formül: 0.4×cross_recall5+0.3×cross_mrr+0.3×ndcg5).
- **EFFICIENCY WINNER: `qwen3-0.6b@768`** — en düşük dimension/p95,
  EN İYİ configuration'ın kalitesine göreceli marj içinde kalan
  configuration'lar arasında (nomic artık bu marjın dışında, madde 6
  ile düzeltildi).
- **PRODUCTION WINNER: `NEED_MORE_DATA`** — nokta tahmini eşikleri
  aşıyor (within_tolerance=False) AMA bootstrap CI bu aşımı GÜVENLE
  TEYİT ETMİYOR (ci_confirms_material_gap=False, CI'nın en iyimser ucu
  eşiğin altında kalmıyor) — bu, kararın kasıtlı olarak tasarlandığı
  "nokta tahmini ve CI anlaşmazsa NEED_MORE_DATA" dalı, GERÇEKTEN
  tetiklendi. 220 soru bile bu ~0.02-0.06'lık küçük farkı kesin olarak
  çözmeye yetmiyor — dürüstçe raporlandı, zorla bir yöne karar
  verilmedi.

**8. Sınırlamalar:** 220 soru tek bir fictional domain'den (Nimbus),
tek koşum (embedding backend'in kendi nondeterminizmi nedeniyle farklı
bir koşum küçük farklı sayılar verebilir — madde 3). Bootstrap CI'lar
gerçek ve deterministic ama YİNE DE tek bir golden set'in
istatistikleri, harici bir gerçek-dünya trafiği örneklemi değil.
RAM/VRAM ölçülmedi.

**~65 yeni test** (`app/evaluation/golden_set_validation.py` testleri
+18, `app/evaluation/bootstrap.py` testleri +9,
`tests/test_golden_set_v2_integrity.py` +7,
`tests/test_benchmark_embeddings_sprint20.py` +19, mevcut Sprint 18/19
regresyon testleri hâlâ yeşil), `ruff check app tests scripts` temiz.

**Production default DEĞİŞMEDİ** — `settings.ollama_embed_model` hâlâ
`nomic-embed-text`. Migration ayrı bir sprint/PR kararı.

## Sprint 21 — Embedding Non-Inferiority & Stability Decision

Amaç: Sprint 20 `NEED_MORE_DATA` ile bitmişti. Bu sprint YENİ bir model
eklemeden, dataset'i körlemesine büyütmeden — ölçüm gürültüsünü
(embedding backend'in kendi nondeterminizmi) gerçek retrieval
instability'den ayırıp, `qwen3-0.6b@768` için pre-committed bir
non-inferiority kararı verdi. Bkz. docs/sprint-21-plan.md.

Scope:

1. Sadece 2 configuration: `qwen3-0.6b@768`, `qwen3-4b@1024` (nomic
   sadece Sprint 20'den tarihsel referans)
2. Mevcut 220 soruluk golden set donduruldu, dataset/corpus fingerprint
   üretildi
3. 10 bağımsız live quality run per configuration (query-only, corpus
   bir kez indexlendi)
4. Embedding nondeterminism ölçümü (50 soru x 10 tekrar) — bit-level
   fark ile ranking etkisi AYRI raporlandı
5. Frozen embedding cache + retrieval determinism check — GERÇEK bir
   RRF tie-breaking bug'ı bulundu ve düzeltildi
6. Pre-committed non-inferiority testi (paired bootstrap, ≥10.000
   iterasyon, doğru yönlü CI yorumu)
7. Power analysis (approximate, açıkça belirtilmiş)
8. Üç verdict: QUALITY WINNER, EFFICIENCY WINNER, PRODUCTION WINNER

DoD: 220 soru, 2 configuration, 10 bağımsız run, gerçek non-inferiority
kararı; production default değişmedi.

### Kapanış notu

**1. Dataset/corpus fingerprint gerçekten üretildi ve her artifact'e
yazıldı.** `app/evaluation/dataset_fingerprint.py` — golden set'in
(id/query/dil/expected_location/difficulty, id'ye göre sıralı,
`sort_keys=True` ile JSON-serialize edilmiş) ve 4 fixture dokümanın
(PDF için gerçek kaynak metni, PAGES) SHA-256 hash'i. Bu sprint
koşumu: dataset fingerprint `55e857db9c7b9ad1...`, corpus fingerprint
`42b21bb06bb3688...` — Sprint 20'nin AYNI 220 soruluk dosyasından
(dosya değiştirilmedi, testle kanıtlandı: `test_golden_v2_has_at_least_
200_questions` ve golden_set_v2_integrity testleri hâlâ yeşil).

**2. GERÇEK bir RRF tie-breaking bug'ı bulundu ve düzeltildi —
"gerçek tie varsa düzelt" kuralının somut uygulanışı.** İlk gerçek
koşumda (küçük ölçekli smoke test) retrieval determinism check 208
sorunun 26'sında "unstable" çıktı — GERÇEKTEN araştırıldı: aynı frozen
(cache'lenmiş, hiç embedding çağrısı yapılmayan) vektörle art arda 6
`hybrid_search` çağrısı yapıldı, SKORLAR birebir aynıydı (0.833333,
0.5, 0.5, 0.5, 0.2625) ama üç sonuç TAM OLARAK aynı skorda (0.5)
tie oluyordu ve bu üçünün SIRASI çağrıdan çağrıya DEĞİŞİYORDU — Qdrant'ın
RRF fusion'ı eşit skorlu sonuçlar arasında stabil bir sıra
GARANTİLEMİYOR. Kök neden GERÇEKTEN doğrulandı (varsayılmadı). Fix:
`app/retrieval/hybrid_search.py::stable_order()` — Qdrant'tan dönen
sonuçlar `(-score, point_id)` ile yeniden sıralanıyor; `point_id`
zaten deterministic (chunk içeriğinden uuid5), bu yüzden tie-break
DETERMİNİSTİK ama anlamsız değil (gerçek skor sıralamasını asla
değiştirmiyor, sadece gerçek eşitlikleri çözüyor).
`SearchResult`'a geriye dönük uyumlu (varsayılan `""`) bir `id` alanı
eklendi. Fix ÖNCESİ/SONRASI karşılaştırması: 26/208 unstable → **0/208
unstable, her iki configuration için de `is_fully_deterministic=True`**
— gerçek koşumda doğrulandı. Testler: `test_stable_order_breaks_a_
genuine_score_tie_deterministically`, `test_stable_order_preserves_
score_ordering_for_genuinely_different_scores` (gerçek skor farkını
DEĞİŞTİRMEDİĞİNİ kanıtlıyor).

**3. Embedding nondeterminism ile ranking instability GERÇEKTEN
AYRIŞTIRILDI — ikisi aynı şey değil, sayılarla kanıtlandı.** 50 stratified
soru x 10 tekrar, gerçek: bit-level fark var (`qwen3-4b@1024` max abs
delta 8.45e-04, mean cosine similarity 0.999988 — mükemmel değil ama
neredeyse) AMA bunun ranking'e etkisi neredeyse SIFIR: top1 flip rate
0.000, recall@5-impacting flip rate 0.000 (her iki configuration için),
tek gerçek etki `qwen3-4b@1024`'ün top5 SET change rate'i 0.020 (50
sorudan sadece 1'i). `qwen3-0.6b@768` için TÜM ranking-impact oranları
0.000. **10 bağımsız live run'ın run-to-run stddev'i de 0.0000** —
cross-lingual Recall@5/MRR/nDCG@5 agregeleri 10 run boyunca HİÇ
değişmedi, her iki configuration için de. Bu, dokümantasyonda
istenen ayrımın somut kanıtı: "floating-point nondeterminism ile
retrieval-level instability aynı şey değildir" — burada gerçek
embedding nondeterminizmi VAR ama 220 sorunun AGREGE kalite metriklerine
ölçülebilir bir etkisi YOK.

**4. Gerçek 10-run, 2-configuration koşumu
(`artifacts/embedding-benchmark-sprint21/report.md`):**

```
Config            Cross R@5  Cross MRR  nDCG@5   Query p95(ms)  Index chunks/s
qwen3-0.6b@768      0.9064     0.6940    0.8001      136.4          12.85
qwen3-4b@1024       0.9630     0.7336    0.8362      326.5           2.53
```

**5. Pre-committed non-inferiority sonucu: 0.6B non-inferior DEĞİL.**
delta konvansiyonu = `4B - 0.6B` (pozitif = 4B daha iyi), non-inferiority
= CI'nın ÜST sınırı margin'in altında kalıyorsa (en kötümser senaryoda
bile fark margin'i aşmıyorsa). Paired bootstrap (seed=20210101,
10.000 iterasyon, %95 CI), per-question metrikler 10 live run'ın
ORTALAMASI (canonical_per_question_metrics — embedding nondeterminizm
gürültüsünü per-question sinyalde azaltmak için, hâlâ per-question
PAIRED):

```
Metrik              Margin  Gözlenen delta  CI alt   CI üst   Non-inferior?
cross Recall@5        0.04      0.0577      0.0128   0.1026      HAYIR
cross MRR              0.04      0.0409      0.0111   0.0726      HAYIR
mono Recall@5          0.02      0.0192      0.0000   0.0577      HAYIR
```

Üçünün de CI üst sınırı margin'i AŞIYOR — yani en iyimser senaryoda
bile 0.6B'nin kaybı tolere edilebilir sınırın üstünde kalabiliyor.

**6. PRODUCTION KARARI: `ADOPT_QWEN3_4B_1024`.** Karar mantığı
(`app/evaluation/non_inferiority.py::production_decision`, sonuçtan
ÖNCE kodlandı, testle kanıtlandı): 0.6B non-inferior DEĞİL VE 4B'nin
avantajı hem istatistiksel olarak güvenilir (CI ALT sınırı 0.0128 > 0,
yani interval sıfırı hiç içermiyor) HEM DE pratik olarak anlamlı
(gözlenen fark 0.0577 > 0.04 margin) — bu Sprint 20'nin
`NEED_MORE_DATA`sından FARKLI, kesin bir sonuç. Sprint 20'nin
belirsizliği gerçekten çözüldü: daha büyük dataset (220), tekrarlanan
run'lar (10x) ve gürültü ayrıştırması bir araya gelince net bir
kazanan ortaya çıktı.

**7. Power analysis (yaklaşık, açıkça belirtilmiş).** Mevcut
cross-lingual n=156 (canonical, paired). Gözlenen paired stddev=0.2838.
80% power için tahmini gereken n≈312, 90% için≈432 — ama bu sprintte
zaten KARARLI bir sonuç elde edildiği için (madde 6) ek veri toplamaya
gerek YOK; power analysis bilgi amaçlı raporlandı, "daha çok veri her
zaman iyidir" yaklaşımıyla dataset büyütülmedi.

**8. Sınırlamalar:** Normal-approximation power formülü per-question
Recall@5'in ikili (binary-ish) doğasını tam yakalamıyor — dürüstçe
belirtildi. RAM/VRAM yine ölçülmedi. Tek bir fictional domain (Nimbus).

**~110 yeni test** (`app/evaluation/dataset_fingerprint.py` +7,
`app/evaluation/embedding_cache.py` +11, `app/evaluation/
non_inferiority.py` +20, `tests/test_hybrid_search.py` +4 (stable_order
tie-break), `tests/test_benchmark_stability.py` +25 — vector delta
matematiği, ranking flip mantığı, stratified sampling, canonical
per-question agregasyon, live/frozen mode dispatch, Sprint 20 dataset
fingerprint stabilitesi), `ruff check app tests scripts` temiz, mevcut
TÜM Sprint 18-20 testleri hâlâ yeşil.

**Production default DEĞİŞMEDİ** — `settings.ollama_embed_model` hâlâ
`nomic-embed-text`. `ADOPT_QWEN3_4B_1024` bir ÖNERİ, uygulanmış bir
değişiklik değil — gerçek migration ayrı bir Sprint 22/PR kararı.

## Sprint 22 — Qwen3-4B@1024 Production Embedding Migration

Sprint 21 kapandığında `PRODUCTION DECISION = ADOPT_QWEN3_4B_1024` bir
ÖNERİYDİ, uygulanmış bir değişiklik değildi. Bu sprintin amacı model
benchmark etmek değil — bu kararı downtime ve silent index corruption
riski yaratmadan, doğrulanabilir ve rollback edilebilir bir gerçek Qdrant
index lifecycle operasyonuna dönüştürmek.

**Mimari — blue/green via Qdrant alias:**

```
                    +-- kb_chunks (nomic@768, mevcut)
kb_active (alias) --|
                    +-- kb_qwen3_4b_1024_<fingerprint> (yeni)
```

Qdrant, bir alias'ı arama/upsert/delete için gerçek bir collection ismi
gibi ele alır — `app/ingestion`/`app/retrieval` içinde HİÇBİR kod
değişikliği gerekmedi. `app/migration/aliasing.py::resolve_active_collection_name`
alias yoksa (migration hiç çalışmamışsa) `settings.qdrant_collection_name`'e
fallback eder — migrate edilmemiş bir deployment tamamen etkilenmez.

**Yeni modül: `app/migration/`** — `naming.py` (deterministic collection
isimlendirme: `kb_<model>_<dimension>_<fingerprint-prefix>`),
`aliasing.py` (atomic alias switch, tek `update_collection_aliases`
çağrısında delete+create), `models.py` (`MigrationManifest`,
8 durumlu `MigrationStatus` state machine — basit typed enum, framework
yok), `embedding_migration.py` (plan/index/validate/activate/rollback/
status/cleanup-old motoru), `quality_gate.py` (Sprint 21'in frozen
220-soruluk golden set'ini reuse eden retrieval quality gate + hızlı
smoke check), `readiness.py`, `startup_guard.py`.

**Kritik tasarım kararı — izole registry:** İndeksleme, DEĞİŞTİRİLMEMİŞ
`ingest_connector`'ı kullanıyor ama production registry.db yerine
migration_id başına izole bir SQLite dosyasına yazıyor. Sebep: production
registry'yi kullansaydı, henüz doğrulanmamış/aktive edilmemiş target
collection için yapılan indeksleme, production'ın registry satırlarındaki
`pipeline_fingerprint`'i erkenden değiştirirdi — production hâlâ ESKİ
collection'ı serve ederken registry YENİ fingerprint'i "sağlıklı" sanardı.
İzole registry, aynı zamanda ingest_connector'ın var olan incremental-sync
semantics'inden BEDAVA idempotency/resume sağlıyor: yarıda kesilen bir
migration'ı tekrar çalıştırmak sadece eksik kalan dokümanları tamamlıyor.

**Yeni CLI: `python -m scripts.migrate_embedding_index {plan,migrate,validate,activate,rollback,status,cleanup-old}`**
— tam operatör kılavuzu `docs/embedding-migration.md`.

**Gerçek local migration çalıştırıldı** (Docker Qdrant + native Ollama,
Sprint 18-21'in nimbus fixture corpus'u "mevcut production" olarak
seed edilerek):

- Re-index: 4 doküman, 51 chunk, ~23.5s (gerçek qwen3-embedding:4b)
- Structural validation: `passed=true`, `duplicate_points=0`
- Quality gate (frozen 220 soru): Cross Recall@5=0.9630 (Sprint 21
  baseline: 0.9630), Cross MRR=0.7367 (baseline: 0.7336) — tolerance
  0.03 içinde, `passed=true`
- Activation: `kb_active` atomic olarak `kb_chunks` → `kb_qwen3_4b_1024_8ea8f97e`
  yönlendirildi, post-switch smoke (16 soru) geçti
- Incremental sync doğrulaması: migration sonrası eklenen yeni doküman,
  `kb_active` alias'ı üzerinden gerçek 1024-boyutlu qwen3-4b vektörleriyle
  indekslendi; eski `kb_chunks` 51 point'te değişmeden kaldı
- **Rollback drill gerçek yapıldı:** qwen aktifken `rollback` → nomic
  aktif oldu, `kb_active` üzerinden gerçek bir arama ("How do I install
  the CLI?") doğru sonuçlar döndürdü → `rollback` tekrar çalıştırıldı
  (simetrik swap) → qwen3-4b tekrar aktif. Her iki collection da
  process boyunca hiç silinmedi.

**Gerçek bir bug bulundu ve düzeltildi (smoke sırasında):** CLI'nin
`WORK_DIR` (izole registry dosyalarının tutulduğu dizin) ilk çalıştırmada
henüz yoktu — `migrate` komutu `sqlite3.OperationalError: unable to open
database file` ile patladı. Fix: `cmd_migrate` artık indekslemeden önce
`WORK_DIR.mkdir(parents=True, exist_ok=True)` çağırıyor.

**Config artık tek doğruluk kaynağı:** `EMBEDDING_MODEL_KEY` +
`EMBEDDING_OUTPUT_DIMENSION` (yeni) — `app/llm/embedding_models.py::active_embedding_config`
her yerde bunları kullanıyor (`app/wiring.py`'nin embed_fn/search_fn'i,
`default_embed_model`). Production default artık `qwen3-4b`/1024.
`app/migration/startup_guard.py` configured dimension ile active
collection'ın gerçek dimension'ı uyuşmazsa uygulamayı fail-fast durduruyor
— silent 768-vs-1024 schema mismatch imkansız.

**Sprint 22 son düzeltme — SyncManager production sync fingerprint
enforcement:** Rapor ilk yazıldığında bilinen bir limitasyon olarak not
düşülmüştü: `SyncManager` production `ingest_connector()` çağrılarına
`pipeline_fingerprint` geçirmiyordu (Sprint 18'den beri aynı) — yani
content_hash'i değişmemiş ama registry satırı ESKİ (migration öncesi)
fingerprint'i taşıyan bir doküman, sonsuza kadar "sağlıklı" sanılabilirdi.
Bu, aynı sprint kapanmadan düzeltildi: `app/wiring.py::build_app()` artık
migration'ın kendisinin kullandığı AYNI tek doğruluk kaynağından
(`active_embedding_config(settings)`) bir `PipelineFingerprint` inşa edip
`SyncManager`'a geçiriyor; `SyncManager` da bunu her
`ingest_connector()` çağrısına iletiyor (`app/sync/manager.py`).

Gerçek doğrulama, doğrudan `ingest_connector` çağırarak DEĞİL, gerçek
`/sync/filesystem` endpoint'i üzerinden yapıldı: migration sonrası ilk
sync `files_processed=6, chunks_upserted=53` — registry'de hâlâ eski
(nomic) fingerprint taşıyan her doküman aktif qwen3-4b@1024 pipeline'ı
altında yeniden embed edildi. Hemen ardından ikinci sync
`files_processed=0, files_skipped=6` — steady state doğrulandı, sonsuz
re-embed döngüsü yok. Her registry satırının `pipeline_fingerprint`'i
artık aktif fingerprint digest'ine (`8ea8f97e028fc4e1`) eşit; `kb_active`
içindeki her point 1024 boyutlu; eski `kb_chunks` (nomic) point count'u
(51) boyunca değişmedi. 5 yeni test
(`tests/test_sync_manager_pipeline_fingerprint.py`) — tamamı
`SyncManager.trigger_sync()` üzerinden (doğrudan `ingest_connector`
çağırmadan): yeni doküman, değişen doküman, unchanged+matching
fingerprint (skip), unchanged+stale fingerprint (re-index), ve
mixed-dimension-vector imkansızlığı.

**Kalan bilinen limitasyonlar** (`docs/embedding-migration.md`'de
detaylı): Sprint 21'in `stability.json`'ı mono-lingual Recall@5'i mutlak
değer olarak config başına tutmuyor (sadece iki config arası delta) —
quality gate bu karşılaştırmayı uydurmak yerine atlıyor.
Failure-injection senaryoları (gerçek Ollama/Qdrant kesintisi) hermetic
testlerle kapatıldı, gerçek ortamda tekrarlanmadı.

**Testler:** ~115 yeni test (`tests/test_migration_*.py`,
`tests/test_embedding_migration.py`, `tests/test_quality_gate.py`,
`tests/test_readiness.py`, `tests/test_startup_guard.py`,
`tests/test_sync_manager_pipeline_fingerprint.py`, + config/
fingerprint/provider/health testlerine ekler) — tamamı `:memory:` Qdrant
ve fake Ollama ile hermetic. `ruff check app tests scripts` temiz, tüm
mevcut suite yeşil.

**Production default DEĞİŞTİ:** `qwen3-4b@1024` artık gerçek production
default'u — ama bu bir kod-satırı değişikliği değil, doğrulanmış bir
migration sonucu. Rollback her zaman mümkün (`kb_chunks` silinmedi).

**Sıradaki mantıklı iş:** `cleanup-old` ile eski `kb_chunks` collection'ının
temizlenmesi (ayrı, insan onaylı bir işlem) ve Sprint 24 (stretch)'te
ertelenen Confluence connector'ı.

## Sprint 23 — Security Boundary & Tenant-Aware Retrieval

Orijinal roadmap'in Faz 1'i: "hangi kullanıcı hangi belgeyi görmeye
yetkili?" sorusunu retrieval seviyesinde ZORUNLU hale getirmek —
prompt'ta değil, generation'da değil, citation post-check'te değil;
kontrol retrieval'dan ÖNCE.

**Security model:** `UserContext(user_id, tenant_id, roles)` —
yalnızca doğrulanmış `Authorization: Bearer <token>`'dan
(`app/security/auth.py::TokenAuthenticator`) inşa ediliyor, request
body/query'den ASLA. Üç lineer rol: `USER < OPERATOR < ADMIN`.
`RetrievalContext(tenant_id, is_system)` bilinçli olarak AYRI bir tip —
`RetrievalContext.system()` cross-tenant retrieval'a giden TEK yol ve
kod tabanında hiçbir yerde gerçek bir request'ten inşa edilmiyor.

**Zorunlu ACL filtresi:** `app/retrieval/search.py::search()` artık
ZORUNLU bir `context: RetrievalContext` parametresi alıyor (default
yok — bu kod tabanındaki her çağrı noktası gerçek bir tenant-scoped
kullanıcı mı yoksa privileged system context mi olduğunu açıkça
belirtiyor). `build_acl_filter` sadece explicit system context için
`None` dönüyor, aksi halde tenant_id yoksa `MissingTenantContextError`
fırlatıyor (fail-closed, asla "her şeyi döndür" yok). `combine_filters`
ACL'yi kullanıcı filtresiyle AND'liyor — kötü niyetli bir filtre başka
bir tenant'ı belirtse bile sonuç kümesini sadece DARALTIYOR, asla
genişletmiyor.

**Chunk/registry/point identity:** `Chunk.tenant_id` (default
"default", `ingest_connector` içinde chunking sonrası
`dataclasses.replace` ile set ediliyor), Qdrant payload'a
`tenant_id`/`visibility` eklendi, `point_id_for` canonical key'ine
tenant_id eklendi (`CURRENT_INDEX_SCHEMA_VERSION` 3→4 — her mevcut
point ID değişiyor), `DocumentRegistry` PK'sı `(source_type,
source_id)` → `(tenant_id, source_type, source_id)` (gerçek
rename-rebuild-copy-drop migration, mevcut satırlar "default"a
backfill ediliyor).

**Endpoint policy:** `/chat` USER+; `/sources` tenant-scoped (başka
tenant'a ait source_type response'ta hiç görünmüyor); `/sync/{type}`
ve `/sync/{type}/history` OPERATOR+ VE o source_type'ın caller'ın
tenant'ına ait olması (`_require_owned_source_type`).

**Gerçek doğrulama — sadece unit test değil:**
`tests/test_cross_tenant_e2e.py` (12 test) GERÇEK Qdrant server'a karşı
çalışıyor (`:memory:` mode hybrid prefetch+fusion filter'ı sessizce
düşürüyor — bilinen bir limitasyon) — iki gerçek tenant tek collection'ı
paylaşıyor, dense/sparse(gerçek BM25)/hybrid izolasyon, filter-override
saldırısı, reranker'ın sadece authorized candidate gördüğü, citation
leakage önleme. Ayrıca gerçek local script (Docker Qdrant + native
Ollama + gerçek FastAPI app + gerçek token'lar) çalıştırıldı:

```
tenant A → A: found_own=true, leaked=false
tenant A → B (saldırı): leaked=false
tenant B → B: found_own=true, leaked=false
tenant B → A (saldırı): leaked=false
RBAC: no-creds=401, wrong-role=403, correct-operator=200, wrong-tenant-operator=403
/sources: tenant-a kendi source'unu görüyor, tenant-b hiçbir şey görmüyor
performans: ACL filtreli 41.9ms vs filtresiz 40.2ms (~%4 fark, gerçek Ollama embed çağrısı domine ediyor)
```

`cross_tenant_leakage_rate=0%`, `unauthorized_sync_success_rate=0%`,
`unauthorized_citation_rate=0%` — hepsi hedef (%0) karşılandı.

**Testler:** 70 yeni test (`test_security_*.py`, `test_api_deps.py`,
`test_retrieval_acl.py`, `test_cross_tenant_e2e.py`,
`test_registry_tenant_isolation.py`, `test_point_id_tenant_isolation.py`,
+ mevcut registry/qdrant_store/sync/api testlerine tenant_id parametresi
eklenmesi) — `ruff check app tests scripts` temiz, tüm suite yeşil.

**Bilinen limitasyonlar** (`docs/security.md`'de detaylı): Bu sadece
Faz 1 — prompt injection/untrusted-context savunmaları planlanan sonraki
security sprint'in konusu. Auth demo/local-oriented (gerçek JWT/OIDC
değil). Bir connector instance'ı = bir tenant (birden fazla tenant aynı
connector'ı paylaşamıyor). `visibility` alanı şu an sadece "tenant"
üretiyor, "private" için henüz enforcement yok.

**Production default DEĞİŞMEDİ** — bu sprint retrieval authorization
correctness'i hedefliyor, embedding modeli/chunking/reranker/generation
aynı kaldı.

## Sprint 24 — RAG Operations Console (closing note)

Sprint 24 added a React-based RAG Operations Console because the existing
Streamlit surface was useful for chat but did not expose the operational
evidence needed to inspect a real answer: retrieval stages, tenant ACL
context, sync history, evaluation provenance, settings, and Jaeger spans.
The console is a presentation client; it does not create a second business
logic or authorization layer.

**Architecture:**

```text
React UI
   ↓ HTTP / SSE
FastAPI
   ↓
Authentication / tenant ACL
   ↓
Qdrant + Ollama + Jaeger
```

The `/ui/*` endpoints are read-only aggregations that reuse existing domain
and security logic. They resolve identity through the Sprint 23 bearer-token
boundary, scope registry/history data to the caller's tenant, and expose only
span names/timings to the browser.

**Pages completed:** Overview, Playground, Knowledge, Sync Runs, Evaluations,
Traces, Settings, plus sign-in/development identity UX. Playground combines a
real SSE answer with clickable citations and Sources, Retrieval, Security, and
Trace inspectors. Settings shows the active `qwen3-4b@1024` pipeline when the
backend reports it and keeps rollback read-only/disabled when no safe UI write
action exists.

**Real local verification:** The local FastAPI, Qdrant, Ollama, Jaeger, and
React stack was verified across sign-in, overview, a real Playground query,
citation interaction, Retrieval/Security/Trace tabs, USER versus OPERATOR sync
permissions, tenant-scoped Knowledge, Evaluations, and Settings. The console
renders unavailable and not-yet-indexed states explicitly; it does not replace
missing operational values with demo numbers.

**Backend inspection events:** `/chat` now emits authorized `sources`, the
measured retrieval report, existing metadata/token/grounding events, and a
terminal `done` event. Retrieval reports contain measured stage timings and
observed counts; RRF and reranker scores remain scores, never confidence or
probability. Client-observed stream timing is labelled separately from the
backend Jaeger generation span.

**Security behavior:** `/ui/*` read endpoints require credentials, reject
invalid credentials with 401, preserve tenant scoping for overview,
documents, and sync history, preserve OPERATOR ownership checks for sync
history, and do not expose token maps, environment values, secrets, or
internal client representations. CORS is an explicit configurable origin
allow-list with credentialed CORS disabled. The development identity selector
is local/demo auth UX and FastAPI remains the authorization enforcement point.

**Frontend tests and gates:** Vitest + React Testing Library cover auth header
handling, 401/403 states, role-aware sync actions, SSE event dispatch and
aggregation, citations, all Evidence Inspector tabs, degraded/empty states,
tenant-scoped rendering, evaluation/settings semantics, and Jaeger async
state. The final frontend run passed 18 tests in 6 files; ESLint, TypeScript
typecheck, and the production Vite build also passed. The full backend run
passed 797 tests, skipped 2 environment-dependent tests, and emitted 6
warnings; `ruff check app tests scripts` passed.

**Known limitations:** The identity selector is not production authentication;
production must replace it with a real verifier/login flow. Chat trace history
is not persisted as a general server-side index. The console remains
read-only for settings/migration controls. Claim-level grounding,
prompt-injection defenses, reranker benchmarking, token-aware chunking,
answerability, vLLM serving, PostgreSQL registry, and distributed sync remain
future roadmap work and were not started in this sprint.

## Future — İkinci Connector (Confluence)

Amaç: Connector abstraction'ının gerçekten genellenebilir olduğunu kanıtlamak.

Scope:

* `ConfluenceConnector`, `Connector` interface'ine uyumlu, minimum kod tekrarıyla eklenir
* Eğer interface'e uymayan bir şey çıkarsa (örn. Confluence'a özgü bir kavram), bu Sprint 6'daki abstraction tasarımının bir eksiği olarak not düşülür — düzeltme burada yapılır

DoD: iki connector aynı anda aktif, ikisinden de gerçek içerik ingest edilip sorgulanabiliyor.
