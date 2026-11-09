# INDIGO QUANT — Free Public Dashboard Hosting Guide

This guide explains how to host your **INDIGO QUANT** interactive dashboard publicly on **Streamlit Community Cloud** (or as a static report on **GitHub Pages**) at zero cost, with a permanent public HTTPS URL (e.g., `https://indigo-quant.streamlit.app/`).

---

## 1. Local Engine vs. Public Presentation Architecture

To ensure total system security, privacy, and regulatory compliance, INDIGO QUANT implements a strict separation of concerns:

```
+------------------------------------------+        +------------------------------------------+
|  PRIVATE LOCAL ENGINE (Windows 11)       |        |  PUBLIC DASHBOARD (Streamlit Cloud)      |
|                                          |        |                                          |
|  • Full SQLite database (WAL mode)       |        |  • Purely read-only                      |
|  • Real TejHQ API key                    |        |  • Reads sanitized JSON snapshots        |
|  • Telegram Bot credentials              |  --->  |  • Zero database connections             |
|  • Windows Task Scheduler 24/7 daemon    | (Git)  |  • Zero credentials or private paths     |
|  • Paper order execution & exits         |        |  • Lightning-fast cloud deployment       |
|  • Daily data export to public_data/     |        |  • Safe for ChatGPT & public research    |
+------------------------------------------+        +------------------------------------------+
```

---

## 2. Step-by-Step Streamlit Community Cloud Deployment

Streamlit Community Cloud offers **100% free hosting** for public Streamlit applications hosted on GitHub.

### Step 1: Initialize Git and Push to GitHub
If your project is not yet connected to a GitHub repository:
1. Open PowerShell in the project directory:
   ```powershell
   git init
   git add .
   git commit -m "feat: Indigo Quant production autonomous engine and public app"
   ```
2. Create a new repository on GitHub (named `indigo-quant` or `indigo-quant-public`).
3. Link your local project to GitHub and push:
   ```powershell
   git branch -M main
   git remote add origin https://github.com/<your-github-username>/indigo-quant.git
   git push -u origin main
   ```

### Step 2: Deploy on Streamlit Community Cloud
1. Go to **[https://share.streamlit.io/](https://share.streamlit.io/)** and click **Sign in with GitHub**.
2. Click the **Create app** (or **New app**) button in the top right corner.
3. Configure the deployment settings:
   - **Repository**: `<your-github-username>/indigo-quant`
   - **Branch**: `main`
   - **Main file path**: `public_app.py`
   - **App URL (optional customization)**: `indigo-quant.streamlit.app` (or your preferred subdomain)
4. Click **Deploy!**

Within 30–60 seconds, your public dashboard is live and accessible worldwide over HTTPS.

---

## 3. Automated Daily Data Synchronization

Whenever the autonomous scheduler on your Windows laptop runs its evening scan (19:15 IST), fresh market signals, virtual portfolio values, and leaderboard stats are exported to `public_data/`.

To automatically push updated data to GitHub so your Streamlit Cloud dashboard refreshes:

```powershell
# Run the automated sync script
powershell -ExecutionPolicy Bypass -File .\scripts\sync_public_data.ps1
```

Or via CLI:
```powershell
.\.venv\Scripts\python.exe -m indigo_quant.cli export-public
```

---

## 4. Alternative Fallback: Static HTML Hosting on GitHub Pages

If you prefer a static HTML dashboard without any Python server:
1. Indigo Quant automatically compiles a single-file, publication-grade dashboard at:
   `public_data/index.html`
2. In your GitHub repository:
   - Go to **Settings** -> **Pages**.
   - Under **Build and deployment** -> **Source**: select **Deploy from a branch**.
   - Branch: `main` / folder: `/public_data` (or deploy via GitHub Actions).
3. Your static dashboard will be live at: `https://<your-username>.github.io/indigo-quant/`
