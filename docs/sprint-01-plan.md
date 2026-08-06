# Sprint 1 — Provider Abstraction

## Gerçek kullanım yerleri (interface buradan çıkarıldı)

Varsayımsal bir arayüz tasarlamak yerine, Sprint 0'da taşınan kodun LLM'i gerçekte nasıl çağırdığına bakıldı:

* `app/llm/generate.py::stream_answer` — `ollama.stream_chat(messages, model=model)` çağırıyor, `messages: list[dict]` (`{"role", "content"}`, `build_messages()`'ın ürettiği OpenAI/Ollama tarzı format — bir `role="system"` mesajı + bir `role="user"` mesajı), dönüş `AsyncIterator[str]` (token token). Zaten yerel bir `StreamingOllamaProtocol` ile bu şekilde tipleniyordu.
* `app/retrieval/search.py::search` — `ollama.embed(query, model=embed_model, prefix=SEARCH_QUERY_PREFIX)` çağırıyor, dönüş `list[float]`. Yerel `OllamaEmbedProtocol` ile tipleniyordu.
* `app/ingestion/ingest.py::ingest_path` — `embed_fn(chunk.text)` (bağımsız bir `Callable[[str], Awaitable[list[float]]]`, çağıran taraf model/prefix'i closure ile bağlıyor).
* `app/llm/grounding.py::check_grounding` — LLM'den tamamen bağımsız; sadece üretilen metindeki `[s.source_type:source_id/page/paragraph]` regex'ini kontrol ediyor. Hangi provider'ın ürettiği fark etmiyor — bu yüzden grounding katmanına DOKUNULMUYOR, sadece bunun gerçekten doğru olduğu bir testle kanıtlanacak.

Sonuç: iki farklı şekil var, iki farklı yerde kullanılıyor — birleştirilmiş "tek LLMProvider" yerine iki ayrı Protocol daha doğru bir model:

```python
class ChatProvider(Protocol):
    def stream_chat(self, messages: list[dict], model: str) -> AsyncIterator[str]: ...

class EmbeddingProvider(Protocol):
    async def embed(self, text: str, model: str, prefix: str = "") -> list[float]: ...
```

Bu iki Protocol `app/llm/provider.py`'de merkezi olarak tanımlanacak; `generate.py`/`search.py`'deki yerel (aynı şekle sahip) Protocol tanımları buradan import edilecek — davranış değişmiyor (yapısal tipleme), sadece tekrar kaldırılıyor.

## Embedding vs Generation kararı

**Karar: embedding, generation'dan tamamen ayrı bir seçim.** Claude API'nin embedding endpoint'i yok — bu bir gerçek, aşılamaz bir kısıt, dolayısıyla `ChatProvider` seçimi `EmbeddingProvider` seçimini etkilemiyor/etkilemesi mümkün değil.

Bu sprintte `EmbeddingProvider`'ın tek implementasyonu yine Ollama (`nomic-embed-text`) — ama config'de generation'dan **ayrı bir alan** olarak tutuluyor (`embedding_provider: Literal["ollama"]`), OpenAI/Voyage gibi bir embedding sağlayıcısı eklenmek istendiğinde `search.py`/`ingest.py`'a dokunmadan sadece yeni bir `EmbeddingProvider` implementasyonu + factory'ye bir dal eklenmesi yeterli olacak şekilde. Bunu şimdiden somut bir üçüncü implementasyonla "kanıtlamak" bu sprintin kapsamı dışı (YAGNI) — sadece iki farklı Protocol olarak ayrıştırmak, embedding tarafını generation seçiminden bağımsız kılmaya yetiyor.

## Modüller

* `app/llm/provider.py` — `ChatProvider`, `EmbeddingProvider` Protocol'leri (`@runtime_checkable`, testte `isinstance` ile conformance kanıtlanabilsin diye); `default_chat_model(settings)`, `get_chat_provider(settings)`, `get_embedding_provider(settings)` factory fonksiyonları.
* `app/llm/ollama_provider.py` — `OllamaProvider = OllamaClient`'ı yeniden export eden ince modül. `OllamaClient` zaten `stream_chat`/`embed` metotlarıyla her iki Protocol'ü de yapısal olarak karşılıyor (Sprint 0'da hiç değişmedi) — bu yüzden yeni bir adapter sınıfı yazmak (aynı metotları olduğu gibi başka bir sınıfa taşımak) gereksiz bir katman olurdu. `OllamaProvider` ismi, factory'nin döneceği somut bir sembol olması için var.
* `app/llm/claude_provider.py` — `ClaudeProvider` (yeni), `anthropic` SDK'nın `AsyncAnthropic.messages.stream(...)` ile gerçek streaming. `messages`'daki `role="system"` mesaj(lar)ı Anthropic'in ayrı `system=` parametresine çevriliyor (Anthropic, Ollama/OpenAI'nin aksine system prompt'u mesaj listesinde değil ayrı bir alanda bekliyor) — bu çeviri `prompt.py`'a dokunmadan provider sınırında yapılıyor. `ClaudeUnreachableError` (Ollama'daki `OllamaUnreachableError` ile simetrik).

## Config

`app/shared/config.py`'ye eklenecek alanlar:

```python
generation_provider: Literal["ollama", "claude"] = "ollama"
embedding_provider: Literal["ollama"] = "ollama"
claude_api_key: str | None = None
claude_model: str = "claude-haiku-4-5-20251001"
claude_max_tokens: int = 2048
```

`local-first` varsayılan: `generation_provider="ollama"`.

## Test stratejisi

* `ClaudeProvider` testleri `httpx.MockTransport` ile gerçek Anthropic SSE formatını (`event: content_block_delta` / `data: {...}`) simüle eder — `OllamaClient`'ın test deseniyle aynı (gerçek network yok, ama gerçek parsing kodu çalışıyor).
* `generate.py`'nin `ollama` parametresi artık `ChatProvider` tipiyle anotasyonlu ve testlerde hem Ollama hem Claude fake'iyle çağrılarak polymorphism kanıtlanıyor — mevcut testlerde `ollama=` keyword kullanılmadığı doğrulandı (`grep -n "ollama=" tests/test_generate.py` boş döndü), o yüzden parametre ismi değişmiyor.
* `search.py`'nin `ollama` parametresi ismi/DEĞİŞMİYOR — embedding bu sprintte hâlâ sadece Ollama, isim zaten doğru; sadece tip anotasyonu paylaşılan `EmbeddingProvider` Protocol'üne işaret edecek.
* Yeni: `tests/test_provider.py`, `tests/test_ollama_provider.py`, `tests/test_claude_provider.py`.
* Yeni: provider-agnostic grounding testi — aynı citation tag'ini hem `OllamaProvider` hem `ClaudeProvider` fake'inden üretip `check_grounding`'in ikisinde de aynı şekilde çalıştığını kanıtlıyor.
* Gerçek karşılaştırma: `tests/test_provider_comparison_e2e.py` — hem Ollama hem Claude'a AYNI soruyu gerçekten sorar, ikisinin cevabını karşılaştırır. Ollama tarafı `localhost:11434` reachable değilse, Claude tarafı `ANTHROPIC_API_KEY` yoksa otomatik skip (Sprint 0'daki `_ollama_up()` deseniyle aynı). Bu makinede `ANTHROPIC_API_KEY` yok — bu test büyük ihtimalle skip olacak, kullanıcıya ayrıca haber verilecek.

## DoD doğrulama planı

1. `pytest -q` yeşil, `ruff check` temiz.
2. `ChatProvider`/`EmbeddingProvider` Protocol'lerine karşı `isinstance` ile hem `OllamaProvider` hem `ClaudeProvider`'ın conformance'ı test edilmiş.
3. Grounding/citation'ın provider'dan bağımsız çalıştığı somut bir testle kanıtlanmış.
4. Gerçek Ollama + gerçek Claude API karşılaştırması: `ANTHROPIC_API_KEY` varsa gerçekten çalıştırılıp iki cevap karşılaştırılacak; yoksa test otomatik skip olacak ve bu kapanış notunda açıkça belirtilecek.
