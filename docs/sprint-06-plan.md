# Sprint 6 — Web Page Parser + İlk Uzak Connector (Notion)

## `Connector` interface'inde Sprint 3'ten beri saklı kalmış iki varsayım

Sprint 3'ün notu aynen şöyleydi: *"ingest_connector'ın tip imzası LocalFilesystemConnector'a özel... Sprint 6'da gerçek bir ikinci connector eklendiğinde bu dispatch mekanizması yeniden değerlendirilecek."* İşte o an geldi — gerçekten ikinci bir implementasyon (Notion) yazılınca iki gerçek varsayım ortaya çıktı:

**1) Protocol metotları SENKRON tanımlıydı — bir ağ connector'ı için bu çalışmaz.** `Connector.list_documents()`/`fetch_content()`/`get_content_hash()` `def ...` idi (`async def` değil). `LocalFilesystemConnector` için sorun değildi (disk I/O hızlı, zaten Sprint 2'nin `DocumentRegistry`/`QdrantStore` senkron kalma presedansıyla tutarlıydı). Ama `NotionConnector` gerçek ağ çağrıları yapmak ZORUNDA (`httpx.AsyncClient` ile) — senkron bir metot içinde `await` kullanılamaz. **Karar: üç metot da `async def` oldu.** Bu, `LocalFilesystemConnector` için bedelsiz (disk I/O'yu `async def` içine sarmak, içeride `await` olmasa bile geçerli Python — hiçbir performans kaybı yok), ama `NotionConnector`'ı gerçekten mümkün kılıyor. Senkron bir connector'ın async bir arayüzü karşılaması her zaman mümkündür; tersi (async bir connector'ı senkron bir arayüze sığdırmak, engelleyici `asyncio.run()` hack'leri olmadan) mümkün değildir — bu yüzden "async'e genelleştir" doğru yön, tersi değil.

**2) `get_content_hash()` her zaman TAM İÇERİĞİ getirmeyi varsayıyordu.** `LocalFilesystemConnector.get_content_hash()` içeriği okuyup (`fetch_content()`) hash'liyor — yerel diskte bedelsiz. Ama Notion'da "değişti mi" kontrolü (sync'in HER ÇALIŞTIRMADA yaptığı `has_changed()` sorgusu, Sprint 4) için TÜM sayfa bloklarını çekmek (`GET /blocks/{id}/children`, sayfalanmış) hem yavaş hem gereksiz API çağrısı — incremental sync'in tüm amacını (Sprint 4: "değişmeyeni atla, hiç dokunma") baltalar. Notion'ın `search` endpoint'i zaten her sayfa için ucuza `last_edited_time` veriyor — içerik gerçekten değiştiğinde bu alan DA değişiyor (Notion'ın garantisi). **Karar: `ConnectorDocument`'a `etag: str | None = None` eklendi** (yeni bir connector-özel-ama-paylaşılan alan — `path`'in zaten kurduğu presedansla aynı desen). `NotionConnector.list_documents()` her sayfa için `etag=last_edited_time` dolduruyor; `get_content_hash()` SADECE bu `etag`'i hash'liyor, `fetch_content()`'i hiç çağırmıyor. `LocalFilesystemConnector` `etag` kullanmıyor (hep `None`), davranışı değişmedi.

Bu iki düzeltme dışında `Connector` Protocol'ü (üç metot + `source_type`) Sprint 3'te tasarlandığı gibi kaldı — gerçek ikinci implementasyon bunu doğruladı.

## Web sayfası parser — Markdown location şemasının yeniden kullanımı

`trafilatura.extract(html, output_format="markdown", include_formatting=True)` gerçekten test edildi (varsayılmadı): nav/header/footer/aside gibi "boilerplate" içeriği doğru şekilde ATIYOR, ana içeriği `#`/`##` başlık işaretleyicileriyle GERÇEK markdown olarak veriyor (bkz. bu planın hazırlığında yapılan canlı deney). Bu, Sprint 3'ün markdown location şemasını (heading-path) SIFIRDAN yeniden yazmak yerine DOĞRUDAN yeniden kullanmayı mümkün kılıyor:

```
HTML → trafilatura (markdown çıktı) → app/parsing/markdown_parser.py::extract_blocks() → chunk_markdown_text()
```

Bunu mümkün kılmak için `app/ingestion/markdown_chunker.py::chunk_markdown_document()`'ın metin-işleme çekirdeği `chunk_markdown_text(text, source_id, source_type, doc_id, ...)` olarak ayrıştırıldı (dosyadan okuma sorumluluğu dışarıda kaldı) — `chunk_markdown_document`'ın PUBLIC imzası DEĞİŞMEDİ (geriye dönük uyumlu, mevcut testler dokunulmadan geçiyor). Hem web parser hem `NotionConnector` (aşağıda) bu ORTAK metin tabanlı fonksiyonu kullanıyor — kod tekrarı yok.

**Bu sprintte `WebConnector` YOK — bilinçli kapsam sınırı.** DoD'nin tam metni: *"bir web sayfası gerçekten parse edilip location'lı chunk'lara ayrılıyor"* — bu sadece PARSE+CHUNK kanıtı istiyor, uçtan uca ingest değil. Bir `WebConnector` (URL listesi, crawling, `list_documents()` kavramı) tanımlamak bu sprintte spekülatif olurdu — gerçek ihtiyaç (hangi URL'ler, nasıl keşfediliyor) belli değil. `app/parsing/web_parser.py` + `app/ingestion/web_chunker.py` gerçek bir HTML fixture'ıyla kanıtlanıyor, connector'a bağlanması ileri bir sprintin (ihtiyaç netleşince) konusu.

## `NotionConnector` — gerçek API şekli (varsayılmadı, resmi API referansına göre)

* **Auth:** `Authorization: Bearer <token>` + `Notion-Version: 2022-06-28` header'ı zorunlu.
* **`list_documents()`:** `POST /v1/search` (`filter: {property: "object", value: "page"}`, `page_size: 100`, `start_cursor` ile sayfalama, `has_more`/`next_cursor` yanıtta). Her sonuç: `id` (UUID, doğrudan `source_id` olarak kullanılıyor — zaten tag-safe, `slugify` gerekmiyor) + `last_edited_time` (→ `etag`).
* **`fetch_content()`:** `GET /v1/blocks/{page_id}/children` (sayfalanmış, aynı `has_more`/`next_cursor` deseni). Desteklenen blok tipleri: `heading_1/2/3` (→ `#`/`##`/`###` satırı), `paragraph`/`bulleted_list_item`/`numbered_list_item`/`quote`/`to_do`/`code` (→ düz metin, `rich_text[].plain_text` birleştirilerek). Diğer blok tipleri (image, table, divider, embed, ...) atlanıyor — metin içermiyorlar ya da MVP kapsamı dışı, bilinçli bir sınır (LocalFilesystemConnector'ın "recursive değil" kararıyla aynı ölçülülük). **Alt bloklar (nested children) ÇEKİLMİYOR** — sadece sayfanın top-level block'ları. Gerçek ihtiyaç (örn. toggle/nested list içeriği) ortaya çıkarsa genişletilir.
* **Rate limit / backoff:** Notion'ın belgelenen limiti ortalama ~3 istek/saniye. `429` yanıtında `Retry-After` header'ı varsa onu, yoksa üstel geri çekilmeyi (1s/2s/4s) kullanan basit bir retry (`DEFAULT_MAX_RETRIES=3`) eklendi. Diğer 4xx/5xx'lerde `NotionUnreachableError` (Ollama/Claude'un `*UnreachableError` deseniyle aynı).

## Gerçek API'ye karşı test edildi mi? HAYIR — açıkça belgeleniyor

Bu makinede `NOTION_API_KEY` yok, `.env` yok (Sprint 1'deki `ANTHROPIC_API_KEY` durumunun birebir aynısı). `NotionConnector`'ın testleri `httpx.MockTransport` ile GERÇEK Notion API JSON şekillerini (resmi dokümantasyondan alınan örnek response'lar) simüle ediyor — gerçek network çağrısı yok. Sprint 1'in `test_provider_comparison_e2e.py` desenini izleyen, `NOTION_API_KEY` set edilirse otomatik çalışacak, yoksa otomatik skip olan bir gerçek-API testi de ekleniyor. DoD'nin "gerçek API varsa gerçek, yoksa açıkça belgelenmiş mock'lı" şartı böyle karşılanıyor.

## `ingest_connector` güncellemesi

* `content_type == "notion"` dalı eklendi: `content_bytes = await connector.fetch_content(document); chunks = chunk_markdown_text(content_bytes.decode("utf-8"), document.source_id, connector.source_type, doc_id=content_hash, ...)`.
* Fonksiyonun tip imzası artık `connector: Connector` (generic Protocol) — Sprint 3/4'te `LocalFilesystemConnector`'a özel bırakılmıştı, gerçek ikinci implementasyon bunu genellemeyi gerektirdi ve doğruladı.
* `connector.list_documents()`, `connector.get_content_hash(document)`, `connector.fetch_content(document)` çağrılarına `await` eklendi (yukarıdaki async değişikliğin doğal sonucu). `registry.*`/`store.*` çağrıları SENKRON kalıyor, değişmedi.

## Test stratejisi

* `NotionConnector` birim testleri: `httpx.MockTransport` ile gerçek Notion JSON şekilleri (arama sayfalama, blocks sayfalama, 429+Retry-After, diğer hatalar).
* `chunk_markdown_text`/web parser: gerçek bir HTML fixture (nav/footer/reklam kirliliği + gerçek başlıklı içerik) ile uçtan uca parse+chunk kanıtı.
* `ingest_connector` + `NotionConnector` + gerçek Qdrant (`:memory:`) + gerçek SQLite registry: mock'lı Notion transport üzerinden TAM bir ingest, `source_type="notion"` ile registry kaydı, `[s.notion:<page_id>/<heading>]` formatında aranabilir citation, VE Sprint 4'ün sync üçlüsünün (skip/update/delete) `etag` üzerinden Notion için de çalıştığının kanıtı (aynı senaryolar, `tests/test_sync_scenarios.py`'nin Notion karşılığı).

## DoD doğrulama planı

1. `pytest -q` yeşil, `ruff check` temiz.
2. Gerçek bir HTML sayfası parse edilip location'lı (heading-path) chunk'lara ayrılıyor — testte kanıtlı.
3. `NotionConnector`, `Connector` Protocol'ünü GERÇEKTEN karşılıyor (`isinstance` ile async Protocol'e karşı doğrulanmış) ve mock'lı uçtan uca ingest ile `source_type="notion"` kaydı üretiyor.
4. Sprint 2-4'ün registry/sync mantığının Notion için değişiklik gerektirmeden çalıştığı (ya da gerektirdiyse ne değiştiği — burada async+etag) net.
