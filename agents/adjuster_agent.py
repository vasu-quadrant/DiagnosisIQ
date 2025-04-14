from prompts.system_prompts import adjuster_agent_system_prompt
from agents.physician_agent import call_search_icd_code, get_agent_response
from typing import Any, Callable, Set
from azure.ai.projects.models import FunctionTool, ToolSet
import json
import logging
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

    file_handler = RotatingFileHandler("logs/adjuster_agent.log", maxBytes=5 * 1024 * 1024, backupCount=5)
    file_handler.setFormatter(formatter)

    logger.addHandler(console_handler)
    logger.addHandler(file_handler)



def adjuster_agent(project_client, thread, adjuster_input_json):
    try:
        logger.info("Initializing Adjuster Agent...")

        user_functions: Set[Callable[..., Any]] = { call_search_icd_code }

        functions = FunctionTool(user_functions)
        toolset = ToolSet()
        toolset.add(functions)

        agent = project_client.agents.create_agent(
            model="gpt-35-turbo",
            name="adjuster-agent",
            instructions=adjuster_agent_system_prompt,
            toolset=toolset,
            temperature=0.1
        )

        logger.info(f"Created agent with ID: {agent.id}")

        final_result = []
        response_to_iterate = []

        for idx, entity in enumerate(adjuster_input_json):
            try:
                logger.debug(f"Processing entity index {idx} with feedback: {entity.get('feedback')}")

                if entity.get('feedback') == "Incorrect":
                    adjuster_agent_context = f"""
                        You MUST use the call_search_icd_code(term, context) tool to process this correction request.
                        Remember: You CANNOT modify or assign ICD codes without using the tool!

                        Here is the ICD assignment input JSON:
                        {str(entity)}

                        I need you to Carefully review the 'feedback_review' field to understand the issue or suggestion.
                    """
                    adjuster_response = get_agent_response(project_client, thread, agent.id, adjuster_agent_context)

                    if not adjuster_response:
                        logger.warning(f"Empty or null response from agent for entity index {idx}")
                        continue

                    if '```' in adjuster_response:
                        adjuster_response = adjuster_response.split('```')[1].strip()
                        if adjuster_response[:4] == 'json':
                            adjuster_response = adjuster_response[4:].strip()

                    parsed_response = json.loads(adjuster_response)
                    response_to_iterate.append(parsed_response)
                    final_result.append(parsed_response)
                else:
                    final_result.append(entity)

            except json.JSONDecodeError as json_err:
                logger.error(f"JSON decoding failed for entity index {idx}: {json_err}")
            except Exception as entity_err:
                logger.error(f"Unexpected error while processing entity index {idx}: {entity_err}")

        adjuster_agent_output = json.loads(json.dumps(final_result))
        project_client.agents.delete_agent(agent.id)
        logger.info("Deleted Adjuster Agent after processing.")
        logger.debug(f"Final Adjuster Agent Output: {adjuster_agent_output}")

        return adjuster_agent_output

    except Exception as e:
        logger.exception(f"Fatal error in adjuster_agent: {e}")
        raise
