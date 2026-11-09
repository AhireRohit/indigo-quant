# INDIGO QUANT — Windows 11 Autonomous 24/7 Engine Configuration

This guide provides step-by-step instructions for running the **INDIGO QUANT** autonomous research and paper-trading platform 24/7 on your Windows 11 laptop.

---

## 1. Architecture Overview

```
+---------------------------------------------------------------------------------+
| Windows 11 Laptop (Authoritative Autonomous Trading Engine)                     |
|                                                                                 |
|   +--------------------------+          +-----------------------------------+   |
|   | Windows Task Scheduler   | -------> | Silent Daemon Launcher            |   |
|   | ("IndigoQuantScheduler") |          | (launch_scheduler_daemon.vbs)     |   |
|   +--------------------------+          +-----------------------------------+   |
|                                                           |                     |
|                                                           v                     |
|                                         +-----------------------------------+   |
|                                         | Scheduler Runner (runner.py)      |   |
|                                         | • Single-Instance C-runtime Lock  |   |
|                                         | • Heartbeat Watchdog (30s)        |   |
|                                         | • Missed-Job Recovery             |   |
|                                         +-----------------------------------+   |
|                                             |            |            |         |
|                     +-----------------------+            |            +----+    |
|                     v                                    v                 v    |
|       +---------------------------+       +-------------------+  +------------+ |
|       | APScheduler Jobs          |       | SQLite Database   |  | Telegram   | |
|       | 19:15 Evening Scan        |       | (WAL Mode)        |  | Real-Time  | |
|       | 22:00 EOD Data Retry      |       | • Virtual Capital |  | Alerts     | |
|       | 09:20 Morning Order Fills |       | • Audited Fills   |  +------------+ |
|       | 15:20 MTM Exits & Cash    |       +-------------------+                 |
|       +---------------------------+                  |                          |
|                     |                                v                          |
|                     +---------------------> +-------------------+               |
|                                             | Public Snapshots  |               |
|                                             | (public_data/*.json)              |
+---------------------------------------------------------------------------------+
                                                       |
                                            Git Push / Auto-Sync
                                                       |
                                                       v
+---------------------------------------------------------------------------------+
| Streamlit Community Cloud (Public Read-Only Dashboard)                          |
| URL: https://indigo-quant.streamlit.app/ (or GitHub Pages index.html)          |
| Zero database connection, zero secret leakage, safe public inspection           |
+---------------------------------------------------------------------------------+
```

---

## 2. Windows 11 Power & Energy Settings (Manual Step-by-Step)

To prevent your Windows 11 laptop from entering Sleep or Modern Standby while performing autonomous trading scans, configure the following native Windows 11 settings.

> [!IMPORTANT]
> Always keep your laptop connected to AC mains power. Do not run 24/7 autonomous scheduling on battery alone.

### A. Prevent Automatic Sleep when Plugged In
1. Press `Win + I` to open **Settings**.
2. Navigate to **System** -> **Power & battery**.
3. Expand **Screen and sleep**.
4. Set **When plugged in, put my device to sleep after**: select **Never**.
   *(You may set "When plugged in, turn off my screen after" to 5–15 minutes to preserve display longevity and reduce heat).*

### B. Configure Lid Close Action (Continue Operating with Lid Closed)
1. Press `Win + R`, type `control powercfg.cpl`, and press **Enter** (opens Classic Power Options).
2. On the left sidebar, click **Choose what closing the lid does**.
3. Under the **When I close the lid** row:
   - For **Plugged in**: select **Do nothing** from the drop-down menu.
4. Click **Save changes** at the bottom.

### C. Prevent Network Adapter Sleep (Keep Wi-Fi Active)
1. Right-click the **Start** button and select **Device Manager**.
2. Expand **Network adapters**.
3. Double-click your active Wi-Fi or Ethernet adapter (e.g. *Intel Wi-Fi 6 AX201* or *Realtek PCIe*).
4. Go to the **Power Management** tab.
5. **Uncheck** the box: *Allow the computer to turn off this device to save power*.
6. Click **OK**.

### D. Windows Update Active Hours
To avoid automatic reboots in the middle of market sessions:
1. Open **Settings** -> **Windows Update** -> **Advanced options**.
2. Click **Active hours**.
3. Set from **08:00 AM** to **11:00 PM** (or select **Automatically** based on your laptop activity).

---

## 3. How to Restore Default Power Settings

When you wish to return your laptop to standard power-saving behavior:
1. In **Settings** -> **System** -> **Power & battery** -> **Screen and sleep**:
   - Set **When plugged in, put my device to sleep after** back to **30 minutes** (default).
2. In Classic Control Panel (**control powercfg.cpl**):
   - Set **When I close the lid (Plugged in)** back to **Sleep**.
3. In **Device Manager**:
   - Re-check *Allow the computer to turn off this device to save power* on your Wi-Fi adapter.

---

## 4. Registering the Autonomous Background Service

The autonomous engine is managed via a dedicated Windows Scheduled Task that launches silently in the background using `wscript.exe` and `launch_scheduler_daemon.vbs`.

### Install Autostart Task
Open PowerShell in the project directory and run:
```powershell
powershell -ExecutionPolicy Bypass -File .\deployment\install_autostart.ps1
```

This registers the task `IndigoQuantScheduler` with:
- **Trigger**: Runs automatically whenever you log into Windows.
- **Auto-Restart**: If the process ever crashes, Windows automatically attempts up to 3 restarts within 1 minute.
- **Power Resiliency**: Configured with `-AllowStartIfOnBatteries` and `-DontStopIfGoingOnBatteries`.

### Service Management Commands
You can inspect and manage the service at any time:

```powershell
# 1. Inspect status, PID, and heartbeat
.\deployment\manage_service.ps1 -Action status
# or via CLI:
.\.venv\Scripts\python.exe -m indigo_quant.cli service status

# 2. Start service manually
.\deployment\manage_service.ps1 -Action start

# 3. Stop service gracefully
.\deployment\manage_service.ps1 -Action stop

# 4. Stream real-time rotating logs
.\deployment\manage_service.ps1 -Action logs
```

### To Uninstall the Scheduled Task
```powershell
powershell -ExecutionPolicy Bypass -File .\deployment\install_autostart.ps1 -Uninstall
```

---

## 5. Persistent Logging and Heartbeat Diagnostics

All autonomous background operations are logged to disk with 10 MB rotating archives:

| File | Purpose |
| :--- | :--- |
| `logs/indigo_scheduler.log` | Complete operational daemon log (APScheduler jobs, Telegram alerts, errors, recoveries) |
| `data/heartbeat.json` | Live heartbeat updated every 30 seconds with PID, uptime, status, and next scheduled runs |
| `data/indigo_scheduler.lock` | Exclusive Windows C-runtime single-instance lock file |
| `data/indigo_scheduler.pid` | PID of active scheduler process |
| `data/sent_alerts.json` | Persistent deduplication cache preventing duplicate Telegram alerts |
| `public_data/*.json` | Sanitized public snapshots exported for Streamlit Cloud |
| `public_data/index.html` | Standalone interactive HTML report deployable to GitHub Pages |
