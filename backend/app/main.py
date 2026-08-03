import os
from datetime import date
from fastapi import FastAPI, Request, HTTPException
from supabase import create_client, Client

app = FastAPI()

# Supabase Admin Client
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY) if SUPABASE_URL and SUPABASE_KEY else None

def check_and_increment_usage(installation_id: int, owner_login: str) -> bool:
    if not supabase:
        return True

    today = date.today()
    response = supabase.table("usage_tracker").select("*").eq("github_installation_id", installation_id).execute()
    data = response.data
    
    if not data:
        supabase.table("usage_tracker").insert({
            "github_installation_id": installation_id,
            "owner_login": owner_login,
            "monthly_quota": 5,
            "used_this_month": 1,
            "last_reset_date": str(today)
        }).execute()
        return True
    
    record = data[0]
    last_reset = date.fromisoformat(record["last_reset_date"])
    
    if today.month != last_reset.month or today.year != last_reset.year:
        supabase.table("usage_tracker").update({
            "used_this_month": 1,
            "last_reset_date": str(today)
        }).eq("github_installation_id", installation_id).execute()
        return True
    
    if record["used_this_month"] >= record["monthly_quota"]:
        print(f"⚠️ Quota Limit Reached for installation {installation_id}")
        return False
        
    supabase.table("usage_tracker").update({
        "used_this_month": record["used_this_month"] + 1
    }).eq("github_installation_id", installation_id).execute()
    
    return True

@app.get("/")
def home():
    return {"message": "DevOps AI Agent Service is Live"}

@app.post("/webhook/github")
async def github_webhook(request: Request):
    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event")

    if event_type == "workflow_run":
        action = payload.get("action")
        workflow_run = payload.get("workflow_run", {})
        conclusion = workflow_run.get("conclusion")

        if action == "completed" and conclusion == "failure":
            installation_id = payload.get("installation", {}).get("id")
            owner_login = payload.get("repository", {}).get("owner", {}).get("login")

            if installation_id and owner_login:
                if not check_and_increment_usage(installation_id, owner_login):
                    return {"status": "ignored", "reason": "Monthly quota limit reached"}

            # Process failure with Gemini AI & GitHub API
            print("Processing failure with Gemini AI...")

    return {"status": "ok"}