# Simple To-Do App (Python Frontend with Streamlit)

A minimal "frontend" web app made entirely in Python using **Streamlit**. Add, edit, complete, delete, and filter tasks. Data is stored locally as JSON.

## Features
- All UI built in Python (Streamlit).
- Add tasks with title, description, due date, and priority.
- Mark as done, edit, delete.
- Search, status, and priority filters.
- Local JSON storage at `data/todos.json`.

## Step-by-step in VS Code
1. **Install** Python 3.9+ and **VS Code**. In VS Code, also install the **Python** and **Pylance** extensions.
2. **Open this folder** in VS Code (`File → Open Folder…`).
3. Create a virtual environment:
   - **Windows (PowerShell):**
     ```ps1
     python -m venv .venv
     .venv\Scripts\Activate.ps1
     ```
   - **macOS/Linux:**
     ```bash
     python3 -m venv .venv
     source .venv/bin/activate
     ```
4. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
5. Run the app:
   ```bash
   streamlit run app.py
   ```
   Streamlit will open your browser automatically. If not, visit the URL it prints (usually `http://localhost:8501`).

### Optional: VS Code Task
You can run Streamlit via **Terminal → Run Task → Run Streamlit**.
This is configured in `.vscode/tasks.json`.

## Project Structure
```
py-frontend-todo/
├─ app.py
├─ requirements.txt
├─ README.md
├─ data/
│  └─ todos.json
├─ .streamlit/
│  └─ config.toml
└─ .vscode/
   └─ tasks.json
```

## Notes
- Everything is local. To reset, delete `data/todos.json`.
- For deployment later, consider Streamlit Community Cloud or any server where you can `pip install` and `streamlit run`.
 
 https://docs.google.com/spreadsheets/d/1FgRr7YSe_NpwJOuJdw_BHdHkorsgCY1v2RJcwguL2W8/edit?gid=0#gid=0 