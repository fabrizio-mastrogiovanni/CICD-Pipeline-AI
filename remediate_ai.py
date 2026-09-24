import os
import requests
import json

# --- SETUP ---
api_key = os.getenv("AZURE_OPENAI_KEY")
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
gh_token = os.getenv("GITHUB_TOKEN")
repo = os.getenv("GITHUB_REPOSITORY")
pr_number = os.getenv("PR_NUMBER")

# YOUR DEPLOYMENT NAME
DEPLOY_NAME = "lab-ai"


def get_ai_fix(issue):
    # This celans the URL and adds the exact path from your succesful cURL test
    base_url = endpoint.split("/openai")[0].rstrip("/")
    url = f"{base_url}/openai/deployments/{DEPLOY_NAME}/chat/completions?api-version=2024-12-01-preview"

    headers = {"content-type": "application/json", "api-key": api_key}
    data = {
        "messages": [
            {"role": "system", "content": "You are a DevSecOps expert. Provide the HCL code to fix the following issue in a Terraform file."},
            {"role": "user", "content": f"Fix this: {issue}"}
        ]
    }

    print(f"DEBUG: Calling AI at {url}")
    response = requests.post(url, headers=headers, json=data)

    if response.status_code == 200:
        # Extract the content just like your cURL output showed
        return response.json()["choices"][0]["message"]["content"]
    else:
        print(f"!!! API ERROR: {response.status_code} - {response.text}")
        return None


if pr_number:
    fix = get_ai_fix(
        "Storage account has public_networkaccess enabled = true.")
    if fix:
        # Post the fix as a comment on the Pull request
        comment_url = f"https://api.github.com/repos/{repo}/issues/{pr_number}/comments"
        requests.post(comment_url, headers={"Authorization": f"token {gh_token}"}, json={
                      "body": f"### Suggested Fix\n\n{fix}"})
