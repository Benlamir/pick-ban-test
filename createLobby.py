import json
import boto3
import uuid
import os
import time

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

# --- Helper function placeholder ---
# You MUST replace this with the actual logic to get the username
# based on your specific API Gateway and authorizer setup.
def get_organizer_name_from_event(event):
    """
    Extracts the organizer's name from the Lambda event object.
    """
    try:
        print("Received event:", json.dumps(event))  # Debug log
        
        # Get the name from the request body
        request_body = json.loads(event.get('body', '{}'))
        print("Parsed request body:", json.dumps(request_body))  # Debug log
        
        organizer_name = request_body.get('playerName')
        print("Extracted organizer name:", organizer_name)  # Debug log
        
        if not organizer_name:
            raise ValueError("Organizer name is missing or empty")
        return organizer_name

    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as e:
        print(f"Error extracting organizer name: {e}")
        print("Event body:", event.get('body'))  # Debug log
        raise ValueError("Could not determine organizer name from request.")


def lambda_handler(event, context):
    try:
        # --- Step 1: Extract Organizer Name ---
        # This now calls the helper function defined above
        organizer_name = get_organizer_name_from_event(event)

        # --- Step 2: Generate Lobby Code ---
        # Generate a unique lobby code (using UUID and timestamp for extra uniqueness)
        lobby_code = f"{uuid.uuid4().hex[:4]}-{int(time.time() * 1000) % 10000:04d}"

        # --- Step 3: Calculate TTL ---
        current_timestamp = int(time.time())
        # Set TTL duration (24 hours in seconds)
        ttl_duration_seconds = 24 * 60 * 60 
        expiration_timestamp = current_timestamp + ttl_duration_seconds

        # --- Step 4: Store the lobby in DynamoDB, including organizerName and TTL ---
        table.put_item(
            Item={
                'lobbyCode': lobby_code,
                'organizerName': organizer_name,
                'createdAt': current_timestamp,
                'player1': '',
                'player2': '',
                'gameState': 'waiting',
                'ttl': expiration_timestamp  # Add TTL attribute
            },
            # ConditionExpression to prevent overwriting an existing lobby (unlikely, but good practice)
            ConditionExpression='attribute_not_exists(lobbyCode)'
        )

        # --- Step 5: Return Success Response ---
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Origin': '*',  # CORS: Allow requests from any origin
                'Access-Control-Allow-Methods': 'OPTIONS,POST'
            },
            # Optionally return organizerName if frontend needs it (though it should have it)
            'body': json.dumps({'lobbyCode': lobby_code, 'organizerName': organizer_name})
        }

    # --- Error Handling ---
    except boto3.client('dynamodb').exceptions.ConditionalCheckFailedException:
        # Extremely unlikely: Lobby code collision.
        return {
            'statusCode': 500,
             'headers': {
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'OPTIONS,POST'
            },
            'body': json.dumps({'error': 'Could not create lobby (code collision). Please try again.'})
        }
    except ValueError as ve: # Catch error from get_organizer_name_from_event
         print(ve)
         return {
            'statusCode': 400, # Bad Request - missing required info
            'headers': {
                 'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                 'Access-Control-Allow-Origin': '*',
                 'Access-Control-Allow-Methods': 'OPTIONS,POST'
             },
            'body': json.dumps({'error': str(ve)}) # Return the specific error
         }
    except Exception as e:
        print(e)
        return {
            'statusCode': 500,
            'headers': {
                 'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                 'Access-Control-Allow-Origin': '*',
                 'Access-Control-Allow-Methods': 'OPTIONS,POST'
             },
            # Keep error messages generic for security reasons in production
            'body': json.dumps({'error': 'Could not create lobby due to an internal error.'})
        }