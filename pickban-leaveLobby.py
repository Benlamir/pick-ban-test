import json
import boto3
import os
from decimal import Decimal

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

def get_cors_headers():
    return {
        'Access-Control-Allow-Origin': '*',
        'Access-Control-Allow-Methods': 'POST, OPTIONS',
        'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token'
    }

def decimal_to_int(obj):
    """Convert Decimal objects to integers for JSON serialization."""
    if isinstance(obj, Decimal):
        return int(obj)
    raise TypeError

def lambda_handler(event, context):
    if event.get('httpMethod') == 'OPTIONS':
        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': ''
        }

    try:
        lobby_code = event.get('pathParameters', {}).get('lobbyCode')
        if not lobby_code:
            return {'statusCode': 400, 'headers': get_cors_headers(), 'body': json.dumps({'error': 'Missing lobbyCode'})}

        body = json.loads(event.get('body', '{}'))
        player_role = body.get('player')

        if not player_role or player_role not in ('player1', 'player2'):
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Invalid or missing player role in request body'})
            }

        # First get the current lobby state
        response = table.get_item(Key={'lobbyCode': lobby_code})
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Lobby not found'})
            }

        item = response['Item']
        
        # Check if the player is actually in the lobby
        if item.get(player_role) == '':
            return {
                'statusCode': 400,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': f'Player {player_role} is not in the lobby'})
            }

        # --- Update DynamoDB ---
        # Simply clear the leaving player's slot
        update_expression = f"SET {player_role} = :empty, picks = :empty_list, bans = :empty_list, gameState = :waiting"
        expression_attribute_values = {
            ':empty': '',
            ':empty_list': [],
            ':waiting': 'waiting'
        }

        try:
            table.update_item(
                Key={'lobbyCode': lobby_code},
                UpdateExpression=update_expression,
                ExpressionAttributeValues=expression_attribute_values,
                ReturnValues="UPDATED_NEW",
                ConditionExpression="attribute_exists(lobbyCode)"
            )
        except Exception as e:
            print(f"Error updating DynamoDB: {str(e)}")
            return {
                'statusCode': 500,
                'headers': get_cors_headers(),
                'body': json.dumps({'error': 'Failed to update lobby state'})
            }

        # Get the updated item to return
        updated_response = table.get_item(Key={'lobbyCode': lobby_code})
        updated_item = updated_response.get('Item', {})

        # Ensure we're not returning empty player slots
        if 'player1' in updated_item:
            updated_item['player1'] = updated_item.get('player1', '')
        if 'player2' in updated_item:
            updated_item['player2'] = updated_item.get('player2', '')

        return {
            'statusCode': 200,
            'headers': get_cors_headers(),
            'body': json.dumps({
                'message': f'Successfully removed {player_role} and reset lobby state',
                'lobbyData': updated_item
            }, default=decimal_to_int)
        }

    except dynamodb.meta.client.exceptions.ConditionalCheckFailedException:
        return {
            'statusCode': 404,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': 'Lobby not found'})
        }
    except Exception as e:
        print(f"Error leaving lobby: {e}")  # Log the error
        return {
            'statusCode': 500,
            'headers': get_cors_headers(),
            'body': json.dumps({'error': f'Could not leave lobby: {str(e)}'})
        }