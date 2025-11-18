import os
import re
import json
from fastapi import FastAPI, Request, UploadFile, File, Form, Depends, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from dotenv import load_dotenv

# optional LLM
try:
    import google.generativeai as genai
except Exception:
    genai = None

from tools.local_tools import (
    list_drive_roots, list_directory, read_file, write_file, append_file,
    create_file, create_folder, delete_path, rename_path, save_upload
)

load_dotenv()

GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY")
if GOOGLE_API_KEY and genai:
    genai.configure(api_key=GOOGLE_API_KEY)

app = FastAPI()
templates = Jinja2Templates(directory="templates")
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/", response_class=HTMLResponse)
async def homepage(request: Request):
    return templates.TemplateResponse("index.html", {"request": request})

# --- Filesystem API ---
@app.get("/api/drives")
async def api_drives():
    return {"drives": list_drive_roots()}

@app.get("/api/browse")
async def api_browse(path: str):
    return {"items": list_directory(path)}

@app.get("/api/read")
async def api_read(path: str):
    return {"content": read_file(path)}

@app.post("/api/save")
async def api_save(data: dict):
    path = data.get("path")
    content = data.get("content", "")
    if not path:
        raise HTTPException(400, "path required")
    return write_file(path, content)

@app.post("/api/create")
async def api_create(path: str = Form(...)):
    return create_file(path)

@app.post("/api/mkdir")
async def api_mkdir(path: str = Form(...)):
    return create_folder(path)

@app.delete("/api/delete")
async def api_delete(path: str):
    return delete_path(path)

@app.post("/api/rename")
async def api_rename(old: str = Form(...), new: str = Form(...)):
    return rename_path(old, new)

@app.post("/api/upload")
async def api_upload(path: str = Form(...), file: UploadFile = File(...)):
    return save_upload(path, file)

@app.get("/api/download")
async def api_download(path: str):
    p = os.path.abspath(path)
    if not os.path.exists(p):
        raise HTTPException(404, "Not found")
    return FileResponse(p, media_type="application/octet-stream", filename=os.path.basename(p))

# --- Prompt parsing + optional LLM parsing ---
class PromptIn(BaseModel):
    prompt: str

def simple_parse_and_execute(prompt: str):
    """
    Very simple pattern-based parser:
    - create file PATH with content: CONTENT
    - append to file PATH with content: CONTENT
    - delete file PATH
    - create folder PATH
    - rename PATH to NEWPATH
    - write file PATH with content: CONTENT
    """
    low = prompt.strip()

    # create file
    m = re.search(r"create (?:a )?file\s+(?:at\s+)?(?P<path>['\"]?[^:]+?['\"]?)\s*(?:with content:|with content\s*[:\-])\s*(?P<content>.+)", low, re.I|re.S)
    if m:
        raw_path = m.group("path").strip(" '\"")
        content = m.group("content").strip()
        write_file(raw_path, content)
        return {"message": f"Created file {raw_path}"}

    # write file (overwrite)
    m = re.search(r"(?:write|save|update|edit)\s+(?:file\s+)?(?P<path>['\"]?[^:]+?['\"]?)\s*(?:with content:|with:)\s*(?P<content>.+)", low, re.I|re.S)
    if m:
        raw_path = m.group("path").strip(" '\"")
        content = m.group("content").strip()
        write_file(raw_path, content)
        return {"message": f"Wrote file {raw_path}"}

    # append
    m = re.search(r"(?:append to|add to)\s+(?:file\s+)?(?P<path>['\"]?[^:]+?['\"]?)\s*(?:with content:|with:)\s*(?P<content>.+)", low, re.I|re.S)
    if m:
        raw_path = m.group("path").strip(" '\"")
        content = m.group("content").strip()
        append_file(raw_path, content)
        return {"message": f"Appended to {raw_path}"}

    # delete file
    m = re.search(r"(?:delete|remove)\s+(?:file\s+)?(?P<path>['\"][^'\"]+['\"]|[^ ]+)", low, re.I)
    if m and ("delete file" in low or "remove file" in low):
        raw_path = m.group("path").strip(" '\"")
        delete_path(raw_path)
        return {"message": f"Deleted {raw_path}"}

    # create folder
    m = re.search(r"(?:create|make)\s+(?:a )?folder\s+(?:at\s+)?(?P<path>['\"][^'\"]+['\"]|[^ ]+)", low, re.I)
    if m:
        raw_path = m.group("path").strip(" '\"")
        create_folder(raw_path)
        return {"message": f"Created folder {raw_path}"}

    # rename: rename X to Y
    m = re.search(r"rename\s+(?P<old>['\"][^'\"]+['\"]|[^ ]+)\s+(?:to|as)\s+(?P<new>['\"][^'\"]+['\"]|[^ ]+)", low, re.I)
    if m:
        old = m.group("old").strip(" '\"")
        new = m.group("new").strip(" '\"")
        rename_path(old, new)
        return {"message": f"Renamed {old} -> {new}"}

    return {"error": "Could not parse prompt. Try: create file /path/to/file with content: ..."}

async def llm_parse_and_execute(prompt: str):
    # requires genai configured
    if not genai:
        return {"error": "LLM library not installed"}
    try:
        # Ask LLM to return JSON {"action":"create_file","path":"/...","content":"..."} exactly
        system = "You are a file system assistant. Parse the user's natural language instruction and return a single JSON object with keys: action (one of create_file, write_file, append_file, delete, mkdir, rename), path (string), content (optional), new_path (optional). Only output valid JSON. Do not add any commentary."
        resp = genai.generate_content(system_prompt=system, model="gemini-pro", text=prompt)
        # different versions of API may return differently; try to parse text
        text = getattr(resp, "text", None) or str(resp)
        parsed = json.loads(text)
        act = parsed.get("action")
        if act == "create_file" or act == "write_file":
            write_file(parsed["path"], parsed.get("content",""))
            return {"message": f"{act} executed", "path": parsed["path"]}
        if act == "append_file":
            append_file(parsed["path"], parsed.get("content",""))
            return {"message":"appended", "path": parsed["path"]}
        if act == "delete":
            delete_path(parsed["path"])
            return {"message":"deleted", "path": parsed["path"]}
        if act == "mkdir":
            create_folder(parsed["path"])
            return {"message":"mkdir", "path": parsed["path"]}
        if act == "rename":
            rename_path(parsed["path"], parsed.get("new_path"))
            return {"message":"renamed", "from": parsed["path"], "to": parsed.get("new_path")}
        return {"error":"Unrecognized action from LLM"}
    except Exception as ex:
        return {"error": f"LLM parse error: {ex}"}

@app.post("/api/prompt")
async def api_prompt(data: PromptIn):
    prompt = data.prompt
    # If LLM available, try LLM first; fallback to simple parser
    if GOOGLE_API_KEY and genai:
        result = await llm_parse_and_execute(prompt)
        # if LLM returned error or couldn't parse, try simple
        if "error" not in result:
            return result
    return simple_parse_and_execute(prompt)
