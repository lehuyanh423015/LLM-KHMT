import asyncio
import json
import sys
import os
import io

# Fix for Windows Unicode output
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')

# Add apps/backend to sys.path
sys.path.append(os.path.abspath("e:/University/Semester VI/KHMT - INT3011E 4/LLM-KHMT/apps/backend"))

# Mock core.database to avoid DB dependency in scratch
import models.database_models
class MockDB:
    def query(self, *args, **kwargs): return self
    def filter(self, *args, **kwargs): return self
    def first(self): return None
    def add(self, *args): pass
    def commit(self): pass
    def refresh(self, *args): pass
    def rollback(self): pass

async def test_logic():
    from services.dialogue_orchestrator_service import DialogueOrchestrator
    from models.database_models import DialogueState
    from services.product_search_service import search_products_enhanced
    from core.config import settings
    
    orchestrator = DialogueOrchestrator()
    user_msg = "cho tôi một vài mẫu điện thoại ở tầm giá 15 triệu để phục vụ nhu cầu chơi game của tôi"
    
    print(f"--- Step 1: Orchestration ---")
    state = DialogueState(session_id="test-session")
    res = await orchestrator.process_user_message(user_msg, state, [], MockDB())
    
    print(f"Intent: {res['intent']}")
    print(f"Need Tool: {res['need_tool']}")
    print(f"Tool Type: {res['tool_type']}")
    print(f"Tool Query: {res['tool_query']}")
    
    if res['need_tool'] and res['tool_type'] == "product_search":
        print(f"\n--- Step 2: Product Search ---")
        try:
            query_params = json.loads(res['tool_query'])
            products = await search_products_enhanced(
                query=query_params.get("query", user_msg),
                category=query_params.get("category", "electronics"),
                budget_max=query_params.get("budget_max"),
                excluded_brands=query_params.get("excluded_brands", [])
            )
            print(f"Found {len(products)} products")
            for p in products[:3]:
                print(f"- {p['product_name']} | {p['price_vnd']} | {p['url']}")
        except Exception as e:
            print(f"Product Search FAILED: {e}")

if __name__ == "__main__":
    # Ensure env vars are loaded
    from dotenv import load_dotenv
    load_dotenv("e:/University/Semester VI/KHMT - INT3011E 4/LLM-KHMT/apps/backend/.env")
    
    asyncio.run(test_logic())
