import json
import datetime
from typing import Any, Callable, Set, Dict, List, Optional
from azure.ai.projects.models import FunctionTool, ToolSet
import pandas as pd
import os
# from icdapi1 import get_token, search_icd_code
import requests
import os
import logging
from prompts.system_prompts  import physician_agent_system_prompt
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

    file_handler = RotatingFileHandler("logs/physician_agent.log", maxBytes=5 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


# ========== ENVIRONMENT VARIABLES ==========
try:
    TOKEN_ENDPOINT = os.getenv("TOKEN_ENDPOINT")
    CLIENT_ID = os.getenv("CLIENT_ID")
    CLIENT_SECRET = os.getenv("CLIENT_SECRET")
    SCOPE = os.getenv("SCOPE")
    GRANT_TYPE = os.getenv("GRANT_TYPE")
    SEARCH_URL = os.getenv("SEARCH_URL")
    PHYSICIAN_AGENT_ID = os.getenv("PHYSICIAN_AGENT_ID")
except Exception as e:
    logger.exception("Failed to load environment variables: %s", e)
    raise





# =====================================================

import os
from openai import AzureOpenAI
from azure.core.credentials import AzureKeyCredential

# ========== ENVIRONMENT VARIABLES ==========
try:
    OPENAI_ENDPOINT = os.getenv("OPENAI_ENDPOINT")
    EMBEDDING_MODEL_NAME = os.getenv("EMBEDDING_MODEL_NAME")
    EMBEDDING_DEPLOYMENT = os.getenv("EMBEDDING_DEPLOYMENT")
    EMBEDDING_API_VERSION = os.getenv("EMBEDDING_API_VERSION")
    EMBEDDING_MODEL_API_KEY= os.getenv("EMBEDDING_MODEL_API_KEY")
except Exception as e:
    logger.exception("Failed to load environment variables: %s", e)
    raise


try:
    embedding_client = AzureOpenAI(
        api_version=EMBEDDING_API_VERSION,
        azure_endpoint=OPENAI_ENDPOINT,
        api_key= EMBEDDING_MODEL_API_KEY,
    )
except Exception as e:
    logger.exception("Failed to create AzureOpenAI embedding client: %s", e)
    raise


def get_embeddings(client, input_list):
    try:
        logger.info("Getting embeddings for input: %s", input_list)
        response = client.embeddings.create(
            input=input_list,
            model=EMBEDDING_DEPLOYMENT,
            dimensions=1536,
            encoding_format="float"
        )
        return response
    except Exception as e:
        logger.exception("Error generating embeddings: %s", e)
        raise


def get_similarity_score(embedding1, embedding2):
    """
    Calculate the cosine similarity between two embeddings.
    """
    try:
        dot_product = sum(a * b for a, b in zip(embedding1, embedding2))
        norm_a = sum(a ** 2 for a in embedding1) ** 0.5
        norm_b = sum(b ** 2 for b in embedding2) ** 0.5
        return dot_product / (norm_a * norm_b)
    except Exception as e:
        logger.exception("Error computing similarity score: %s", e)
        raise


def finalize_physician_ouput(embedding_client, physician_agent_ouput_json):
    try:
        filtered, eliminated = [], []
        for entity in physician_agent_ouput_json:
            input = [entity['term'], entity['title']]
            embeddings = get_embeddings(embedding_client, input)
            score = get_similarity_score(
                embeddings.data[0].embedding,
                embeddings.data[1].embedding
            )
            entity['title_term_matching_score'] = score

            if score > 0: # 0.8:
                entity['Dataframe'] = dataframes_from_tool.get(entity['term'], [])
                filtered.append(entity)
            else:
                eliminated.append(entity)

        # return {"final_ouput": filtered, "eliminated": eliminated}
        return filtered
    except Exception as e:
        logger.exception("Error finalizing physician output: %s", e)
        raise

# =====================================================



def get_access_token(client_id, client_secret, token_endpoint, scope, grant_type):
    try:
        logger.info("Fetching access token...")
        payload = {
            'client_id': client_id,
            'client_secret': client_secret,
            'scope': scope,
            'grant_type': grant_type
        }
        response = requests.post(token_endpoint, data=payload, verify=False).json()
        if 'error' in response:
            raise Exception(response['error_description'])
        return response['access_token']
    except Exception as e:
        logger.exception("Failed to retrieve access token: %s", e)
        raise



def add_definition(access_token, entity_id_url):
    # print(entity_id_url)
    HEADERS = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "API-Version": "v2",
        "Accept-Language": "en"
    }
    print("In Add Definition: ",entity_id_url )
    desc_response = requests.get(entity_id_url, headers=HEADERS)
    description = desc_response.json().get("definition", {}).get("@value", " --- ")
    # print(f"\nDescription of {entity_id_url}: {description}")
    print(description)

    return description



def search_icd_code(access_token, query):
    try:
        logger.info("Searching ICD for query: %s", query)
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
            "API-Version": "v2",
            "Accept-Language": "en"
        }
        params = {
            "q": query,
            "useFlexisearch": "true",
            "flatResults": "true",
            "highlightingEnabled": "false"
        }

        response = requests.get(SEARCH_URL, headers=headers, params=params)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        logger.exception("ICD search failed for '%s': %s", query, e)
        raise



def get_token():
    access_token = get_access_token(CLIENT_ID, CLIENT_SECRET, TOKEN_ENDPOINT, SCOPE, GRANT_TYPE)
    return access_token



def pprint_results(access_token, results):
    try:
        logger.info("Formatting ICD search results")
        
        if not results.get("destinationEntities"):
            logger.info("No results found.")
            return
        logger.info(results['destinationEntities'][0])
        
        # Initialize lists
        codes = []
        titles = []
        scores = []
        matchingPVs = []
        descriptions = []

        for entity in results["destinationEntities"]:
            code = entity["theCode"]
            title = entity["title"]
            score = entity['score']

            # internal_matchingPVs = []
            # for pv in entity['matchingPVs']:
            #     property = pv['propertyId']
            #     label = pv['label']
            #     internal_matchingPVs.append({
            #         "propertyId": property,
            #         "label": label
            #     })
            # if '&' in entity['id']:
            #     id_url_list = entity['id'].split(' & ')
            #     logger.info("=+"*200)
            #     logger.info("In list & : ", id_url_list)
            #     description = ""
            #     for id in range(len(id_url_list)):
            #         id_url = id_url_list[0]
            #         logger.info("ID URL: ", id_url)
            #         description += add_definition(access_token, id_url)
            # else: 
            #     id_url = entity['id']
            #     logger.info("ID URL: ", id_url)
            #     description = add_definition(access_token, id_url)
            # matchingPVs.append(internal_matchingPVs)
            # descriptions.append(description)

            # logger.info(f"Code: {code}, Title: {title}, Score: {score}") #,Desciption: {description}")
            codes.append(code)
            titles.append(title)
            scores.append(score)

        logger.info("Creating Dataframe...")
        logger.info("Codes: %d, Titles: %d, Scores: %d", len(codes), len(titles), len(scores))

        df = pd.DataFrame({
            'Code': codes,
            'Title': titles,
            'Score': scores
            # 'matchingPVs': matchingPVs,
            # 'Description': descriptions
        }).drop_duplicates(subset=['Code'])

        # df.drop_duplicates(subset=['Code'], inplace=True)
        logger.info("Search result dataframe created with %d entries", len(df))
        return df
    except Exception as e:
        logger.exception("Failed to process ICD results: %s", e)
        raise


dataframes_from_tool = {}
def call_search_icd_code(diagnosis: str) -> str:
    """
    Search for the ICD with a Diagnosis term and Fetches the dataframe with CODE, TITLE, SCORE. 

    :param diagnosis (str): Diagnosis term
    :return: dataframe

    :rtype: JSON

    """
    try:
        global dataframes_from_tool
        logger.info(f"Tool called successfully! Searching for ICD codes for diagnosis: {diagnosis}")
        access_token = get_token()
        logger.info("Access Token Received...")
        results = search_icd_code(access_token, diagnosis)
        logger.info("Results Retrieved...")
        df = pprint_results(access_token, results)            # Ensure pprint_results returns a DataFrame
        logger.info("Dataframe is Ready...")

        df_json = df.to_json(orient= 'records')
        dataframes_from_tool[diagnosis] = json.loads(df_json)
        
        logger.info("Tool Call Ended..")
        return df_json
    except Exception as e:
        logger.exception("Error in call_search_icd_code: %s", e)
        raise



# Statically defined user functions for fast reference
# user_functions: Set[Callable[..., Any]] = {
#     call_search_icd_code,
# }

# # Initialize agent toolset with user functions
# functions = FunctionTool(user_functions)
# toolset = ToolSet()
# toolset.add(functions)

# agent = project_client.agents.create_agent(
#     model="gpt-35-turbo", name="sample-ps-agent", instructions=sample_physician_agent_system_prompt, toolset=toolset
# )
# print(f"Created agent, ID: {agent.id}")


def get_agent_response(project_client, thread, agent_id, context, max_wait_seconds=60, poll_interval=2):
    try:
        import time

        logger.info("Starting agent run: thread_id=%s, agent_id=%s", thread.id, agent_id)
        project_client.agents.create_message(
            thread_id=thread.id,
            role="user",
            content=context,
        )
        
        print("Agent run started")

        start_time = time.time()
        max_iterations = max_wait_seconds // poll_interval
        iteration = 0

        while iteration < max_iterations:
            logger.info("Agent run iteration %d", iteration)
            run_status = project_client.agents.create_and_process_run(thread_id=thread.id, agent_id=agent_id)
            if run_status.status == "completed":
                logger.info("Agent run completed.")
                break
            elif run_status.status in ["failed", "cancelled"]:
                logger.info("Agent processing failed or was cancelled.")
                return None
            
            time.sleep(poll_interval)
            iteration += 1

        else:
            logger.warning(f"Agent run did not complete within {max_wait_seconds} seconds.")
            return None

        messages = project_client.agents.list_messages(thread_id=thread.id)
        return messages.data[0].content[0].text.value
    except Exception as e:
        logger.exception("Agent response handling failed: %s", e)
        raise





def physician_agent(project_client, thread, soap):
    try: 
        global embedding_client
        physician_agent_context = f"""
            You MUST use the call_search_icd_code tool to process this SOAP note.
            Remember: You CANNOT analyze diagnoses without using the tool!
            
            Here is the patient's SOAP note:
            {str(soap)}

            I need you to:
            1. Extract all diagnoses from the Assessment section
            2. For EACH diagnosis, call the tool: call_search_icd_code("diagnosis")
            3. Use ONLY the results from the tool to assign ICD codes
            4. Extract treatments from the Plan section
            5. Format your response according to the instructions
        """
        # Statically defined user functions for fast reference
        user_functions: Set[Callable[..., Any]] = {
            call_search_icd_code,
        }

        # Initialize agent toolset with user functions
        functions = FunctionTool(user_functions)
        toolset = ToolSet()
        toolset.add(functions)

        agent = project_client.agents.create_agent(
            model="gpt-35-turbo",
            name="physician-agent",
            instructions=physician_agent_system_prompt,
            toolset=toolset,
            temperature= 0.1
        )    

        logger.info("Created agent with ID: %s", agent.id)

        physician_response = get_agent_response(project_client, thread, agent.id, physician_agent_context)

        if '```' in physician_response:
            physician_response = physician_response.split('```')[1].strip()
            if physician_response[:4]== 'json':
                physician_response = physician_response[4:].strip()

        print("="*50)
        print(physician_response)
        try:
            physician_response_json = json.loads(physician_response)
            project_client.agents.delete_agent(agent.id)
            logger.info("Ready for Finalizing...")

            finalized_ouput = finalize_physician_ouput(embedding_client, physician_response_json)
            logger.info("Ready to return Output...")
            # return finalized_ouput['final_ouput']

            return finalized_ouput

            # return physician_response_json
        except Exception as e:
            logger.exception("Response Formate is not JSON")
    except Exception as e:
        logger.exception("Error in physician_agent flow: %s", e)
        raise