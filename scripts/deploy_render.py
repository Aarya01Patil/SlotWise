"""Publish the authorized synthetic demo on Render's explicit free plan.

Reads secrets locally; never prints API responses or environment values.
"""

import argparse
import json
import os
import secrets
import sys
import time
from pathlib import Path

import httpx
from dotenv import load_dotenv

REPO = "https://github.com/Aarya01Patil/SlotWise"


def main():
    load_dotenv()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--owner", help="Workspace ID, required if multiple are accessible")
    args = parser.parse_args()
    key = os.getenv("RENDER_API_KEY", "")
    groq = (os.getenv("GROQ_API_KEY") or os.getenv("groq_api_key") or "").strip()
    if not key or not groq:
        sys.exit("Save RENDER_API_KEY and GROQ_API_KEY (or groq_api_key) in the local .env first.")
    with httpx.Client(
        base_url="https://api.render.com/v1", headers={"Authorization": "Bearer " + key}, timeout=60
    ) as client:

        def api(method, path, **kwargs):
            response = client.request(method, path, **kwargs)
            if response.is_error:
                sys.exit(
                    f"Render {method} {path} failed: HTTP {response.status_code}. Check account access in the dashboard. Credentials and response bodies are hidden."
                )
            return response.json()

        owners = [row["owner"] for row in api("GET", "/owners", params={"limit": 100})]
        if args.owner:
            owner = next((owner for owner in owners if owner["id"] == args.owner), None)
            if owner is None:
                sys.exit("Requested workspace is not accessible with this key.")
        elif len(owners) == 1:
            owner = owners[0]
        else:
            sys.exit(
                "Multiple workspaces: choose --owner from "
                + ", ".join(owner["id"] for owner in owners)
            )
        existing = api("GET", "/services", params={"ownerId": owner["id"], "limit": 100})
        matches = [
            row["service"]
            for row in existing
            if row["service"].get("repo", "").removesuffix(".git") == REPO
        ]
        if matches:
            service = matches[0]
            print("Reusing existing SlotWise service; its configuration was preserved.", flush=True)
        else:
            token = secrets.token_urlsafe(32)
            payload = {
                "type": "web_service",
                "name": "slotwise",
                "ownerId": owner["id"],
                "repo": REPO,
                "branch": "main",
                "autoDeployTrigger": "commit",
                "serviceDetails": {
                    "runtime": "docker",
                    "plan": "free",
                    "region": "singapore",
                    "numInstances": 1,
                    "healthCheckPath": "/healthz",
                    "envSpecificDetails": {
                        "dockerCommand": "",
                        "dockerContext": ".",
                        "dockerfilePath": "./Dockerfile",
                    },
                },
                "envVars": [
                    {"key": name, "value": value}
                    for name, value in {
                        "LLM_PROVIDER": "groq",
                        "GROQ_MODEL": os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
                        "GROQ_API_KEY": groq,
                        "SLOTWISE_MODE": "live",
                        "SLOTWISE_PUBLIC": "1",
                        "SLOTWISE_OPERATOR_TOKEN": token,
                        "SLOTWISE_EVAL_INTERVAL": "12",
                    }.items()
                ],
            }
            service = api("POST", "/services", json=payload)["service"]
            local = Path(".slotwise/render-operator-token.txt")
            local.parent.mkdir(parents=True, exist_ok=True)
            local.write_text(token, encoding="utf-8")
            print("Free service created. Operator token saved in ignored .slotwise/.", flush=True)
        service_id = service["id"]
        url = service.get("serviceDetails", {}).get("url")
        previous = None
        for _ in range(80):
            deploys = api("GET", f"/services/{service_id}/deploys", params={"limit": 1})
            state = deploys[0]["deploy"]["status"] if deploys else "waiting_for_build"
            if state != previous:
                print("Render deployment: " + state, flush=True)
                previous = state
            if state == "live":
                service = api("GET", f"/services/{service_id}")
                url = service["serviceDetails"]["url"]
                check = httpx.get(url + "/healthz", timeout=60)
                check.raise_for_status()
                if check.json().get("synthetic") is not True:
                    sys.exit("Unexpected health response; deployment verification failed.")
                evidence = {
                    "service_id": service_id,
                    "url": url,
                    "plan": "free",
                    "status": "live",
                    "health_verified": True,
                }
                Path("examples/deployment.json").write_text(
                    json.dumps(evidence, indent=2), encoding="utf-8"
                )
                print("Verified public demo: " + url, flush=True)
                return
            if state in {
                "build_failed",
                "update_failed",
                "pre_deploy_failed",
                "canceled",
                "deactivated",
            }:
                sys.exit("Deployment failed; inspect Render build logs in the dashboard.")
            time.sleep(15)
        sys.exit("Deployment still pending. Check the Render dashboard; no success was claimed.")


if __name__ == "__main__":
    main()
