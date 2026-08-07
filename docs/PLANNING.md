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

## Sprint 12 (stretch) — İkinci Connector (Confluence)

Amaç: Connector abstraction'ının gerçekten genellenebilir olduğunu kanıtlamak.

Scope:

* `ConfluenceConnector`, `Connector` interface'ine uyumlu, minimum kod tekrarıyla eklenir
* Eğer interface'e uymayan bir şey çıkarsa (örn. Confluence'a özgü bir kavram), bu Sprint 6'daki abstraction tasarımının bir eksiği olarak not düşülür — düzeltme burada yapılır

DoD: iki connector aynı anda aktif, ikisinden de gerçek içerik ingest edilip sorgulanabiliyor.
