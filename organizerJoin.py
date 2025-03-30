# Lambda function for POST /lobbies/{lobbyCode}/organizer-join
# INSECURE VERSION: Trusts player name sent in request body.

import json
import boto3
import os
# import time # Needed if you add TTL or timestamps

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME']) # Assumes TABLE_NAME env var is set

def lambda_handler(event, context):
    # Standard headers for CORS and JSON
    headers = {
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Origin': '*', # Adjust in production
        'Access-Control-Allow-Methods': 'OPTIONS,POST' # Adjust if needed
    }

    try:
        # --- Step 1: Extract Lobby Code and Requesting Player Name ---
        try:
            lobby_code = event['pathParameters']['lobbyCode']
        except (KeyError, TypeError):
            raise ValueError("Missing or invalid 'lobbyCode' in path parameters.")

        # --- INSECURE: Get player name from request BODY ---
        try:
            body = json.loads(event.get('body', '{}'))
            # Assumes frontend sends {"playerName": "OrganizerNameFromLocalStorage"}
            requesting_player_name = body.get('playerName')
            if not requesting_player_name:
                raise ValueError("Missing 'playerName' in request body.")
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            print(f"Error parsing body or getting playerName: {e}")
            raise ValueError("Invalid or missing request body/playerName.")
        # --- End of insecure name extraction ---

        # --- Step 2: Fetch Lobby Data ---
        response = table.get_item(Key={'lobbyCode': lobby_code})
        item = response.get('Item')

        if not item:
            return {
                'statusCode': 404,
                'headers': headers,
                'body': json.dumps({'error': 'Lobby not found.'})
            }

        # --- Step 3: Authorize - Check if name from BODY matches stored organizerName ---
        stored_organizer_name = item.get('organizerName')
        # Note: This check relies on trusting the requesting_player_name from the body
        if not stored_organizer_name or requesting_player_name != stored_organizer_name:
            # Although insecure, we still perform the check based on the (untrusted) input
            print(f"Auth fail: Input name '{requesting_player_name}' != Stored name '{stored_organizer_name}'")
            return {
                'statusCode': 403, # Forbidden (based on untrusted input)
                'headers': headers,
                'body': json.dumps({'error': 'Provided player name does not match organizer.'})
            }

        # --- Step 4: Check Player Slots ---
        player1 = item.get('player1', '') # Default to empty string if attribute missing
        player2 = item.get('player2', '')

        assigned_slot = None
        # Check if player1 slot is free
        if not player1:
            assigned_slot = 'player1'
        # Else check if player2 slot is free AND organizer isn't already player1
        elif not player2 and player1 != requesting_player_name:
            assigned_slot = 'player2'
        # Else check edge cases: organizer is already player1 or player2
        elif player1 == requesting_player_name or player2 == requesting_player_name:
             return {
                 'statusCode': 400, # Bad Request
                 'headers': headers,
                 'body': json.dumps({'error': 'Organizer is already in a player slot.'})
             }

        # --- Step 5: Handle Full Lobby ---
        if assigned_slot is None:
            # This means both slots were filled and neither was the organizer themselves
            return {
                'statusCode': 409, # Conflict - Lobby is full
                'headers': headers,
                'body': json.dumps({'error': 'Lobby is full'})
            }

        # --- Step 6: Update Lobby Item ---
        table.update_item(
            Key={'lobbyCode': lobby_code},
            UpdateExpression=f'SET {assigned_slot} = :playerName',
            ExpressionAttributeValues={
                ':playerName': requesting_player_name # Use the name from the body
            }
        )

        # --- Step 7: Return Success ---
        return {
            'statusCode': 200,
            'headers': headers,
            'body': json.dumps({
                'message': f'Organizer joined successfully as {assigned_slot}',
                'assignedSlot': assigned_slot,
                'newRole': 'organizer_player' # Critical: Tell frontend the new role
            })
        }

    except ValueError as ve: # Catch errors from input validation or body parsing
         print(ve)
         return {
            'statusCode': 400, # Bad Request
            'headers': headers,
            'body': json.dumps({'error': str(ve)})
         }
    except Exception as e:
        print(f"Internal error: {e}")
        # Keep production errors generic for security
        error_message = 'Could not process request due to an internal error.'
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': error_message})
        }