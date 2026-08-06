# Sprint 2 — Document Registry

## SQLite erişimi: ham `sqlite3` mü, SQLAlchemy mi?

**Karar: stdlib `sqlite3` + ince bir DAO sınıfı (`DocumentRegistry`). SQLAlchemy yok.**

Gerekçe:

* Tek tablo, tek gerçek sorgu şekli var (bir `(source_type, source_id)` çiftini oku/yaz/sil, hash karşılaştır). ORM'in çözdüğü asıl problemler — ilişkisel join karmaşıklığı, migration yönetimi, çoklu backend taşınabilirliği — burada yok. Bir ORM eklemek "önce soyutlama sonra ihtiyaç" olurdu.
* Proje baştan beri bu tercihi yapıyor: `QdrantStore` ham `qdrant-client`'ı sarmalıyor, `OllamaClient` ham `httpx`'i sarmalıyor, `Settings` dışında hiçbir yerde bir "framework" katmanı yok. Registry'nin bu düzenden farklı davranması gerektiğini gösteren bir sinyal yok.
* M2/16GB önceliği: SQLAlchemy + (muhtemelen) Alembic ek bağımlılık, ek import süresi, ek öğrenilecek API demek — hiçbiri bu sprintin somut ihtiyacına karşılık gelmiyor.
* stdlib `sqlite3` zaten Python'un içinde — yeni bağımlılık yok.

Migration: şu an tek tablo olduğu için ayrı bir migration aracı (Alembic vb.) yok — `DocumentRegistry.__init__` bağlanırken `CREATE TABLE IF NOT EXISTS` çalıştırıyor. İleride şema gerçekten evrilmeye başlarsa (birden fazla tablo, foreign key'ler) bu karar gözden geçirilir; bugün için erken optimizasyon olur.

## Şema

```sql
CREATE TABLE IF NOT EXISTS documents (
    source_type    TEXT    NOT NULL,
    source_id      TEXT    NOT NULL,
    content_hash   TEXT    NOT NULL,
    last_synced_at TEXT    NOT NULL,  -- ISO 8601 UTC string, bkz. not aşağıda
    version        INTEGER NOT NULL,
    status         TEXT    NOT NULL,
    PRIMARY KEY (source_type, source_id)
);
```

Kararlar:

* **Primary key `(source_type, source_id)`** — Sprint 0/1'de zaten citation/grounding'in kimlik anahtarı olarak kurulan aynı çift (`[s.source_type:source_id/...]`, `check_grounding`'in `(source_type, source_id, page, paragraph)` dörtlüsü). Registry'nin de aynı kimliği kullanması, ileride "bu chunk hangi registry kaydına ait" sorusunun ekstra bir eşleme tablosu gerektirmeden cevaplanmasını sağlıyor.
* **`last_synced_at` TEXT (ISO 8601), datetime nesnesi değil** — Python 3.12, `sqlite3`'ün örtük datetime adapter/converter'larını deprecated etti (3.12 changelog). Kendi adapter'ımızı yazmak yerine en basit çözüm: `datetime.now(timezone.utc).isoformat()` ile yaz, okurken `datetime.fromisoformat()` ile parse et. Ekstra bağımlılık ya da deprecated API kullanımı yok.
* **`version`** — kayıt ilk oluşturulduğunda `1`; `content_hash` bir önceki kayıttan FARKLIYSA bir sonraki upsert'te `version += 1`; hash aynıysa (aynı içerik yeniden senkronize edildi) version DEĞİŞMİYOR, sadece `last_synced_at` tazeleniyor. Bu, Sprint 4'ün "sadece değişen içerik yeniden indekslenir" mantığının registry tarafındaki temelini oluşturuyor.
* **`status`** — bu sprintte gerçek bir durum makinesi yok (senkronizasyon Sprint 4'te geliyor), ama alan DoD'de isteniyor ve Sprint 4/7'nin (`sync geçmişi başarı/hata`) üzerine oturacağı yer burası. Şimdilik serbest bir `str`, varsayılan `"active"` — `upsert_document` çağıran tarafın `status` geçmesine izin veriyor (örn. ileride bir sync hata verirse `"error"` yazılabilir), ama bu sprint hiçbir yerde otomatik olarak `"error"` üretmiyor.

## CRUD API

Üç ayrı ilkel yerine (`insert`, `update`, ayrıca "var mı yok mu" kontrolü) tek bir `upsert_document` tercih edildi:

```python
def upsert_document(self, source_type, source_id, content_hash, status="active") -> DocumentRecord: ...
def get_document(self, source_type, source_id) -> DocumentRecord | None: ...
def delete_document(self, source_type, source_id) -> None: ...
def has_changed(self, source_type, source_id, content_hash) -> bool: ...
def list_documents(self, source_type: str | None = None) -> list[DocumentRecord]: ...
```

Gerekçe — bu da gerçek kullanım yerinden çıkarıldı (Sprint 1'deki "varsayımsal arayüz değil, gerçek çağrı şekli" ilkesiyle aynı): Sprint 4'teki bir sync döngüsü her zaman "bu dokümanı az önce senkronize ettim, kaydı güncel tut" der — dokümanın registry'de olup olmadığını ÖNCEDEN bilmiyor/bilmesine gerek yok. Çağıran tarafı "önce var mı diye bak, sonra insert ya da update'e karar ver" akışına zorlamak gereksiz bir katman olurdu; SQL tarafında zaten `INSERT ... ON CONFLICT(source_type, source_id) DO UPDATE` tek sorguda hallediyor. `has_changed` ayrı bir metot çünkü DoD'nin asıl kanıtlamak istediği şey bu — "değişti mi" sorusu, `get_document` + hash karşılaştırmasına sarılmış, çağıran tarafın kendi karşılaştırma mantığı yazmasını gerektirmeyecek şekilde.

`has_changed(source_type, source_id, content_hash)`:
* Registry'de hiç yoksa → `True` (yeni doküman, "değişti" sayılır — ilk kez görülüyor).
* Registry'de var ve hash aynıysa → `False`.
* Registry'de var ve hash farklıysa → `True`.

## Test stratejisi

* **Gerçek bir SQLite dosyasına karşı** (`tmp_path / "registry.db"`), `:memory:` değil — production-rag-platform'un Qdrant `:memory:` modunun gerçek sunucudan farklı davrandığı (filtre + fusion sorgularını sessizce yok sayması) dersinden hareketle, aynı riskin SQLite'ta da olabileceği varsayılıyor. Gerçek dosyaya yazan bir test aynı zamanda ikinci bir bağlantıyla verinin dosyada kalıcı olduğunu da kanıtlıyor — `:memory:` bunu gösteremez.
* `tests/test_document_registry.py`: şema oluşturma, upsert (yeni + var olanı güncelleme + version artışı + version'ın hash aynıyken artmaması), get, delete, has_changed (üç durum), list_documents (tümü + source_type filtresi), ve iki ayrı bağlantı ile dosya kalıcılığı testi.

## DoD doğrulama planı

1. `pytest -q` yeşil, `ruff check` temiz.
2. Somut test: bir doküman `upsert_document` ile kaydedilir → `has_changed(..., aynı_hash)` `False` döner → `upsert_document` FARKLI bir hash ile tekrar çağrılır → `has_changed(..., eski_hash)` artık `True` döner, `get_document(...).version` bir artmış olur.
