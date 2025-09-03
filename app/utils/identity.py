"""Module for Azure identity utils."""

import base64
import json
import logging
import re
from datetime import timedelta

import streamlit as st
from azure.core.credentials import AccessToken
from azure.identity import DefaultAzureCredential, get_bearer_token_provider

# Get logger for this module
logger = logging.getLogger(__name__)


def extract_resource_name_from_resource_id(resource_id: str, custom_endpoint: str = None) -> str:
    """
    Extract the resource name from either a full ARM resource ID, custom endpoint, or return the input if it's already a resource name.
    
    Args:
        resource_id: Either a full ARM resource ID or a simple resource name
        custom_endpoint: Optional custom endpoint URL (e.g., "https://wkswecenspeech.cognitiveservices.azure.com/")
        
    Returns:
        str: The resource name/identifier to use for speech authentication
        
    Examples:
        - Input: "/subscriptions/xxx/resourceGroups/xxx/providers/Microsoft.CognitiveServices/accounts/speech-resource"
          Output: "speech-resource"
        - Input: "speech-resource"
          Output: "speech-resource"
        - Custom endpoint: "https://wkswecenspeech.cognitiveservices.azure.com/"
          Output: "wkswecenspeech" (extracted from custom endpoint)
    """
    if not resource_id:
        return resource_id
    
    # If we have a custom endpoint, extract the custom domain name from it
    if custom_endpoint:
        import re
        # Extract custom domain name from URL like "https://wkswecenspeech.cognitiveservices.azure.com/"
        match = re.match(r'https://([^.]+)\.cognitiveservices\.azure\.com/?', custom_endpoint)
        if match:
            custom_domain_name = match.group(1)
            logger.info(f"Extracted custom domain name '{custom_domain_name}' from custom endpoint: {custom_endpoint}")
            return custom_domain_name
        else:
            logger.warning(f"Could not extract custom domain name from endpoint: {custom_endpoint}")
    
    # If it looks like a full ARM resource ID, extract the resource name from the end
    if resource_id.startswith('/subscriptions/'):
        parts = resource_id.split('/')
        if len(parts) >= 8 and parts[-2].lower() == 'accounts':
            resource_name = parts[-1]
            logger.info(f"Extracted resource name '{resource_name}' from ARM resource ID")
            return resource_name
        else:
            logger.warning(f"ARM resource ID format appears invalid: {resource_id}")
            return resource_id
    else:
        # Assume it's already a resource name
        logger.info(f"Using provided value as resource name: {resource_id}")
        return resource_id


def validate_resource_id(resource_id: str) -> bool:
    """
    Validate Azure Speech resource ID format.
    
    Accepts either:
    1. Full ARM resource ID: /subscriptions/{subscription-id}/resourceGroups/{resource-group-name}/providers/Microsoft.CognitiveServices/accounts/{resource-name}
    2. Simple resource name: {resource-name}
    
    Args:
        resource_id: The Azure resource ID to validate
        
    Returns:
        bool: True if the resource ID has a valid format, False otherwise
    """
    if not resource_id:
        logger.error("Resource ID is empty or None")
        return False
    
    # Check if it's a full ARM resource ID
    if resource_id.startswith('/subscriptions/'):
        # Azure resource ID pattern for Cognitive Services
        pattern = r"^/subscriptions/[a-f0-9-]{36}/resourceGroups/[^/]+/providers/Microsoft\.CognitiveServices/accounts/[^/]+$"
        
        if re.match(pattern, resource_id):
            logger.info(f"Valid ARM resource ID format: {resource_id}")
            return True
        else:
            logger.error(f"Invalid ARM resource ID format: {resource_id}")
            logger.error("Expected ARM format: /subscriptions/{{subscription-id}}/resourceGroups/{{resource-group-name}}/providers/Microsoft.CognitiveServices/accounts/{{resource-name}}")
            return False
    else:
        # Simple resource name - just check it's not empty and doesn't contain invalid characters
        if re.match(r"^[a-zA-Z0-9][a-zA-Z0-9-]*[a-zA-Z0-9]$|^[a-zA-Z0-9]$", resource_id):
            logger.info(f"Valid resource name format: {resource_id}")
            return True
        else:
            logger.error(f"Invalid resource name format: {resource_id}")
            logger.error("Resource name must contain only alphanumeric characters and hyphens, and must start/end with alphanumeric")
            return False


@st.cache_resource
def get_azure_credential():
    return DefaultAzureCredential()


@st.cache_resource
def get_token_provider():
    """Get Azure Token Provider."""

    token_provider = get_bearer_token_provider(
        get_azure_credential(), "https://cognitiveservices.azure.com/.default"
    )
    return token_provider


@st.cache_data(
    ttl=timedelta(minutes=60)
)  # Temporary fix, need to add cache for exact lifetime of token
def get_access_token(
    scope: str = "https://cognitiveservices.azure.com/.default",
) -> AccessToken:
    """Get Microsoft Entra access token for scope."""

    try:
        logger.info(f"Requesting access token for scope: {scope}")
        token_credential = get_azure_credential()
        token = token_credential.get_token(scope)
        
        logger.info("Access token retrieved successfully")
        logger.debug(f"Token expires at: {token.expires_on}")
        
        return token
        
    except Exception as e:
        logger.error(f"Failed to get access token for scope '{scope}': {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        raise


def get_speech_token(resource_id: str, custom_endpoint: str = None) -> str:
    """
    Create Speech Service token.
    
    Args:
        resource_id: Azure Speech resource ID (can be full ARM ID or resource name)
        custom_endpoint: Optional custom endpoint URL for Entra ID authentication
        
    Returns:
        str: Authorization token for Speech Service
        
    Raises:
        ValueError: If resource_id format is invalid
        Exception: If access token retrieval fails
    """
    
    try:
        logger.info(f"Creating speech token for resource: {resource_id}")
        if custom_endpoint:
            logger.info(f"Using custom endpoint: {custom_endpoint}")
        
        # Validate resource ID format
        if not validate_resource_id(resource_id):
            raise ValueError(f"Invalid Azure Speech resource ID format: {resource_id}")
        
        # For speech token generation, Microsoft documentation suggests using:
        # 1. Full ARM resource ID if available
        # 2. Custom domain name only if we don't have a full ARM resource ID
        
        if resource_id.startswith('/subscriptions/'):
            # Use the full ARM resource ID as specified in the documentation
            resource_identifier = resource_id
            logger.info(f"Using full ARM resource ID for speech token: {resource_identifier}")
        else:
            # Extract the resource name (in case a simple name was provided)
            # If custom_endpoint is provided, prioritize extracting the domain name from there
            resource_identifier = extract_resource_name_from_resource_id(resource_id, custom_endpoint)
            logger.info(f"Using resource identifier for speech token: {resource_identifier}")
        
        # Get access token
        logger.info("Retrieving access token for speech service")
        access_token = get_access_token()
        
        if not access_token or not access_token.token:
            raise Exception("Failed to retrieve valid access token")
            
        # Create authorization token
        # You need to include the "aad#" prefix and the "#" (hash) separator between resource identifier and Microsoft Entra access token.
        authorization_token = "aad#" + resource_identifier + "#" + access_token.token
        
        logger.info("Speech authorization token created successfully")
        logger.debug(f"Token length: {len(authorization_token)} characters")
        logger.debug(f"Token format: aad#{resource_identifier}#[access_token]")
        
        return authorization_token
        
    except ValueError as e:
        logger.error(f"Resource ID validation error: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"Failed to create speech token: {str(e)}")
        logger.error(f"Exception type: {type(e).__name__}")
        raise


def check_claim_for_tenant(client_principal: str, authorized_tenants: list):
    """Check if claim is authorized tenant."""

    decoded_bytes = base64.b64decode(client_principal.encode("utf-8"))
    decoded_str = decoded_bytes.decode("utf-8")
    client_principal = json.loads(decoded_str)
    tenant_id = next(
        (
            claim["val"]
            for claim in client_principal["claims"]
            if claim["typ"] == "http://schemas.microsoft.com/identity/claims/tenantid"
        ),
        None,
    )

    return tenant_id in authorized_tenants
