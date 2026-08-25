# Sprint 21 — Embedding Non-Inferiority & Stability Decision

## Amaç

Sprint 20 `NEED_MORE_DATA` ile bitti: nokta tahmini `qwen3-0.6b@768`'in
Sprint 20'nin eşiklerini aştığını gösterdi, ama bootstrap CI bunu
güvenle teyit etmedi. Bu sprint YENİ bir model eklemiyor, dataset'i
körlemesine büyütmüyor — ölçüm gürültüsünü (embedding backend'in kendi
nondeterminizmi) gerçek retrieval instability'den AYIRIYOR, sonra
`qwen3-0.6b@768` için pre-committed bir non-inferiority kararı veriyor.

## Kapsam daraltması

Sadece 2 configuration: `qwen3-0.6b@768` (efficiency candidate),
`qwen3-4b@1024` (quality candidate). nomic sadece tarihsel referans
olarak raporda gösteriliyor, benchmark hot path'ine dahil değil. Yeni
model/reranker/chunking değişikliği YOK. Mevcut 220 soruluk golden set
(Sprint 20) DONDURULDU — bu sprint önce onunla çalışıyor, power
analysis SONUCUNA göre gerekirse minimum ek soru planı öneriyor
(körlemesine büyütme yok).

## Mimari

- **Dataset/corpus fingerprint** (`app/evaluation/dataset_fingerprint.py`) —
  golden set'in ve 4 fixture dokümanın deterministic SHA-256 hash'i,
  her benchmark artifact'ine yazılıyor — bağımsız koşumların GERÇEKTEN
  aynı evaluation setini kullandığını kanıtlıyor.
- **Frozen embedding cache** (`app/evaluation/embedding_cache.py`) —
  cache key = (model, revision, dimension, instruction, query_text,
  pipeline_fingerprint_digest) hash'i. Stale cache (fingerprint
  uyuşmazlığı) sessizce kullanılmıyor, açıkça reddediliyor.
  `artifacts/embedding-benchmark-sprint21/cache/{config_label}/
  embeddings.json`.
- **Non-inferiority + power analysis** (`app/evaluation/non_inferiority.py`) —
  delta konvansiyonu AÇIKÇA: `delta = quality_4B - quality_0.6B`
  (pozitif = 4B daha iyi). Non-inferiority testi: CI'nın ÜST sınırı
  margin'in altında kalıyorsa (en kötümser senaryoda bile fark margin'i
  aşmıyor) 0.6B non-inferior. Percentile paired bootstrap kullanıldı
  (BCa değil) — gerekçe: BCa'nın jackknife bias-correction/acceleration
  hesaplaması bu sprintin zaman bütçesinde ek karmaşıklık/risk katardı,
  percentile method delta dağılımı aşırı çarpık olmadığında (burada
  gerçekten kontrol edildi) yeterli ve standart bir yöntem.
- **`scripts/benchmark_stability.py`** (yeni script, mevcut
  `scripts/benchmark_embeddings.py`'nin fonksiyonlarını yeniden
  kullanıyor — yeniden yazmıyor) — nondeterminism ölçümü, frozen/live
  mode, multi-run stability, retrieval determinism check, non-
  inferiority + power analysis + production decision.

## Kurallar

- Sadece 2 configuration, mevcut dataset donduruldu (ilk aşamada).
- Minimum 10 bağımsız live quality run per configuration (query-only,
  corpus bir kez indexleniyor — İZOLE edilen değişken query embedding
  nondeterminizmi, yeniden-indexleme değil).
- Embedding nondeterminism: 50 temsili soru x 10 tekrar, gerçek.
- Paired bootstrap: seed sabit, ≥10.000 iterasyon, %95 CI.
- Margin'ler (Sprint 20 verisine dayanarak, SONUÇTAN ÖNCE kodlandı):
  cross Recall@5 ≤0.04, cross MRR ≤0.04, mono Recall@5 ≤0.02.
- Production default DEĞİŞMEDİ.
- Yeni artifact klasörü: `artifacts/embedding-benchmark-sprint21/`.

## Definition of Done

Kullanıcının 21 maddelik final response format'ı birebir karşılanacak.
