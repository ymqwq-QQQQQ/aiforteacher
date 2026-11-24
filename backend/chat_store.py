import re
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

META_RE = re.compile(
    r"^---\s*\n"
    r"id:\s*(?P<id>[^\n]+)\n"
    r"title:\s*(?P<title>[^\n]+)\n"
    r"pinned:\s*(?P<pinned>true|false)\n"
    r"created_at:\s*(?P<created_at>\d+(?:\.\d+)?)\n"
    r"updated_at:\s*(?P<updated_at>\d+(?:\.\d+)?)\n"
    r"---\s*\n?",
    re.MULTILINE,
)

MSG_BLOCK_RE = re.compile(
    r"### \[(?P<role>USER|ASSISTANT)\]\s*\n(?P<body>.*?)(?=\n### \[(?:USER|ASSISTANT)\]|\Z)",
    re.DOTALL,
)

THINK_RE = re.compile(r"<thinking>\s*(?P<think>.*?)\s*</thinking>\s*", re.DOTALL)


class MarkdownChatStore:
    def __init__(self, chats_dir: Path):
        self.chats_dir = chats_dir
        self.chats_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, chat_id: str) -> Path:
        safe_id = re.sub(r"[^a-zA-Z0-9_-]", "", chat_id)
        return self.chats_dir / f"{safe_id}.md"

    def serialize_chat(self, chat: Dict[str, Any]) -> str:
        title = (chat.get("title") or "Untitled Chat").replace("\n", " ").strip()
        pinned = "true" if chat.get("pinned") else "false"
        created_at = float(chat.get("created_at", time.time()))
        updated_at = float(chat.get("updated_at", created_at))
        lines = [
            "---",
            f"id: {chat['id']}",
            f"title: {title}",
            f"pinned: {pinned}",
            f"created_at: {created_at:.3f}",
            f"updated_at: {updated_at:.3f}",
            "---",
            "",
        ]
        for msg in chat.get("messages", []):
            role = "USER" if msg.get("role") == "user" else "ASSISTANT"
            lines.append(f"### [{role}]")
            thinking = (msg.get("thinking") or "").strip()
            if role == "ASSISTANT" and thinking:
                lines.append(f"<thinking>\n{thinking}\n</thinking>")
            lines.append((msg.get("content") or "").strip())
            lines.append("")
        return "\n".join(lines).rstrip() + "\n"

    def parse_chat(self, raw_md: str) -> Optional[Dict[str, Any]]:
        m = META_RE.search(raw_md)
        if not m:
            return None
        body = raw_md[m.end():]
        messages: List[Dict[str, Any]] = []
        for bm in MSG_BLOCK_RE.finditer(body):
            role = "user" if bm.group("role") == "USER" else "assistant"
            msg_body = bm.group("body").strip()
            thinking = ""
            if role == "assistant":
                tm = THINK_RE.search(msg_body)
                if tm:
                    thinking = tm.group("think").strip()
                    msg_body = THINK_RE.sub("", msg_body, count=1).strip()
            messages.append({
                "role": role,
                "thinking": thinking,
                "content": msg_body,
            })
        return {
            "id": m.group("id").strip(),
            "title": m.group("title").strip(),
            "pinned": m.group("pinned").strip() == "true",
            "created_at": float(m.group("created_at")),
            "updated_at": float(m.group("updated_at")),
            "messages": messages,
        }

    def save_chat(self, chat: Dict[str, Any]) -> Dict[str, Any]:
        if not chat.get("id"):
            chat["id"] = uuid.uuid4().hex[:12]
        now = time.time()
        chat.setdefault("created_at", now)
        chat["updated_at"] = now
        path = self._path_for(chat["id"])
        path.write_text(self.serialize_chat(chat), encoding="utf-8")
        return chat

    def get_chat(self, chat_id: str) -> Optional[Dict[str, Any]]:
        path = self._path_for(chat_id)
        if not path.exists():
            return None
        return self.parse_chat(path.read_text(encoding="utf-8"))

    def list_chats(self, query: str = "", retention_days: Optional[int] = None) -> List[Dict[str, Any]]:
        now = time.time()
        cutoff = now - (retention_days * 86400) if retention_days and retention_days > 0 else None
        q = (query or "").lower().strip()
        items: List[Dict[str, Any]] = []
        for path in self.chats_dir.glob("*.md"):
            chat = self.parse_chat(path.read_text(encoding="utf-8"))
            if not chat:
                continue
            if cutoff and not chat["pinned"] and chat["updated_at"] < cutoff:
                path.unlink(missing_ok=True)
                continue
            if q:
                haystack = chat["title"].lower() + " " + " ".join(m["content"].lower() for m in chat["messages"])
                if q not in haystack:
                    continue
            items.append({
                "id": chat["id"],
                "title": chat["title"],
                "pinned": chat["pinned"],
                "created_at": chat["created_at"],
                "updated_at": chat["updated_at"],
                "message_count": len(chat["messages"]),
            })
        items.sort(key=lambda x: (not x["pinned"], -x["updated_at"]))
        return items

    def update_chat_meta(self, chat_id: str, title: Optional[str] = None, pinned: Optional[bool] = None) -> Optional[Dict[str, Any]]:
        chat = self.get_chat(chat_id)
        if not chat:
            return None
        if title is not None:
            chat["title"] = title.strip() or chat["title"]
        if pinned is not None:
            chat["pinned"] = bool(pinned)
        return self.save_chat(chat)

    def delete_chat(self, chat_id: str) -> bool:
        path = self._path_for(chat_id)
        if path.exists():
            path.unlink()
            return True
        return False
