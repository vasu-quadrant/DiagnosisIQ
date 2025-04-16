import os
import json
import logging
from dotenv import load_dotenv
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from azure.identity import DefaultAzureCredential
from azure.ai.projects import AIProjectClient
from agents.formatter_agent import soap_formatter
from agents.physician_agent import physician_agent, get_token, search_icd_code, pprint_results
from agents.adjuster_agent import adjuster_agent
from pdf2image import convert_from_bytes
import pytesseract
import tempfile
import os

# Load environment variables
load_dotenv()

# from loggers import get_app_logger
# logger = get_app_logger(__name__)


import logging
from logging.handlers import RotatingFileHandler

# Create a logger
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# Console handler
console_handler = logging.StreamHandler()
console_handler.setLevel(logging.DEBUG)

# Rotating file handler
file_handler = RotatingFileHandler(
    filename="logs/main.log",       # Path to your log file
    maxBytes=5 * 1024 * 1024,       # Rotate after 5MB
    backupCount=5,                  # Keep last 5 logs
    encoding='utf-8'
)
file_handler.setLevel(logging.DEBUG)

# Formatter
formatter = logging.Formatter(
    "%(asctime)s | %(levelname)s | %(name)s | %(filename)s | %(funcName)s | line:%(lineno)d | %(message)s"
)
console_handler.setFormatter(formatter)
file_handler.setFormatter(formatter)

# Add handlers to logger
logger.addHandler(console_handler)
logger.addHandler(file_handler)


# FastAPI app setup
app = FastAPI(debug=True)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change this to your frontend origin in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global variables
project_client = None
thread = None

# Pydantic models
class PhysicianInput(BaseModel):
    soap_data: dict

class AdjusterInput(BaseModel):
    adjuster_input: list

class SearchInput(BaseModel):
    diagnosis: str


import numpy as np
import pandas as pd
df = pd.read_csv("all_icd_records.csv")
df = df.drop_duplicates(subset=['Code'], keep='first')


@app.on_event("startup")
async def startup_event():
    global project_client, thread
    try:
        credential = DefaultAzureCredential()
        project_client = AIProjectClient.from_connection_string(
            conn_str=os.getenv("PROJECT_CONNECTION_STRING"),
            credential=credential
        )
        thread = project_client.agents.create_thread()
        logger.info("Project Client initialized and thread created: %s", thread.id)
    except Exception as e:
        logger.exception("Startup error: %s", str(e))

# ===========================================

POPPLER_PATH = r"C:\poppler-24.08.0\Library\bin"
import pytesseract

# Set tesseract path explicitly
pytesseract.pytesseract.tesseract_cmd = r"C:\Users\KondapalliVasudevaRa\AppData\Local\Programs\Tesseract-OCR\tesseract.exe"

# ===========================================

@app.post("/upload/")
async def upload_file(file: UploadFile = File(...)):
    if not file.filename.endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files are supported.")
    try:
        pdf_bytes = await file.read()
        pages = convert_from_bytes(pdf_bytes, 500, poppler_path=POPPLER_PATH)
        extracted_text = ""
        for page_number, page in enumerate(pages):
            text = pytesseract.image_to_string(page, lang='eng')
            extracted_text += f"\n\n--- Page {page_number + 1} ---\n{text}"

        soap_json = soap_formatter(project_client, thread, extracted_text, file.filename)
        logger.info("SOAP JSON successfully generated")
        return {"soap": soap_json}
    except Exception as e:
        logger.exception("Upload processing failed: %s", str(e))
        return JSONResponse(status_code=500, content={"error": "Failed to process uploaded file."})


@app.post("/confirm_soap/")
async def confirm_soap(physician_input: PhysicianInput):
    try:
        logger.debug("Received SOAP data for confirmation")
        output = physician_agent(project_client, thread, physician_input.soap_data)
        logger.info("Physician agent processing complete")
        return {"physician_agent_output": output}
    except Exception as e:
        logger.exception("Physician agent error: %s", str(e))
        return JSONResponse(status_code=500, content={"error": "Failed to process SOAP data."})


@app.post("/adjust/")
async def adjust_codes(adjuster_input: AdjusterInput):
    try:
        logger.debug("Received input for Adjuster Agent")
        output = adjuster_agent(project_client, thread, adjuster_input.adjuster_input)
        logger.info("Adjuster agent processing complete")
        return {"Adjuster_agent_output": output}
    except Exception as e:
        logger.exception("Adjuster error: %s", str(e))
        return JSONResponse(status_code=500, content={"error": "Failed to adjust codes."})


@app.post("/search")
async def search_diagnosis(search_input: SearchInput):
    try:
        logger.debug("Search ICD code for diagnosis: %s", search_input.diagnosis)
        access_token = get_token()
        results = search_icd_code(access_token, search_input.diagnosis)
        df = pprint_results(access_token, results)
        df_json = df.to_json(orient='records')
        logger.info("ICD code search and formatting complete")
        return {"dataframe_json": json.loads(df_json)}
    except Exception as e:
        logger.exception("Search diagnosis error: %s", str(e))
        return JSONResponse(status_code=500, content={"error": "Failed to search diagnosis."})


@app.get("/local_search")
def search_titles(q: str):
    filtered = df[df['Title'].str.contains(pat= q, case=False, na=False)]
    print(filtered['Title'])
    return filtered['Title'].tolist()


@app.get("/get_entry")
def get_entry(title: str):
    row = df[df['Title'] == title]
    if row.empty:
        return JSONResponse(content={}, status_code=404)
    
    # Replace NaN and Inf with None
    row_dict = row.iloc[0].replace({np.nan: None, np.inf: None, -np.inf: None}).to_dict()
    return JSONResponse(content=row_dict)