from daily_summary import fetch_antigravity_activity
from datetime import datetime
import sys
from pathlib import Path

# Add current dir to path to import daily_summary
sys.path.append(str(Path.cwd()))

print(f"Testing fetch_antigravity_activity for today ({datetime.now()})")
data = fetch_antigravity_activity(datetime.now())
print(f"Result: {data}")
