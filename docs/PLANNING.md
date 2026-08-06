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
