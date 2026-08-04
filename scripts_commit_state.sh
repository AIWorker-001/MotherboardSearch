#!/usr/bin/env bash
set -euo pipefail

ORG=${ORG:-AIWorker-001}
REPO=${REPO:-MotherboardSearch}
BRANCH=${BRANCH:-main}
STATE_FILE=${STATE_FILE:-data/processed.json}
MESSAGE=${MESSAGE:-"Update rolling processed motherboard ledger"}

python3 - "$ORG" "$REPO" "$BRANCH" "$STATE_FILE" "$MESSAGE" <<'PY'
from pathlib import Path
import base64, json, subprocess, sys
org, repo, branch, state_file, message = sys.argv[1:]
path = Path(state_file)

def gh(args, payload=None):
    cp = subprocess.run(
        ["gh", "api", *args, *(["--input", "-"] if payload is not None else [])],
        input=json.dumps(payload) if payload is not None else None,
        text=True,
        capture_output=True,
    )
    if cp.returncode:
        print(f"GH_EXIT_CODE={cp.returncode}")
        print(cp.stdout)
        print(cp.stderr, file=sys.stderr)
        raise SystemExit(cp.returncode)
    return json.loads(cp.stdout)

ref = gh([f"repos/{org}/{repo}/git/ref/heads/{branch}"])
parent = ref["object"]["sha"]
base_tree = gh([f"repos/{org}/{repo}/git/commits/{parent}"])["tree"]["sha"]
blob = gh([f"repos/{org}/{repo}/git/blobs"], {
    "content": base64.b64encode(path.read_bytes()).decode("ascii"),
    "encoding": "base64",
})
tree = gh([f"repos/{org}/{repo}/git/trees"], {
    "base_tree": base_tree,
    "tree": [{"path": state_file, "mode": "100644", "type": "blob", "sha": blob["sha"]}],
})
commit = gh([f"repos/{org}/{repo}/git/commits"], {
    "message": message,
    "tree": tree["sha"],
    "parents": [parent],
})
gh([f"repos/{org}/{repo}/git/refs/heads/{branch}", "-X", "PATCH"], {
    "sha": commit["sha"],
    "force": False,
})
print(json.dumps({"commit": commit["sha"], "state_file": state_file}))
PY
