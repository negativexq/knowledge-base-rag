# Sprint 20 — Embedding Benchmark Stability & Production Decision

## Amaç

Sprint 19, `qwen3-0.6b@768`'in `qwen3-4b@1024`'e çok yakın retrieval
kalitesi verdiğini ama 68 soruluk küçük bir dataset yüzünden bu
kabul/red kararının run-to-run gürültüye duyarlı olduğunu buldu. Bu
sprint YENİ bir model eklemiyor — aynı 3 configuration'ı (nomic@768,
qwen3-0.6b@768, qwen3-4b@1024), çok daha büyük (200+ soru) ve
istatistiksel olarak paired bootstrap CI ile desteklenen bir
değerlendirmeyle karşılaştırıp, gerçek bir production kararı üretiyor.

## Golden set genişletmesi

Mevcut 4 fixture dokümanı (2'si Sprint 18'de eklendi) GENİŞLETİLDİ,
YENİ doküman eklenmedi: `nimbus_api_reference.md` 10→20 bölüm,
`nimbus_kurumsal_sss.md` 8→17 bölüm. PDF (6 konum) ve CLI.md (8 bölüm)
değişmedi. Toplam gerçek "fact" sayısı: 27 EN-content, 25 TR-content.

Her fact için: 1 native-dil soru + 3 çapraz-dil soru (10 zorluk
kategorisinden rotasyonla: exact_lexical, semantic_paraphrase,
terminology_mismatch, acronym_abbreviation, number_date_lookup,
multi_sentence_evidence, heading_dependent, ambiguous_wording,
hard_negative) + 12 not-found kontrol sorusu (6 TR + 6 EN). Toplam
**220 soru** — `tests/fixtures/embedding_benchmark_golden_v2.json`
(Sprint 18/19'un 68 soruluk dosyası DEĞİŞMEDİ, dokunulmadı).

Dağılım: TR→EN=81, EN→TR=75, TR→TR=25, EN→EN=27 — hepsi hedefin
üzerinde (75+/75+/25+/25+).

## Doğrulama

`app/evaluation/golden_set_validation.py` (yeni, testli): exact/
normalized duplicate tespiti, dangling expected-location tespiti,
language-pair dağılım kontrolü, not-found oranı kontrolü.
`tests/test_golden_set_v2_integrity.py`, GERÇEK fixture dosyasını
GERÇEK chunker'lardan (Qdrant/Ollama olmadan, tamamen deterministic)
üretilen konumlara karşı doğruluyor — 0 dangling location, 0 duplicate.

## Determinism araştırması

Kullanıcının istediği gibi GERÇEKTEN araştırıldı, gizlenmedi: aynı
metni iki kez embed etmek (`qwen3-embedding:0.6b`, aynı model, aynı
girdi) GERÇEKTEN farklı float değerleri üretiyor (max mutlak fark
~2.7e-05) — bu, Ollama/backend'in kendi sayısal olmayan-deterministik
inference'ından kaynaklanıyor (muhtemelen Metal/GPU accumulation
sırası), bu projenin kontrol edebileceği bir şey DEĞİL. Sorgu sırası
artık deterministic (id'ye göre sıralı), metrik agregasyonu zaten saf
Python (deterministic), bootstrap seed sabit — ama embedding çıktısının
kendisi bit-exact tekrarlanabilir değil, bu GERÇEK ve raporda açıkça
belirtildi.

## Kurallar

- Sadece 3 configuration: nomic@768, qwen3-0.6b@768, qwen3-4b@1024.
- Aynı 220 soru, aynı chunk seti, aynı retrieval config üç configuration
  için de.
- Paired bootstrap CI: seed=20200601, iterations=5000, %95 güven
  aralığı, 5 metrik x 3 subset (overall/cross_lingual/mono_lingual).
- Eşikler (Sprint 20'ye özgü, `qwen3-4b@1024`'e göre): cross-lingual
  Recall@5 kaybı ≤0.03, cross-lingual MRR kaybı ≤0.04, mono-lingual
  Recall@5 kaybı ≤0.01 — sonuçtan ÖNCE kodlandı.
- Production default değişmedi.
- Yeni artifact klasörü: `artifacts/embedding-benchmark-sprint20/`
  (Sprint 18/19'unkiler ezilmedi).

## Definition of Done

Kullanıcının 19 maddelik final response format'ı birebir karşılanacak.
