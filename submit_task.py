import httpx, json, sys, time
instance_id = sys.argv[1] if len(sys.argv) > 1 else "django__django-11099"
payload = {
    "title": "swebench-task",
    "description": "resolve issue",
    "resources": {"scenario_id": instance_id},
    "constraints": {"time_limit": 1800}
}
r = httpx.post("http://localhost:8002/a2a/task", json=payload, timeout=30)
print("create status", r.status_code, r.text)
data = r.json()
task_id = data.get("task_id")
print("task_id", task_id)
if not task_id:
    sys.exit(1)
while True:
    s = httpx.get(f"http://localhost:8002/a2a/task/{task_id}", timeout=30).json()
    print("status", s)
    if s["status"] in ["completed", "failed"]:
        break
    time.sleep(2)
