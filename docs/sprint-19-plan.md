# Sprint 19 — Qwen3 Size & Dimension Trade-off Benchmark

## Amaç

Sprint 18, "Qwen3-Embedding-4B nomic'ten daha mı iyi?" sorusunu
cevapladı (evet, çapraz-dilli tarafta, ciddi bir operasyonel maliyetle).
Bu sprint farklı bir soru soruyor: **hangi Qwen3 varyantı (boyut x
output-dimension) production için en iyi kalite/maliyet dengesini
veriyor?** Sprint 18'in altyapısını (EmbeddingModelConfig, fingerprint,
rank_metrics, benchmark script) yeniden yazmak yerine GENİŞLETİYOR.

## Ollama'nın resmi output-dimension mekanizması — gerçekten doğrulandı

Ollama 0.32.6, `/api/embed` (çoğul — mevcut `OllamaClient.embed()`'in
kullandığı eski, tekil `/api/embeddings`'ten FARKLI bir endpoint)
üzerinden bir `dimensions` parametresi destekliyor. GERÇEKTEN test
edildi: `qwen3-embedding:4b`'ye `dimensions=1024` verildiğinde backend
gerçekten 1024 boyutlu, normalize edilmiş bir vektör döndürüyor — bu,
native 2560 boyutlu çıktının ilk 1024'ünü alıp yeniden normalize etmekle
AYNI DEĞİL (doğrudan karşılaştırıldı, farklı değerler), yani gerçekten
backend'in kendi (muhtemelen Matryoshka-farkında) mekanizması, bizim
sonradan yaptığımız bir hack değil. Bu, kullanıcının "yalnızca resmi
mekanizma, truncate hack yok" kuralına tam uyuyor.

Sonuç: `OllamaClient.embed()` GERİYE DÖNÜK UYUMLU şekilde genişletildi —
opsiyonel bir `dimensions: int | None = None` parametresi eklendi.
`None` (varsayılan, TÜM mevcut çağrı yerleri) eski `/api/embeddings`
endpoint'ini KULLANMAYA DEVAM EDİYOR, davranış birebir aynı. Bir
`dimensions` değeri verildiğinde `/api/embed`'e geçiliyor. Her
configuration'ın gerçekten desteklenip desteklenmediği (bazı
dimensions/model kombinasyonları backend tarafından reddedilebilir)
GERÇEK bir çağrıyla test edilip `results.json`'a `supported: bool`
olarak kaydediliyor — asla varsayılmıyor.

## Configuration matrisi

Kullanıcının istediği 6 configuration'ın hepsi GERÇEKTEN test edildi
(hangisi desteklenip desteklenmediği koşum sırasında belirlendi, bkz.
kapanış notu):

1. `nomic@768` (mevcut baseline, Sprint 18'den değişmedi)
2. `qwen3-0.6b@native`
3. `qwen3-4b@native` (Sprint 18'in kalite tavanı)
4. `qwen3-4b@1024`
5. `qwen3-0.6b@1024`
6. `qwen3-0.6b@768`

## Mimari genişletme (yeniden yazma değil)

- `EmbeddingModelConfig`'e `output_dimension: int | None` (None = native,
  backend'in varsayılan boyutu) ve `backend: str` alanları eklendi.
  Mevcut `dimension` alanı `output_dimension`'ın çözülmüş (resolved)
  hali olarak kalıyor — geriye dönük uyumlu.
- `PipelineFingerprint` zaten `embedding_dimension`'ı kapsıyordu (Sprint
  18) — aynı model, farklı `output_dimension` (`qwen3-4b@2560` vs
  `qwen3-4b@1024`) otomatik olarak FARKLI fingerprint üretiyor, ek bir
  değişiklik gerekmedi, sadece testle kanıtlandı.
- `scripts/benchmark_embeddings.py` multi-candidate hale getirildi:
  `--models`/`--dimensions` (kartezyen çarpım, desteklenmeyenler açıkça
  `unsupported` işaretleniyor) — CLI tasarımı, mevcut argparse stiline
  uygun.
- Her configuration ayrı, izole bir Qdrant collection'ında
  (`kb_benchmark_{model}_{dimension}`) — production'a hiç dokunmuyor.

## Kurallar

- AYNI 68 soruluk golden set (Sprint 18 ile apples-to-apples).
- Tek değişken: embedding model + output dimension. Chunking/sparse/RRF/
  limits/filters/expected_locations SABİT.
- Reranker KAPALI, generation kapsam DIŞI.
- Warmup ile steady-state ayrılıyor (deterministic warmup call, SONRA
  ölçüm).
- Birden fazla query run, p50/p95 gerçek dağılımdan.
- Production default DEĞİŞMİYOR bu sprintte de.
- Sprint 18 artifact'ları EZİLMİYOR — yeni klasör
  `artifacts/embedding-benchmark-sprint19/`.

## Definition of Done

Kullanıcının talimatındaki 15 maddelik final response format'ı + tüm
scope maddeleri (bkz. görev metni) birebir karşılanacak.
