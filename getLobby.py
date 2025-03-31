import json
import boto3
import os
import time
import datetime # Added for schedule creation
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])
scheduler = boto3.client('scheduler') # Added for schedule creation
handle_timeout_lambda_arn = os.environ.get('HANDLE_TIMEOUT_LAMBDA_ARN', '') # Added for schedule creation
lambda_role_arn = os.environ.get('LAMBDA_EXECUTION_ROLE_ARN', '') # Added for schedule creation

def decimal_to_int(obj):
    """Convert Decimal objects to integers for JSON serialization."""
    if isinstance(obj, Decimal):
        return int(obj)
    raise TypeError

def create_schedule(lobby_code, game_state, start_time_ms, duration_ms):
    """Creates the EventBridge schedule for the next timeout."""
    schedule_name = f"timeout-{lobby_code}-{game_state}"
    if not handle_timeout_lambda_arn or not lambda_role_arn:
         print("ERROR: Lambda ARN or Role ARN environment variables not set. Cannot create schedule.")
         return None

    expiration_time_seconds = (start_time_ms + duration_ms) / 1000
    schedule_trigger_time_seconds = expiration_time_seconds # 2 REMOVED + 2 buffer

    schedule_dt_utc = datetime.datetime.fromtimestamp(schedule_trigger_time_seconds, tz=datetime.timezone.utc)
    schedule_time_str = schedule_dt_utc.strftime('%Y-%m-%dT%H:%M:%S')

    try:
        payload = json.dumps({
            'lobbyCode': lobby_code,
            'expectedGameState': game_state # The state that just started
        })
        print(f"Attempting to create schedule: {schedule_name} at {schedule_time_str} targeting {handle_timeout_lambda_arn}")

        response = scheduler.create_schedule(
            Name=schedule_name,
            GroupName='default', # Use default group or create one if needed
            ActionAfterCompletion='DELETE',
            FlexibleTimeWindow={'Mode': 'OFF'},
            ScheduleExpression=f'at({schedule_time_str})',
            State='ENABLED',
            Target={
                'Arn': handle_timeout_lambda_arn, # ARN of handleTimeout Lambda
                'RoleArn': lambda_role_arn,      # Execution role ARN passed to scheduler
                'Input': payload
            }
        )
        print(f"Successfully created schedule: {schedule_name} for time {schedule_time_str}")
        return schedule_name
    except scheduler.exceptions.ConflictException:
         print(f"Schedule {schedule_name} already exists. Assuming it's okay.")
         return schedule_name
    except Exception as e:
        print(f"ERROR creating schedule {schedule_name}: {str(e)}")
        return None

def lambda_handler(event, context):
    headers = {
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'GET,POST,OPTIONS'
    }

    if event['httpMethod'] == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': headers
        }

    try:
        lobby_code = event['pathParameters']['lobbyCode']
        print(f"Processing request for lobby: {lobby_code}, method: {event['httpMethod']}")
        
        if event['httpMethod'] == 'POST':
            # Handle POST request (ready action)
            body = json.loads(event['body'])
            print(f"POST body: {body}")
            
            player = body.get('player')
            ready = body.get('ready')
            action = body.get('action')
            
            print(f"Action: {action}, Player: {player}, Ready: {ready}")

            if action == 'ready':
                # Get current lobby state first to determine roles
                response = table.get_item(Key={'lobbyCode': lobby_code})
                if 'Item' not in response:
                    print(f"Lobby not found: {lobby_code}")
                    return {
                        'statusCode': 404,
                        'headers': headers,
                        'body': json.dumps({'error': 'Lobby not found'})
                    }

                item = response['Item']
                print(f"Current lobby state: {item}")
                
                # Handle organizer_player special case
                actual_player = player
                if player == 'organizer_player':
                    # Use .strip() to remove leading/trailing whitespace during comparison
                    organizer_name = item.get('organizerName', '').strip()
                    player1_name = item.get('player1', '').strip()
                    player2_name = item.get('player2', '').strip()

                    print(f"DEBUG: Resolving organizer_player...")
                    print(f"  DB organizerName: '{organizer_name}'")
                    print(f"  DB player1: '{player1_name}'")
                    print(f"  DB player2: '{player2_name}'")

                    # Ensure organizerName exists before comparing
                    if not organizer_name:
                        print("ERROR: organizerName is missing from lobby item during role resolution.")
                        return {
                            'statusCode': 500,
                            'headers': headers,
                            'body': json.dumps({'error': 'Lobby state inconsistent: organizerName missing'})
                        }

                    # Compare stripped names
                    if organizer_name == player1_name:
                        actual_player = 'player1'
                        print(f"  Resolved organizer_player -> player1")
                    elif organizer_name == player2_name:
                        actual_player = 'player2'
                        print(f"  Resolved organizer_player -> player2")
                    else:
                        print(f"ERROR: Organizer name '{organizer_name}' does not match any occupied player slot ('{player1_name}', '{player2_name}').")
                        return {
                            'statusCode': 400,
                            'headers': headers,
                            'body': json.dumps({
                                'error': 'Organizer role mismatch. Cannot determine player slot.',
                                'details': {
                                    'organizerName': organizer_name,
                                    'player1': player1_name,
                                    'player2': player2_name
                                }
                            })
                        }
                elif player not in ['player1', 'player2']:
                    print(f"Invalid player role: {player}")
                    return {
                        'statusCode': 400,
                        'headers': headers,
                        'body': json.dumps({'error': f'Invalid player role: {player}. Must be player1, player2, or organizer_player.'})
                    }
                
                if ready is None:
                    print("Ready status is missing")
                    return {
                        'statusCode': 400,
                        'headers': headers,
                        'body': json.dumps({'error': 'Ready status is missing'})
                    }
                
                # Update ready status for the player
                player_ready_key = f"{actual_player}Ready"
                print(f"Setting {player_ready_key} to {ready}")
                
                # Update the ready status
                update_response = table.update_item(
                    Key={'lobbyCode': lobby_code},
                    UpdateExpression=f'SET {player_ready_key} = :ready',
                    ExpressionAttributeValues={':ready': ready},
                    ReturnValues='ALL_NEW'
                )
                
                updated_item = update_response.get('Attributes', {})
                print(f"Updated lobby state: {updated_item}")
                
                # Check if both players are ready
                player1_ready = updated_item.get('player1Ready', False)
                player2_ready = updated_item.get('player2Ready', False)
                print(f"Ready status check:")
                print(f"  Player1 ready: {player1_ready}")
                print(f"  Player2 ready: {player2_ready}")
                
                if ready and player1_ready and player2_ready:
                    # Both players are ready, start the game
                    print("Both players ready, updating game state to ban1_p1")
                    current_time = int(time.time() * 1000)
                    initial_duration = 30000  # 30 seconds
                    try:
                        table.update_item(
                            Key={'lobbyCode': lobby_code},
                            UpdateExpression='SET gameState = :state, timerState = :timer',
                            ExpressionAttributeValues={
                                ':state': 'ban1_p1',
                                ':timer': {
                                    'startTime': current_time,
                                    'duration': initial_duration,
                                    'isActive': True
                                }
                            }
                        )
                        print(f"Lobby {lobby_code} state updated to ban1_p1.")

                        # --- Schedule Creation Call ---
                        start_time_int = int(current_time)  # Convert to int
                        duration_int = int(initial_duration)  # Convert to int
                        create_schedule(lobby_code, 'ban1_p1', start_time_int, duration_int)
                        # --- End Schedule Creation Call ---

                    except Exception as update_error:
                        print(f"ERROR updating lobby to start game: {update_error}")
                        return {
                            'statusCode': 500,
                            'headers': headers,
                            'body': json.dumps({'error': f'Failed to start game: {str(update_error)}'})
                        }
                
                return {
                    'statusCode': 200,
                    'headers': headers,
                    'body': json.dumps({
                        'message': 'Ready status updated',
                        'lobbyState': updated_item,
                        'debug': {
                            'actualPlayer': actual_player,
                            'originalRole': player,
                            'readyStatus': {
                                'player1': player1_ready,
                                'player2': player2_ready
                            }
                        }
                    }, default=decimal_to_int)
                }
            
            return {
                'statusCode': 400,
                'headers': headers,
                'body': json.dumps({'error': f'Invalid action: {action}'})
            }

        # Handle GET request (fetch lobby state)
        try:
            response = table.get_item(Key={'lobbyCode': lobby_code})
            if 'Item' not in response:
                return {
                    'statusCode': 404,
                    'headers': headers,
                    'body': json.dumps({'error': 'Lobby not found'})
                }

            item = response['Item']
            print(f"Current lobby state for GET: {item}")

            # Use strip() to handle potential whitespace in names stored in DB
            player1_present = item.get('player1') and item.get('player1', '').strip() != ''
            player2_present = item.get('player2') and item.get('player2', '').strip() != ''
            current_state = item.get('gameState')

            print(f"DEBUG (GET): Checking state transition conditions: P1 Present={player1_present}, P2 Present={player2_present}, State='{current_state}'")

            # Check if state needs transition from 'waiting' to 'ready_check'
            if player1_present and player2_present and current_state == 'waiting':
                print("DEBUG (GET): Conditions met! Both players present and state is 'waiting'. Attempting state update to 'ready_check'.")
                try:
                    update_response = table.update_item(
                        Key={'lobbyCode': lobby_code},
                        UpdateExpression='SET gameState = :state',
                        # Ensure we only update if the state is *still* 'waiting'
                        ConditionExpression='gameState = :currentState',
                        ExpressionAttributeValues={
                            ':state': 'ready_check',
                            ':currentState': 'waiting'
                        },
                        ReturnValues="ALL_NEW"  # Get the updated item directly
                    )
                    # Use the updated item from the response for the rest of the GET logic
                    item = update_response.get('Attributes', item)
                    print(f"DEBUG (GET): State successfully updated to 'ready_check'. New item state: {item}")
                except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
                    # This means the state was *not* 'waiting' when the update was attempted
                    print("DEBUG (GET): ConditionalCheckFailed - State was not 'waiting' during update attempt. No action needed.")
                except Exception as update_error:
                    print(f"ERROR (GET): Failed to update gameState to ready_check: {update_error}. Returning current state.")

            # Initialize picks and bans if they don't exist
            if 'picks' not in item:
                item['picks'] = []
            if 'bans' not in item:
                item['bans'] = []

            # Initialize ready states if they don't exist
            if 'player1Ready' not in item:
                item['player1Ready'] = False
            if 'player2Ready' not in item:
                item['player2Ready'] = False

            # Initialize timer state if it doesn't exist
            if 'timerState' not in item:
                item['timerState'] = {
                    'startTime': None,
                    'duration': None,
                    'isActive': False
                }

            # Ensure player slots exist
            if 'player1' not in item:
                item['player1'] = ''
            if 'player2' not in item:
                item['player2'] = ''

            # Ensure gameState exists
            if 'gameState' not in item:
                item['gameState'] = 'waiting'

            return {
                'statusCode': 200,
                'headers': headers,
                'body': json.dumps(item, default=decimal_to_int)
            }

        except Exception as e:
            print(f"ERROR: Failed during GET request processing: {e}")
            return {
                'statusCode': 500,
                'headers': headers,
                'body': json.dumps({'error': str(e)})
            }

    except Exception as e:
        print(f"Error: {str(e)}")
        return {
            'statusCode': 500,
            'headers': headers,
            'body': json.dumps({'error': str(e)})
        }