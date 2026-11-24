import json
from pathlib import Path
from typing import Any, Dict

DEFAULT_SETTINGS: Dict[str, Any] = {
    "provider": "openai",
    "base_url": "",
    "api_key": "",
    "model": "gpt-4o-mini",
    "thinking_level": "default",
    "storage_duration_days": 30,
    "language": "en",
    "theme": "light",
    "help_email": "teacher-support@example.com",
}

DEFAULT_MEMORY: Dict[str, Any] = {
    "focus_areas": "",
    "file_naming": "{title}_{date}",
    "chat_style": "Clear, structured, classroom-ready",
    "notes": "",
}


class LocalStateStore:
    def __init__(self, state_dir: Path):
        self.state_dir = state_dir
        self.state_dir.mkdir(parents=True, exist_ok=True)
        self.settings_path = self.state_dir / "settings.json"
        self.memory_path = self.state_dir / "memory.json"

    def get_settings(self) -> Dict[str, Any]:
        if not self.settings_path.exists():
            return dict(DEFAULT_SETTINGS)
        try:
            data = json.loads(self.settings_path.read_text(encoding="utf-8"))
            return {**DEFAULT_SETTINGS, **data}
        except Exception:
            return dict(DEFAULT_SETTINGS)

    def save_settings(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = {**self.get_settings(), **payload}
        self.settings_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        return merged

    def get_memory(self) -> Dict[str, Any]:
        if not self.memory_path.exists():
            return dict(DEFAULT_MEMORY)
        try:
            data = json.loads(self.memory_path.read_text(encoding="utf-8"))
            return {**DEFAULT_MEMORY, **data}
        except Exception:
            return dict(DEFAULT_MEMORY)

    def save_memory(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        merged = {**self.get_memory(), **payload}
        self.memory_path.write_text(json.dumps(merged, indent=2, ensure_ascii=False), encoding="utf-8")
        return merged
