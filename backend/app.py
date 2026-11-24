from pathlib import Path
from typing import Any, Dict, List, Literal, Optional

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response, StreamingResponse
from pydantic import BaseModel

from backend.chat_store import MarkdownChatStore
from backend.curriculum_kb import CurriculumKB
from backend.exporter import export_content, format_filename
from backend.llm_router import PROVIDERS, stream_lesson_response, validate_and_fetch_models
from backend.memory_store import LocalStateStore

BASE_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = BASE_DIR / "data"
STORAGE_DIR = BASE_DIR / "storage"
FRONTEND_FILE = BASE_DIR / "frontend" / "index.html"

kb = CurriculumKB(DATA_DIR / "curriculum_standards.json", STORAGE_DIR / "custom_standards_folders.json")
chat_store = MarkdownChatStore(STORAGE_DIR / "chats")
state_store = LocalStateStore(STORAGE_DIR / "state")

app = FastAPI(title="aiforteachers v1.0", version="1.0.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class ChatStreamRequest(BaseModel):
    chat_id: Optional[str] = None
    prompt: str
    use_web_search: bool = False


class ChatMetaPatch(BaseModel):
    title: Optional[str] = None
    pinned: Optional[bool] = None


class ChatSaveRequest(BaseModel):
    id: Optional[str] = None
    title: str
    pinned: bool = False
    messages: List[Dict[str, Any]]


class FolderCreateRequest(BaseModel):
    name: str


class StandardCreateRequest(BaseModel):
    code: Optional[str] = ""
    subject: str
    grade_level: str
    title: str
    objectives: List[str] = []


class ExportRequest(BaseModel):
    title: str = "Lesson Plan"
    content: str
    format: Literal["md", "docx", "pdf"]


@app.get("/")
def serve_frontend() -> FileResponse:
    return FileResponse(FRONTEND_FILE)


@app.get("/api/providers")
def get_providers() -> Dict[str, Any]:
    return {"providers": PROVIDERS}


@app.get("/api/settings")
def get_settings() -> Dict[str, Any]:
    return state_store.get_settings()


@app.put("/api/settings")
def put_settings(payload: Dict[str, Any]) -> Dict[str, Any]:
    return state_store.save_settings(payload)


@app.get("/api/memory")
def get_memory() -> Dict[str, Any]:
    return state_store.get_memory()


@app.put("/api/memory")
def put_memory(payload: Dict[str, Any]) -> Dict[str, Any]:
    return state_store.save_memory(payload)


@app.post("/api/models/validate")
async def validate_models(payload: Dict[str, Any]) -> Dict[str, Any]:
    settings = state_store.get_settings()
    provider = payload.get("provider", settings.get("provider", "openai"))
    api_key = payload.get("api_key", settings.get("api_key", ""))
    base_url = payload.get("base_url", settings.get("base_url", ""))
    model = payload.get("model", settings.get("model", ""))
    thinking_level = payload.get("thinking_level", settings.get("thinking_level", "default"))
    return await validate_and_fetch_models(provider, api_key, base_url, model, thinking_level)


@app.get("/api/standards")
def search_standards(q: str = "", subject: str = "", grade: str = "") -> Dict[str, Any]:
    return {"standards": kb.search(query=q, subject=subject, grade_level=grade, limit=10)}


@app.get("/api/standards/folders")
def list_standard_folders() -> Dict[str, Any]:
    return {"folders": kb.list_folders()}


@app.post("/api/standards/folders")
def create_standard_folder(req: FolderCreateRequest) -> Dict[str, Any]:
    return kb.create_folder(req.name)


@app.delete("/api/standards/folders/{folder_id}")
def delete_standard_folder(folder_id: str) -> Dict[str, Any]:
    if not kb.delete_folder(folder_id):
        raise HTTPException(status_code=404, detail="Folder not found")
    return {"deleted": True}


@app.post("/api/standards/folders/{folder_id}/items")
def add_standard_item(folder_id: str, req: StandardCreateRequest) -> Dict[str, Any]:
    item = kb.add_standard_to_folder(folder_id, req.model_dump())
    if not item:
        raise HTTPException(status_code=404, detail="Folder not found")
    return item


@app.delete("/api/standards/folders/{folder_id}/items/{std_id}")
def delete_standard_item(folder_id: str, std_id: str) -> Dict[str, Any]:
    if not kb.delete_standard_from_folder(folder_id, std_id):
        raise HTTPException(status_code=404, detail="Standard not found")
    return {"deleted": True}


@app.get("/api/chats")
def list_chats(q: str = "") -> Dict[str, Any]:
    settings = state_store.get_settings()
    days = settings.get("storage_duration_days", 30)
    return {"chats": chat_store.list_chats(query=q, retention_days=days)}


@app.get("/api/chats/{chat_id}")
def get_chat(chat_id: str) -> Dict[str, Any]:
    chat = chat_store.get_chat(chat_id)
    if not chat:
        raise HTTPException(status_code=404, detail="Chat not found")
    return chat


@app.post("/api/chats")
def save_chat(req: ChatSaveRequest) -> Dict[str, Any]:
    return chat_store.save_chat(req.model_dump())


@app.patch("/api/chats/{chat_id}")
def patch_chat(chat_id: str, req: ChatMetaPatch) -> Dict[str, Any]:
    updated = chat_store.update_chat_meta(chat_id, title=req.title, pinned=req.pinned)
    if not updated:
        raise HTTPException(status_code=404, detail="Chat not found")
    return updated


@app.delete("/api/chats/{chat_id}")
def delete_chat(chat_id: str) -> Dict[str, Any]:
    if not chat_store.delete_chat(chat_id):
        raise HTTPException(status_code=404, detail="Chat not found")
    return {"deleted": True}


@app.post("/api/chat/stream")
async def chat_stream(req: ChatStreamRequest) -> StreamingResponse:
    settings = state_store.get_settings()
    memory = state_store.get_memory()
    history: List[Dict[str, Any]] = []
    if req.chat_id:
        existing = chat_store.get_chat(req.chat_id)
        if existing:
            history = existing.get("messages", [])
    return StreamingResponse(
        stream_lesson_response(req.prompt, history, settings, memory, kb, req.use_web_search),
        media_type="text/event-stream",
    )


@app.post("/api/export")
def export_answer(req: ExportRequest) -> Response:
    memory = state_store.get_memory()
    filename = format_filename(req.title, memory.get("file_naming", "{title}_{date}"), req.format)
    data = export_content(req.content, req.format, title=req.title)
    media_types = {
        "md": "text/markdown; charset=utf-8",
        "docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        "pdf": "application/pdf",
    }
    return Response(
        content=data,
        media_type=media_types[req.format],
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
