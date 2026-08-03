import io
import os
import zipfile
from dotenv import load_dotenv
from github import Auth, Github, GithubIntegration
import requests

load_dotenv()

APP_ID = os.getenv("GITHUB_APP_ID")
PRIVATE_KEY_PATH = os.getenv("GITHUB_PRIVATE_KEY_PATH", "private-key.pem")


def get_github_installation_client(installation_id: int):
    """Authenticates as a GitHub App Installation dynamically using PyGithub."""
    try:
        if not APP_ID or not os.path.exists(PRIVATE_KEY_PATH):
            # Fallback to Personal Access Token if App credentials are not present
            token = os.getenv("GITHUB_TOKEN")
            if token:
                return Github(token)
            print("⚠️ Neither GitHub App keys nor GITHUB_TOKEN are configured.")
            return None

        with open(PRIVATE_KEY_PATH, "r") as f:
            private_key = f.read()

        auth = Auth.AppAuth(app_id=int(APP_ID), private_key=private_key)
        gi = GithubIntegration(auth=auth)
        return gi.get_github_for_installation(installation_id)
    except Exception as e:
        print(f"❌ Error authenticating GitHub App: {str(e)}")
        return None


def get_file_content(
    repo_full_name: str,
    file_path: str,
    ref: str = "main",
    installation_id: int = None,
) -> str:
    """Fetches the raw content of a file from GitHub."""
    try:
        g = get_github_installation_client(installation_id)
        if not g:
            return ""
        repo = g.get_repo(repo_full_name)
        file_content = repo.get_contents(file_path, ref=ref)
        return file_content.decoded_content.decode("utf-8")
    except Exception as e:
        print(f"⚠️ Could not fetch {file_path} from GitHub: {str(e)}")
        return ""


def create_fix_pull_request(
    repo_full_name: str,
    file_path: str,
    fixed_code: str,
    explanation: str,
    installation_id: int = None,
) -> str:
    """Creates a new branch, commits the AI fix, and opens a Pull Request on GitHub."""
    g = get_github_installation_client(installation_id)
    if not g:
        return ""

    try:
        repo = g.get_repo(repo_full_name)
        default_branch = repo.default_branch
        base_sha = repo.get_branch(default_branch).commit.sha
        new_branch_name = f"devops-agent-fix-{repo.get_commits()[0].sha[:7]}"

        # 1. Create a new branch off default branch
        repo.create_git_ref(ref=f"refs/heads/{new_branch_name}", sha=base_sha)

        # 2. Get file SHA if it exists
        sha = None
        try:
            contents = repo.get_contents(file_path, ref=default_branch)
            sha = contents.sha
        except Exception:
            pass  # File doesn't exist yet, update_file will create it

        # 3. Update or Create File
        if sha:
            repo.update_file(
                path=file_path,
                message="🤖 Autonomous DevOps Agent: Applied AI bug fix",
                content=fixed_code,
                sha=sha,
                branch=new_branch_name,
            )
        else:
            repo.create_file(
                path=file_path,
                message="🤖 Autonomous DevOps Agent: Created fixed file",
                content=fixed_code,
                branch=new_branch_name,
            )

        # 4. Open Pull Request
        pr = repo.create_pull(
            title="🤖 [DevOps Agent] Automated CI/CD Bug Fix",
            body=f"## 🤖 Autonomous AI Fix\n\n**Explanation:**\n{explanation}\n\n---\n*Generated automatically by DevOps Agent*",
            head=new_branch_name,
            base=default_branch,
        )

        print(f"✅ Pull Request created successfully: {pr.html_url}")
        return pr.html_url

    except Exception as e:
        print(f"❌ Error creating PR: {str(e)}")
        return ""


def get_workflow_run_logs(
    repo_full_name: str, run_id: int, installation_id: int = None
) -> str:
    """Downloads and extracts failure logs from a GitHub Actions workflow run."""
    try:
        g = get_github_installation_client(installation_id)
        if not g:
            return ""

        # Get access token from client
        token = g._Github__requester._Requester__auth.token
        url = f"https://api.github.com/repos/{repo_full_name}/actions/runs/{run_id}/logs"

        headers = {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

        response = requests.get(url, headers=headers, stream=True)
        if response.status_code != 200:
            print(f"⚠️ Could not fetch logs (Status Code: {response.status_code})")
            return ""

        # Extract log zip archive in memory
        error_lines = []
        with zipfile.ZipFile(io.BytesIO(response.content)) as z:
            for filename in z.namelist():
                if filename.endswith(".txt"):
                    content = z.read(filename).decode("utf-8", errors="ignore")
                    for line in content.splitlines():
                        if any(
                            keyword in line.lower()
                            for keyword in [
                                "error",
                                "failed",
                                "exception",
                                "traceback",
                                "fatal",
                            ]
                        ):
                            error_lines.append(line)

        return "\n".join(error_lines[-30:]) if error_lines else ""

    except Exception as e:
        print(f"❌ Error fetching workflow logs: {str(e)}")
        return ""