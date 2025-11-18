let currentPath = "";
const api = {
  drives: "/api/drives",
  browse: "/api/browse",
  read: "/api/read",
  save: "/api/save",
  create: "/api/create",
  mkdir: "/api/mkdir",
  delete: "/api/delete",
  rename: "/api/rename",
  upload: "/api/upload",
  download: "/api/download",
  prompt: "/api/prompt"
};

async function $(sel){ return document.querySelector(sel) }

// init
window.addEventListener("load", async () => {
  document.getElementById("refreshBtn").onclick = loadDrives;
  document.getElementById("saveBtn").onclick = saveFile;
  document.getElementById("createBtn").onclick = createFile;
  document.getElementById("mkdirBtn").onclick = createFolder;
  document.getElementById("deleteBtn").onclick = deletePath;
  document.getElementById("downloadBtn").onclick = downloadFile;
  document.getElementById("promptRun").onclick = runPrompt;
  document.getElementById("pathInput").onchange = (e) => loadPath(e.target.value);

  await loadDrives();
});

async function loadDrives(){
  const res = await fetch(api.drives);
  const j = await res.json();
  const d = document.getElementById("drives");
  d.innerHTML = "";
  (j.drives || []).forEach(dr => {
    const btn = document.createElement("button");
    btn.innerText = dr;
    btn.onclick = () => loadPath(dr);
    d.appendChild(btn);
  })
}

async function loadPath(path){
  currentPath = path;
  document.getElementById("pathInput").value = path;
  try {
    const res = await fetch(`${api.browse}?path=${encodeURIComponent(path)}`);
    const j = await res.json();
    renderTree(j.items || []);
  } catch(err) {
    alert("Could not list path: " + err);
  }
}

function renderTree(items){
  const tree = document.getElementById("tree");
  tree.innerHTML = "";
  items.forEach(it => {
    const div = document.createElement("div");
    div.className = "file-item";
    div.innerHTML = `<div>
      <div style="font-weight:600">${it.name}</div>
      <div class="meta">${it.is_dir ? "Folder" : (it.size ? (it.size + " bytes") : "File")}</div>
    </div>
    <div>
      <button onclick="openItem(event,'${encodeURIComponent(it.path)}')">Open</button>
    </div>`;
    tree.appendChild(div);
  })
}

async function openItem(e, encpath){
  e.stopPropagation();
  const path = decodeURIComponent(encpath);
  if(!path) return;
  const res = await fetch(`${api.read}?path=${encodeURIComponent(path)}`);
  if(!res.ok){
    // likely directory: open path
    loadPath(path);
    return;
  }
  const j = await res.json();
  document.getElementById("editor").value = j.content;
  document.getElementById("pathInput").value = path;
  currentPath = path;
}

async function saveFile(){
  const path = document.getElementById("pathInput").value;
  const content = document.getElementById("editor").value;
  const res = await fetch(api.save, { method:"POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({path, content}) });
  const j = await res.json();
  document.getElementById("promptStatus").innerText = j.message || JSON.stringify(j);
  // refresh parent folder
  const parent = path.substring(0, path.lastIndexOf(path.includes("/") ? "/" : "\\"));
  loadPath(parent || path);
}

async function createFile(){
  const name = prompt("File name (relative to current folder):");
  if(!name) return;
  const path = (currentPath || "/") + (currentPath.endsWith("/") || currentPath.endsWith("\\") ? "" : (currentPath.includes("\\") ? "\\" : "/")) + name;
  const fd = new FormData();
  fd.append("path", path);
  await fetch(api.create, { method:"POST", body: fd });
  loadPath(currentPath);
}

async function createFolder(){
  const name = prompt("Folder name (relative to current folder):");
  if(!name) return;
  const path = (currentPath || "/") + (currentPath.endsWith("/") || currentPath.endsWith("\\") ? "" : (currentPath.includes("\\") ? "\\" : "/")) + name;
  const fd = new FormData();
  fd.append("path", path);
  await fetch(api.mkdir, { method:"POST", body: fd });
  loadPath(currentPath);
}

async function deletePath(){
  const path = document.getElementById("pathInput").value;
  if(!confirm("Delete " + path + " ?")) return;
  await fetch(`${api.delete}?path=${encodeURIComponent(path)}`, { method:"DELETE" });
  document.getElementById("editor").value = "";
  loadPath(currentPath.includes("/") ? currentPath.substring(0, currentPath.lastIndexOf("/")) : "/");
}

async function downloadFile(){
  const path = document.getElementById("pathInput").value;
  window.location = `${api.download}?path=${encodeURIComponent(path)}`;
}

async function runPrompt(){
  const prompt = document.getElementById("promptInput").value;
  if(!prompt.trim()) return;
  document.getElementById("promptStatus").innerText = "Processing...";
  const res = await fetch(api.prompt, { method:"POST", headers: {"Content-Type":"application/json"}, body: JSON.stringify({prompt}) });
  const j = await res.json();
  document.getElementById("promptStatus").innerText = j.message || j.error || JSON.stringify(j);
  // refresh current path to reflect changes
  loadPath(currentPath || "/");
}
