import tempfile
import time
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

from backend.app import app
from backend.chat_store import MarkdownChatStore
from backend.curriculum_kb import CurriculumKB
from backend.exporter import export_content, strip_thinking
from backend.llm_router import PROVIDERS, classify_intent, infer_thinking_levels


class TestAIForteachers(unittest.TestCase):
    def test_markdown_regex_roundtrip_and_retention(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = MarkdownChatStore(Path(tmp))
            c1 = store.save_chat({
                "id": "c_old",
                "title": "Old Fractions Lesson",
                "pinned": False,
                "created_at": time.time() - 40 * 86400,
                "messages": [
                    {"role": "user", "content": "Teach fractions"},
                    {"role": "assistant", "thinking": "Step 1", "content": "Here is the plan."},
                ],
            })
            p = Path(tmp) / "c_old.md"
            raw = p.read_text(encoding="utf-8")
            old_ts = f"{time.time() - 40 * 86400:.3f}"
            p.write_text(raw.replace(f"updated_at: {c1['updated_at']:.3f}", f"updated_at: {old_ts}"), encoding="utf-8")

            store.save_chat({
                "id": "c_new",
                "title": "Grade 7 Physics",
                "pinned": True,
                "messages": [
                    {"role": "user", "content": "Forces lesson"},
                    {"role": "assistant", "thinking": "Checking SCI-68-PS1", "content": "## Lesson Plan"},
                ],
            })

            loaded = store.get_chat("c_new")
            self.assertIsNotNone(loaded)
            self.assertEqual(loaded["messages"][1]["thinking"], "Checking SCI-68-PS1")

            listed = store.list_chats(retention_days=30)
            self.assertEqual(len(listed), 1)
            self.assertEqual(listed[0]["id"], "c_new")

    def test_curriculum_kb_and_custom_folders(self):
        with tempfile.TemporaryDirectory() as tmp:
            kb = CurriculumKB(
                Path(__file__).resolve().parent.parent / "data" / "curriculum_standards.json",
                Path(tmp) / "folders.json",
            )
            fld = kb.create_folder("108課綱自然科")
            self.assertEqual(fld["name"], "108課綱自然科")
            added = kb.add_standard_to_folder(fld["id"], {
                "code": "TW-NAT-7",
                "subject": "Science",
                "grade_level": "Grade 7",
                "title": "康軒版物質與能量",
                "objectives": ["認識物質的物理與化學變化"],
            })
            self.assertIsNotNone(added)
            matches = kb.search("康軒版物質與能量")
            self.assertTrue(any(m["id"] == "TW-NAT-7" for m in matches))

    def test_providers_and_thinking_inference(self):
        self.assertEqual(set(PROVIDERS.keys()), {"openai", "google_ai_studio", "deepseek", "other"})
        self.assertIn("high", infer_thinking_levels("google_ai_studio", "gemini-2.5-pro"))
        self.assertEqual(infer_thinking_levels("google_ai_studio", "gemini-2.0-flash"), ["default"])
        self.assertIn("high", infer_thinking_levels("deepseek", "deepseek-reasoner"))

    def test_intent_classification(self):
        self.assertEqual(classify_intent("Create a Grade 5 math lesson plan on fractions"), "lesson_prep")
        self.assertEqual(classify_intent("What is the bitcoin stock price today?"), "unrelated")

    def test_export_strips_thinking(self):
        raw = "<thinking>Secret reasoning</thinking>\n## Lesson Plan\n- Objective 1"
        self.assertEqual(strip_thinking(raw), "## Lesson Plan\n- Objective 1")
        self.assertNotIn(b"Secret reasoning", export_content(raw, "md", "Test"))
        self.assertTrue(len(export_content(raw, "docx", "Test")) > 100)
        self.assertTrue(export_content(raw, "pdf", "Test").startswith(b"%PDF"))

    def test_api_endpoints(self):
        client = TestClient(app)
        self.assertEqual(client.get("/").status_code, 200)
        self.assertEqual(client.get("/api/settings").status_code, 200)
        val_res = client.post("/api/models/validate", json={"provider": "openai", "api_key": "", "base_url": ""})
        self.assertEqual(val_res.status_code, 200)
        self.assertFalse(val_res.json()["valid"])
        stream_res = client.post("/api/chat/stream", json={"prompt": "Grade 7 science forces lesson plan"})
        self.assertEqual(stream_res.status_code, 200)
        self.assertIn("error", stream_res.text)


if __name__ == "__main__":
    unittest.main()
