# Automation Setup (macOS launchd)

This guide documents how to schedule the AutoTailor job watcher and resume-tailoring pipeline to run automatically in the background on macOS using `launchd`.

Using `launchd` (via `~/Library/LaunchAgents`) is preferred over legacy `cron` on macOS because:
- **Sleep Catch-Up**: If your Mac is asleep during a scheduled trigger window, `launchd` automatically fires the job as soon as the system wakes up.
- **Native User Session**: Runs within the user's GUI login session, avoiding permission and environment sandbox restrictions common with `cron`.

---

## 1. Wrapper Script

The pipeline is invoked through [`run.sh`](file:///path/to/autotailor/run.sh):

```bash
chmod +x /path/to/autotailor/run.sh
```

Ensure `run.sh` contains:
```bash
#!/bin/bash
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR" || exit 1

PYTHON_BIN="$SCRIPT_DIR/.venv/bin/python"
if [ ! -f "$PYTHON_BIN" ]; then
    PYTHON_BIN="python3"
fi

"$PYTHON_BIN" -m src.main --limit 25 >> "$SCRIPT_DIR/data/cron.log" 2>&1
```

---

## 2. LaunchAgent Configuration

Create a launch agent definition at `~/Library/LaunchAgents/com.user.autotailor.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.user.autotailor</string>
    <key>ProgramArguments</key>
    <array>
        <!-- Replace with the absolute path to your run.sh -->
        <string>/path/to/autotailor/run.sh</string>
    </array>
    <key>StartCalendarInterval</key>
    <array>
        <!-- Monday -->
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>1</integer><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer></dict>
        <!-- Tuesday -->
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>2</integer><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer></dict>
        <!-- Wednesday -->
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>3</integer><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer></dict>
        <!-- Thursday -->
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>10</integer><key>Minute</key><integer>0</integer></dict>
        <dict><key>Weekday</key><integer>4</integer><key>Hour</key><integer>22</integer><key>Minute</key><integer>0</integer></dict>
    </array>
</dict>
</plist>
```

**Schedule**: 10:00 AM & 10:00 PM, Monday through Thursday (configurable via `StartCalendarInterval`).

---

## 3. Managing the Job

To register and activate the agent:
```bash
launchctl load ~/Library/LaunchAgents/com.user.autotailor.plist
```

To verify the job is registered:
```bash
launchctl list | grep autotailor
```

To trigger a run immediately without waiting for the timer:
```bash
launchctl start com.user.autotailor
```

To stop or unload the job:
```bash
launchctl unload ~/Library/LaunchAgents/com.user.autotailor.plist
```

---

## 4. Monitoring Logs

Background execution logs, job evaluations, errors, and delivery statuses are appended to:

```bash
tail -f data/cron.log
tail -f data/pipeline.log
```
