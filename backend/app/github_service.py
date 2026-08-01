import os
from dotenv import load_dotenv
from github import Github

load_dotenv()


def get_github_client():
    token = os.getenv("GITHUB_TOKEN")
    if not token:
        print("⚠️ GITHUB_TOKEN missing from .env")
        return None
    return Github(token)


def get_file_content(
    repo_full_name: str, file_path: str, ref: str = "main"
) -> str:
    """Fetches the raw content of a file from GitHub."""
    try:
        g = get_github_client()
        if not g:
            return ""
        repo = g.get_repo(repo_full_name)
        file_content = repo.get_contents(file_path, ref=ref)
        return file_content.decoded_content.decode("utf-8")
    except Exception as e:
        print(f"⚠️ Could not fetch {file_path} from GitHub: {str(e)}")
        return ""


def create_fix_pull_request(
    repo_full_name: str, file_path: str, fixed_code: str, explanation: str
) -> str:
    """Creates a new branch, commits the AI fix, and opens a Pull Request on GitHub."""
    g = get_github_client()
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