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

from __future__ import print_function
import sys
import UpdateBlueprint
import CheckMachine
import LaunchMachine
import requests
import json
import boto3
import os
from boto3.dynamodb.conditions import Key, Attr

application = os.environ['application']
environment = os.environ['environment']

servers_table_name = '{}-{}-servers'.format(application, environment)
apps_table_name = '{}-{}-apps'.format(application, environment)

servers_table = boto3.resource('dynamodb').Table(servers_table_name)
apps_table = boto3.resource('dynamodb').Table(apps_table_name)

def execute(launchtype, session, headers, endpoint, HOST, projectname, dryrun, waveid, relaunch):

    r = requests.get(HOST + endpoint.format('projects'), headers=headers, cookies=session)
    if r.status_code != 200:
        return "ERROR: Failed to fetch the project...."
    try:
        # Get Project ID
        projects = json.loads(r.text)["items"]
        project_exist = False
        for project in projects:
            if project["name"] == projectname:
               project_id = project["id"]
               project_exist = True
        if project_exist == False:
            return "ERROR: Project Name does not exist in CloudEndure...."
        
        # Get Machine List from CloudEndure
        m = requests.get(HOST + endpoint.format('projects/{}/machines').format(project_id), headers=headers, cookies=session)
        if "sourceProperties" not in m.text:
            return "ERROR: Failed to fetch the machines...."
        machinelist = {}
        print("**************************")
        print("*CloudEndure Machine List*")
        print("**************************")
        for machine in json.loads(m.text)["items"]:
            print('Machine name:{}, Machine ID:{}'.format(machine['sourceProperties']['name'], machine['id']))
            machinelist[machine['id']] = machine['sourceProperties']['name']
        print("")
       
       # Get all Apps and servers from migration factory

        getserver = servers_table.scan()['Items']
        servers = sorted(getserver, key = lambda i: i['server_name'])

        getapp = apps_table.scan()['Items']
        apps = sorted(getapp, key = lambda i: i['app_name'])

        # Get App list
        applist = []
        for app in apps:
            if 'wave_id' in app and 'cloudendure_projectname' in app:
                if str(app['wave_id']) == str(waveid) and str(app['cloudendure_projectname']) == str(projectname):
                    applist.append(app['app_id'])
        # Get Server List
        serverlist = []
        for app in applist:
            for server in servers:
                if "app_id" in server:
                    if app == server['app_id']:
                        serverlist.append(server)
        if len(serverlist) == 0:
            return "ERROR: Serverlist for wave " + waveid + " in Migration Factory is empty...."

        
        # Check Target Machines
        print("****************************")
        print("* Checking Target machines *")
        print("****************************")
        r = CheckMachine.status(session, headers, endpoint, HOST, project_id, launchtype, dryrun, serverlist, relaunch)
        if r is not None and "ERROR" in r:
            return r
        
        # Update Machine Blueprint
        print("**********************")
        print("* Updating Blueprint *")
        print("**********************")
    
        r = UpdateBlueprint.update(launchtype, session, headers, endpoint, HOST, project_id, machinelist, dryrun, serverlist)
        print(r)
        if r is not None and "ERROR" in r:
           return r
        if r is not None and "successful" in r:
           return r
        # Launch Target machines
        if dryrun.lower() != "yes":
           print("*****************************")
           print("* Launching target machines *")
           print("*****************************")
           r = LaunchMachine.launch(launchtype, session, headers, endpoint, HOST, project_id, serverlist)
           return r
    except:
        print(sys.exc_info())