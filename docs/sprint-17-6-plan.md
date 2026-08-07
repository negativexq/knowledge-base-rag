# Sprint 17.6 — Citation Schema Closure (GERÇEKTEN SON sprint)

## Context

Sprint 17.5'in kapanış notu, `heading_occurrence`'ın tekrarlanan Markdown
heading'lerini ayırt ettiğini ve mevcut, tekrarlamayan heading'ler için
"location string'i hiç değişmedi" dediğini iddia ediyordu. Dokuzuncu bir
review, bu iddianın DOĞRU ama EKSİK olduğunu buldu: `heading_occurrence`
alanı YENİ bir Chunk/payload alanı — Sprint 17.5'ten ÖNCE indexlenmiş,
DEĞİŞMEMİŞ bir dokümanın Qdrant point'lerinde bu alan hiç yok
(`payload.get("heading_occurrence") or 0` → `0` varsayılan, geriye dönük
"güvenli" görünüyor). Ama sorun bu değil — sorun, dokümanın kendisi
DEĞİŞMEDİĞİ için (`content_hash` aynı) incremental sync onu asla yeniden
indexlemiyor, yani gerçekte TEKRARLANAN heading'i olan eski bir doküman,
Sprint 17.5'in fix'i deploy edildikten SONRA bile eski (yanlış,
çakışan) point ID'leri ve location'larıyla sonsuza dek Qdrant'ta kalıyor.
`heading_occurrence`'ın kendisi doğru çalışıyor — ama SADECE yeni
ingest edilen veya gerçekten içeriği değişen dokümanlar için. Review
ayrıca location encoding'inde iki ayrı gerçek collision riski buldu.

## Kapsam ve gerekçe

### 1. EN KRİTİK — Index schema version bump (mevcut mekanizmayı yeniden kullan)

Sprint 17.1 zaten bu tam problemi çözmek için bir mekanizma inşa etti:
`app/registry/store.py::CURRENT_INDEX_SCHEMA_VERSION` +
`ensure_index_schema_version()` — kod, registry'nin index'inin
GÜVENEBİLECEĞİ bir formatta olduğunu varsayamayacağı her seferinde bu
sayıyı artırıyor (Sprint 17'nin point_id_for + source_id fix'i version
2'yi tetikledi). Sprint 17.5'in `heading_occurrence`'ı TAM OLARAK aynı
kategoride bir değişiklik: point identity'yi ve location'ı etkileyen bir
format değişikliği, content_hash'in asla yakalayamayacağı bir çeşit.
Yeni bir mekanizma icat ETMEK yerine (ki bu kendi başına bir bug
kaynağı olurdu), mevcut olanı yeniden kullan: `CURRENT_INDEX_SCHEMA_VERSION`
2'den 3'e çıkar.

Bunun pratik etkisi: version 2 (veya daha eski) bir registry ile boot
edilen app, `app/wiring.py::build_app()`'taki `ensure_index_schema_version()`
çağrısında fail-fast eder — `docker compose down -v && docker compose up`
gerektiren net bir hata, sessiz bozukluk değil. Bu, Sprint 17.1'in zaten
kabul ettiği "otomatik re-index yerine, insana söyle" politikasının
DEVAMI, yeni bir tasarım kararı değil.

**Test:** `tests/test_document_registry.py`'deki Sprint 17.1/17.2 testleri
(`test_a_registry_with_an_explicit_stale_version_row_is_detected` gibi)
zaten `CURRENT_INDEX_SCHEMA_VERSION - 1` gibi RELATİF değerler kullanıyor
— version 3'e geçtikten sonra da otomatik olarak doğru davranıyorlar
(elle güncellenmesi gerekmiyor, ama bu doğrulanacak). Ek olarak: version
2 (bir önceki gerçek sürüm) olarak açıkça damgalanmış bir registry'nin,
yeni kodun (version 3 bekleyen) `IndexSchemaMismatchError` fırlattığını
kanıtlayan bir regression testi (madde 4 ile aynı test olabilir).

### 2. Collision-safe location encoding

İki ayrı, gerçek çakışma riski:

a) **Occurrence suffix'i gerçek bir heading ile çakışabilir.** Şu anki
   `f"{location}#{occurrence + 1}"` formatı, eğer doküman GERÇEKTEN
   "# Overview#2" diye bir başlığa sahipse, "Overview"'in İKİNCİ
   occurrence'ının ürettiği location ("Overview#2") ile bu gerçek
   başlığın location'ı ("Overview#2", occurrence=0 olduğu için suffix'siz)
   birebir çakışır.
b) **Heading component'inde "/" geçmesi farklı path'leri çakıştırabilir.**
   `"/".join(heading_path)`, `["A/B"]` (tek, "/" içeren bir component) ile
   `["A", "B"]` (iki ayrı, nested component) için AYNI "A/B" string'ini
   üretir — teorik ama gerçek bir Markdown başlığı ("## A/B") bunu tetikler.

**Fix:** her heading component'i `location_for` içine girmeden önce
escape edilir (`\` → `\\`, `/` → `\/`, `#` → `\#`), escape edilmiş
component'ler unescaped `/` ile birleştirilir. Occurrence suffix'i HÂLÂ
unescaped `#` kullanıyor — ama artık bu, tek yerde kullanılan bir
"rezerve" karakter: gerçek bir heading'in içindeki her `#` escape
edildiği için, sonuçtaki string'de unescaped `#` SADECE occurrence
delimiter'ı olarak görünebilir, hiçbir gerçek heading component'i bunu
üretemez. Bu, `grounding.py`'nin `_CITATION_RE`'sini etkilemez — location
hâlâ `[^\]]+` olarak opak yakalanıyor, iç yapısı hiçbir yerde
parse edilmiyor (doğrulandı: `grep` ile tüm `location_for` tüketicileri
tarandı).

**Test 1:** dokümanda GERÇEKTEN "# Overview#2" başlığı VE ayrıca iki
tane "# Overview" başlığı olsun (toplam 3 farklı bölüm — ilk "Overview",
"Overview#2", ikinci "Overview"). Üçünün de birbirinden ayrı location
string'lerine sahip olduğu kanıtlanacak (fix öncesi: ikinci "Overview"
occurrence'ı ile gerçek "Overview#2" başlığı aynı string'i üretiyordu).

**Test 2:** heading component'i "/" içeren bir doküman (`## A/B` gibi
gerçek bir başlık) ile nested bir "A" > "B" heading path'inin AYNI
dokümanda bulunduğu senaryo — ikisinin farklı location'lara sahip
olduğu kanıtlanacak.

### 3. `run_id` tip düzeltmesi

`app/sync/manager.py::trigger_sync`'teki yerel `run_id: str | None = None`
anotasyonu yanlış — `SyncHistory.start_run()` (`app/sync/history.py`)
SQLite'ın `lastrowid`'inden gerçek bir `int` döndürüyor, `SyncRunResult.run_id`
alanı da zaten doğru şekilde `int | None` (app/sync/models.py). Sadece
Sprint 17.5'te eklenen yerel değişkenin tipi yanlış yazılmış — davranış
etkilenmiyor (Python runtime'da tip anotasyonları zorlanmıyor), ama
statik analiz/okunabilirlik için düzeltilecek: `run_id: int | None = None`.

### 4. Regression testi

Madde 1'in testi zaten bunu kapsıyor — ayrı bir test yazmaya gerek yok,
tek testte kanıtlanacak (eski/version-2 bir registry state'i simüle
edilip yeni kodun fail-fast yaptığı gösterilecek).

## Kurallar

- Test-first ilerle.
- Git commit mesajına AI co-author satırı eklenmeyecek.
- Sprint bitince docs/PLANNING.md'ye kapanış notu: yeni encoding
  şemasının nasıl çalıştığı, version 3'e geçişin gerçekten test
  edildiği.
- README'de rerank'ın PDF recall'ını düşürdüğü bulgusunun
  "araştırılmamış hipotez" olarak kaldığı zaten Sprint 17.5'te net
  şekilde yazıldı (Türkçe golden set + İngilizce eğitilmiş reranker
  olası açıklaması, "ayrıca araştırılmadı" ifadesiyle) — kontrol
  edilecek, eksikse tamamlanacak.

## Definition of Done

- Version 3'e geçiş gerçek bir eski (version 2) state ile test edilmiş.
- Yeni encoding şeması collision-safe — hem gerçek "#N" başlıklı hem "/"
  içeren heading senaryolarıyla kanıtlanmış.
- `run_id` tipi doğru (`int | None`).
- Testler ve `ruff check app tests scripts` temiz.
