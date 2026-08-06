# Sprint 0 — Foundation + Core Port

## Kaynak

`production-rag-platform`, local checkout: `/Users/ofk/production-rag-platform` (github.com/negativexq/production-rag-platform).

## Repo iskeleti

```
app/
  connectors/   # Sprint 3+ — boş, sadece __init__.py
  parsing/      # Paragraph model + format-özel parser'lar (pdf_parser.py bu sprintte)
  ingestion/    # Chunk model, chunker, qdrant_store, ingest pipeline
  retrieval/    # sparse encoder, hybrid_search, filters, search orchestration
  reranker/     # cross-encoder reranker
  llm/          # ollama_client, prompt, grounding, generate
  registry/     # Sprint 2+ — boş, sadece __init__.py
  sync/         # Sprint 4+ — boş, sadece __init__.py
  shared/       # config, tracing
  ui/           # citation_formatting (Streamlit'in geri kalanı Sprint 10'da)
tests/
docs/
prompts/
```

## Citation format kararı

Sprint 0'da genişletilmiş multi-source format ile başlanıyor (Sprint 5'e ertelenmiyor):

```
[s.<source_type>:<source_id>/<page>/<paragraph>]
örnek: [s.pdf:handbook/2/0]
```

`source_type` bu sprintte her zaman `"pdf"`. `source_id`, production-rag-platform'daki `doc_label()` mantığıyla dosya adından türetilir (uzantı atılır, non-word karakterler `_` olur).

Gerekçe: grounding kontrolü `(source_type, source_id, page, paragraph)` dörtlüsüne göre çalışacak şekilde en baştan tasarlanıyor — production-rag-platform'da tek-doküman `(doc, page, paragraph)` üçlüsünden `(source_type, source_id, page, paragraph)` dörtlüsüne geçiş, ileride grounding/citation kodunu tekrar değiştirmeyi gerektirmeyecek. Detay: `docs/PLANNING.md`'deki "Sprint 0" açık soru notu ve hafızadaki `citation-format-multisource` kaydı.

## Taşınacak modüller (adapte + namespace değişikliği)

| Kaynak (production-rag-platform) | Hedef (knowledge-base-rag) | Değişiklik |
|---|---|---|
| `app/shared/config.py` | `app/shared/config.py` | aynen, service_name güncellendi |
| `app/shared/tracing.py` | `app/shared/tracing.py` | aynen |
| `app/ingestion/models.py` (Paragraph) | `app/parsing/models.py` | aynen taşındı |
| `app/ingestion/models.py` (Chunk) | `app/ingestion/models.py` | `source_type`, `source_id` alanları eklendi |
| `app/ingestion/parser.py` | `app/parsing/pdf_parser.py` | aynen |
| `app/ingestion/chunker.py` | `app/ingestion/chunker.py` | `chunk_document` artık `source_id`/`source_type` alıyor |
| `app/ingestion/qdrant_store.py` | `app/ingestion/qdrant_store.py` | payload'a `source_type`/`source_id`, `source_filename` param kaldırıldı (chunk üzerinden geliyor) |
| `app/retrieval/sparse.py` | `app/retrieval/sparse.py` | aynen |
| `app/retrieval/hybrid_search.py` | `app/retrieval/hybrid_search.py` | aynen |
| `app/retrieval/filters.py` | `app/retrieval/filters.py` | `source_filenames` yerine `source_types`/`source_ids` |
| `app/retrieval/search.py` | `app/retrieval/search.py` | aynen (filters imzası güncellendi) |
| `app/reranker/cross_encoder.py` | `app/reranker/cross_encoder.py` | aynen |
| `app/llm/ollama_client.py` | `app/llm/ollama_client.py` | aynen |
| `app/llm/prompt.py` | `app/llm/prompt.py` | `citation_tag`/`doc_label` → `source_type`+`source_id` alıyor |
| `app/llm/grounding.py` | `app/llm/grounding.py` | 4'lü tuple ile çalışıyor |
| `app/llm/generate.py` | `app/llm/generate.py` | aynen |
| `app/ingestion/ingest.py` | `app/ingestion/ingest.py` | `source_filename` yerine `source_type`/`source_id` geçiyor |
| `app/ui/citation_formatting.py` | `app/ui/citation_formatting.py` | regex yeni formata güncellendi |
| `prompts/answer_v1.txt`, `answer_v2.txt` | aynı | citation tag örneği yeni formatla |

Taşınmayanlar (bu sprint kapsamı dışı, ilgili sprintte eklenecek): `app/api/chat.py`, `app/main.py`, `app/ui/streamlit_app.py`, `app/ui/sse_client.py`, `app/ui/trace_client.py`, `app/ui/ingest_helper.py`, `app/evaluation/*`.

## DoD doğrulama planı

1. Taşınan/uyarlanan testlerin tamamı `pytest -q` ile yeşil (gerçek Ollama/Qdrant gerektirenler skip edilebilir).
2. `tests/test_ingest.py` tarzı hermetik bir e2e testle tek bir PDF: chunk → (fake) embed → upsert → hybrid search → rerank → grounded citation formatlama uçtan uca çalışıyor, multi-source tag formatıyla.
