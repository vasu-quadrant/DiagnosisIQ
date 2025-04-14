import json
import os
import re
import logging
from PyPDF2 import PdfReader
from io import BytesIO
from prompts.system_prompts import formatting_system_prompt
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# from loggers import get_app_logger
# logger = get_app_logger(__name__)

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

if not logger.hasHandlers():
    from logging.handlers import RotatingFileHandler

    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)s | %(name)s | %(filename)s | %(funcName)s | line:%(lineno)d | %(message)s"
    )
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)

    file_handler = RotatingFileHandler("logs/formatting_agent.log", maxBytes=5 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)

FORMATTING_AGENT_ID = os.getenv("FORMATTING_AGENT_ID")


def get_agent_response(project_client, thread, agent_id, context, system_prompt, max_wait_seconds=500, poll_interval=2):
    import time
    try:
        logger.info("Starting agent response generation...")
        logger.debug("Thread ID: %s | Agent ID: %s", thread.id, agent_id)

        project_client.agents.create_message(
            thread_id=thread.id,
            role="user",
            content=context,
        )

        response = project_client.agents.create_run(
            thread_id=thread.id,
            agent_id=agent_id,
            instructions=system_prompt,
        )
        logger.info("Agent run started")

        start_time = time.time()
        max_iterations = max_wait_seconds // poll_interval
        iteration = 0

        while iteration < max_iterations:
            run_status = project_client.agents.get_run(thread_id=thread.id, run_id=response.id)

            if run_status.status == "completed":
                logger.info("Agent run completed")
                break
            elif run_status.status in ["failed", "cancelled"]:
                logger.error("Agent processing failed or was cancelled.")
                return None

            time.sleep(poll_interval)
            iteration += 1
        else:
            logger.warning("Agent run timed out after %s seconds", max_wait_seconds)
            return None

        messages = project_client.agents.list_messages(thread_id=thread.id)
        return messages.data[0].content[0].text.value
    except Exception as e:
        logger.exception("Error during get_agent_response: %s", str(e))
        return None


def anonymize_personal_info(text: str) -> str:
    try:
        logger.debug("Anonymizing personal information...")
        substitutions = [
            (r"Dr\.?\s+[A-Z][A-Za-z\s\.-]+(?:\s*\([^)]+\))?", "Dr. [SUB]"),
            (r"(Consultant’s Name\s*:?\s*)(Dr\.?\s+[A-Za-z\s\.-]+(?:\s*\([^)]+\))?)", r"\1Dr. [SUB]"),
            (r"(Name of Patient\s*:?\s*)([^\n]*)", r"\1[SUB]"),
            (r"(Guardian(?:’s|'s)? Name\s*:?\s*)([^\n]*)", r"\1[SUB]"),
            (r"(IP\.? Number\s*:?\s*)([^\n]*)", r"\1[SUB]"),
            (r"(Bed No\.?\s*:?\s*)([^\n]*)", r"\1[SUB]"),
            (r"(Address\s*:?\s*)([^\n]*)", r"\1[SUB]"),
            (r"(Telephone\s*#*\s*:?\s*)([^\n]*)", r"\1[SUB]"),
            (r"\b(?:\+91[-\s]?|0)?\d{10}\b", "[SUB]"),
            (r"\b(Ruby General Hospital|Bengal Oncology Centre|Medical Center|Clinic)\b", "[SUB]"),
            (r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}", "[SUB]"),
            (r"(Registration No\.?\s*:?\s*)([^\n]*)", r"\1[SUB]"),
            (r"(Signature\s*:?\s*)([^\n]*)", r"\1[SUB]"),
            (r"(Name of MO\s*/\s*Consultant\s*:?\s*)([^\n]*)", r"\1[SUB]"),
            (r"(Admission Date|Discharge Date|Admission Time|Discharge Time)\s*:?\s*[^\n]*", r"\1: [SUB]"),
            (r"(Age\s*:?\s*)(\d{1,3}\s*years)", r"\1[SUB]"),
            (r"(Sex\s*:?\s*)(Male|Female)", r"\1[SUB]")
        ]

        for pattern, replacement in substitutions:
            text = re.sub(pattern, replacement, text, flags=re.IGNORECASE)

        logger.info("Anonymization complete")
        return text
    except Exception as e:
        logger.exception("Anonymization failed: %s", str(e))
        return text



def soap_formatter(project_client, thread, file_text: str, filename: str):
    try:
        logger.info("Received file for formatting: %s", filename)
        logger.debug("Project client available: %s", bool(project_client))

        discharge_summary = anonymize_personal_info(file_text)
        if not discharge_summary:
            raise ValueError("Empty discharge summary extracted.")

        logger.debug("Discharge summary length: %d", len(discharge_summary))
        soap_str = get_agent_response(
            project_client,
            thread,
            FORMATTING_AGENT_ID,
            context=discharge_summary,
            system_prompt=formatting_system_prompt
        )

        if not soap_str:
            raise ValueError("Agent response is empty or None.")

        if '```' in soap_str:
            soap_str = soap_str.split('```')[1].strip()
            if soap_str[:4].lower() == 'json':
                soap_str = soap_str[4:].strip()

        soap_json = json.loads(str(soap_str))
        logger.info("SOAP JSON successfully parsed")
        return soap_json

    except json.JSONDecodeError as je:
        logger.exception("Failed to decode JSON: %s", str(je))
        raise
    except Exception as e:
        logger.exception("Error in soap_formatter for file %s: %s", filename, str(e))
        raise