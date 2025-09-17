import json
import asyncio
from pathlib import Path


log_lock = asyncio.Lock()
LOG_FILE = Path("logs/request_logs.json")

async def log_request_response(log_data: dict):
    
    async with log_lock:
        try:
            logs = []
            
            if LOG_FILE.exists() and LOG_FILE.stat().st_size > 0:
                with open(LOG_FILE, "r", encoding="utf-8") as f:
                    try:
                        logs = json.load(f)
                        
                        if not isinstance(logs, list):
                            logs = []
                    except json.JSONDecodeError:
                        
                        logs = []

            
            if not logs:
                next_id = 1
            else:
                
                max_id = max(log.get("id", 0) for log in logs)
                next_id = max_id + 1

            
            log_data["id"] = next_id

            
            logs.append(log_data)

            
            with open(LOG_FILE, "w", encoding="utf-8") as f:
                json.dump(logs, f, ensure_ascii=False, indent=4)

        except Exception as e:
            print(f"Error writing to JSON log file: {e}")