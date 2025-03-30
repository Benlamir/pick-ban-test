# Modified pickban-resetLobby.py

import json
import boto3
import os
from decimal import Decimal # Import Decimal if needed for response serialization

dynamodb = boto3.resource('dynamodb')
# Ensure your environment variable is correctly set in Lambda configuration
table = dynamodb.Table(os.environ.get('TABLE_NAME', 'YourTableNameDefault')) # Added default for safety

def decimal_to_int(obj):
    """Helper to convert Decimal for JSON if needed."""
    if isinstance(obj, Decimal):
        return int(obj)
    raise TypeError

def get_cors_headers():
    return {
        'Access-Control-Allow-Origin': '*', # Adjust in production
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }

def lambda_handler(event, context):
    headers = get_cors_headers()

    # Handle CORS preflight requests
    if event.get('httpMethod') == 'OPTIONS':
        print("Responding to OPTIONS request")
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    try:
        lobby_code = event.get('pathParameters', {}).get('lobbyCode')
        if not lobby_code:
            print("ERROR: Missing lobbyCode")
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Missing lobbyCode path parameter'})}

        print(f"Processing RESET request for lobby: {lobby_code}")

        # --- Authorization Check (Only Organizer) ---
        try:
            body = json.loads(event.get('body', '{}'))
            # Assuming frontend sends organizer's name for verification (as done in deleteLobby)
            requesting_player_name = body.get('playerName')
            if not requesting_player_name:
                 raise ValueError("Missing 'playerName' in request body")
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            print(f"ERROR: Invalid request body: {e}")
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': f'Invalid request body: {str(e)}'})}

        try:
            # Get the lobby to check the organizer name
            response = table.get_item(Key={'lobbyCode': lobby_code})
            if 'Item' not in response:
                print(f"ERROR: Lobby not found: {lobby_code}")
                return {'statusCode': 404, 'headers': headers, 'body': json.dumps({'error': 'Lobby not found'})}
            item = response['Item']

            stored_organizer_name = item.get('organizerName')
            # Perform the check
            if not stored_organizer_name or requesting_player_name != stored_organizer_name:
                print(f"AUTH FAIL: Request name '{requesting_player_name}' != Stored organizer '{stored_organizer_name}'")
                return {'statusCode': 403, 'headers': headers, 'body': json.dumps({'error': 'Only the organizer can reset the lobby'})}
            print("Authorization successful.")

        except Exception as e:
            print(f"ERROR: Failed during auth/get item: {e}")
            return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': 'Failed to retrieve lobby data for authorization'})}

        # --- Perform Reset Update (Modified) ---
        print(f"Attempting full reset for lobby: {lobby_code}")
        update_expression = (
            "SET gameState = :newState, "
            "player1Ready = :notReady, "
            "player2Ready = :notReady, "
            "picks = :emptyList, "
            "bans = :emptyList, "
            "timerState = :emptyTimer"
        )
        expression_attribute_values = {
            ':newState': 'ready_check',     # Set state to ready_check
            ':notReady': False,             # Reset ready flags
            ':emptyList': [],               # Clear picks and bans
            ':emptyTimer': {'startTime': None, 'duration': None, 'isActive': False} # Reset timer
        }

        try:
            response = table.update_item(
                Key={'lobbyCode': lobby_code},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues="ALL_NEW", # Get the updated item back
                ConditionExpression="attribute_exists(lobbyCode)" # Make sure lobby exists
            )
            updated_item = response.get('Attributes', {}) # Get the updated item
            print(f"Reset successful. New state: {updated_item}")

            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'message': 'Lobby reset successfully to ready_check state.',
                    # Return the full updated state
                    'lobbyState': updated_item
                }, default=decimal_to_int) # Use helper if needed for Decimals
            }

        except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
            print(f"ERROR: Lobby {lobby_code} not found during reset update.")
            return {'statusCode': 404, 'headers': headers, 'body': json.dumps({'error': 'Lobby not found'})}
        except Exception as e:
            print(f"Error resetting lobby: {e}")  # Log the error
            return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': f'Could not reset lobby: {str(e)}'})}

    except Exception as e:
         # Catch any unexpected errors at the top level
        print(f"FATAL ERROR in resetLobby handler: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'An unexpected server error occurred.'})
        }