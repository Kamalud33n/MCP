import os
import shutil
from pathlib import Path
from fastapi import HTTPException, UploadFile

# Helpers: normalize path (on Windows allow C:\ style), no sandboxing (user asked full access)
def norm_path(p: str) -> str:
    return os.path.abspath(os.path.expanduser(p))

def list_drive_roots():
    # Cross-platform: on Windows return drives; on *nix return root "/"
    if os.name == "nt":
        drives = []
        for letter in "ABCDEFGHIJKLMNOPQRSTUVWXYZ":
            d = f"{letter}:\\"
            if os.path.exists(d):
                drives.append(d)
        return drives
    else:
        return ["/"]

def list_directory(path: str):
    p = norm_path(path)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Path not found")
    try:
        entries = []
        with os.scandir(p) as it:
            for e in it:
                entries.append({
                    "name": e.name,
                    "path": e.path,
                    "is_dir": e.is_dir(),
                    "size": e.stat().st_size if not e.is_dir() else None
                })
        # sort: directories first then files
        entries.sort(key=lambda x: (not x["is_dir"], x["name"].lower()))
        return entries
    except PermissionError:
        raise HTTPException(status_code=403, detail="Permission denied")
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

def read_file(path: str):
    p = norm_path(path)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="File not found")
    if os.path.isdir(p):
        raise HTTPException(status_code=400, detail="Path is a directory")
    try:
        # try to return as text; ignore errors in decoding
        with open(p, "r", encoding="utf-8", errors="replace") as f:
            return f.read()
    except Exception as ex:
        # for binary or other, return base64? but we raise
        raise HTTPException(status_code=500, detail=str(ex))

def write_file(path: str, content: str):
    p = norm_path(path)
    dirname = os.path.dirname(p)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname, exist_ok=True)
    try:
        with open(p, "w", encoding="utf-8") as f:
            f.write(content)
        return {"status": "ok", "path": p}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

def append_file(path: str, content: str):
    p = norm_path(path)
    try:
        with open(p, "a", encoding="utf-8") as f:
            f.write(content)
        return {"status": "appended", "path": p}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

def create_file(path: str):
    p = norm_path(path)
    dirname = os.path.dirname(p)
    if dirname and not os.path.exists(dirname):
        os.makedirs(dirname, exist_ok=True)
    try:
        open(p, "a").close()
        return {"status": "created", "path": p}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

def create_folder(path: str):
    p = norm_path(path)
    try:
        os.makedirs(p, exist_ok=True)
        return {"status": "created_folder", "path": p}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

def delete_path(path: str):
    p = norm_path(path)
    if not os.path.exists(p):
        raise HTTPException(status_code=404, detail="Not found")
    try:
        if os.path.isdir(p):
            # only remove empty dir for safety; if you want recursive, use shutil.rmtree
            if not os.listdir(p):
                os.rmdir(p)
            else:
                # recursive delete
                shutil.rmtree(p)
        else:
            os.remove(p)
        return {"status": "deleted", "path": p}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

def rename_path(old: str, new: str):
    oldp = norm_path(old)
    newp = norm_path(new)
    try:
        os.makedirs(os.path.dirname(newp), exist_ok=True)
        os.rename(oldp, newp)
        return {"status": "renamed", "from": oldp, "to": newp}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))

def save_upload(target_path: str, upload: UploadFile):
    p = norm_path(target_path)
    dirname = os.path.dirname(p)
    os.makedirs(dirname, exist_ok=True)
    try:
        with open(p, "wb") as f:
            shutil.copyfileobj(upload.file, f)
        return {"status": "uploaded", "path": p, "filename": upload.filename}
    except Exception as ex:
        raise HTTPException(status_code=500, detail=str(ex))
