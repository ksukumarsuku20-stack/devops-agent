import hashlib
import hmac
import os
import re
from dotenv import load_dotenv
from fastapi import FastAPI, Header, HTTPException, Request

from app.agent import generate_code_fix
from app.github_service import (
    create_fix_pull_request,
    get_file_content,
    get_workflow_run_logs,
)

load_dotenv()

app = FastAPI(title="DevOps Agent Backend")

WEBHOOK_SECRET = os.getenv("GITHUB_WEBHOOK_SECRET", "")


def parse_ai_response(response_text: str):
    """Helper function to split explanation and fixed code from Gemini output."""
    explanation, fixed_code = "", ""

    if "---EXPLANATION---" in response_text:
        parts = response_text.split("---FIXED_CODE---")
        explanation = (
            parts[0].replace("---EXPLANATION---", "").strip()
            if len(parts) > 0
            else ""
        )
        fixed_code = parts[1].strip() if len(parts) > 1 else ""
    else:
        explanation = "Automated bug fix applied by Gemini AI."
        fixed_code = response_text

    # Clean markdown code blocks if present
    fixed_code = re.sub(r"^```[a-zA-Z]*\n", "", fixed_code)
    fixed_code = re.sub(r"\n```$", "", fixed_code)

    return explanation, fixed_code


@app.get("/")
def read_root():
    return {"message": "DevOps Agent Backend is running!"}


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    x_github_event: str = Header(None),
    x_hub_signature_256: str = Header(None),
):
    payload_body = await request.body()

    # HMAC Verification
    if x_hub_signature_256 and WEBHOOK_SECRET:
        hash_object = hmac.new(
            WEBHOOK_SECRET.encode("utf-8"),
            msg=payload_body,
            digestmod=hashlib.sha256,
        )
        expected_signature = "sha256=" + hash_object.hexdigest()
        if not hmac.compare_digest(expected_signature, x_hub_signature_256):
            raise HTTPException(
                status_code=400, detail="Invalid HMAC signature"
            )

    payload = await request.json()
    print(f"Received GitHub Event: {x_github_event}")

    # Process Workflow Failures (CI/CD)
    if x_github_event == "workflow_run":
        workflow = payload.get("workflow_run", {})
        conclusion = workflow.get("conclusion")
        installation_id = payload.get("installation", {}).get("id")

        if conclusion == "failure":
            print("❌ CI/CD Build Failed! Agent initiating fix sequence...")

            repo_full_name = payload.get("repository", {}).get("full_name")
            head_branch = workflow.get("head_branch", "main")
            run_id = workflow.get("id")
            target_file = "README.md"  # Target file to inspect/fix

            # 1. Fetch real build logs from GitHub Actions
            real_logs = get_workflow_run_logs(
                repo_full_name, run_id, installation_id=installation_id
            )
            if not real_logs:
                real_logs = f"Workflow '{workflow.get('name')}' failed on branch '{head_branch}'"

            # 2. Fetch real file content from GitHub
            real_code = get_file_content(
                repo_full_name,
                target_file,
                ref=head_branch,
                installation_id=installation_id,
            )
            if not real_code:
                real_code = "# Default fallback code file"

            # 3. Ask Gemini for Fix using real code and terminal failure logs
            ai_result = generate_code_fix(
                file_path=target_file,
                code_snippet=real_code,
                error_log=real_logs,
            )

            print("\n------------------ 🤖 GEMINI AI RESULT ------------------")
            print(ai_result)
            print("---------------------------------------------------------\n")

            if ai_result.get("status") == "success":
                explanation, fixed_code = parse_ai_response(
                    ai_result["ai_response"]
                )

                # 4. Open PR on GitHub
                pr_url = create_fix_pull_request(
                    repo_full_name=repo_full_name,
                    file_path=target_file,
                    fixed_code=fixed_code,
                    explanation=explanation,
                    installation_id=installation_id,
                )
                print(f"🔗 PR Status / URL: {pr_url}")
                return {
                    "status": "fix_submitted",
                    "pr_url": pr_url,
                    "explanation": explanation,
                }

    return {"status": "success", "event_processed": x_github_event}