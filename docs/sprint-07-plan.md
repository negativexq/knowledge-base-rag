# Sprint 7 — Sync Scheduler

## Scheduler mekanizması: APScheduler değil, düz `asyncio` döngüsü

Sprint 2'nin SQLite/SQLAlchemy kararıyla aynı usul: gerçekten düşünüldü, varsayılmadı.

Gerçek ihtiyaç: N connector'ın (şu an 2: filesystem, notion) HER BİRİ için sabit bir aralıkta (`sync_now()`'u tekrar tekrar çağıran basit bir zamanlayıcı) periyodik tetikleme + manuel tetikleme + aynı connector için çakışmayı engelleme. Bu, cron ifadeleri, kalıcı job store'lar (restart sonrası kaldığı yerden devam), misfire/coalescing gibi APScheduler'ın çözdüğü problemlerin HİÇBİRİNİ gerektirmiyor — hepsi "sabit aralık" (`interval`) senaryosu.

**Karar: `asyncio.create_task` + `while True: await asyncio.sleep(interval); ...` deseninde düz bir `SyncScheduler`, APScheduler YOK.** Gerekçe: (1) M2/hafiflik önceliği — yeni bir bağımlılık, yeni bir "nasıl çalışır" öğrenme yükü getirmeden aynı ihtiyacı karşılıyor; (2) proje zaten bu düzende — Sprint 2 SQLAlchemy'yi, Sprint 6 web-crawling'i, hep "gerçek ihtiyaç kanıtlanmadan araç eklemeyelim" ilkesiyle erteledi; (3) test edilebilirlik — düz bir asyncio döngüsü kısa interval'larla (örn. 0.05s) gerçek zamanlı test edilebiliyor, APScheduler'ın kendi zamanlama iç mekanizmasını mock'lamak gerekmiyor. Celery zaten kullanıcı tarafından da makul şekilde elenmiş (mesaj kuyruğu/worker altyapısı, tek-worker yerel bir uygulama için aşırı).

Eğer ileride gerçek ihtiyaç ortaya çıkarsa (örn. cron-tarzı zamanlar — "her gün 03:00", ya da process restart'ları arasında kalınan yerden devam), o zaman APScheduler'a geçiş değerlendirilir — şimdi spekülatif olurdu.

## Kilit stratejisi: connector başına non-reentrant bayrak, `asyncio.Lock` DEĞİL

Aynı connector için iki sync'in çakışmaması gerekiyor (manuel tetikleme + periyodik job aynı anda). İki tasarım karşılaştırıldı:

* **`asyncio.Lock` + `async with lock:`** — doğal seçenek gibi görünüyor, ama semantiği "kilit boşalana kadar BEKLE" (queue), oysa DoD "biri beklerken/REDDEDİLİRKEN diğeri çalışıyor" diyor — reddetme de kabul edilen bir davranış. Ayrıca `lock.locked()` kontrolü ile `await lock.acquire()` arasında (yanlış yazılırsa) bir race penceresi açılabilir.
* **Connector başına düz bir `bool` bayrak** (`self._running: dict[str, bool]`), check-and-set arasında HİÇBİR `await` YOK — bu, tek-thread'li asyncio'nun cooperative scheduling modelinde ATOMIK: `if self._running[x]: return rejected; self._running[x] = True` iki satırı arasında event loop başka bir coroutine'e geçemez (arada await noktası yok).

**Karar: bayrak tabanlı, REDDET (queue etme).** `trigger_sync(source_type)` çağrıldığında o connector için zaten bir sync çalışıyorsa ANINDA `status="rejected_already_running"` ile döner (bekletmeden) — bu, manuel API endpoint'inin HTTP isteğini belirsiz süre bloklamamasını sağlıyor (409 Conflict ile anında cevap). Gerçek bir race condition testiyle kanıtlanacak: iki `trigger_sync()` çağrısı `asyncio.gather` ile GERÇEKTEN eşzamanlı başlatılıyor (embed_fn yapay olarak yavaşlatılmış), sadece biri gerçek işi yapıyor, diğeri anında reddediliyor — Qdrant'a yazma sayısı sayılarak kanıtlanıyor.

## `sync_runs` şeması — Sprint 10'un "Sync Status" sayfasının veri kaynağı

Sprint 2'nin registry'siyle AYNI SQLite dosyasında (`registry_db_path`) yeni bir tablo — ayrı bir DB dosyası açmaya gerek yok, sqlite tek dosyada çoklu tabloyu zaten destekliyor:

```sql
CREATE TABLE IF NOT EXISTS sync_runs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    source_type     TEXT    NOT NULL,
    trigger         TEXT    NOT NULL,  -- "scheduled" | "manual"
    status          TEXT    NOT NULL,  -- "running" | "success" | "error"
    started_at      TEXT    NOT NULL,
    finished_at     TEXT,
    files_processed INTEGER,
    files_skipped   INTEGER,
    files_deleted   INTEGER,
    chunks_upserted INTEGER,
    error_message   TEXT
);
```

`IngestStats`'ın (Sprint 3/4) dört alanı (`files_processed/files_skipped/files_deleted/chunks_upserted`) birebir buraya yazılıyor — Sprint 10'un "kaç doküman değişti/silindi" ihtiyacı zaten `ingest_connector`'ın döndürdüğü veriden geliyor, yeni bir hesaplama gerekmiyor. `started_at`/`finished_at` Sprint 2'nin ISO 8601 TEXT kararıyla tutarlı (Python 3.12'nin deprecated sqlite3 datetime adapter'larından kaçınmak için).

## API endpoint — senkron, arka plan görevi YOK

`POST /sync/{source_type}` sync BİTENE KADAR bekliyor, sonucu döndürüyor — arka planda çalıştırıp ayrı bir durum sorgulama endpoint'i eklemek bu sprintte spekülatif olurdu (gerçek veri boyutları/UI ihtiyacı Sprint 10/11'de netleşmeden). Test edilebilirlik için `app/main.py`, modül yüklenirken gerçek Qdrant/Ollama'ya bağlanan bir singleton YERİNE bir `create_app(sync_manager, history) -> FastAPI` FACTORY fonksiyonu — testler gerçek servislere dokunmadan sahte bileşenlerle `TestClient(create_app(...))` kurabiliyor. Gerçek servislerle uçtan uca çalıştırma (uvicorn ile deploy) Sprint 11'in (docker compose) konusu — bu sprint sadece endpoint'in GERÇEKTEN çalıştığını (FastAPI TestClient ile, ASGI üzerinden gerçek request/response) kanıtlıyor.

Zaten bilinmeyen bir `source_type` için `404`, çalışan bir sync'e ikinci istek için `409` dönüyor.

## Config

```python
filesystem_sync_interval_seconds: int = 300   # 5 dakika
notion_sync_interval_seconds: int = 1800      # 30 dakika
```

`SyncScheduler` genel bir `dict[str, float]` alıyor (source_type → interval) — Settings'teki connector-başına-alan deseni (Sprint 1'in `claude_*`, Sprint 6'nın `notion_api_key` gibi) korunuyor, ama scheduler'ın kendisi connector-özel değil, tamamen generic.

## Test stratejisi

* `SyncHistory`: gerçek SQLite dosyasına karşı (Sprint 2 presedansı).
* `SyncManager`: gerçek eşzamanlılık testi (`asyncio.gather`, yapay gecikmeli sahte embed_fn, sayan bir `QdrantStore` sarmalayıcısı — Sprint 4'ün `_CountingStore` deseniyle aynı).
* `SyncScheduler`: kısa interval (`0.05s`) ile gerçek zamanlı test, birden fazla tetiklemenin gerçekleştiği sayılarak kanıtlanıyor.
* API: `fastapi.testclient.TestClient` ile gerçek ASGI request/response, sahte `SyncManager`/`SyncHistory` enjekte edilerek.

## DoD doğrulama planı

1. `pytest -q` yeşil, `ruff check` temiz.
2. Periyodik job kısa bir interval'la gerçekten config'e göre tetikleniyor (testte kanıtlı).
3. Manuel tetikleme (`POST /sync/{source_type}`) gerçek bir ASGI isteğiyle çalışıyor.
4. Çakışan iki sync denemesi: biri gerçekten çalışıyor, diğeri anında reddediliyor, Qdrant'a sadece BİR sync'in yazdığı sayılarak kanıtlanıyor.
5. `sync_runs` tablosuna her koşum (başarı/hata, süre, değişen/silinen doküman sayısı) gerçekten yazılıyor.
