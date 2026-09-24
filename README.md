AI-Powered Terraform CI/CD Pipeline on Azure

A pull-request pipeline where AI reviews Terraform code for security issues before anything reaches Azure.

Every pull request (PR) runs terraform plan, then sends the infrastructure code to Azure OpenAI (GPT-4o). The AI posts a security fix as a comment on the PR. Infrastructure is only deployed (terraform apply) after the PR is merged into main.

Table of Contents
Architecture
Tech Stack
Repository Structure
Prerequisites
Step-by-Step Build
How the Pipeline Works
Result
Troubleshooting Log
Lessons Learned
Next Improvements
Architecture
git push
Open pull request
Merge
push event
Service Principal
Terraform code
Suggested fix
Bot comment
pull_request event
GitHub Actions Runner
Checkout code
Setup Terraform
terraform init + plan
Run AI Security Fixerremediate_ai.py
DeveloperVS Code
Feature branch
Pull Request
Azure OpenAIGPT-4o
main branch
terraform apply
AzureResource Group +Storage Account

Two stages:

Stage	Trigger	What happens
Review	Pull request opened or updated	Plan the changes + AI security review posted as PR comment
Deploy	Merge (push) to main	terraform apply creates the resources in Azure
Tech Stack
Tool	Purpose
Terraform	Infrastructure as Code (IaC): defines Azure resources in code files
Azure	Cloud platform where resources are created
Azure Resource Manager (ARM)	Azure's deployment service; Terraform talks to it
Azure OpenAI (GPT-4o)	AI model that reviews the Terraform code
GitHub Actions	CI/CD (continuous integration / continuous delivery) engine that runs the pipeline
Python	Script that calls the AI and posts the PR comment
Git	Version control, feature-branch workflow
Repository Structure
CICD-Pipeline/
├── .github/
│   └── workflows/
│       └── devsecops-ai.yml     # Pipeline definition
├── .gitignore                   # Keeps state files and providers out of Git
├── .terraform.lock.hcl          # Locks Terraform provider versions
├── main.tf                      # Azure resources
├── provider.tf                  # Azure provider configuration
├── variables.tf                 # Input variables
└── remediate_ai.py              # AI security reviewer
Prerequisites
Azure subscription
Azure CLI (command-line interface) installed: az --version
Terraform installed: terraform --version
Git + GitHub account
An Azure OpenAI resource with a deployed model (this project uses gpt-4o)
Step-by-Step Build
Step 1 — Write the Terraform code

provider.tf — tells Terraform to use Azure.

hcl
terraform {
  required_providers {
    azurerm = {
      source = "hashicorp/azurerm"
    }
  }
}

provider "azurerm" {
  features {}
}

variables.tf — reusable inputs.

hcl
variable "resource_group_name" {
  type    = string
  default = "rg-openai"
}

variable "location" {
  type    = string
  default = "East US"
}

main.tf — a resource group and a storage account. The storage account is intentionally insecure (open to the public internet) so the AI has something to catch.

hcl
resource "azurerm_resource_group" "lab" {
  name     = var.resource_group_name
  location = var.location
}

resource "azurerm_storage_account" "insecure" {
  name                     = "aisecurityproject"   # must be globally unique
  resource_group_name      = azurerm_resource_group.lab.name
  location                 = azurerm_resource_group.lab.location
  account_tier             = "Standard"
  account_replication_type = "LRS"

  public_network_access_enabled = true   # intentional security issue
}

Check the code locally:

bash
terraform fmt       # auto-format
terraform init      # download the Azure provider
terraform validate  # check for errors without creating anything
Step 2 — Set up Git and .gitignore

Initialize the repo in the folder that contains .github (GitHub only reads workflows from .github/workflows at the repo root).

bash
git init
git branch -M main

Create .gitignore so large and sensitive files are never uploaded:

.terraform/
*.tfstate
*.tfstate.*
*.tfvars

The .terraform/ folder contains the Azure provider binary (~215 MB). GitHub rejects files over 100 MB. State files (*.tfstate) can contain passwords and keys.

Create an empty repo on GitHub, then connect and push:

bash
git add .
git commit -m "Initial commit"
git remote add origin https://github.com/<your-user>/CICD-Pipeline-AI.git
git push -u origin main
Step 3 — Create a Service Principal

A Service Principal is a non-human "service account" that lets GitHub log in to Azure.

Client ID + Secret + TenantID
Contributor role
GitHub Actions
Service Principal
Azure Subscription
bash
az login
az account show --query id -o tsv   # prints your Subscription ID

az ad sp create-for-rbac \
  --name "github-cicd-ai" \
  --role Contributor \
  --scopes /subscriptions/<SUBSCRIPTION_ID>

The output maps to these values:

Output field	GitHub secret
appId	ARM_CLIENT_ID
password	ARM_CLIENT_SECRET
tenant	ARM_TENANT_ID
(your subscription ID)	ARM_SUBSCRIPTION_ID

⚠️ The password is shown only once. Never commit it or share it in screenshots. If exposed, rotate it: az ad sp credential reset --id <appId>

Step 4 — Deploy the Azure OpenAI model
In Microsoft Foundry (ai.azure.com), open your Azure OpenAI resource.
Go to Models + endpoints → Deploy model and deploy gpt-4o.
Note:
Deployment name (this project: lab-ai) — the script must use this exact, case-sensitive name.
Endpoint (Target URI)
Key
Step 5 — Add GitHub secrets

Repo → Settings → Secrets and variables → Actions → New repository secret

Secret	Source
ARM_CLIENT_ID	Service Principal appId
ARM_CLIENT_SECRET	Service Principal password
ARM_TENANT_ID	Service Principal tenant
ARM_SUBSCRIPTION_ID	Azure subscription ID
AZURE_OPENAI_KEY	Foundry → deployment → Key
AZURE_OPENAI_ENDPOINT	Foundry → deployment → Endpoint

GITHUB_TOKEN is created automatically by GitHub for every run.

Why ARM_? ARM = Azure Resource Manager. Terraform's Azure provider automatically reads environment variables that start with ARM_ to authenticate.

Step 6 — Write the pipeline

.github/workflows/devsecops-ai.yml

yaml
name: AI-Powered Terraform CI/CD

on:
  pull_request:          # Review stage
  push:
    branches:
      - main             # Deploy stage

jobs:
  terraform-job:
    runs-on: ubuntu-latest
    permissions:
      contents: read
      pull-requests: write   # lets the bot comment on the PR

    steps:
      - name: Checkout code
        uses: actions/checkout@v4

      - name: Set up Terraform
        uses: hashicorp/setup-terraform@v3

      # --- STAGE 1: PLAN ---
      - name: Terraform init & Plan
        env:
          ARM_CLIENT_ID: ${{ secrets.ARM_CLIENT_ID }}
          ARM_CLIENT_SECRET: ${{ secrets.ARM_CLIENT_SECRET }}
          ARM_SUBSCRIPTION_ID: ${{ secrets.ARM_SUBSCRIPTION_ID }}
          ARM_TENANT_ID: ${{ secrets.ARM_TENANT_ID }}
        run: |
          terraform init
          terraform plan

      # --- AI REMEDIATION ---
      - name: Set up Python
        if: github.event_name == 'pull_request'
        uses: actions/setup-python@v5
        with:
          python-version: '3.11'

      - name: Install Python dependencies
        if: github.event_name == 'pull_request'
        run: pip install requests

      - name: Run AI Security Fixer
        if: github.event_name == 'pull_request'
        env:
          AZURE_OPENAI_KEY: ${{ secrets.AZURE_OPENAI_KEY }}
          AZURE_OPENAI_ENDPOINT: ${{ secrets.AZURE_OPENAI_ENDPOINT }}
          GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
          PR_NUMBER: ${{ github.event.pull_request.number }}
        run: python remediate_ai.py

      # --- STAGE 2: APPLY (only after merge) ---
      - name: Terraform Apply
        if: github.event_name == 'push' && github.ref == 'refs/heads/main'
        env:
          ARM_CLIENT_ID: ${{ secrets.ARM_CLIENT_ID }}
          ARM_CLIENT_SECRET: ${{ secrets.ARM_CLIENT_SECRET }}
          ARM_SUBSCRIPTION_ID: ${{ secrets.ARM_SUBSCRIPTION_ID }}
          ARM_TENANT_ID: ${{ secrets.ARM_TENANT_ID }}
        run: terraform apply -auto-approve
Step 7 — Write the AI reviewer

remediate_ai.py — reads credentials from environment variables, calls Azure OpenAI, and posts the answer as a PR comment.

Key parts:

python
import os
import sys
import requests

api_key  = os.getenv("AZURE_OPENAI_KEY")
endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")
gh_token = os.getenv("GITHUB_TOKEN")
repo     = os.getenv("GITHUB_REPOSITORY")
pr_number = os.getenv("PR_NUMBER")

DEPLOY_NAME = "lab-ai"   # exact deployment name from Foundry

def get_ai_fix(issue):
    base_url = endpoint.split("/openai")[0].rstrip("/")
    url = (f"{base_url}/openai/deployments/{DEPLOY_NAME}"
           f"/chat/completions?api-version=2024-12-01-preview")

    headers = {"content-type": "application/json", "api-key": api_key}
    data = {
        "messages": [
            {"role": "system", "content": "You are a DevSecOps expert. Provide the HCL code to fix the following issue in a Terraform file."},
            {"role": "user", "content": f"Fix this: {issue}"},
        ]
    }

    response = requests.post(url, headers=headers, json=data)
    if response.status_code == 200:
        return response.json()["choices"][0]["message"]["content"]

    print(f"API ERROR: {response.status_code} - {response.text}")
    sys.exit(1)   # fail the step so errors are visible

The script then posts the result to the PR using the GitHub REST API: POST https://api.github.com/repos/{repo}/issues/{pr_number}/comments

Step 8 — Test with a feature branch
gitGraph
    commit id: "Initial commit"
    branch feature-branch-1
    checkout feature-branch-1
    commit id: "Add pipeline + TF"
    commit id: "Fix requests import"
    commit id: "Fix deployment name"
    checkout main
    merge feature-branch-1 id: "Merge PR → terraform apply"
bash
git switch -c feature-branch-1
# make a change, save
git add .
git commit -m "test ai pipeline"
git push -u origin feature-branch-1

On GitHub: Pull requests → New pull request → base: main, compare: feature-branch-1.

The pipeline runs automatically. When it finishes, the github-actions bot posts the AI Security Fix in the Conversation tab. Once reviewed, click Merge pull request to trigger terraform apply.

How the Pipeline Works
Azure OpenAI
Azure (ARM)
Actions Runner
GitHub
Azure OpenAI
Azure (ARM)
Actions Runner
GitHub
Developer
Push feature branch + open PR
Trigger (pull_request)
terraform plan (Service Principal)
Planned changes
Send Terraform code
Security fix (HCL)
Post PR comment
Review + merge PR
Trigger (push to main)
terraform apply
Resources created
Developer
Result

The AI detected that public_network_access_enabled = true exposes the storage account to the internet and suggested:

hcl
public_network_access_enabled = false

The fix appears on the PR before merge, so the issue can be corrected before it ever reaches Azure.

Troubleshooting Log

Real issues hit while building this project and how they were solved.

Symptom	Cause	Fix
fatal: not a git repository	git init never run, or run in wrong folder	Run git init in the folder containing .github
Workflow never ran	.github not at repo root	Re-initialize repo one level up
has no upstream branch	New branch not yet on GitHub	git push -u origin <branch>
Push rejected: file is 215 MB	.terraform/ folder committed	Add .gitignore, git rm -r --cached .terraform, git commit --amend
ModuleNotFoundError: No module named 'request'	Typo + library not installed on runner	import requests + pip install requests step
Please run 'az login' in pipeline	ARM_* secrets missing	Create Service Principal, add GitHub secrets
Merge conflict in variables.tf	Same lines edited on both branches (terraform fmt)	Resolved in GitHub editor, then git pull
404 DeploymentNotFound	Wrong deployment name in script	Use exact name from Foundry (lab-ai)
AI step green but no comment	Script printed error instead of failing	sys.exit(1) on API errors
Push rejected: fetch first	Remote had a commit not on local	git pull --no-rebase, then git push
Lessons Learned
Pipelines should fail loudly. A green step that silently failed cost debugging time.
Never commit generated or sensitive files. .gitignore goes in before the first commit.
Names must match exactly. Secret names, deployment names, and branch names are all case-sensitive.
Secrets stay out of code and screenshots. Rotate anything that leaks.
Next Improvements
 Remote state backend — store Terraform state in an Azure Storage Account so resources are tracked between runs and terraform destroy works.
 OIDC (OpenID Connect) authentication — replace the client secret with short-lived tokens; no password to leak.
 Security scanner + AI — add Checkov or tfsec to find issues deterministically, then let the AI explain and fix them.
 Manual approval before apply — use a GitHub Environment with required reviewers instead of -auto-approve.
 Plan output in PR — post the terraform plan summary alongside the AI review.
Author

Fabrizio Mastrogiovanni — Cloud Engineer - LinkedIn: https://www.linkedin.com/in/fabrizio-mastrogiovanni-499335276/