# Continual Learning Conversational AI

A minimal, beginner-friendly starter template for building a Continual Learning AI System. It includes a modern Next.js frontend and a FastAPI backend with SQLite, Chroma, and a Local LLM Provider (Ollama) pre-configured.

## 🚀 Features
- **Frontend**: Next.js 15, React 19, TypeScript, Tailwind CSS, minimal App Router setup.
- **Backend**: FastAPI, Async Local LLM integration via Ollama pattern provider.
- **Database**: SQLite with SQLAlchemy for storing conversations and messages.
- **Vector Store**: ChromaDB (locally persisted) scaffolding ready for continual learning logic.

## 📁 Project Structure

```text
.
├── apps/
│   ├── frontend/         # Next.js web application
│   └── backend/          # FastAPI REST API
│       ├── core/         # Config and database engines
│       ├── models/       # ORM definitions and Pydantic schemas
│       ├── routes/       # API endpoint handlers
│       ├── services/     # Modular LLM Providers and Continual Learning Placeholders
│       └── vector_store/ # Chroma connection and memory logic
├── chroma_data/          # Local vector storage (generated on run)
├── app.db                # SQLite database (generated on run)
└── package.json          # ...
```

## 🛠️ Local Setup Instructions

### 1. Requirements
- Node.js >= 20
- Python >= 3.10
- pnpm (package manager for frontend)
- [Ollama](https://ollama.com/) (For running LLMs locally)

### 2. Prepare Ollama Models (Operation Modes)
The chatbot supports two runtime modes:
- **FAST MODE** (`qwen2.5:0.5b`): Perfect for development. Runs instantly even without a dedicated GPU.
- **QUALITY MODE** (`qwen3:4b`): Perfect for the final academic demo. Slower, but provides much better reasoning and natural conversation.

Pull both models before starting the backend:
```bash
ollama run qwen2.5:0.5b
ollama run qwen3:4b
```
*(You can exit the chat prompt immediately using `/bye`, as the model is now stored locally).*

### 3. Configure Environment
In the root directory, create a `.env` file by copying the provided example:
```bash
cp .env.example .env
```
Open `.env`. It is pre-configured to use Ollama with `fast` mode active:
```ini
LLM_MODE=fast
OLLAMA_FAST_MODEL=qwen2.5:0.5b
OLLAMA_QUALITY_MODEL=qwen3:4b
```
> **How to switch modes**: You can change `LLM_MODE=quality` inside `.env` to enforce high-quality generation. Or, natively click the "FAST / QUALITY" toggle button instantly inside the Frontend Browser UI toolbar!
### 4. Backend Setup
The backend runs on Python and uses a virtual environment to manage dependencies.

```bash
cd apps/backend

# Create a virtual environment
python -m venv venv

# Activate the virtual environment
# On Windows:
venv\Scripts\activate
# On Mac/Linux:
# source venv/bin/activate

# Install dependencies
pip install -r requirements.txt

# Run the backend server
uvicorn main:app --reload --port 8000
```

### 5. Frontend Setup
The frontend uses Next.js and pnpm. Open a new terminal window:

```bash
cd apps/frontend

# Install dependencies using pnpm
pnpm install

# Run the development server
pnpm dev
```
*The frontend web app will be running at http://localhost:3000*

## 🧪 Testing Endpoints

### Health Check (GET `/health`)
Test if the backend is successfully connected to Ollama:
```bash
curl http://localhost:8000/health
```
*(Expected: returns JSON featuring `ollama_reachable: true` and `model_available_in_ollama: true`).*

### Chat (POST `/chat`)
Test the inference:
```bash
curl -X POST http://localhost:8000/chat \
     -H "Content-Type: application/json" \
     -d '{"message": "Hello! What model are you?"}'
```

## 🧠 Continual Learning: Academic Demonstration

## 🧠 Continual Learning: Academic Demonstration

This system represents an advanced **Shopping Assistant chatbot** that can securely store and remember customer preferences locally using SQLite, and properly thread conversational contexts!

### Under the Hood Structure
1. **Conversational Context**: Before calling Ollama, `apps/backend/services/chat_context_service.py` securely extracts the 6 most recent conversational turns from the database and constructs a highly intelligent array-based context payload. This stops "amnesia" between turns.
2. **Customer Memory Extraction**: `apps/backend/services/memory_service.py` functions as an invisible heuristic listener. Whenever you talk to the agent, it extracts crucial shopping profile logic (Budget, Priorities, Category, Dislikes) and actively handles updates and overwrites smartly over time.
3. **Retrieval**: `apps/backend/services/retrieval_service.py` sweeps through this saved parameter base and natively rebuilds the LLM system prompt right before handing it to Ollama.
4. **Dynamic Experiment Configuration**: FastAPI endpoints natively accept runtime UI toggles to enable or disable these modules on the fly, allowing easy academic experiments and ablations.

### 🧪 Running Academic Experiments

The backend features `ENABLE_MEMORY` and `ENABLE_RECENT_CONTEXT` environment variables. Through the UI, these are exposed natively for **live experimental comparison**.

#### Experiment A: Memory Enabled vs Memory Disabled
**Objective**: Demonstrate how explicit profile tracking shapes reasoning.
1. Open the UI, open the **Customer Profile Memory** panel. Ensure both Experiment controls are checked.
2. Send: *"I want to buy a laptop under 20 million VND for gaming."*
3. Notice that immediately after the bot replies, the Customer Profile updates the UI reflecting Budget: 20 million and Category: laptop.
4. Now, uncheck **Enable Memory Extraction** in the UI panel.
5. In a new conversation tab (or after clearing storage), if you try to ask for recommendations, the AI will forget your exact budget parameters constraints that were formally saved. Re-enabling it causes the AI to instantly remember that budget again via system injection!

#### Experiment B: Dynamic Feature Overwrites
**Objective**: Demonstrate Continual Learning Heuristics adjusting bounds dynamically.
1. Continuing from the laptop example, send: *"Actually, I don't want a gaming laptop anymore. I dislike heavy machines. I prefer lightweight."*
2. Watch the Debug panel. The parameters overwrite with the new Priority (`lightweight`) and explicitly removes contradicting items from past turns, registering `heavy` inside Dislikes!
3. Future replies natively shape around this new requirement!

#### Experiment C: Fast vs Quality Inference
**Objective**: Compare latency and reasoning logic between 0.5b parameters and 4b parameters.
1. Click the toggle at the top of the chat: `FAST (Zap)` -> `QUALITY (Star)`.
2. Send identical questions and compare how well `qwen3:4b` respects negative constraints compared to the fast model!
