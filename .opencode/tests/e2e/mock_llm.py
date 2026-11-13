"""Faux fournisseur compatible OpenAI (chat/completions, streaming) pour tester
permissions et plugins OpenCode sans clé ni LLM réel.

Le scénario (JSON) liste les appels d'outils à émettre dans l'ordre :
  [{"tool": "read", "args": {"path": "/abs/.env"}}, ...]      (noms et arguments des outils OpenCode 2.x)
Après le dernier appel, le faux modèle répond par un texte qui recopie les
résultats d'outils reçus (permet de voir ce que l'agent « observe »).
Usage : python3 mock_llm.py scenario.json <port> journal.jsonl <racine_du_depot>
({RACINE} dans le scénario est remplacé par la racine du dépôt.)
MOCK_CONTEXTE=1 : le journal contient aussi le prompt système et la définition des outils reçus
(utilisé par ce-que-voit-le-modele.sh).
"""
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RACINE = sys.argv[4] if len(sys.argv) > 4 else "."
SCENARIO = json.loads(open(sys.argv[1], encoding="utf-8").read().replace("{RACINE}", RACINE))
PORT = int(sys.argv[2])
JOURNAL = sys.argv[3]
CONTEXTE = os.environ.get("MOCK_CONTEXTE") == "1"


def chunk(delta, finish=None):
    return {
        "id": "mock-1", "object": "chat.completion.chunk", "created": int(time.time()),
        "model": "scripted",
        "choices": [{"index": 0, "delta": delta, "finish_reason": finish}],
    }


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *args):
        pass

    def do_GET(self):
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps({"data": [{"id": "scripted", "object": "model"}]}).encode())

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))) or b"{}")
        messages = body.get("messages", [])
        tools = body.get("tools") or []
        done = sum(1 for m in messages if m.get("role") == "assistant" and m.get("tool_calls"))
        tool_results = [m for m in messages if m.get("role") == "tool"]
        with open(JOURNAL, "a", encoding="utf-8") as j:
            ligne = {"tools_offerts": sorted(t["function"]["name"] for t in tools),
                     "etape": done,
                     "dernier_resultat": str(tool_results[-1]["content"])[:600] if tool_results else None}
            if CONTEXTE and tools:
                ligne["systeme"] = "\n".join(str(m.get("content")) for m in messages if m.get("role") == "system")
                ligne["outils"] = {t["function"]["name"]: t["function"].get("description", "") for t in tools}
            j.write(json.dumps(ligne, ensure_ascii=False) + "\n")
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        events = []
        if tools and done < len(SCENARIO):
            step = SCENARIO[done]
            events.append(chunk({"role": "assistant", "tool_calls": [{
                "index": 0, "id": f"call_{done}", "type": "function",
                "function": {"name": step["tool"], "arguments": json.dumps(step["args"])}}]}))
            events.append(chunk({}, "tool_calls"))
        else:
            text = "Résultats observés :\n" + "\n---\n".join(
                str(m.get("content"))[:300] for m in tool_results) if tools else "Titre de test"
            events.append(chunk({"role": "assistant", "content": text}))
            events.append(chunk({}, "stop"))
        for e in events:
            self.wfile.write(f"data: {json.dumps(e, ensure_ascii=False)}\n\n".encode())
        usage = {"id": "mock-1", "object": "chat.completion.chunk", "created": 0, "model": "scripted",
                 "choices": [], "usage": {"prompt_tokens": 10, "completion_tokens": 5, "total_tokens": 15}}
        self.wfile.write(f"data: {json.dumps(usage)}\n\ndata: [DONE]\n\n".encode())


ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
