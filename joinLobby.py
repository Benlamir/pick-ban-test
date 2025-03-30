import json
import boto3
import os
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

def decimal_to_int(obj):
    """Convert Decimal objects to integers for JSON serialization."""
    if isinstance(obj, Decimal):
        return int(obj)
    raise TypeError

def lambda_handler(event, context):
    try:
        # Get lobby code from path parameters
        lobby_code = event['pathParameters']['lobbyCode']
        
        # Parse request body
        try:
            body = json.loads(event.get('body', '{}'))
            player_name = body.get('playerName')
        except json.JSONDecodeError:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
                },
                'body': json.dumps({'error': 'Invalid request body format'})
            }

        # --- Input Validation ---
        if not player_name or len(player_name.strip()) == 0:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
                },
                'body': json.dumps({'error': 'Player name is required'})
            }
        player_name = player_name.strip() # Remove leading/trailing spaces

        # Get the lobby from DynamoDB
        response = table.get_item(Key={'lobbyCode': lobby_code})

        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
                },
                'body': json.dumps({'error': 'Lobby not found'})
            }

        item = response['Item']

        # Check if player is already in the lobby
        if item.get('player1') == player_name or item.get('player2') == player_name:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
                },
                'body': json.dumps({'error': 'Player is already in this lobby'})
            }

        # Check if there's an empty player slot and assign the name
        if item.get('player1', '') == '':
            item['player1'] = player_name
            role = "player1"
        elif item.get('player2', '') == '':
            item['player2'] = player_name
            role = "player2"
        else:
            return {
                'statusCode': 409,  # Conflict - Lobby is full
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
                },
                'body': json.dumps({'error': 'Lobby is full'})
            }

        # --- Update DynamoDB ---
        update_expression = "SET player1 = :p1, player2 = :p2"
        expression_attribute_values = {
            ':p1': item['player1'],
            ':p2': item['player2']
        }

        try:
            table.update_item(
                Key={'lobbyCode': lobby_code},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues="UPDATED_NEW"
            )
        except Exception as e:
            print(f"Error updating DynamoDB: {str(e)}")
            return {
                'statusCode': 500,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'POST,OPTIONS',
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
                },
                'body': json.dumps({'error': 'Failed to update lobby state'})
            }

        # Remove sensitive/unsupported fields before returning
        item.pop("organizer", None)  # Remove old field if it exists
        item.pop("organizerName", None)  # Remove organizer name for security

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST,OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
            },
            'body': json.dumps({
                'message': 'Joined lobby successfully',
                'role': role,
                'lobbyData': item
            }, default=decimal_to_int)
        }

    except Exception as e:
        print(f"Error in joinLobby: {str(e)}")  # Add detailed error logging
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'POST,OPTIONS',
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
            },
            'body': json.dumps({'error': f'Could not join lobby: {str(e)}'})
        } 