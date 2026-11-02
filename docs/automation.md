# Automation Setup (macOS Cron)

This guide documents how to schedule the job watcher and resume-tailoring pipeline to run automatically in the background on macOS using `cron`.

---

## 1. Make the Wrapper Script Executable

Ensure that [`run.sh`](file:///path/to/recruiting/run.sh) has execute permissions:

```bash
chmod +x run.sh
```

> [!NOTE]
> Open [`run.sh`](file:///path/to/recruiting/run.sh) and confirm the `cd /path/to/recruiting` line matches your project's absolute path (e.g., `/Users/aaryan/Desktop/Projects/recruiting`).

---

## 2. Edit the Crontab

Open your user `crontab` in your terminal editor:

```bash
crontab -e
```

---

## 3. Sample Cron Schedules

Add one of the following schedule lines into your crontab editor (replace `/path/to/recruiting` with your absolute repository path):

### Option A: Run Every 2 Hours
```cron
0 */2 * * * /path/to/recruiting/run.sh
```

### Option B: Run Daily at 8:00 AM
```cron
0 8 * * * /path/to/recruiting/run.sh
```

Save and exit the editor (`:wq` in vim, or `Ctrl + O` then `Ctrl + X` in nano). You should see:
```text
crontab: installing new crontab
```

To verify the installed crontab:
```bash
crontab -l
```

---

## 4. macOS Permissions & Troubleshooting (Full Disk Access)

> [!IMPORTANT]
> macOS enforces strict **Transparency, Consent, and Control (TCC)** permissions on background daemons. Because `cron` runs detached from your active desktop session, macOS will block it from accessing your `Desktop`, `Documents`, or user folders. This causes `run.sh` to silently fail when writing state or PDF files to disk.

### Grant Full Disk Access to Cron:
1. Open **System Settings** &rarr; **Privacy & Security**.
2. Scroll down and click **Full Disk Access**.
3. Click the **`+`** (Add) button (enter your administrator password or Touch ID if prompted).
4. In the file picker dialog, press `Command + Shift + G` to bring up the **Go to Folder** prompt.
5. Paste `/usr/sbin/cron` and press **Enter**.
6. Select **cron** and click **Open**.
7. Ensure the toggle switch next to **cron** is turned **ON**.

---

## 5. Monitoring Logs

All automated background run output, job evaluations, errors, and delivery statuses are appended to:

```bash
tail -f data/cron.log
```

