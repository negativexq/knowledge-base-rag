# Sprint 18 — Multilingual Embedding Benchmark: Nomic vs Qwen3-Embedding-4B

## Amaç

`nomic-embed-text`'i hemen değiştirmek değil — Sprint 17.7'nin bulduğu
çapraz-dilli retrieval zayıflığına karşı `Qwen/Qwen3-Embedding-4B`'nin
gerçekten daha iyi olup olmadığını kontrollü, tekrarlanabilir bir
benchmark'la ölçmek. Production default'u sonuç kanıtlanmadan
değiştirilmiyor.

## Mimari kararlar

**Qwen3-Embedding-4B, Ollama üzerinden servis ediliyor
(`qwen3-embedding:4b`)** — bu, YENİ bir HTTP/transport backend'i
gerekmediği anlamına geliyor: `app/llm/ollama_client.py::OllamaClient`
zaten `embed(text, model, prefix)` şeklinde generic. Modeller arası
gerçek fark transport değil, İKİ ŞEY: (a) hangi model adı, (b) sorgu/
doküman için hangi instruction/prefix formatı. Bu yüzden yeni bir
`EmbeddingProvider` alt sınıfı YERİNE, `app/llm/embedding_models.py`'de
bir `EmbeddingModelConfig` (model adı, revision, dimension, query/
document instruction) + bunu config/env'den kuran bir factory ekleniyor
— "provider" burada bu config, retrieval/ingest kodu asla
`if model == "qwen3"` yapmıyor, sadece `EmbeddingModelConfig`'in
`query_prefix()`/`document_prefix()`'ini kullanıyor.

**Qwen3'ün resmi instruction formatı korunuyor, nomic'in prefix'i
KÖRÜ KÖRÜNE taşınmıyor.** Qwen3-Embedding model kartının belirttiği
asimetrik format: query tarafında `f"Instruct: {task}\nQuery: "` + metin,
doküman tarafında HİÇBİR instruction yok (çıplak metin). Bu,
`OllamaClient.embed`'in mevcut `prefix + text` sözleşmesiyle BİREBİR
uyumlu — `query_prefix()` bu tam string'i üretiyor, `document_prefix()`
boş string dönüyor. nomic'in `search_query: `/`search_document: `
davranışı DEĞİŞMİYOR (aynı sabit prefix'ler, `EmbeddingModelConfig`
olarak yeniden ifade edildi, davranış birebir aynı).

**Boyut (dimension) artık QdrantStore'un sabit modül seviyesi
`EMBEDDING_DIM`'ine kilitli değil.** `QdrantStore.__init__`'e opsiyonel
`dense_dimension: int = EMBEDDING_DIM` parametresi eklendi — verilmezse
davranış BİREBİR AYNI (mevcut tüm çağrı yerleri, testler etkilenmiyor).
Benchmark, farklı boyutlu bir koleksiyon açarken bunu geçiyor.

**Fingerprint, mevcut `CURRENT_INDEX_SCHEMA_VERSION` mekanizmasını
GENİŞLETİYOR, yeni bir paralel sayaç icat etmiyor.** `app/ingestion/
fingerprint.py::PipelineFingerprint` — embedding model/revision/
dimension/query+document instruction VE mevcut
`registry.store.CURRENT_INDEX_SCHEMA_VERSION`'ı (chunker/parser/point-
identity şeması) tek bir canonical, deterministic-hash'lenmiş
temsile birleştiriyor. Registry'ye nullable `pipeline_fingerprint`
kolonu eklendi (Sprint 17.4'ün öğrettiği ders: NOT NULL DEFAULT'suz,
`ALTER TABLE ADD COLUMN`). `ingest_connector`'a OPSİYONEL bir
`pipeline_fingerprint: PipelineFingerprint | None = None` parametresi
eklendi — verilmezse (mevcut TÜM production çağrı yerleri, SyncManager
dahil) davranış BİREBİR AYNI, geriye dönük uyumlu. Verilirse,
reconciliation mantığı (Sprint 17.2'nin `chunk_count` kontrolüyle AYNI
noktada) fingerprint uyuşmazlığını da "index eksik/bozuk" sayıyor —
content_hash aynı kalsa bile yeniden indexlemeyi zorluyor. Production
SyncManager'a GERÇEK bir fingerprint bağlamak bu sprintin kapsamı DIŞINDA
bilinçli olarak bırakıldı — bunu şimdi bağlamak her kullanıcının mevcut
index'ini bir sonraki sync'te zorla yeniden indexlerdi, ki bu bir
benchmark sprint'inin yan etkisi olmamalı. Mekanizma inşa edildi ve
test edildi, PRODUCTION'a bağlanması ayrı, bilinçli bir karar.

**Benchmark izolasyonu: ayrı Qdrant collection + ayrı SQLite registry,
production'a hiç dokunmuyor.** `scripts/benchmark_embeddings.py`,
`kb_benchmark_{model_key}` collection'ları ve geçici bir dizindeki
SQLite dosyalarını kullanıyor — `app/wiring.py`'nin gerçek
`settings.qdrant_collection_name`/`settings.registry_db_path`'ine hiç
dokunmuyor. Baseline ve challenger birbirinden bağımsız, aynı corpus'tan
yeniden indexleniyor.

## Golden set genişletmesi — 4 dil-çifti hücresi

Sprint 17.7'nin bulduğu gibi mevcut golden set (PDF=EN, MD=TR, 12 soru)
zaten iki hücreyi (PDF+TR=çapraz, MD+TR=tek-dilli) ima ediyordu, ama her
hücrede sadece 5-7 soru vardı — hedef 15-20'nin altında. Bu sprint,
GERÇEK içerikten iki yeni fixture doküman ekliyor (`golden_source_en2.py`
— İngilizce Markdown "Nimbus API Reference"; `golden_source_tr2.py` —
Türkçe Markdown "Nimbus Kurumsal SSS") ve mevcut iki dokümanla birlikte
her biri gerçek, ingest edilmiş içerikten doğrulanmış (paraphrase-kolay
değil) sorularla 4 hücreyi de en az 15 soruya çıkarıyor:

- TR soru → TR içerik (mevcut MD + yeni TR MD)
- EN soru → EN içerik (mevcut PDF + yeni EN MD)
- TR soru → EN içerik (aynı EN içerik, TR soru çevirisi)
- EN soru → TR içerik (aynı TR içerik, EN soru çevirisi)

Her `expected_locations`, gerçek ingest edilmiş Qdrant point'lerine
karşı doğrulanıyor (Sprint 9/17.5'in kurduğu disiplin).

## Metrikler

Rank-aware metrikler (Recall@1/3/5, MRR, nDCG@5) hiçbir yerde yoktu —
mevcut `app/evaluation/retrieval_metrics.py` sadece sırasız
precision/recall hesaplıyordu. Yeni `app/evaluation/rank_metrics.py`
bunları SIRALI (retrieval sırası korunmuş) sonuç listesinden hesaplıyor.

Operasyonel metrikler (indexing throughput, query embedding p50/p95,
model load süresi, boyut, Qdrant storage etkisi) gerçek saatle
ölçülüyor. RAM/VRAM güvenilir ölçülemiyorsa ("Ollama subprocess'inin
gerçek bellek kullanımını izole ölçecek bir mekanizma yok") `null`/
"not measured" olarak AÇIKÇA işaretleniyor, uydurulmuyor.

## Kurallar

- Tek değişken: embedding modeli. Chunking/sparse/RRF/top-k baseline ile
  challenger arasında BİREBİR aynı.
- Benchmark sırasında reranker KAPALI.
- Generation/LLM kalitesi bu sprintin ölçüm kapsamı DIŞINDA.
- Mevcut nomic-embed-text davranışı (prefix, model, dimension) hiç
  değişmiyor.
- Git commit mesajına AI co-author satırı eklenmeyecek.
- Mevcut test suite + ruff tamamen yeşil kalmalı.

## Definition of Done

Yukarıdaki kullanıcı talimatındaki DoD birebir geçerli — 8 gerçek
retrieval hücresi + operasyonel metrikler, `artifacts/embedding-
benchmark/{results.json,report.md}`, `scripts/benchmark_embeddings.py`
CLI, en az 9 test kategorisi, README/PLANNING güncellemesi (sonuç
kanıtlanmadan iddia yok), açık bir KEEP/ADOPT/NEED-MORE-DATA önerisi.
