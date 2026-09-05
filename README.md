# AI Knowledge Engine (RAG)

Production-ready FastAPI project scaffold for an AI Knowledge Engine (RAG).

## Project Structure

```text
rag_project/
├── app/
│   ├── api/
│   ├── services/
│   ├── rag/
│   ├── database/
│   ├── schemas/
│   ├── models/
│   ├── core/
│   ├── __init__.py
│   └── main.py
├── data/
│   ├── uploads/
│   └── processed/
├── tests/
├── requirements.txt
├── .env.example
├── .gitignore
└── README.md
```

## Setup Instructions

### 1. Create a Virtual Environment

On Windows (PowerShell):
```powershell
python -m venv .venv
```

On macOS / Linux:
```bash
python3 -m venv .venv
```

### 2. Activate the Virtual Environment

On Windows (PowerShell):
```powershell
.\.venv\Scripts\Activate.ps1
```

On Windows (Command Prompt):
```cmd
.\.venv\Scripts\activate.bat
```

On macOS / Linux:
```bash
source .venv/bin/activate
```

### 3. Install Dependencies

```bash
pip install -r requirements.txt
```

### 4. Running the Application

Run the server with Uvicorn:

```bash
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

### 5. Accessing API Documentation

Once the server is running, you can access:

- **Swagger UI**: [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **ReDoc**: [http://127.0.0.1:8000/redoc](http://127.0.0.1:8000/redoc)
- **Health Check**: [http://127.0.0.1:8000/health](http://127.0.0.1:8000/health)
