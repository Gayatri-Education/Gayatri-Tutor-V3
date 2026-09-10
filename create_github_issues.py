import os
import re
import urllib.request
import urllib.error
import json
import sys

# Replace with your repository
GITHUB_REPO = "Gayatri-Education/Gayatri-Tutor-V3"

def parse_issues(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    # Split by issue headers
    # e.g., # 3. P0 — [HELP WANTED] Tutor Mastery Assessment Is Fundamentally Unsafe
    pattern = r'(# \d+\. P[0-3] — \[HELP WANTED\] .*?)\n(?=# \d+\. P[0-3] — |$)'
    matches = re.finditer(pattern, content, re.DOTALL)
    
    issues = []
    for match in matches:
        block = match.group(1).strip()
        lines = block.split('\n')
        title = lines[0].lstrip('#').strip()
        body = '\n'.join(lines[1:]).strip()
        
        # Extract severity for labels
        severity = "bug"
        if "P0" in title: severity = "P0-critical"
        elif "P1" in title: severity = "P1-high"
        elif "P2" in title: severity = "P2-medium"
        elif "P3" in title: severity = "P3-low"

        issues.append({
            "title": title,
            "body": body,
            "labels": ["help wanted", "good first issue", severity]
        })
    return issues

def create_issue(token, issue):
    url = f"https://api.github.com/repos/{GITHUB_REPO}/issues"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github.v3+json",
        "User-Agent": "python-urllib"
    }
    data = json.dumps(issue).encode('utf-8')
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req) as response:
            res = json.loads(response.read().decode())
            print(f"Created issue: {res['html_url']}")
    except urllib.error.HTTPError as e:
        print(f"Failed to create issue '{issue['title']}': {e.code} {e.reason}")
        print(e.read().decode())

def main():
    token = os.environ.get("GITHUB_TOKEN")
    if not token:
        print("Error: GITHUB_TOKEN environment variable is not set.")
        print("Please set it using: set GITHUB_TOKEN=your_personal_access_token")
        sys.exit(1)

    print("Parsing audit document...")
    filepath = "gayatri_tutor_v3_comprehensive_audit_and_fix.md"
    if not os.path.exists(filepath):
        print(f"Error: Could not find {filepath}")
        sys.exit(1)

    issues = parse_issues(filepath)
    print(f"Found {len(issues)} issues to create.")
    
    confirm = input("Do you want to create these issues on GitHub? (y/N): ")
    if confirm.lower() != 'y':
        print("Aborted.")
        sys.exit(0)

    for i, issue in enumerate(issues, 1):
        print(f"[{i}/{len(issues)}] Creating: {issue['title']}")
        create_issue(token, issue)

if __name__ == "__main__":
    main()
