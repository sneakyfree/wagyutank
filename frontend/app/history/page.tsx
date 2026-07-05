"use client";
import { useEffect, useState } from "react";
import { api } from "../../lib/api";

function renderMarkdown(md: string): string {
  const esc = (s: string) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
  const inline = (s: string) =>
    esc(s).replace(/\*\*(.+?)\*\*/g, "<strong>$1</strong>").replace(/\*(.+?)\*/g, "<em>$1</em>");
  const lines = md.split("\n");
  let html = "", inList = false;
  const closeList = () => { if (inList) { html += "</ul>"; inList = false; } };
  for (const raw of lines) {
    const line = raw.trimEnd();
    if (/^### /.test(line)) { closeList(); html += `<h3>${inline(line.slice(4))}</h3>`; }
    else if (/^## /.test(line)) { closeList(); html += `<h2>${inline(line.slice(3))}</h2>`; }
    else if (/^# /.test(line)) { closeList(); html += `<h1>${inline(line.slice(2))}</h1>`; }
    else if (/^---\s*$/.test(line)) { closeList(); html += "<hr/>"; }
    else if (/^[-*] /.test(line)) { if (!inList) { html += "<ul>"; inList = true; } html += `<li>${inline(line.slice(2))}</li>`; }
    else if (line === "") { closeList(); }
    else { closeList(); html += `<p>${inline(line)}</p>`; }
  }
  closeList();
  return html;
}

export default function History() {
  const [md, setMd] = useState<string | null>(null);
  useEffect(() => { api.breedHistory().then((r) => setMd(r.markdown)).catch(() => setMd("")); }, []);
  return (
    <div className="container section">
      <div className="prose">
        {md === null ? <p className="muted">Loading…</p> : (
          <div dangerouslySetInnerHTML={{ __html: renderMarkdown(md) }} />
        )}
      </div>
    </div>
  );
}
