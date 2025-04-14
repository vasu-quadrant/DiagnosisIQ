import requests
import os

TOKEN_ENDPOINT = os.getenv("TOKEN_ENDPOINT")
CLIENT_ID = os.getenv("CLIENT_ID")
CLIENT_SECRET = os.getenv("CLIENT_SECRET")
SCOPE = os.getenv("SCOPE")
GRANT_TYPE = os.getenv("GRANT_TYPE")
SEARCH_URL = os.getenv("SEARCH_URL")




def get_access_token(client_id, client_secret, token_endpoint, scope, grant_type):
    print("Getting access token...")
    payload = {'client_id': client_id, 
	   	   'client_secret': client_secret, 
           'scope': scope, 
           'grant_type': grant_type}
           
    # make request
    response_from_endpoint = requests.post(token_endpoint, data=payload, verify=False).json()
    
    # check if response is valid
    if 'error' in response_from_endpoint:
        raise Exception(f"Error getting access token: {response_from_endpoint['error_description']}")
    
    # extract access token
    return response_from_endpoint['access_token']




def search_icd_code(access_token, query):
    print(f"Searching ICD for: '{query}'...")
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
    print(response)
    return response.json()


def get_token():
    access_token = get_access_token(CLIENT_ID, CLIENT_SECRET, TOKEN_ENDPOINT, SCOPE, GRANT_TYPE)
    return access_token