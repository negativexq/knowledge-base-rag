# Sprint 17.5 — Reconciliation Rollback Safety & Eval Parity (GERÇEKTEN SON sprint)

## Context

Sprint 17.4'ün kapanış notu "PROJE GERÇEKTEN VE KESİN OLARAK DONDURULDU"
diyordu, yedi dış review turunun (Sprint 15→17.4) sonunda gerçek, kanıtlanmış
bir taban çizgisine ulaşıldığı iddiasıyla. Sekizinci bir review, sistemi
baştan sona okuyarak reconciliation (Sprint 17.2) ile rollback (Sprint 16)
mekanizmalarının ETKİLEŞİMİNDE daha önce hiç test edilmemiş bir regresyon
buldu, artı üç başka gerçek bulgu. Bu sprint bunları kapatıyor.

## Kapsam ve gerekçe

### 1. EN KRİTİK — Reconciliation rollback sağlam point'leri silebiliyor

`app/ingestion/ingest.py`'deki rollback (`except Exception` / `except
asyncio.CancelledError`, satır ~394-441), Sprint 16'da tasarlandığında tek
bir varsayıma dayanıyordu: girilen try bloğu her zaman bir version
DEĞİŞİKLİĞİ (A→B) temsil eder, yani `content_hash` her zaman YENİ bir
document_version'dır ve `store.delete_version(..., content_hash)` o an
Qdrant'ta o version'a ait HİÇBİR sağlam point olmadığı için güvenlidir —
sadece bu denemenin kendi upsert'lediği partial point'leri siler.

Sprint 17.2 bu varsayımı sessizce bozdu: `index_present_and_complete`
False olduğunda (`not changed` ama reconciliation eksik/bozuk index
tespit ettiğinde) aynı `content_hash` (mevcut version) için bir "repair"
denemesi başlatılıyor — try bloğuna GİREN content_hash artık Qdrant'ta
ZATEN kısmen sağlam point'leri olan bir version olabilir. Bu denemede
batch 2'de bir hata olursa, `delete_version(..., content_hash)` o
version'a ait TÜM point'leri siler — denemenin kendi eklediklerini DEĞİL,
zaten sağlam olan orijinal point'leri de. Somut senaryo: 8 chunk'lık bir
doküman, 1'i eksik (7/8 sağlam), reconciliation repair başlatıyor, batch
2'de embed hatası → rollback devreye giriyor → 7 sağlam point de silinip
doküman 0/8 aranabilir hale düşüyor. Review'ın verdiği tam senaryo bu.

**Fix:** try bloğuna girmeden HEMEN ÖNCE, bu (source_type, source_id,
content_hash) üçlüsü için mevcut point ID'lerinin bir "before" snapshot'ını
al (`store.list_point_ids_for_version` zaten Sprint 17.3'ten beri var, ek
bir Qdrant çağrı tipi gerekmiyor). Rollback tetiklenirse (her iki branch'te
de), `delete_version` yerine: "after" point ID'lerini tekrar oku, `after -
before` farkını hesapla (yani SADECE bu deneme sırasında eklenenler) ve
sadece onları `store.delete_points(...)` ile sil.

Normal A→B senaryosunda (gerçek içerik değişikliği veya ilk ingest) bu
"before" snapshot boş küme olacağı için davranış birebir eskisi gibi kalır
— `after - {}` == `after`, yani bugüne kadarki testlerin varsaydığı "tüm
partial-new-version point'leri sil" davranışı korunur. Bu snapshot'ın
maliyeti: her ingest denemesinde bir ekstra `list_point_ids_for_version`
scroll çağrısı — sadece try bloğuna girecek dokümanlar için (skip edilen
dokümanlar bu maliyeti ödemiyor), Sprint 17.2/17.3'ün zaten kabul ettiği
"reconciliation her sync'te ekstra Qdrant çağrısı ister" trade-off'una
benzer, ayrıca dokümante edilecek.

**Test:** `tests/test_versioned_reindex.py` (veya `test_ingest_connector.py`)
içine review'ın verdiği senaryoyu birebir simüle eden bir test: 8 chunk'lık
gerçek bir doküman ingest edilir (8/8 sağlam), sonra Qdrant'tan doğrudan 1
point silinir (7/8 sağlam, registry hâlâ eski chunk_count=8 diyor — bir
sonraki sync'in `index_present_and_complete=False` görmesini sağlıyor),
`embed_fn` batch 2'de hata fırlatacak şekilde sarmalanır, sync tetiklenir,
rollback sonrası Qdrant'ta kalan point sayısının hâlâ 7 olduğu (0 değil)
doğrudan `count_for_document_version` / `list_point_ids_for_version` ile
kanıtlanır. Ayrıca normal A→B update senaryosunun (yeni içerik, multi-batch
embed hatası) Sprint 16'daki orijinal testinin hâlâ yeşil kaldığı
doğrulanacak — regresyon değil.

### 2. `SyncManager.start_run()` try/finally dışında

`app/sync/manager.py:103`, `run_id = self._history.start_run(...)` satırı
`try:` bloğunun (satır 104) DIŞINDA, ama `self._running[source_type] =
True` (satır 102) zaten atanmış durumda. `start_run` (bir SQLite INSERT)
hata fırlatırsa, exception hiçbir `except`/`finally` tarafından
yakalanmadan doğrudan çağırana yükselir — `finally: self._running[...] =
False` (satır 168-169) hiç ÇALIŞMAZ, çünkü o `finally` `try` bloğuna
bağlı ve `try`'a hiç girilmedi. Sonuç: `_running[source_type]` sonsuza
kadar `True` kalır, o connector için `trigger_sync` her zaman
`STATUS_REJECTED` döner — process restart'a kadar kilitli.

**Fix:** `run_id: str | None = None` başlangıç değeriyle, `start_run(...)`
çağrısını `try:` bloğunun İLK satırı yap. `except Exception as exc:`
branch'i `run_id is None` durumunu ayrıca ele almalı — eğer `start_run`
kendisi patladıysa, kaydedilecek bir `run_id` yok, `finish_run` çağırmadan
(zaten hata verecek bir run_id'yle) exception'ı OLDUĞU GİBİ yukarı
fırlat (`raise`), `SyncRunResult(status=ERROR)` DÖNDÜRME — mevcut
`except Exception` davranışı (ingest_connector hatalarını yutup ERROR
result'ı dönmek) sadece `ingest_connector` hatası için doğru, `start_run`
hatası için görev metninin DoD'u "trigger_sync'in hatayı yukarı verdiğini"
istiyor. `except asyncio.CancelledError` branch'i de benzer şekilde `run_id
is not None` kontrolüyle korunacak (start_run sırasında cancel edilme
teorik ama ele alınmalı).

**Test:** `history.start_run`'ı hata fırlatacak şekilde sahte (fake) bir
history objesiyle mock'la, `trigger_sync`'in exception'ı GERÇEKTEN yukarı
verdiğini (`pytest.raises`) VE hemen ardından `manager.is_running(source)`
`False` döndüğünü doğrula.

### 3. Eval/production parity

`app/evaluation/cli.py::run_golden_set`'in `search_fn`'i `search()`'i
`reranker=` parametresi VERMEDEN çağırıyor — `app/wiring.py`'nin production
chat path'i (`CrossEncoderReranker` instantiate edip `search()`'e geçiren,
satır 65/76) ile aynı pipeline'ı ÖLÇMÜYOR. README'deki Sprint 9 golden-set
sayıları (PDF recall 0.429, Markdown recall 1.0) rerank ÖNCESİ hybrid
retrieval kalitesini ölçüyor — kullanıcının gerçekte gördüğü, top-20
hybrid'den top-5'e reranked sonucu değil.

**Fix:** `run_golden_set`'e production'daki gibi bir `CrossEncoderReranker`
instantiate edilip `search_fn` içinde `search(..., reranker=reranker)`
olarak geçirilecek. `--no-reranker` bayrağı eklenecek (varsayılan: rerank
AÇIK/production-parity; bayrak verilirse rerank kapalı, pre-rerank
retrieval-only benchmark modu — CrossEncoder'ın etkisini izole ölçmek
isteyen biri için).

Golden set (`tests/fixtures/golden_set.json`, 12 soru) GERÇEK Ollama+Qdrant
+ CrossEncoderReranker'a karşı YENİDEN çalıştırılacak
(`python -m app.evaluation.cli --golden-set tests/fixtures/golden_set.json
--collection kb_eval_golden`, aynı iki-model kurulumu:
`qwen2.5:3b-instruct` generation + `qwen2.5:7b-instruct` judge). Yeni
sayılar README'ye YAZILACAK — iyileşse de kötüleşse de olduğu gibi
raporlanacak, "muhtemelen değişecek" öngörüsü doğrulanmadan varsayılmayacak.
Golden set'in fixture dokümanlarında (`golden_source.py`,
`golden_markdown_source.py`) tekrarlanan heading YOK (madde 4'ün
etkilemediği doğrulandı) — sayı değişimi sadece rerank'in eklenmesinden
gelecek.

### 4. Tekrarlanan Markdown heading identity çakışması

`app/parsing/markdown_parser.py::extract_blocks`, `heading_stack`'i her
heading satırında günceller ama `block_counts` (block_index sayacı)
SADECE `heading_path` tuple'ına göre anahtarlanıyor — aynı `heading_path`
(örn. `("Overview",)`) bir dokümanda İKİ AYRI, birbirinden uzak yerde
(örn. iki farklı H1 "# Overview" bloğu, arada başka başlıklar varken)
tekrar ortaya çıkarsa, ikinci occurrence'ın `block_index`'i BİRİNCİ
occurrence'ın devamıymış gibi sayılır — ve daha kötüsü,
`markdown_chunker.py::chunk_markdown_text`'teki `surrogate_by_heading:
dict[tuple[str,...], int]` de aynı şekilde SADECE `heading_path`'e göre
anahtarlandığı için, iki AYRI section'ın paragrafları AYNI surrogate
"sayfa" altında BİRLEŞTİRİLİYOR — iki farklı section'ın metni tek bir
chunk zincirine karışabiliyor, ve citation location'ları
(`app/llm/citation_location.py::location_for`, `heading_path`'i "/"
ile birleştiren) ayırt edilemez hale geliyor: her ikisi de
`[s.filesystem:doc/Overview]`.

**Fix:** `MarkdownBlock`'a yeni bir `heading_occurrence: int` alanı
eklenecek — `extract_blocks`, her heading satırı işlendiğinde (yeni
`heading_path` oluştuğunda) o tam path için bir occurrence sayacını
artıracak (`occurrence_by_path: dict[tuple[str,...], int]`), block'lar bu
occurrence numarasıyla etiketlenecek. `block_counts`'un anahtarı da
`(heading_path, heading_occurrence)` olacak (block_index'in occurrence'lar
arası sızmaması için). `chunk_markdown_text`'teki `surrogate_by_heading`
anahtarı `(block.heading_path, block.heading_occurrence)` olacak — iki
occurrence artık AYRI surrogate'ler, AYRI chunk'lar.

Human-facing citation label (`app/llm/prompt.py::_human_label`, "Bölüm:
Overview" gibi) DEĞİŞMEYECEK — kullanıcıya hâlâ düz heading path
gösterilecek. Ama internal citation LOCATION'ı (`citation_location.py`,
`[s.source_type:source_id/LOCATION]` formatının parçası,
[[citation_format_multisource]] Sprint 0'da karara bağlanan format)
occurrence > 0 olduğunda ayırt edici olacak, örn. ilk occurrence
`"Overview"`, ikinci occurrence `"Overview#2"` (1-indexed, insan-okunur,
occurrence 0 için suffix YOK — geriye dönük uyumluluk: tekrar etmeyen
heading'lerin location'ı hiç değişmiyor). Bu, `Chunk` modeline de bir
`heading_occurrence: int = 0` alanı eklenmesini ve bunun Qdrant payload'ına
yazılmasını gerektiriyor (`location_for`'ın payload'tan okuyabilmesi için).

**Test:** Aynı heading path'in (örn. `# Overview`) iki kez geçtiği bir
Markdown fixture'ı oluşturulacak (aralarında farklı bir heading olacak
şekilde, gerçekçi bir doküman yapısı), `chunk_markdown_text` ile chunk'lanıp
iki occurrence'ın (a) farklı chunk'lara ait olduğu (metinleri
birbirine karışmadığı) ve (b) `location_for()`'dan farklı location
string'leri ürettiği doğrudan doğrulanacak. Ayrıca tekrarlamayan (normal)
heading'lerin location'ının HİÇ değişmediği (geriye dönük uyumluluk)
mevcut testlerle zaten dolaylı doğrulanıyor — ek bir regresyon testi de
eklenecek.

## Kurallar

- Test-first, özellikle madde 1 — fix'ten ÖNCE testin GERÇEKTEN
  `count_for_document_version == 0` (ya da 7'den az) ile fail ettiği
  kanıtlanacak.
- Git commit mesajına AI co-author satırı eklenmeyecek.
- Sprint bitince `docs/PLANNING.md`'ye kapanış notu: rollback
  düzeltmesinin gerçek etkisi (before/after point sayıları), yeniden
  ölçülen golden-set sayıları (eskisiyle karşılaştırmalı), heading
  collision testinin nasıl çalıştığı.
- Bu sprint bitince README'de/PLANNING.md'de projenin GERÇEKTEN
  dondugunu netleştiren güncellenmiş bir kapanış ifadesi (sekiz review
  turu sonrası).

## Definition of Done

- Başarısız bir reconciliation repair'i artık önceden sağlam olan
  point'leri silmiyor — 8/1-eksik senaryosuyla kanıtlanmış.
- `SyncManager`, `start_run` SQLite hatasında kilitlenmiyor — testle
  kanıtlanmış.
- Eval CLI production'la aynı pipeline'ı (CrossEncoderReranker dahil)
  ölçüyor, golden-set sayıları gerçek bir koşumla güncellenmiş.
- Tekrarlanan heading'ler ayrı citation identity'sine sahip, testle
  kanıtlanmış.
- Testler ve `ruff check app tests scripts` temiz.
