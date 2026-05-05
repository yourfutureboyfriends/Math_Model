"""
Macro Research Platform - Dashboard Redirect

The dashboard has been migrated to a React frontend.

To use the new React dashboard:

1. Start the FastAPI backend:
   cd api && python main.py

2. Start the React frontend (in a new terminal):
   cd frontend && npm install && npm run dev

3. Open http://localhost:3000 in your browser

The old Streamlit dashboard has been backed up to dashboard.py.backup
"""

import streamlit as st

st.set_page_config(
    page_title="Macro Research Platform",
    page_icon="📊",
    layout="wide"
)

st.title("📊 Macro Research Platform")

st.info("""
## Dashboard Migrated to React

The dashboard has been overhauled with a modern **React + TypeScript** frontend
while maintaining the Bloomberg Terminal aesthetic.

### Quick Start

**Terminal 1 - Start Backend:**
```bash
cd api && python main.py
```

**Terminal 2 - Start Frontend:**
```bash
cd frontend && npm install && npm run dev
```

Then open **http://localhost:3000** in your browser.

### New Features

- ⚡ **Fast**: Vite-powered development server
- 🎨 **Bloomberg Terminal Styling**: Dark theme with amber accents
- 📱 **Responsive**: Works on desktop and tablet
- 🔄 **Auto-refresh**: Data updates every 5 minutes
- 📊 **Interactive Charts**: Sparklines, bar charts with Recharts

### API Endpoints

The FastAPI backend serves data at:
- `http://localhost:8000/api/dashboard` - Full dashboard data
- `http://localhost:8000/api/health` - Health check

### File Structure

```
macro_research_platform/
├── api/                    # FastAPI backend
│   ├── main.py
│   └── requirements.txt
├── frontend/               # React frontend
│   ├── src/
│   │   ├── components/     # React components
│   │   ├── hooks/          # Custom hooks
│   │   ├── api/            # API client
│   │   └── types/          # TypeScript types
│   ├── package.json
│   └── vite.config.ts
└── dashboard.py            # This file (redirect)
```

---

**Note**: The original Streamlit dashboard is backed up at `dashboard.py.backup`
and `src/ui_backup/`. To restore it, rename these files.
""")

st.divider()

st.subheader("Start Dashboard")

if st.button("🚀 Start React Dashboard", type="primary"):
    st.markdown("""
    ### Manual Steps Required

    Since Streamlit cannot start external processes, please run these commands manually:

    **1. Start Backend (Terminal 1):**
    ```bash
    cd /Users/daltonyuen/Math_Model/macro_research_platform/api
    python main.py
    ```

    **2. Start Frontend (Terminal 2):**
    ```bash
    cd /Users/daltonyuen/Math_Model/macro_research_platform/frontend
    npm install
    npm run dev
    ```

    **3. Open Browser:**
    Navigate to http://localhost:3000
    """)

st.divider()

st.caption("Macro Research Platform v2.0 • React + FastAPI Architecture")
