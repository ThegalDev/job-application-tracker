from fastapi import FastAPI, HTTPException
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel
import csv
import os
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

DATA_FILE = "data/applications.csv"
os.makedirs("data", exist_ok=True)

if not os.path.exists(DATA_FILE):
    with open(DATA_FILE, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["Company", "Role", "URL", "Date", "Status", "Notes"])

class JobApplication(BaseModel):
    company: str
    role: str
    url: str
    date: str
    status: str

@app.post("/log")
async def log_application(job: JobApplication):
    try:
        with open(DATA_FILE, "a", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow([job.company, job.role, job.url, job.date, job.status, ""])
        return {"message": "Application logged successfully"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/data")
def get_data():
    if not os.path.exists(DATA_FILE):
        return []
    
    jobs = []
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            jobs.append(row)
    return jobs

# Serve static files
app.mount("/static", StaticFiles(directory="static"), name="static")

@app.get("/")
def read_root():
    return FileResponse("static/index.html")
