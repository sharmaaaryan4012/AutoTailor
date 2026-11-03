# Automation Setup (macOS launchd)

This guide documents how to schedule the AutoTailor job watcher and resume-tailoring pipeline to run automatically in the background on macOS using `launchd`.

Using `launchd` (via `~/Library/LaunchAgents`) is preferred over legacy `cron` on macOS because:
- **Sleep Catch-Up**: If your Mac is asleep during a scheduled trigger window, `launchd` automatically fires the job as soon as the system wakes up.
- **Native User Session**: Runs within the user's GUI login session, avoiding permission and environment sandbox restrictions common with `cron`.

---

## 1. Wrapper Script

The pipeline is invoked through [`run.sh`](file:///Users/aaryan/Desktop/Projects/autotailor/run.sh):

```bash
chmod +x /Users/aaryan/recruiting/run.sh
```

Contents of `run.sh`:
```bash
#!/bin/bash
cd /Users/aaryan/recruiting
/Users/aaryan/recruiting/.venv/bin/python -m src.main --limit 10 >> /Users/aaryan/recruiting/data/cron.log 2>&1
```

---

## 2. LaunchAgent Configuration

The agent definition resides at `~/Library/LaunchAgents/com.aaryan.autotailor.plist`:

```xml
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.aaryan.autotailor</string>
    <key>ProgramArguments</key>
    <array>
        <string>/Users/aaryan/recruiting/run.sh</string>
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

**Schedule**: 10:00 AM & 10:00 PM, Monday through Thursday.

---

## 3. Managing the Job

To reload or refresh the agent:
```bash
launchctl unload ~/Library/LaunchAgents/com.aaryan.autotailor.plist
launchctl load ~/Library/LaunchAgents/com.aaryan.autotailor.plist
```

To verify the job is registered:
```bash
launchctl list | grep autotailor
```

To trigger a run immediately without waiting for the timer:
```bash
launchctl start com.aaryan.autotailor
```

---

## 4. Monitoring Logs

Background execution logs, job evaluations, errors, and delivery statuses are appended to:

```bash
tail -f data/cron.log
tail -f data/pipeline.log
```
