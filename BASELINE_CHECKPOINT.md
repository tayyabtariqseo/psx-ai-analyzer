# PSX Sentinel AI - Project Milestone: Baseline Ready (May 6, 2026)

## 🎯 Current Status
The project has reached a stable baseline. All core features are functional, optimized for the Pakistan Stock Exchange (PSX), and synchronized with the live deployment.

## 🛠️ Core Configurations
- **AI Engine:** Primary model is `gemini-2.5-flash` with fallback logic.
- **Data Sources:** `psxdata` for historical and `dps.psx.com.pk` for live JSON feeds.
- **Persistence:** File-based caching in `analysis/` to minimize API quota consumption.
- **Timezone:** All operations normalized to **Pakistan Standard Time (PKT - UTC+5)**.
- **Market Hours:** 
    - Mon-Thu: 9:15 AM - 3:30 PM
    - Friday: 9:00 AM - 4:30 PM

## 📁 Key Files
- `app.py`: Main Streamlit dashboard with session-state persistence.
- `indicators.py`: Technical analysis engine (RSI, MACD, EMAs, SuperTrend, Pivots).
- `ai_engine.py`: Gemini client with error handling and model fallbacks.
- `persistence.py`: Daily report caching logic.
- `GEMINI.md`: Project-level technical documentation and latest SYS analysis.

## 💾 Local Environment Settings
- **Python:** Managed via `.venv`.
- **Git Path:** `C:\Users\HP\AppData\Local\GitHubDesktop\app-3.5.8\resources\app\git\cmd\git.exe`
- **Memory File:** `C:\Users\HP\.gemini\tmp\project-1\memory\MEMORY.md`

## 🚀 Next Steps
The system is now ready for "Next Level" features such as portfolio tracking, multi-stock comparison, or advanced alert systems.
