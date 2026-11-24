import json
import re
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional


class CurriculumKB:
    def __init__(self, data_path: Path, custom_path: Optional[Path] = None):
        self.data_path = data_path
        self.custom_path = custom_path or (data_path.parent / "custom_standards_folders.json")
        self.standards: List[Dict[str, Any]] = []
        self.folders: List[Dict[str, Any]] = []
        self.reload()

    def reload(self) -> None:
        if self.data_path.exists():
            self.standards = json.loads(self.data_path.read_text(encoding="utf-8"))
        else:
            self.standards = []
        if self.custom_path.exists():
            try:
                self.folders = json.loads(self.custom_path.read_text(encoding="utf-8"))
            except Exception:
                self.folders = []
        else:
            self.folders = []

    def _save_folders(self) -> None:
        self.custom_path.parent.mkdir(parents=True, exist_ok=True)
        self.custom_path.write_text(json.dumps(self.folders, indent=2, ensure_ascii=False), encoding="utf-8")

    def list_folders(self) -> List[Dict[str, Any]]:
        return self.folders

    def create_folder(self, name: str) -> Dict[str, Any]:
        clean = (name or "").strip() or "New Standards Folder"
        folder = {
            "id": "fld_" + uuid.uuid4().hex[:8],
            "name": clean,
            "items": [],
        }
        self.folders.append(folder)
        self._save_folders()
        return folder

    def delete_folder(self, folder_id: str) -> bool:
        before = len(self.folders)
        self.folders = [f for f in self.folders if f["id"] != folder_id]
        if len(self.folders) < before:
            self._save_folders()
            return True
        return False

    def add_standard_to_folder(self, folder_id: str, item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        for f in self.folders:
            if f["id"] == folder_id:
                entry = {
                    "id": (item.get("code") or f"STD-{uuid.uuid4().hex[:6].upper()}").strip(),
                    "subject": (item.get("subject") or "General").strip(),
                    "grade_level": (item.get("grade_level") or "All Grades").strip(),
                    "title": (item.get("title") or "Untitled Standard").strip(),
                    "objectives": [o.strip() for o in (item.get("objectives") or []) if o.strip()],
                    "keywords": re.split(r"[\s,]+", f"{item.get('subject','')} {item.get('title','')}".lower()),
                }
                f["items"].append(entry)
                self._save_folders()
                return entry
        return None

    def delete_standard_from_folder(self, folder_id: str, std_id: str) -> bool:
        for f in self.folders:
            if f["id"] == folder_id:
                before = len(f["items"])
                f["items"] = [s for s in f["items"] if s["id"] != std_id]
                if len(f["items"]) < before:
                    self._save_folders()
                    return True
        return False

    def _all_standards(self) -> List[Dict[str, Any]]:
        custom_items = []
        for f in self.folders:
            for item in f.get("items", []):
                custom_items.append({**item, "folder": f["name"]})
        return custom_items + self.standards

    def search(self, query: str = "", subject: str = "", grade_level: str = "", limit: int = 4) -> List[Dict[str, Any]]:
        q = (query or "").lower().strip()
        subj = (subject or "").lower().strip()
        grade = (grade_level or "").lower().strip()

        scored = []
        for item in self._all_standards():
            score = 0
            item_subj = item.get("subject", "").lower()
            item_grade = item.get("grade_level", "").lower()
            text_blob = " ".join([
                item.get("id", ""),
                item_subj,
                item_grade,
                item.get("title", ""),
                " ".join(item.get("objectives", [])),
                " ".join(item.get("keywords", [])),
            ]).lower()

            if subj and subj in item_subj:
                score += 4
            if grade and any(tok in item_grade for tok in grade.split()):
                score += 3
            if q:
                for token in q.split():
                    if len(token) > 2 and token in text_blob:
                        score += 2
            if item.get("folder"):
                score += 1  # slight boost for teacher's own saved standards
            if score > 0 or (not q and not subj and not grade):
                scored.append((score, item))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [item for _, item in scored[:limit]]

    def format_context(self, matches: List[Dict[str, Any]]) -> str:
        if not matches:
            return ""
        lines = ["Relevant Curriculum Standards:"]
        for m in matches:
            objs = "; ".join(m.get("objectives", []))
            fld = f" (Folder: {m['folder']})" if m.get("folder") else ""
            lines.append(f"- [{m['id']}] {m['subject']} ({m['grade_level']}){fld} — {m['title']}: {objs}")
        return "\n".join(lines)
