"""Real backend entrypoint: `uvicorn app.server:app`. Kept separate from
app/main.py (a pure create_app() factory tests call with fakes) and
app/wiring.py (the real-component builder tests never import) — this is
the only module that actually connects to Qdrant/Ollama/SQLite at import
time.
"""

from app.shared.config import settings
from app.wiring import build_app

app = build_app(settings)
