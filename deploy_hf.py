"""One-command deploy of Shuddhi to Hugging Face Spaces.

Prereq (do ONE of these so the HF token is available):
    hf auth login                 # interactive, recommended — token stays on your machine
    # or:  export HF_TOKEN=hf_xxx  (Windows PowerShell: $env:HF_TOKEN="hf_xxx")

Then run from inside the shuddhi-proofreader folder:
    py -3.13 deploy_hf.py
    # optional custom name:  py -3.13 deploy_hf.py my-space-name
"""
import os
import sys
from huggingface_hub import HfApi

SPACE_NAME = sys.argv[1] if len(sys.argv) > 1 else "shuddhi-proofreader"

api = HfApi()
who = api.whoami()                      # raises if not authenticated
user = who["name"]
repo_id = f"{user}/{SPACE_NAME}"

print(f"Authenticated as {user}. Creating Space {repo_id} …")
api.create_repo(repo_id=repo_id, repo_type="space", space_sdk="gradio", exist_ok=True)

# Optionally push the Anthropic key as a Space secret if it's set locally.
key = os.environ.get("ANTHROPIC_API_KEY")
if key:
    try:
        api.add_space_secret(repo_id=repo_id, key="ANTHROPIC_API_KEY", value=key)
        print("Added ANTHROPIC_API_KEY as a Space secret (AI analysis enabled).")
    except Exception as e:
        print("Could not set secret automatically:", e)

print("Uploading files …")
api.upload_folder(
    folder_path=os.path.dirname(os.path.abspath(__file__)),
    repo_id=repo_id, repo_type="space",
    ignore_patterns=["*.pyc", "__pycache__/*", ".venv/*", "venv/*",
                     "shuddhi_*/*", ".git/*", "deploy_hf.py"],
    commit_message="Deploy Shuddhi proofreader",
)
print("\n✅ Deployed:  https://huggingface.co/spaces/" + repo_id)
print("The Space will build for ~2–3 minutes, then be live for anyone.")
print("To enable AI analysis later: Space → Settings → Secrets → add ANTHROPIC_API_KEY.")
