# Sprint 17.7 — Reranker Cross-Lingual Mismatch Investigation (araştırma)

## Context

Sprint 17.5, `CrossEncoderReranker`'ı eval CLI'ye wiring ettikten sonra
gerçek bir golden-set koşumunda PDF recall'ının 0.429'dan 0.143'e
düştüğünü ölçtü — ama olası nedeni ("Türkçe golden set + İngilizce
eğitilmiş reranker") sadece bir hipotez olarak, ayrıca araştırılmadan
bıraktı. Bir sonraki doğrulama adımı (bu sprint'ten önce, kod
değiştirmeden yapıldı) golden set'in aslında HOMOJEN Türkçe olmadığını
ortaya çıkardı:

- **Sorular**: 12 sorunun TAMAMI Türkçe (doğrudan `tests/fixtures/golden_set.json`'dan doğrulandı).
- **PDF kaynak dokümanı** (`tests/fixtures/golden_source.py`, "Nimbus Cloud Storage handbook"): TAMAMEN İngilizce.
- **Markdown kaynak dokümanı** (`tests/fixtures/golden_markdown_source.py`, "Nimbus CLI" referansı): TAMAMEN Türkçe.

Yani mevcut tasarım homojen değil, KARIŞIK: PDF tarafı zaten
ÇAPRAZ-DİLLİ (TR soru / EN içerik), Markdown tarafı TEK-DİLLİ (TR
soru / TR içerik) — ve SADECE çapraz-dilli PDF tarafı regresyona
uğradı (recall 0.429→0.143), tek-dilli Markdown tarafı sabit kaldı
(recall 1.0→1.0). Bu, "Türkçe golden set" hipotezinden daha kesin,
çürütülebilir bir hipotez öneriyor: **rerank'in kötüleştirme etkisi
dile değil, SORU/İÇERİK dil UYUŞMAZLIĞINA bağlı.**

## Amaç

Bu bir düzeltme sprint'i DEĞİL — bir deney. Değişkeni (dil uyuşmazlığı)
izole eden bir 2x2 tasarımla bu hipotezi test etmek: sonucu ne çıkarsa
dürüstçe raporlamak, kod davranışını değiştirmemek.

## Deney tasarımı

**2x2 hücre, her biri hem reranker'sız hem reranker'lı koşulacak (8 koşum toplam):**

| | PDF (EN içerik) | Markdown (TR içerik) |
|---|---|---|
| **TR soru** (mevcut) | Çapraz-dilli (mevcut, referans) | Tek-dilli (mevcut, referans) |
| **EN soru** (yeni) | Tek-dilli (yeni) | Çapraz-dilli (yeni) |

**Uygulama detayı — tek yeni fixture dosyası yeterli:** Eval harness'in
`build_report()`'u zaten her koşumu `content_type` (`pdf`/`markdown`)
bazında ayrı raporluyor (`by_content_type`). Yani TR soru seti
(`golden_set.json`, mevcut) bir koşumda hem "PDF+TR" hem "Markdown+TR"
hücrelerini otomatik üretiyor; paralel bir `golden_set_en.json`
(TÜMÜ İngilizce, AYNI `expected_locations`/`content_type` — içerik
değişmediği için ground truth değişmiyor, sadece soru dili değişiyor)
bir koşumda hem "PDF+EN" hem "Markdown+EN" hücrelerini üretecek. Ayrı
ayrı iki EN dosyası (PDF-only, Markdown-only) yazmaya gerek yok —
aynı sonucu tek dosyayla, mevcut `by_content_type` kırılımını
kullanarak elde ediyoruz.

Toplam koşum: 2 golden set (TR, EN) × 2 reranker modu (`--no-reranker`,
varsayılan) = 4 CLI koşumu, her biri `by_content_type` ile 2 hücre
üretiyor = 8 hücre.

**Sorular gerçek, uydurulmadı:** `golden_set_en.json`'daki 12 soru,
`golden_set.json`'daki Türkçe soruların doğrudan çevirisi — aynı
`expected_locations`, aynı `content_type`, aynı `reference_answer`
(İngilizceye çevrildi, ama `app/evaluation/generation_metrics.py`
`reference_answer`'ı hiç tüketmiyor — `harness.py`'de sadece
`GoldenQuestion` üzerinde saklanıyor, doğrulandı). Ground truth
konumlar zaten gerçek, ingest edilmiş içerikten Sprint 9'da
doğrulanmıştı (bkz. Sprint 9 kapanış notu) — içerik bu sprintte
değişmediği için tekrar doğrulamaya gerek yok, ama koşum öncesi
Qdrant'a gerçekten aynı iki dokümanın ingest edildiği teyit edilecek.

## Hipotez (çürütülebilir)

Eğer sorun gerçekten dil UYUŞMAZLIĞIysa: rerank'in kötüleştirme etkisi
HER ZAMAN çapraz-dilli hücrelerde (PDF+TR, Markdown+EN) görülmeli,
tek-dilli hücrelerde (PDF+EN, Markdown+TR) görülmemeli veya çok daha
zayıf olmalı. Aksi bir desen (örn. her iki dilde de PDF kötüleşiyor,
veya hiçbir hücrede kötüleşme yok) hipotezi çürütür.

## Kurallar

- Kod davranışını DEĞİŞTİRME — bu bir araştırma sprint'i.
- Git commit mesajına AI co-author satırı eklenmeyecek.
- Sprint bitince docs/PLANNING.md'ye kapanış notu: 8 koşumun tam
  sonuçları (2x2xreranker tablosuyla), hipotezin doğrulanıp
  doğrulanmadığı — kesin değilse bunu da dürüstçe yaz.
- README'yi bu yeni bulguyla güncelle — "Türkçe golden set" ifadesini
  daha kesin olan "çapraz-dilli retrieval" çerçevesiyle değiştir.

## Definition of Done

- 8 koşu gerçek servislere (native Ollama + docker-compose Qdrant)
  karşı çalıştırılmış.
- Sonuçlar 2x2 tabloyla raporlanmış.
- Çapraz-dilli hipotezi net şekilde desteklenmiş ya da çürütülmüş.
- README güncellenmiş.
