# Sprint 3 — Filesystem Connector + Multi-format Parsers

## `source_type`'ın anlamı değişiyor — bilinçli bir revizyon

Sprint 0'da `source_type` dosya FORMATI anlamına geliyordu (`"pdf"`). Bu sprint `Connector` soyutlamasını getiriyor ve DoD açıkça `[s.filesystem:.../...]` formatında citation istiyor — yani `source_type` artık dokümanın **hangi connector/kaynaktan geldiğini** ifade ediyor (`"filesystem"`, ileride `"notion"`, `"confluence"`), format'ı değil. Bu daha tutarlı: aynı connector (örn. Confluence) hem HTML hem PDF eki döndürebilir; kullanıcıya "bu bilgi nereden geldi" sorusunun cevabı format değil kaynaktır. Format (pdf/markdown) artık sadece hangi PARSER'ın kullanılacağını belirleyen dahili bir sinyal (`ConnectorDocument.content_type`), citation'a hiç sızmıyor.

Geriye dönük uyumluluk notu: Sprint 0/1 testlerinde `source_type="pdf"` gibi değerler hâlâ geçerli, keyfi string'ler olarak kullanılabilir (mekanizma source_type'ın DEĞERİNE bağımlı değil) — sadece citation/grounding'in TUPLE ŞEKLİ değişiyor (aşağıya bakın), `source_type`'ın "pdf" mi "filesystem" mi olduğu testler için önemli değil.

## Markdown location şeması — "bunu net tanımla"

PDF'in `page_number`/`paragraph_index`'i markdown'a doğrudan uygulanamaz (sayfa kavramı yok). Karar:

* Markdown parser (`app/parsing/markdown_parser.py::extract_blocks`) metni blank-line'larla ayrılmış bloklara (paragraf) böler, her bloğu o anki **heading stack**'e (`#`→H1, `##`→H2, ... en yakın kapsayan başlıklar zinciri) etiketler: `heading_path: tuple[str, ...]`, örn. `("Kurulum", "Adım 1")`. Fenced code block (```` ``` ````) blank-line'larına göre bölünmüyor — tek blok olarak kalıyor.
* `block_index`, PDF'in sayfa-içi `paragraph_index`'inin markdown analoğu: her yeni heading_path'te 0'dan başlar.
* **Citation location**: `heading_path` varsa `"/".join(heading_path)` (örn. `"Kurulum/Adım 1"`); yoksa (ilk başlıktan önceki içerik — nadir) PDF tarzı `"{page_number}/{paragraph_index}"`'e düşer. Bu ikinci durum kabul edilen bir sınırlama: gerçek markdown dosyaları neredeyse her zaman bir başlıkla başlar, ekstra bir alan/karmaşıklık eklemeye değmez.
* Örnek tag: `[s.filesystem:readme_md/Kurulum/Ad%C4%B1m%201]` gibi URL-encode YOK — location düz metin, `/` zaten ayraç olarak kullanıldığı için heading isimlerindeki `/` karakterleri location'ı bölebilir ama bu bir citation TAG'i, URL değil; grounding sadece tam string eşitliği kontrol ediyor, bölmüyor — pratik bir sorun değil.

## `Chunk` modeli — geriye dönük uyumlu ekleme

`Chunk`'a `heading_path: tuple[str, ...] = ()` eklendi (sona, varsayılanla) — tüm mevcut `Chunk(...)` çağrıları (Sprint 0/1 testleri dahil) değişmeden çalışmaya devam ediyor. PDF chunk'larında hep `()`. `page_number`/`paragraph_index` markdown chunk'larında da DOLU kalıyor ama artık gerçek sayfa/paragraf değil, dahili gruplama kimlikleri (heading_path'e göre üretilen surrogate id + o başlık altındaki blok index'i) — citation'a sızmıyorlar (`heading_path` doluyken location hesaplaması onları kullanmıyor).

## Citation/grounding genellemesi — gerekli, kaçınılmaz bir değişiklik

Markdown location'ı iki zorunlu tamsayıya sığmadığı için `grounding.py`'nin `\[s\.([\w\-]+):([\w\-]+)/(\d+)/(\d+)\]` regex'i (2 sayısal grup) artık yanlış varsayım. Yeni:

```python
_CITATION_RE = re.compile(r"\[s\.([\w\-]+):([\w\-]+)/([^\]]+)\]")
```

`GroundingResult.citations_found`/`ungrounded_citations` tipi `list[tuple[str,str,int,int]]`'den `list[tuple[str,str,str]]`'e değişiyor (`(source_type, source_id, location)` üçlüsü). `citation_tag(source_type, source_id, page, paragraph)` → `citation_tag(source_type, source_id, location)`. Ortak bir `app/llm/citation_location.py::location_for(payload) -> str` fonksiyonu hem `prompt.py::build_context` (tag üretimi) hem `grounding.py::check_grounding` (tag doğrulama) tarafından kullanılıyor — ikisinin AYNI mantıkla location hesapladığından emin olmak için (Sprint 0'ın "citation aynı yerden, aynı mantıkla üretilip doğrulanmalı" dersiyle aynı).

Bunun blast radius'u: `app/llm/{prompt,grounding}.py`, `app/ui/citation_formatting.py` (regex), `app/ingestion/qdrant_store.py` (payload'a `heading_path` eklendi), `prompts/answer_v1.txt`/`answer_v2.txt` (metinde "PAGE/PARAGRAPH" yerine "LOCATION"), ve eski 4-tuple varsayan testler (`test_grounding.py`, `test_prompt.py`, `test_generate.py`, `test_generate_provider_agnostic.py`, `test_pipeline_e2e_hermetic.py`, `test_qdrant_store.py`'nin payload eşitlik kontrolü). Bu testler YENİ 3-tuple/location string şekline güncellenecek — `source_type` DEĞERLERİ (ör. "pdf") test verisi olarak kalabilir, sadece tuple şekli/citation_tag imzası değişiyor.

## `Connector` interface'i — gerçek kullanım yerinden çıkarıldı

`ingest_connector` (bu sprintin orkestrasyon fonksiyonu) her doküman için: `list_documents()` ile numaralandırır → `get_content_hash()` ile registry'ye yazacağı hash'i alır → parse+chunk için `document.path`'i kullanır (bkz. aşağıdaki not) → `fetch_content()`/`get_content_hash()` connector-agnostik registry/hash bookkeeping için var.

```python
@dataclass(frozen=True)
class ConnectorDocument:
    source_id: str        # citation-tag-safe (slugify), source_type ile birlikte registry PK
    content_type: str     # "pdf" | "markdown" — hangi parser kullanılacağını belirler
    path: Path | None = None  # filesystem-specific; uzak connector'larda (Sprint 6+) None kalabilir

class Connector(Protocol):
    source_type: str
    def list_documents(self) -> list[ConnectorDocument]: ...
    def fetch_content(self, document: ConnectorDocument) -> bytes: ...
    def get_content_hash(self, document: ConnectorDocument) -> str: ...
```

**Bilinçli sınırlama:** `ingest_connector`'ın bu sprintteki tip imzası `LocalFilesystemConnector`'a özel (`Connector` Protocol'üne değil) — Sprint 1'deki ilkeyle aynı: gerçekte var olmayan bir ikinci connector'a göre soyutlamak spekülasyon olurdu. `Connector` Protocol'ü ileride (Sprint 6, Notion) gerçek bir ikinci implementasyon ortaya çıkınca `ingest_connector`'ı genelleştirmenin ne gerektirdiğini KANITLAYACAK — muhtemelen `document.path` yerine `content_type`+`fetch_content()` bytes'ının parser'lara doğrudan verilmesi gerekecek (PDF/Markdown parser'ları şu an dosya yolundan okuyor, bytes'tan değil — bu da bu sprintin kapsamı dışında bırakılan bir genelleme).

## `LocalFilesystemConnector`

* `source_type = "filesystem"`.
* Klasörü **recursive DEĞİL** tarıyor (`iterdir()`, Sprint 0'ın `glob("*.pdf")` presedanıyla tutarlı) — alt klasör desteği spekülatif, gerçek ihtiyaç çıkınca eklenir.
* `source_id`, dosya adının uzantı DAHİL slugify'i (`slugify(name, strip_extension=False)` — `app/shared/slug.py`'ye eklenen yeni opsiyonel parametre). Uzantı atılırsa `handbook.pdf` ve `handbook.md` aynı `source_id`'ye çarpışır (`registry`'nin `(source_type, source_id)` primary key'ini bozar) — bu yüzden Sprint 0'ın PDF-only `slugify()` davranışından burada BİLEREK ayrılıyoruz.
* `get_content_hash()`, `compute_doc_id()` ile aynı algoritma (sha256 of raw bytes) — `ingest_connector` bu hash'i hem registry'ye hem de `chunk_document`/`chunk_markdown_document`'a (yeni `doc_id` override parametresiyle) geçiyor, dosya iki kere hash'lenmiyor.

## `ingest_connector` — registry entegrasyonu

Her doküman başarıyla chunk'lanıp Qdrant'a yazıldıktan SONRA `registry.upsert_document(connector.source_type, document.source_id, content_hash)` çağrılıyor (kısmi bir hata registry'de yanlış bir "başarılı" izlenimi bırakmasın diye). **Bilinçli sınırlama (DoD'de de belirtildiği gibi):** bu sprintte incremental sync YOK — her çalıştırma TÜM klasörü tarayıp yeniden ingest ediyor, hash aynı olsa bile. `registry.upsert_document` çağrılıyor olması `has_changed()`'in doğru cevap vermesini sağlıyor (Sprint 2'nin DoD'u hâlâ geçerli), ama `ingest_connector` bu bilgiyi henüz "atla" kararı için KULLANMIYOR — bu, Sprint 4'ün tam konusu.

## Test stratejisi

* Sprint 0/2'nin kurduğu ilke aynen sürüyor: gerçek dosyalarla test (gerçek bir geçici klasörde gerçek `.pdf` + `.md` dosyaları, mock değil).
* Yeni: `tests/test_markdown_parser.py`, `tests/test_markdown_chunker.py`, `tests/test_connector_filesystem.py`, `tests/test_ingest_connector.py`.
* Uçtan uca: gerçek bir klasörde PDF+Markdown karışımı `ingest_connector` ile ingest edilip hem Qdrant'ta (`:memory:`, chunk sayıları + `heading_path`/citation location doğru) hem registry'de (gerçek SQLite dosyası, iki doküman da doğru `source_type="filesystem"` ile) doğrulanıyor.
* Değişen tuple şekli nedeniyle güncellenen mevcut testler: `test_grounding.py`, `test_prompt.py`, `test_generate.py`, `test_generate_provider_agnostic.py`, `test_pipeline_e2e_hermetic.py`, `test_qdrant_store.py`, `test_citation_formatting.py`.

## DoD doğrulama planı

1. `pytest -q` yeşil, `ruff check` temiz.
2. Gerçek bir klasörde `handbook.pdf` + `readme.md` → `ingest_connector` → her ikisi de registry'de `source_type="filesystem"` ile görünüyor, farklı `source_id`'lerle.
3. Qdrant'taki markdown chunk'ları `heading_path` taşıyor, PDF chunk'ları taşımıyor (`()`); ikisinin de citation tag'i `[s.filesystem:<source_id>/<location>]` şeklinde ve `check_grounding` her ikisini de doğru doğruluyor.
