# Modified makePick.py with organizer_player handling

import json
import boto3
import os
import time
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ.get('TABLE_NAME', 'YourTableNameDefault'))

def decimal_to_int(obj):
    """Helper to convert Decimal for JSON."""
    if isinstance(obj, Decimal):
        return int(obj)
    raise TypeError

def get_cors_headers():
     return {
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Origin': '*', # Adjust in production
        'Access-Control-Allow-Methods': 'POST,OPTIONS'
    }

def lambda_handler(event, context):
    headers = get_cors_headers()

    if event.get('httpMethod') == 'OPTIONS':
        print("Responding to OPTIONS request")
        return {'statusCode': 200, 'headers': headers, 'body': ''}

    try:
        lobby_code = event.get('pathParameters', {}).get('lobbyCode')
        if not lobby_code:
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Missing lobbyCode'})}

        try:
            body = json.loads(event.get('body', '{}'))
            # Player role received from frontend ('player1', 'player2', or 'organizer_player')
            player_role_from_request = body.get('player')
            pick_or_ban_value = body.get('pick') # The resonator ID being picked/banned
        except json.JSONDecodeError as e:
             print(f"ERROR: Invalid JSON body: {e}")
             return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Invalid JSON body'})}

        # --- Modify initial validation to ALLOW 'organizer_player' ---
        if not player_role_from_request or player_role_from_request not in ['player1', 'player2', 'organizer_player'] or not pick_or_ban_value:
            print(f"ERROR: Missing player role or pick/ban value. Player: {player_role_from_request}, Value: {pick_or_ban_value}")
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Missing player role or pick/ban selection'})}

        print(f"Processing PICK/BAN for lobby {lobby_code}. Requester Role: {player_role_from_request}, Value: {pick_or_ban_value}")

        # --- Get current lobby state ---
        try:
            response = table.get_item(Key={'lobbyCode': lobby_code})
            if 'Item' not in response:
                print(f"ERROR: Lobby not found: {lobby_code}")
                return {'statusCode': 404, 'headers': headers, 'body': json.dumps({'error': 'Lobby not found'})}
            item = response['Item']
            print(f"Current lobby state for PICK/BAN: {item}")
        except Exception as e:
             print(f"ERROR: Failed to get lobby item: {e}")
             return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': 'Failed to retrieve lobby data'})}

        # --- ADD ROLE RESOLUTION LOGIC ---
        actual_player_slot = None # Will be 'player1' or 'player2' after resolution
        if player_role_from_request == 'organizer_player':
            organizer_name_from_db = item.get('organizerName', '').strip()
            player1_name_from_db = item.get('player1', '').strip()
            player2_name_from_db = item.get('player2', '').strip()
            print(f"DEBUG: Resolving organizer_player for pick/ban...")
            print(f"  DB organizerName: '{organizer_name_from_db}'")
            print(f"  DB player1: '{player1_name_from_db}'")
            print(f"  DB player2: '{player2_name_from_db}'")
            if not organizer_name_from_db:
                 print("ERROR: organizerName is missing from lobby item during role resolution.")
                 return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': 'Lobby state inconsistent: organizerName missing'})}
            if organizer_name_from_db == player1_name_from_db:
                 actual_player_slot = 'player1'
                 print(f"  Resolved organizer_player -> player1")
            elif organizer_name_from_db == player2_name_from_db:
                 actual_player_slot = 'player2'
                 print(f"  Resolved organizer_player -> player2")
            else:
                print(f"ERROR: Organizer name '{organizer_name_from_db}' does not match any occupied player slot.")
                return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Organizer role mismatch for pick/ban.'})}
        elif player_role_from_request in ['player1', 'player2']:
            # Check if the requesting player actually occupies that slot
            player_name_in_slot = item.get(player_role_from_request, '').strip()
            if not player_name_in_slot:
                print(f"ERROR: Player role {player_role_from_request} is empty.")
                return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': f'Player {player_role_from_request} is not in the lobby.'})}
            actual_player_slot = player_role_from_request # Role is already resolved
            print(f"DEBUG: Role already resolved -> {actual_player_slot}")
        else:
             # This case should technically be caught by the initial validation, but defensive coding is good
             print(f"ERROR: Unexpected player role value: {player_role_from_request}")
             return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Invalid player role specified.'})}
        # --- END ROLE RESOLUTION LOGIC ---

        # Now use 'actual_player_slot' for subsequent logic


        current_state = item.get('gameState', 'unknown')
        picks = item.get('picks', [])
        bans = item.get('bans', [])

        # Validate pick/ban value is not already used
        if pick_or_ban_value in picks or pick_or_ban_value in bans:
            print(f"ERROR: Value '{pick_or_ban_value}' already picked or banned.")
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Selection already picked or banned'})}

        # --- New State Machine Logic ---
        next_state = None
        next_player_turn_for_timer = None # Tracks whose turn starts next for timer purposes
        timer_duration = 30000 # Default duration, adjust as needed per phase
        action_type = None # 'pick' or 'ban'

        print(f"DEBUG: New State Machine - State='{current_state}', Resolved Player='{actual_player_slot}'")

        if current_state == 'ban1_p1': # P1 Ban 1
            if actual_player_slot != 'player1': return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Not your turn (P1 Ban 1)'})}
            action_type = 'ban'
            next_state = 'ban1_p2'
            next_player_turn_for_timer = 'player2'
        elif current_state == 'ban1_p2': # P2 Ban 1
            if actual_player_slot != 'player2': return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Not your turn (P2 Ban 1)'})}
            action_type = 'ban'
            next_state = 'pick1_p1'
            next_player_turn_for_timer = 'player1'
        elif current_state == 'pick1_p1': # P1 Pick 1 (of 2 total)
            if actual_player_slot != 'player1': return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Not your turn (P1 Pick 1)'})}
            action_type = 'pick'
            next_state = 'pick1_p2'
            next_player_turn_for_timer = 'player2'
        elif current_state == 'pick1_p2': # P2 Pick 1 (of 2 total)
            if actual_player_slot != 'player2': return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Not your turn (P2 Pick 1)'})}
            action_type = 'pick'
            next_state = 'pick1_p1_2'
            next_player_turn_for_timer = 'player1'
        elif current_state == 'pick1_p1_2': # P1 Pick 2 (of 2 total)
            if actual_player_slot != 'player1': return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Not your turn (P1 Pick 2)'})}
            action_type = 'pick'
            next_state = 'pick1_p2_2'
            next_player_turn_for_timer = 'player2'
        elif current_state == 'pick1_p2_2': # P2 Pick 2 (of 2 total)
            if actual_player_slot != 'player2': return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Not your turn (P2 Pick 2)'})}
            action_type = 'pick'
            next_state = 'ban2_p1'
            next_player_turn_for_timer = 'player1'
        elif current_state == 'ban2_p1': # P1 Ban 2
            if actual_player_slot != 'player1': return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Not your turn (P1 Ban 2)'})}
            action_type = 'ban'
            next_state = 'ban2_p2'
            next_player_turn_for_timer = 'player2'
        elif current_state == 'ban2_p2': # P2 Ban 2
            if actual_player_slot != 'player2': return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Not your turn (P2 Ban 2)'})}
            action_type = 'ban'
            next_state = 'pick2_p2' # Player 2 starts the final pick phase
            next_player_turn_for_timer = 'player2'
        elif current_state == 'pick2_p2': # P2 Pick 1 (final pick)
            if actual_player_slot != 'player2': return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Not your turn (P2 Final Pick)'})}
            action_type = 'pick'
            next_state = 'pick2_p1'
            next_player_turn_for_timer = 'player1'
        elif current_state == 'pick2_p1': # P1 Pick 1 (final pick)
            if actual_player_slot != 'player1': return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': 'Not your turn (P1 Final Pick)'})}
            action_type = 'pick'
            next_state = 'complete'
            next_player_turn_for_timer = None # Game ends
        else:
            print(f"ERROR: Invalid current game state for pick/ban: {current_state}")
            return {'statusCode': 400, 'headers': headers, 'body': json.dumps({'error': f'Invalid game state for action: {current_state}'})}
        # --- End New State Machine Logic ---

        # --- Append to picks or bans list ---
        # (Keep existing logic, uses action_type)
        if action_type == 'pick':
            picks.append(pick_or_ban_value)
            update_expression = 'SET picks = :p, gameState = :state'
            expression_values = {':p': picks, ':state': next_state}
            print(f"Adding pick '{pick_or_ban_value}'. New picks: {picks}")
        elif action_type == 'ban':
            bans.append(pick_or_ban_value)
            update_expression = 'SET bans = :b, gameState = :state'
            expression_values = {':b': bans, ':state': next_state}
            print(f"Adding ban '{pick_or_ban_value}'. New bans: {bans}")
        else:
             return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': 'Internal Error: Action type not set'})}

        # --- Update Timer State ---
        # (Keep existing logic, uses timer_duration)
        if timer_duration is not None:
            current_time_ms = int(time.time() * 1000)
            update_expression += ', timerState = :timer'
            expression_values[':timer'] = {
                'startTime': current_time_ms, 'duration': timer_duration, 'isActive': True
            }
            print(f"Updating timer for next state '{next_state}'. Start: {current_time_ms}, Duration: {timer_duration}")
        elif next_state == 'complete':
             update_expression += ', timerState = :timer'
             expression_values[':timer'] = {'startTime': None, 'duration': None, 'isActive': False}
             print("Game complete. Deactivating timer.")
        else:
             print(f"Keeping existing timer running for state '{next_state}'.")

        # --- Update DynamoDB ---
        # (Keep existing logic)
        try:
            update_result = table.update_item(
                Key={'lobbyCode': lobby_code},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values,
                ReturnValues='ALL_NEW'
            )
            updated_item = update_result.get('Attributes', {})
            print(f"DynamoDB update successful. New state: {updated_item}")
            # (Keep existing return success logic)
            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps({
                    'message': f'{action_type.capitalize()} successful.',
                    'nextState': next_state,
                    'nextPlayer': next_player_turn_for_timer,
                    'lobbyState': updated_item
                }, default=decimal_to_int)
            }
        except Exception as e:
            print(f"ERROR: Failed to update lobby state after pick/ban: {e}")
            return {'statusCode': 500, 'headers': headers, 'body': json.dumps({'error': f'Failed to save pick/ban: {str(e)}'})}

    except Exception as e:
        print(f"FATAL ERROR in makePick handler: {str(e)}")
        # (Keep existing fatal error return)
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': 'An unexpected server error occurred.'})
        }