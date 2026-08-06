# Sprint 4 — Incremental Sync (Filesystem üzerinde doğrulama)

## Açık soru: yetim chunk'lar nasıl önlenir?

Planın önerisi "doc_id bazlı: önce eski chunk'ları sil, sonra yenilerini yaz" idi. Bunu düşünüp **`doc_id` yerine `(source_type, source_id)` bazlı silme** kararlaştırıldı. Gerekçe:

`doc_id`, Sprint 3'te dosya içeriğinin sha256 hash'i (`connector.get_content_hash()`) — yani bir dosyanın içeriği her değiştiğinde `doc_id` de değişiyor. "Eski `doc_id`'ye göre sil" stratejisi şunu gerektirir: sync, silmeden ÖNCE registry'den dokümanın ESKİ `content_hash`'ini okumalı (yeni hash zaten elimizde, eskisi değil). Bu ekstra bir okuma adımı ve iki hash'i (eski/yeni) doğru sırada kullanma sorumluluğu getiriyor — bir yerde karışırsa (örn. registry zaten yeni hash'le güncellenmiş ama silme henüz yapılmamışsa) hangi `doc_id`'nin silineceği belirsizleşir.

`(source_type, source_id)` ise dokümanın YAŞAM BOYU SABİT kimliği — içerik ne kadar değişirse değişsin aynı kalır (Sprint 0'dan beri citation/grounding'in zaten kullandığı çift). Bu ikiliye göre silmek:
* Eski hash'i ayrıca okumaya gerek bırakmıyor.
* Chunk sayısı azalsa da artsa da (DoD'nin bahsettiği senaryo) o dokümana ait TÜM eski chunk'ları garanti temizliyor — "kaç tane eski chunk vardı" bilgisine hiç ihtiyaç yok, hepsi tek sorguda gidiyor.
* Daha önceki bir kısmi hatadan kalma (örn. iki farklı `doc_id`'den chunk'lar aynı dokümana ait kalmış) durumları da temizler — `doc_id` bazlı silme sadece TEK bir eski hash'i hedefleyebilirken, kaynak bazlı silme dokümanın adı altındaki HER ŞEYİ temizler.

**Karar: `QdrantStore.delete_by_source(source_type, source_id)`** — Qdrant `Filter(must=[FieldCondition(source_type=...), FieldCondition(source_id=...)])` ile o dokümana ait tüm point'leri siler. Değişen bir doküman yeniden ingest edilmeden HEMEN ÖNCE çağrılıyor (silme başarısız olursa yeni chunk'lar hiç yazılmıyor — kısmi/tutarsız durum yerine net bir hata).

## `ingest_connector` — üç aşamalı sync akışı

```python
current_documents = connector.list_documents()
seen_source_ids = {d.source_id for d in current_documents}

# 1) Silinenler: registry'de bu source_type için olup artık diskte olmayanlar
for record in registry.list_documents(source_type=connector.source_type):
    if record.source_id not in seen_source_ids:
        store.delete_by_source(connector.source_type, record.source_id)
        registry.delete_document(connector.source_type, record.source_id)
        files_deleted += 1

# 2) Ekleme/güncelleme
for document in current_documents:
    content_hash = connector.get_content_hash(document)
    if not registry.has_changed(connector.source_type, document.source_id, content_hash):
        files_skipped += 1
        continue  # Qdrant'a HİÇ dokunulmuyor

    store.delete_by_source(connector.source_type, document.source_id)  # yeni + değişmiş, ikisi için de güvenli — yeni dokümanda silinecek bir şey yok
    ... parse + chunk + embed + upsert ...
    registry.upsert_document(connector.source_type, document.source_id, content_hash)
    files_processed += 1
```

`delete_by_source`'un YENİ bir doküman için de (henüz hiç point'i yokken) çağrılması bilinçli — özel durum kodu eklemeye değmez, silinecek 0 point olduğunda no-op.

**Bilinçli sınırlama:** `atlanan` (`has_changed() == False`) dokümanlar için registry'ye HİÇ dokunulmuyor (ne `upsert_document` ne `last_synced_at` tazeleme) — "atla" kelimesini en dar/literal haliyle uyguluyoruz: Qdrant'a sıfır yazma, registry'ye sıfır yazma. `last_synced_at`'in "en son ne zaman kontrol edildi" bilgisini de tutması (içerik değişmese bile) Sprint 7'nin sync geçmişi/gözlemlenebilirlik ihtiyacı olabilir — şimdi eklemek YAGNI olur, gerçek ihtiyaç Sprint 7'de netleşince eklenir.

`IngestStats`'a `files_skipped: int = 0` ve `files_deleted: int = 0` eklendi (sona, varsayılanla) — `ingest_path`'in (Sprint 0, registry kullanmıyor) `IngestStats(...)` çağrısı değişmeden çalışmaya devam ediyor.

## Test stratejisi — üç gerçek senaryo, mock değil

Sprint 0/2/3'ün kurduğu ilke aynen sürüyor: gerçek bir geçici klasör, gerçek Qdrant (`:memory:`), gerçek SQLite registry dosyası.

1. **Güncelleme:** klasörde 2 dosya (A, B) ingest edilir → A'nın İÇERİĞİ diskte değiştirilir → `ingest_connector` tekrar çağrılır → Qdrant'tan doğrudan sorgulanır: A'nın YENİ metni var, ESKİ metni yok; B'nin point'leri (ID'leri dahil) SYNC ÖNCESİ/SONRASI birebir aynı — B'ye hiç dokunulmadığının somut kanıtı.
2. **Silme:** aynı 2 dosyadan biri (A) diskten silinir → `ingest_connector` çağrılır → Qdrant'ta `source_id=A` ile eşleşen SIFIR point kalır, registry'de A'nın kaydı yok, B dokunulmadan duruyor.
3. **No-op:** hiçbir dosya değişmeden `ingest_connector` ikinci kez çağrılır → `QdrantStore`'u saran, `upsert_chunks`/`delete_by_source` çağrılarını SAYAN bir test-local wrapper ile bu iki metodun SIFIR kez çağrıldığı kanıtlanıyor (gerçek bir "hiç yazma isteği gitmedi" kanıtı, sadece "sonuç aynı" değil).

## DoD doğrulama planı

1. `pytest -q` yeşil, `ruff check` temiz.
2. Yukarıdaki üç senaryo ayrı ayrı, gerçek dosya/Qdrant/registry ile testte kanıtlanmış.
3. Chunk sayısı azalan bir güncellemede (örn. uzun bir dosya kısaltılır) Qdrant'ta o dokümana ait fazladan/yetim point kalmadığı ayrıca doğrulanmış.
