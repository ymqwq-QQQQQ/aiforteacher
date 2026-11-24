# aiforteachers v1.0

Intelligent Courseware & Lesson Preparation assistant with local Markdown chat storage, built-in curriculum standards knowledge base, multi-provider LLM routing, and Gemini-style frontend.

## Quick Start

1. Install dependencies (if not already installed):
   ```bash
   pip install -r requirements.txt
   ```
2. Run the server from the `aiforteachers/` directory:
   ```bash
   uvicorn backend.app:app --host 127.0.0.1 --port 8000
   ```
3. Open `http://127.0.0.1:8000` in your browser.
4. Open **Settings** (bottom-left) to configure your API provider, API key, model, thinking level, teacher memory/focus areas, chat retention duration, language (9 languages), and light/dark mode.

## Running Tests

```bash
python3 -m unittest discover -s tests -v
```
