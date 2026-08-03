import os
import hmac
import hashlib
from datetime import date
from fastapi import FastAPI, Request, HTTPException, Header
from fastapi.responses import HTMLResponse, JSONResponse
from supabase import create_client, Client

# Initialize FastAPI Application
app = FastAPI(
    title="DevOps AI Agent",
    description="Automated CI Failure Detection, Quota Management & AI PR Generator",
    version="1.0.0"
)

# ------------------------------------------------------------------
# Environment Variables & Configuration
# ------------------------------------------------------------------
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
GITHUB_WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET")
GITHUB_TOKEN = os.getenv("GITHUB_TOKEN")
GEMINI_API_KEY = os.getenv("LLM_API_KEY") or os.getenv("GEMINI_API_KEY")

# Initialize Supabase Admin Client safely
supabase: Client = None
if SUPABASE_URL and SUPABASE_KEY:
    try:
        supabase = create_client(SUPABASE_URL, SUPABASE_KEY)
        print("✅ Supabase client initialized successfully.")
    except Exception as e:
        print(f"⚠️ Failed to initialize Supabase client: {e}")
else:
    print("⚠️ SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing.")


# ------------------------------------------------------------------
# Helper Functions
# ------------------------------------------------------------------
def verify_github_signature(payload_body: bytes, signature_header: str) -> bool:
    """Verifies HMAC SHA-256 signature from incoming GitHub Webhooks."""
    if not GITHUB_WEBHOOK_SECRET:
        return True  # Skip signature check if secret is not set
    if not signature_header:
        return False
    
    hash_object = hmac.new(
        GITHUB_WEBHOOK_SECRET.encode("utf-8"),
        msg=payload_body,
        digestmod=hashlib.sha256
    )
    expected_signature = "sha256=" + hash_object.hexdigest()
    return hmac.compare_digest(expected_signature, signature_header)


def check_and_increment_usage(installation_id: int, owner_login: str) -> bool:
    """
    Checks if an installation has remaining AI fix quota.
    Increments usage if allowed, or resets monthly quota if a new month has started.
    Returns True if execution can proceed, False if limit exceeded.
    """
    if not supabase:
        print("⚠️ Supabase not configured. Bypassing quota check.")
        return True

    today = date.today()
    
    try:
        # 1. Fetch usage record from Supabase
        response = supabase.table("usage_tracker").select("*").eq("github_installation_id", installation_id).execute()
        data = response.data
        
        # 2. First time user -> Insert initial record with 1 fix used
        if not data:
            supabase.table("usage_tracker").insert({
                "github_installation_id": installation_id,
                "owner_login": owner_login,
                "monthly_quota": 5,
                "used_this_month": 1,
                "last_reset_date": str(today)
            }).execute()
            print(f"✨ Registered new installation: {owner_login} (ID: {installation_id})")
            return True
        
        record = data[0]
        last_reset = date.fromisoformat(record["last_reset_date"])
        
        # 3. Check if a new month has started -> Reset counter to 1
        if today.month != last_reset.month or today.year != last_reset.year:
            supabase.table("usage_tracker").update({
                "used_this_month": 1,
                "last_reset_date": str(today)
            }).eq("github_installation_id", installation_id).execute()
            print(f"🔄 Monthly quota reset performed for: {owner_login}")
            return True
        
        # 4. Check quota limit (5 / 5)
        if record["used_this_month"] >= record["monthly_quota"]:
            print(f"⚠️ Quota Limit Reached for {owner_login} ({record['used_this_month']}/{record['monthly_quota']})")
            return False
            
        # 5. Increment usage count
        supabase.table("usage_tracker").update({
            "used_this_month": record["used_this_month"] + 1
        }).eq("github_installation_id", installation_id).execute()
        print(f"📈 Usage updated for {owner_login}: {record['used_this_month'] + 1}/{record['monthly_quota']}")
        return True

    except Exception as e:
        print(f"⚠️ Error accessing Supabase usage_tracker table: {e}")
        return True  # Fail-open so pipeline doesn't break on DB glitch


# ------------------------------------------------------------------
# API Routes
# ------------------------------------------------------------------
@app.get("/")
def home():
    return {
        "service": "DevOps AI Agent API",
        "status": "online",
        "dashboard": "/dashboard"
    }


@app.post("/webhook/github")
async def github_webhook(request: Request, x_hub_signature_256: str = Header(None)):
    payload_bytes = await request.body()
    
    # Verify Webhook HMAC Signature
    if GITHUB_WEBHOOK_SECRET and not verify_github_signature(payload_bytes, x_hub_signature_256):
        raise HTTPException(status_code=400, detail="Invalid HMAC signature")

    payload = await request.json()
    event_type = request.headers.get("X-GitHub-Event")

    if event_type == "workflow_run":
        action = payload.get("action")
        workflow_run = payload.get("workflow_run", {})
        conclusion = workflow_run.get("conclusion")
        run_id = workflow_run.get("id")

        # Detect completed CI build failures
        if action == "completed" and conclusion == "failure":
            installation_id = payload.get("installation", {}).get("id") or 0
            owner_login = payload.get("repository", {}).get("owner", {}).get("login", "unknown")
            repo_name = payload.get("repository", {}).get("name", "unknown")

            print(f"❌ CI Failure detected on {owner_login}/{repo_name} (Run ID: {run_id})")

            # 🛑 QUOTA CHECK STEP 🛑
            if installation_id and owner_login:
                has_quota = check_and_increment_usage(installation_id, owner_login)
                if not has_quota:
                    return JSONResponse(
                        status_code=200,
                        content={
                            "status": "ignored",
                            "reason": f"Monthly quota limit reached for {owner_login}. Upgrade plan for more fixes."
                        }
                    )

            # 🤖 Proceed with Gemini AI log analysis & PR creation pipeline
            print("⚡ Quota available! Proceeding with Gemini AI log analysis & PR generation...")

            return {"status": "success", "message": f"Processing CI fix for run {run_id}"}

    return {"status": "ok", "event": event_type}


@app.get("/status/{owner_login}")
def get_user_status(owner_login: str):
    """API Endpoint: Returns JSON quota details for a given GitHub user/org."""
    if not supabase:
        return {"error": "Supabase connection not configured"}
    
    try:
        response = supabase.table("usage_tracker").select("*").eq("owner_login", owner_login).execute()
        data = response.data
        
        if not data:
            return {
                "owner_login": owner_login,
                "used_this_month": 0,
                "monthly_quota": 5,
                "remaining": 5,
                "status": "New User (No fixes used yet)"
            }
        
        record = data[0]
        used = record["used_this_month"]
        quota = record["monthly_quota"]
        remaining = max(0, quota - used)
        
        return {
            "owner_login": owner_login,
            "used_this_month": used,
            "monthly_quota": quota,
            "remaining": remaining,
            "last_reset_date": record["last_reset_date"]
        }
    except Exception as e:
        return {"error": str(e)}


@app.get("/dashboard", response_class=HTMLResponse)
def render_dashboard():
    """UI Route: Serves a modern Tailwind CSS dashboard to check AI usage."""
    html_content = """
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>DevOps Agent | Usage Dashboard</title>
        <script src="https://cdn.tailwindcss.com"></script>
    </head>
    <body class="bg-gray-950 text-white min-h-screen flex flex-col justify-center items-center p-6">
        <div class="max-w-md w-full bg-gray-900 border border-gray-800 rounded-2xl p-8 shadow-2xl">
            <div class="flex items-center space-x-3 mb-6">
                <span class="text-3xl">🤖</span>
                <h1 class="text-2xl font-bold text-transparent bg-clip-text bg-gradient-to-r from-blue-400 to-emerald-400">
                    DevOps AI Quota Tracker
                </h1>
            </div>
            
            <p class="text-gray-400 text-sm mb-6">Enter your GitHub Username or Organization name to check your remaining monthly AI bug fixes.</p>
            
            <div class="space-y-4">
                <div>
                    <label class="block text-xs font-semibold text-gray-400 uppercase tracking-wider mb-2">GitHub Username / Org</label>
                    <input type="text" id="usernameInput" placeholder="e.g. ksukumarsuku20-stack" 
                           class="w-full px-4 py-3 bg-gray-800 border border-gray-700 rounded-lg text-white focus:outline-none focus:border-blue-500 transition">
                </div>
                
                <button onclick="checkUsage()" 
                        class="w-full py-3 bg-gradient-to-r from-blue-600 to-emerald-600 hover:from-blue-500 hover:to-emerald-500 font-semibold rounded-lg shadow-lg transition transform active:scale-95">
                    Check Usage
                </button>
            </div>

            <!-- Result Card -->
            <div id="resultCard" class="hidden mt-8 pt-6 border-t border-gray-800">
                <div class="bg-gray-800/50 p-4 rounded-xl border border-gray-700/50">
                    <div class="flex justify-between items-center mb-2">
                        <span class="text-sm font-medium text-gray-300">Monthly Quota</span>
                        <span id="quotaText" class="text-sm font-bold text-emerald-400">0 / 5</span>
                    </div>
                    <div class="w-full bg-gray-700 h-3 rounded-full overflow-hidden">
                        <div id="progressBar" class="bg-gradient-to-r from-emerald-400 to-blue-500 h-full w-0 transition-all duration-500"></div>
                    </div>
                    <p id="remainingText" class="text-xs text-gray-400 mt-3 text-center"></p>
                </div>
            </div>
        </div>

        <script>
            async function checkUsage() {
                const username = document.getElementById('usernameInput').value.trim();
                if (!username) return alert('Please enter a valid GitHub username!');

                try {
                    const res = await fetch(`/status/${username}`);
                    const data = await res.json();

                    if (data.error) {
                        alert('Error: ' + data.error);
                        return;
                    }

                    document.getElementById('resultCard').classList.remove('hidden');
                    
                    const used = data.used_this_month;
                    const quota = data.monthly_quota;
                    const remaining = data.remaining;
                    const percentage = Math.min(100, (used / quota) * 100);

                    document.getElementById('quotaText').innerText = `${used} / ${quota} used`;
                    document.getElementById('progressBar').style.width = `${percentage}%`;
                    document.getElementById('remainingText').innerText = `🎉 You have ${remaining} AI fix(es) remaining this month.`;
                } catch (err) {
                    alert('Error fetching usage data. Please try again.');
                }
            }
        </script>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)