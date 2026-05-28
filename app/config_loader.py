import os
import json
import boto3
from botocore.exceptions import ClientError
from dotenv import load_dotenv

# 1. Load local .env variables first (for local development and fallback defaults)
load_dotenv()

def load_secrets_manager():
    # Only pull from AWS Secrets Manager if running inside Lambda (AWS_EXECUTION_ENV is set)
    # OR if a secret name is explicitly configured in the environment.
    secret_name = os.getenv("AWS_SECRET_NAME")
    is_lambda = os.environ.get("AWS_EXECUTION_ENV") is not None
    
    # Fallback to a default secret name if running in Lambda and no custom secret name is set
    if not secret_name and is_lambda:
        secret_name = "ucr-smartcity-chatbot-secrets"
        
    if secret_name:
        region_name = os.getenv("AWS_REGION", "ap-southeast-1")
        print(f"[ConfigLoader] Detected AWS environment. Fetching secrets from Secrets Manager: '{secret_name}' in region '{region_name}'...")
        
        try:
            # Create a Secrets Manager client
            client = boto3.client(
                service_name='secretsmanager',
                region_name=region_name
            )
            
            response = client.get_secret_value(SecretId=secret_name)
            
            if 'SecretString' in response:
                secrets = json.loads(response['SecretString'])
                
                # Inject retrieved secrets directly into os.environ
                loaded_keys = []
                for key, value in secrets.items():
                    os.environ[key] = str(value)
                    loaded_keys.append(key)
                
                print(f"[ConfigLoader] Successfully loaded secrets from Secrets Manager. Keys imported: {', '.join(loaded_keys)}")
            else:
                print("[ConfigLoader] Warning: SecretString not found in Secrets Manager response.")
                
        except ClientError as e:
            print(f"[ConfigLoader] Error retrieving secrets from AWS Secrets Manager: {e}")
        except Exception as e:
            print(f"[ConfigLoader] Unexpected error during Secrets Manager retrieval: {e}")
    else:
        print("[ConfigLoader] Running in local/non-AWS mode. Loaded configuration from .env file.")

# Run the loader immediately upon import to ensure environment variables are populated
load_secrets_manager()
