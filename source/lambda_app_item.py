#########################################################################################
# Copyright Amazon.com, Inc. or its affiliates. All Rights Reserved.                    #
# SPDX-License-Identifier: MIT-0                                                        #
#                                                                                       #
# Permission is hereby granted, free of charge, to any person obtaining a copy of this  #
# software and associated documentation files (the "Software"), to deal in the Software #
# without restriction, including without limitation the rights to use, copy, modify,    #
# merge, publish, distribute, sublicense, and/or sell copies of the Software, and to    #
# permit persons to whom the Software is furnished to do so.                            #
#                                                                                       #
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR IMPLIED,   #
# INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS FOR A         #
# PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT    #
# HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION     #
# OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE        #
# SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.                                #
#########################################################################################

import os
import json
import boto3
from boto3.dynamodb.conditions import Key, Attr
from policy import MFAuth

application = os.environ['application']
environment = os.environ['environment']

apps_table_name = '{}-{}-apps'.format(application, environment)
schema_table_name = '{}-{}-schema'.format(application, environment)
waves_table_name = '{}-{}-waves'.format(application, environment)
servers_table_name = '{}-{}-servers'.format(application, environment)

apps_table = boto3.resource('dynamodb').Table(apps_table_name)
schema_table = boto3.resource('dynamodb').Table(schema_table_name)
waves_table = boto3.resource('dynamodb').Table(waves_table_name)
servers_table = boto3.resource('dynamodb').Table(servers_table_name)

def lambda_handler(event, context):

    if event['httpMethod'] == 'GET':
        resp = apps_table.get_item(Key={'app_id': event['pathParameters']['appid']})
        if 'Item' in resp:
            return {'headers': {'Access-Control-Allow-Origin': '*'},
                    'body': json.dumps(resp['Item'])}
        else:
            return {'headers': {'Access-Control-Allow-Origin': '*'},
                    'statusCode': 400, 'body': 'app Id: ' + str(event['pathParameters']['appid']) + ' does not exist'}

    elif event['httpMethod'] == 'PUT':
        auth = MFAuth()
        authResponse = auth.getUserAttributePolicy(event)
        if authResponse['action'] == 'allow':
            try:
                body = json.loads(event['body'])
                app_attributes = []
                if "app_id" in body:
                    return {'headers': {'Access-Control-Allow-Origin': '*'},
                            'statusCode': 400, 'body': "You cannot modify app_id, this is managed by the system"}

                # check if app id exist
                existing_attr = apps_table.get_item(Key={'app_id': event['pathParameters']['appid']})
                print(existing_attr)
                if 'Item' not in existing_attr:
                  return {'headers': {'Access-Control-Allow-Origin': '*'},
                          'statusCode': 400, 'body': 'app Id: ' + str(event['pathParameters']['appid']) + ' does not exist'}

                # Validate Wave_id
                if 'wave_id' in body:
                    waves = waves_table.scan()
                    check = False
                    for wave in waves['Items']:
                        if wave['wave_id'] == str(body['wave_id']):
                           check = True
                    if check == False:
                        message = 'wave Id: ' + body['wave_id'] + ' does not exist'
                        return {'headers': {'Access-Control-Allow-Origin': '*'},
                                'statusCode': 400, 'body': message}

                # Check if there is a duplicate app_name
                apps = apps_table.scan()
                for app in apps['Items']:
                  if 'app_name' in body:
                    if app['app_name'].lower() == str(body['app_name']).lower() and app['app_id'] != str(event['pathParameters']['appid']):
                        return {'headers': {'Access-Control-Allow-Origin': '*'},
                                'statusCode': 400, 'body': 'app_name: ' +  body['app_name'] + ' already exist'}

                # Check if attribute is defined in the App schema
                for app_schema in schema_table.scan()['Items']:
                    if app_schema['schema_name'] == "app":
                        app_attributes = app_schema['attributes']
                for key in body.keys():
                    check = False
                    for attribute in app_attributes:
                        if key == attribute['name']:
                           check = True
                    if check == False:
                        message = "App attribute: " + key + " is not defined in the App schema"
                        return {'headers': {'Access-Control-Allow-Origin': '*'},
                                'statusCode': 400, 'body': message}

                # Check if attribute in the body matches the list value defined in schema
                for attribute in app_attributes:
                    if 'listvalue' in attribute:
                        listvalue = attribute['listvalue'].split(',')
                        for key in body.keys():
                            if key == attribute['name']:
                                if body[key] not in listvalue:
                                    message = "App attribute " + key + " for app " + body['app_name'] + " is '" + body[key] + "', does not match the list values '" + attribute['listvalue'] + "' defined in the App schema"
                                    return {'headers': {'Access-Control-Allow-Origin': '*'},
                                            'statusCode': 400, 'body': message}

                # Merge new attributes with existing one
                for key in body.keys():
                    existing_attr['Item'][key] = body[key]
                print(existing_attr)
                resp = apps_table.put_item(
                Item=existing_attr['Item']
                )
                return {'headers': {'Access-Control-Allow-Origin': '*'},
                        'body': json.dumps(resp)}
            except Exception as e:
                print(e)
                return {'headers': {'Access-Control-Allow-Origin': '*'},
                        'statusCode': 400, 'body': 'malformed json input'}
        else:
            return {'headers': {'Access-Control-Allow-Origin': '*'},
                    'statusCode': 401,
                    'body': json.dumps(authResponse)}

    elif event['httpMethod'] == 'DELETE':
        auth = MFAuth()
        authResponse = auth.getUserResourceCrationPolicy(event)
        if authResponse['action'] == 'allow':
            resp = apps_table.get_item(Key={'app_id': event['pathParameters']['appid']})
            if 'Item' in resp:
                respdel = apps_table.delete_item(Key={'app_id': event['pathParameters']['appid']})
                if respdel['ResponseMetadata']['HTTPStatusCode'] == 200:
                    # Remove App Id from servers
                    servers = servers_table.query(
                            IndexName='app_id-index',
                            KeyConditionExpression=Key('app_id').eq(event['pathParameters']['appid'])
                        )
                    if servers['Count'] is not 0:
                        serverids = []
                        for server in servers['Items']:
                          serverids.append(str(server['server_id']))
                        for id in serverids:
                            serverattr = servers_table.get_item(Key={'server_id': id})
                            del serverattr['Item']['app_id']
                            serverupdate = servers_table.put_item(
                                Item=serverattr['Item']
                                )
                    return {'headers': {'Access-Control-Allow-Origin': '*'},
                            'statusCode': 200, 'body': "App " + str(resp['Item']) + " was successfully deleted"}
                else:
                    return {'headers': {'Access-Control-Allow-Origin': '*'},
                            'statusCode': respdel['ResponseMetadata']['HTTPStatusCode'], 'body': json.dumps(respdel)}
            else:
                return {'headers': {'Access-Control-Allow-Origin': '*'},
                        'statusCode': 400, 'body': 'app Id: ' + str(event['pathParameters']['appid']) + ' does not exist'}
        else:
            return {'headers': {'Access-Control-Allow-Origin': '*'},
                    'statusCode': 401,
                    'body': json.dumps(authResponse)}
