# Sakura AI Documentation

Organized docs for the Sakura AI (local edition) personal AI. Start with **Architecture**,
then dive into the layer you care about.

| Doc | What's inside |
|---|---|
| [project-structure.md](project-structure.md) | The file/folder map, layer boundaries (who imports whom), and the frontend module split. |
| [architecture.md](architecture.md) | The big picture: how a message flows from UI → backend → agent → tools → model, and back. Diagram + directory map. |
| [setup.md](setup.md) | Install Ollama, pull models, install Python deps, run it (window or CLI). Troubleshooting. |
| [frontend.md](frontend.md) | The chat UI: layout, status indicator, confirmation flow, voice (push-to-talk), and how to restyle it. |
| [backend.md](backend.md) | The FastAPI server + the agent brain: routing, the tool-calling loop, memory, RAG, voice, reflection. |
| [api-reference.md](api-reference.md) | Every HTTP endpoint with request/response shapes and examples. |
| [tools.md](tools.md) | Every capability the model can call (incl. **web search**), its arguments, and whether it's gated. How to add your own. |
| [performance.md](performance.md) | How it's tuned to run **fast on 8GB RAM** — keep-alive, single-model mode, generation caps — and the speed/quality dial. |
| [your-machine.md](your-machine.md) | Hardware-specific tuning (auto Low-RAM profile, GPU/Vulkan notes, live Performance switch) for a Ryzen 5650U / 8 GB laptop. |
| [safety.md](safety.md) | The confirmation gates, the workspace lock, autonomy levels, and what "local" really guarantees. |
| [roadmap.md](roadmap.md) | The honest answer to "make it better than Claude" — what's realistic on local hardware and the concrete path to close the gap. |

## 30-second orientation

```
You type  ─▶  Frontend (index.html)  ─▶  Backend (ui_server.py)
                                              │
                                              ▼
                                     Agent brain (agent.py)
                                     routes → calls model → runs tools → loops
                                              │
                        ┌─────────────────────┼─────────────────────┐
                        ▼                     ▼                     ▼
                  Ollama models          tools/tools.py        memory + RAG
                  (llama/qwen/…)        (files, shell, …)      (SQLite, local)
```

Everything runs on your machine. The only network calls are (a) to your local Ollama
server and (b) whatever a tool you approved explicitly does (fetch a URL, send an email).
