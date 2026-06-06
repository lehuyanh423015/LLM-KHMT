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

### 2. Prepare Ollama Model
The chatbot uses one local Ollama model for final answer synthesis. Product facts come from memory/retrieval, not from switching between small and large models.

Pull the synthesis model before starting the backend:
```bash
ollama run qwen3:4b
```
*(You can exit the chat prompt immediately using `/bye`, as the model is now stored locally).*

### 3. Configure Environment
In the root directory, create a `.env` file by copying the provided example:
```bash
cp .env.example .env
```
Open `.env`. It is pre-configured to use one Ollama model for answer synthesis:
```ini
OLLAMA_MODEL=qwen3:4b
ENABLE_PRODUCT_CONTEXT=true
ENABLE_GROUNDED_PRODUCT_ANSWER=false
```
> Product knowledge comes from retrieval/catalog. The LLM is used to synthesize a clearer final answer from that grounded context.
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
*(Expected: returns JSON featuring `ollama_reachable: true` and `configured_model_exists: true`).*

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

#### Experiment C: Grounded Template vs LLM Synthesis
**Objective**: Compare deterministic retrieval output with LLM-written advice based on the same product context.
1. Set `ENABLE_GROUNDED_PRODUCT_ANSWER=true` for the fastest template answer.
2. Set `ENABLE_GROUNDED_PRODUCT_ANSWER=false` to let `qwen3:4b` synthesize the final response from retrieved memory/product context.
