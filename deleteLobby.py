import json
import boto3
import os

dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table(os.environ['TABLE_NAME'])

def lambda_handler(event, context):
    try:
        lobby_code = event['pathParameters']['lobbyCode']

        # --- Authorization Check (Important!) ---
        response = table.get_item(Key={'lobbyCode': lobby_code})
        if 'Item' not in response:
            return {
                'statusCode': 404,
                'headers': {
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'OPTIONS,DELETE'
                },
                'body': json.dumps({'error': 'Lobby not found'})
            }

        item = response['Item']
        
        # Get the organizer name from the request body
        try:
            body = json.loads(event.get('body', '{}'))
            requesting_player_name = body.get('playerName')
            if not requesting_player_name:
                raise ValueError("Missing 'playerName' in request body")
        except (json.JSONDecodeError, TypeError, ValueError) as e:
            print(f"Error parsing body or getting playerName: {e}")
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'OPTIONS,DELETE'
                },
                'body': json.dumps({'error': 'Missing player name in request'})
            }

        # Check if the requesting player is the organizer
        stored_organizer_name = item.get('organizerName')
        if not stored_organizer_name or requesting_player_name != stored_organizer_name:
            print(f"Auth fail: Input name '{requesting_player_name}' != Stored name '{stored_organizer_name}'")
            return {
                'statusCode': 403,
                'headers': {
                    'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                    'Access-Control-Allow-Origin': '*',
                    'Access-Control-Allow-Methods': 'OPTIONS,DELETE'
                },
                'body': json.dumps({'error': 'Only the organizer can delete the lobby'})
            }

        # --- Delete the Item ---
        table.delete_item(Key={'lobbyCode': lobby_code})

        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'OPTIONS,DELETE'
            },
            'body': json.dumps({'message': 'Lobby deleted successfully'})
        }

    except Exception as e:
        print(f"Error in deleteLobby: {str(e)}")  # Add detailed error logging
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Headers': 'Content-Type,X-Amz-Date,Authorization,X-Api-Key,X-Amz-Security-Token',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'OPTIONS,DELETE'
            },
            'body': json.dumps({'error': f'Could not delete lobby: {str(e)}'})
        } 