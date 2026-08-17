#!/usr/bin/env python
"""Check GitHub authentication and repository status."""
import subprocess
import sys
import os

os.chdir(r"c:\Users\NAGAVENI\.gemini\antigravity-ide\scratch\linkplease-intern-assignment")

def check_git_push():
    """Try to push and capture the error"""
    result = subprocess.run(
        ["git", "push", "origin", "main"],
        capture_output=True,
        text=True
    )
    return result.returncode, result.stdout, result.stderr

print("=" * 70)
print("CHECKING GITHUB AUTHENTICATION & REPOSITORY STATUS")
print("=" * 70)

returncode, stdout, stderr = check_git_push()

print("\nGit Push Result:")
print(f"Return code: {returncode}")
print(f"STDOUT: {stdout}")
print(f"STDERR: {stderr}")

if "Repository not found" in stderr or "not found" in stderr:
    print("\n" + "=" * 70)
    print("[STATUS] Repository does not exist on GitHub yet")
    print("=" * 70)
    print("\nREQUIRED ACTION - Choose one:\n")
    print("OPTION 1: Create via GitHub Web UI (Recommended)")
    print("-" * 70)
    print("1. Go to: https://github.com/new")
    print("2. Repository name: linkplease-intern-assignment")
    print("3. Description: LinkPlease Instagram Automation Engine")
    print("4. Make it PUBLIC")
    print("5. Do NOT initialize with README/license/gitignore")
    print("6. Click 'Create repository'")
    print("7. Tell me when done, and I'll push the code\n")
    
    print("OPTION 2: Use GitHub CLI (if installed and authenticated)")
    print("-" * 70)
    print("1. Make sure 'gh' CLI is installed")
    print("2. Make sure you've run: gh auth login")
    print("3. Tell me to run: gh repo create linkplease-intern-assignment --public")
    print("4. I'll then push the code\n")
    
    print("OPTION 3: Use Git with Personal Access Token")
    print("-" * 70)
    print("1. Go to: https://github.com/settings/tokens")
    print("2. Click 'Generate new token (classic)'")
    print("3. Give it scope: 'repo' (full control of private repositories)")
    print("4. Generate the token and copy it")
    print("5. Tell me the token is ready")
    print("6. I'll run: git push origin main")
    print("7. When prompted for password, paste your token\n")

elif "401" in stderr or "403" in stderr or "Unauthorized" in stderr:
    print("\n" + "=" * 70)
    print("[STATUS] Authentication required")
    print("=" * 70)
    print("\nGit needs a Personal Access Token to authenticate.\n")
    print("STEPS:")
    print("1. Go to: https://github.com/settings/tokens")
    print("2. Click 'Generate new token (classic)'")
    print("3. Give it scope: 'repo'")
    print("4. Generate and copy the token")
    print("5. Tell me the token is ready")
    print("6. I'll attempt to push with authentication\n")

elif returncode == 0:
    print("\n" + "=" * 70)
    print("[✓ SUCCESS] Code pushed to GitHub!")
    print("=" * 70)

else:
    print("\n" + "=" * 70)
    print("[STATUS] Unknown error")
    print("=" * 70)
    print("The error output above may help diagnose the issue.")
