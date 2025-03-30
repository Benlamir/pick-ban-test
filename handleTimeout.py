# lambda_function.py (for handleTimeout Lambda - S3 Version)

import json
import boto3
import os
import time
import random
import datetime # Make sure this is imported
from decimal import Decimal

# --- Initialize AWS Clients ---
# Ensure region_name is set if not using default region in environment
dynamodb = boto3.resource('dynamodb')
s3 = boto3.client('s3') # S3 Client
scheduler = boto3.client('scheduler') # EventBridge Scheduler Client

# --- Get Config from Environment Variables ---
table_name = os.environ.get('TABLE_NAME', '')
handle_timeout_lambda_arn = os.environ.get('HANDLE_TIMEOUT_LAMBDA_ARN', '')
lambda_role_arn = os.environ.get('LAMBDA_EXECUTION_ROLE_ARN', '')
s3_bucket_name = os.environ.get('S3_BUCKET_NAME', 'pick-ban-test-2023-10-27') # Bucket for resonators.json
s3_file_key = os.environ.get('S3_FILE_KEY', 'resonators.json') # Path/Key for resonators.json in bucket

# --- Validate Env Vars ---
if not all([table_name, handle_timeout_lambda_arn, lambda_role_arn, s3_bucket_name, s3_file_key]):
     print("ERROR: One or more environment variables are missing (TABLE_NAME, HANDLE_TIMEOUT_LAMBDA_ARN, LAMBDA_EXECUTION_ROLE_ARN, S3_BUCKET_NAME, S3_FILE_KEY)")
     # This will likely cause subsequent operations to fail, raise an exception or handle early
     raise ValueError("Missing required environment variables.")

table = dynamodb.Table(table_name)

# --- Load Resonator Data from S3 ---
resonators_data = []
try:
    print(f"Attempting to fetch s3://{s3_bucket_name}/{s3_file_key}")
    response = s3.get_object(Bucket=s3_bucket_name, Key=s3_file_key)
    resonators_data = json.loads(response['Body'].read().decode('utf-8'))
    print(f"Loaded {len(resonators_data)} resonators from S3.")
except Exception as e:
    print(f"ERROR fetching or parsing resonators.json from S3: {str(e)}")
    # Depending on requirements, either raise error or continue with empty list
    # raise e # Option: Fail the function if resonators can't load

# --- Helper Functions (get_next_state_and_player, get_action_type, create_schedule - Keep as before) ---

def get_next_state_and_player(current_state):
    """Determines the next state and player based on the state that timed out."""
    print(f"DEBUG: get_next_state for timed-out state: {current_state}")
    if current_state == 'ban1_p1': return 'ban1_p2', 'player2'
    if current_state == 'ban1_p2': return 'pick1_p1', 'player1'
    if current_state == 'pick1_p1': return 'pick1_p2', 'player2'
    if current_state == 'pick1_p2': return 'pick1_p1_2', 'player1'
    if current_state == 'pick1_p1_2': return 'pick1_p2_2', 'player2'
    if current_state == 'pick1_p2_2': return 'ban2_p1', 'player1'
    if current_state == 'ban2_p1': return 'ban2_p2', 'player2'
    if current_state == 'ban2_p2': return 'pick2_p2', 'player2'
    if current_state == 'pick2_p2': return 'pick2_p1', 'player1'
    if current_state == 'pick2_p1': return 'complete', None
    print(f"WARNING: Unknown state {current_state} encountered in get_next_state_and_player.")
    return None, None

def get_action_type(game_state):
    """Determines if the timed-out state required a 'pick' or 'ban'."""
    if not game_state: return None
    if 'ban' in game_state: return 'ban'
    if 'pick' in game_state: return 'pick'
    print(f"WARNING: Could not determine action type for state: {game_state}")
    return None

def create_schedule(lobby_code, game_state, start_time_ms, duration_ms):
    """Creates the EventBridge schedule for the next timeout."""
    schedule_name = f"timeout-{lobby_code}-{game_state}" # Needs to be unique
    if not handle_timeout_lambda_arn or not lambda_role_arn:
         print("ERROR: Lambda ARN or Role ARN environment variables not set. Cannot create schedule.")
         return None

    expiration_time_seconds = (start_time_ms + duration_ms) / 1000
    schedule_trigger_time_seconds = expiration_time_seconds + 2 # 2 sec buffer

    schedule_dt_utc = datetime.datetime.fromtimestamp(schedule_trigger_time_seconds, tz=datetime.timezone.utc)
    schedule_time_str = schedule_dt_utc.strftime('%Y-%m-%dT%H:%M:%S')

    try:
        payload = json.dumps({
            'lobbyCode': lobby_code,
            'expectedGameState': game_state
        })
        print(f"Attempting to create schedule: {schedule_name} at {schedule_time_str} targeting {handle_timeout_lambda_arn}")

        response = scheduler.create_schedule(
            Name=schedule_name,
            GroupName='default',
            ActionAfterCompletion='DELETE',
            FlexibleTimeWindow={'Mode': 'OFF'},
            ScheduleExpression=f'at({schedule_time_str})',
            State='ENABLED',
            Target={
                'Arn': handle_timeout_lambda_arn,
                'RoleArn': lambda_role_arn,
                'Input': payload
            }
        )
        print(f"Successfully created schedule: {schedule_name} for time {schedule_time_str}")
        return schedule_name
    except scheduler.exceptions.ConflictException:
         print(f"Schedule {schedule_name} already exists. Assuming it's okay (idempotency).")
         return schedule_name
    except Exception as e:
        print(f"ERROR creating schedule {schedule_name}: {str(e)}")
        return None

# --- Main Handler ---
def lambda_handler(event, context):
    print("Received event:", json.dumps(event))

    try:
        # --- 1. Extract payload ---
        payload = event
        lobby_code = payload.get('lobbyCode')
        expected_game_state = payload.get('expectedGameState')

        if not lobby_code or not expected_game_state:
            print("ERROR: Missing lobbyCode or expectedGameState in payload.")
            return {'statusCode': 400, 'body': 'Invalid payload'}

        # --- 2. Fetch Current Lobby State ---
        try:
            response = table.get_item(Key={'lobbyCode': lobby_code})
        except Exception as db_error:
             print(f"ERROR: Failed to get item from DynamoDB: {db_error}")
             return {'statusCode': 500, 'body': 'Database error'}

        if 'Item' not in response:
            print(f"Lobby {lobby_code} not found. Expired schedule for deleted lobby?")
            return {'statusCode': 200, 'body': 'Lobby not found, ignoring timeout.'}
        item = response['Item']
        current_game_state_db = item.get('gameState')
        print(f"Current DB state: {current_game_state_db}, Expected state from schedule: {expected_game_state}")

        # --- 3. Validate Timeout ---
        if current_game_state_db != expected_game_state:
            print(f"State mismatch ({current_game_state_db} != {expected_game_state}). Player likely acted already. Ignoring timeout.")
            return {'statusCode': 200, 'body': 'State already advanced, ignoring timeout.'}

        # --- 4. Timeout is Valid - Perform Random Action ---
        print(f"Timeout validated for lobby {lobby_code} in state {expected_game_state}.")
        action_type = get_action_type(expected_game_state)
        if not action_type:
             print(f"ERROR: Could not determine action type for state {expected_game_state}")
             return {'statusCode': 500, 'body': 'Internal configuration error.'}

        # Check if resonator data loaded successfully
        if not resonators_data:
             print(f"ERROR: Resonator data is not loaded. Cannot perform random action.")
             return {'statusCode': 500, 'body': 'Internal configuration error (resonators).'}

        all_resonator_ids = [r['id'] for r in resonators_data]
        current_picks = item.get('picks', [])
        current_bans = item.get('bans', [])
        already_selected = set(current_picks + current_bans)
        available_choices = [res_id for res_id in all_resonator_ids if res_id not in already_selected]

        random_choice = None # Initialize
        if not available_choices:
            print(f"ERROR: No available resonators to randomly {action_type} in state {expected_game_state}.")
            next_state = 'complete' # Force complete if no choices
            next_player = None
            print("WARNING: No choices left, forcing state to complete.")
        else:
            random_choice = random.choice(available_choices)
            print(f"Randomly selected '{random_choice}' for action '{action_type}'.")
            next_state, next_player = get_next_state_and_player(expected_game_state)
            if not next_state:
                 print(f"ERROR: Could not determine next state from {expected_game_state}")
                 return {'statusCode': 500, 'body': 'Internal state machine error.'}

        # --- 5. Update Lobby State ---
        expression_values = {':state': next_state}
        update_expression_parts = ['gameState = :state']

        if action_type == 'pick' and random_choice:
            current_picks.append(random_choice)
            update_expression_parts.append('picks = :val')
            expression_values[':val'] = current_picks
        elif action_type == 'ban' and random_choice:
            current_bans.append(random_choice)
            update_expression_parts.append('bans = :val')
            expression_values[':val'] = current_bans

        next_timer_state = {}
        new_start_time = int(time.time() * 1000)
        new_duration = 30000 # Default duration

        if next_state != 'complete':
            next_timer_state = {'startTime': new_start_time, 'duration': new_duration, 'isActive': True}
            update_expression_parts.append('timerState = :timer')
            expression_values[':timer'] = next_timer_state
        else:
            next_timer_state = {'startTime': None, 'duration': None, 'isActive': False}
            update_expression_parts.append('timerState = :timer')
            expression_values[':timer'] = next_timer_state

        update_expression = "SET " + ", ".join(update_expression_parts)
        print(f"Updating DynamoDB. Next state: {next_state}. Update expression: {update_expression}. Values: {json.dumps(expression_values, default=str)}")

        try:
            table.update_item(
                Key={'lobbyCode': lobby_code},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_values
            )
            print("DynamoDB updated successfully by timeout handler.")
        except Exception as db_error:
             print(f"ERROR: Failed to update DynamoDB: {db_error}")
             return {'statusCode': 500, 'body': 'Database update error'}

        # --- 6. Schedule Next Timeout (if needed) ---
        if next_state != 'complete':
             print(f"Scheduling next timeout for state: {next_state}")
             create_schedule(lobby_code, next_state, new_start_time, new_duration)
        else:
             print("Game complete, not scheduling further timeouts.")

        action_info = f"action: {action_type}, choice: {random_choice}" if random_choice else "action: forced complete (no choices)"
        return {'statusCode': 200, 'body': f'Timeout handled for {lobby_code}, {action_info}'}

    except Exception as e:
        print(f"FATAL ERROR in handleTimeout: {str(e)}")
        import traceback
        traceback.print_exc()
        return {'statusCode': 500, 'body': f'Internal server error handling timeout: {str(e)}'}