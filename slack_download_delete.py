import requests
import time
import json
import os
import re
from sys import exit

# Slack legacy API token https://api.slack.com/custom-integrations/legacy-tokens
token = 'xoxp-11111111111-11111111111-111111111111-x1x1x1x1x1x1x1x1x1x1x1x1x1x1x1x1'
# Don't touch files older than this
minimum_age = 5

# Optionally restrict to a source channel
restrict_channel_name = 'general'
# Optionally restrict to a source user
restrict_user_name = None

# Download files
download = True
directory = 'downloads'

# Delete file after successful export
delete = False


DEBUG = False

# Delete files older than this:
ts_to = int(time.time()) - minimum_age * 24 * 60 * 60

restrict_channel_id = None
restrict_user_id = None


def get_channel_ids():
    params = {
        'token': token
    }
    uri = 'https://slack.com/api/channels.list'
    response = requests.get(uri, params=params)
    channel_list = json.loads(response.text)['channels']
    with open('metadata_channels.json', 'wb') as f:
            f.write(response.text)
    db = {}
    for c in channel_list:
        db[c['id']] = c['name']
    return db


def get_user_ids():
    params = {
        'token': token
    }
    uri = 'https://slack.com/api/users.list'
    response = requests.get(uri, params=params)
    users_list = json.loads(response.text)['members']
    with open('metadata_users.json', 'wb') as f:
            f.write(response.text)
    db = {}
    for u in users_list:
        db[u['id']] = u['name']
    return db


def reverse_db_lookup(db, check):
    for key in db:
        if db[key] == check:
            return key


def list_files():
    params = {
        'token': token
        , 'ts_to': ts_to
        , 'count': 1000
        , 'page': 1
    }
    if restrict_channel_id:
        params['channel'] = restrict_channel_id
    if restrict_user_id:
        params['user'] = restrict_user_id
    if DEBUG:
        print 'files.list params:', params

    uri = 'https://slack.com/api/files.list'
    response = requests.get(uri, params=params)
    ret = json.loads(response.text)['files']
    pginfo = json.loads(response.text)['paging']
    if DEBUG:
        print pginfo
    while params['page'] < pginfo['pages']:
        params['page'] += 1
        print 'Loading page', params['page'], 'of', pginfo['pages']
        response = requests.get(uri, params=params)
        ret += json.loads(response.text)['files']
    return ret


def process_files(files):
    count = 0
    num_files = len(files)
    with open(os.path.join('metadata_files.json'), 'w') as f:
        f.write(json.dumps(files))

    for file in files:
        count += 1

        header = {
            'Authorization': ('Bearer ' + token)
        }

        if 'url_private_download' in file:
            print count, "/", num_files, "-", userdb[file['user']], '-', file['title']
            print file['url_private_download']
            skip_delete = True
            if download:
                r = requests.get(file['url_private_download'], headers=header, stream=True)
                if r.status_code == 200:
                    filename = userdb[file['user']] + '_' + str(file['created']) + '_' + file['id'] + '_' + file['name']
                    filename = re.sub('[^\w\-_\. \']', '_', filename)
                    with open(os.path.join(directory, filename), 'wb') as f:
                        for chunk in r:
                            f.write(chunk)
                    print 'Successfully Downloaded', filename
                    skip_delete = False
                else:
                    print 'Download Failed!'
                    skip_delete = True
            if delete:
                if download and skip_delete:
                    print 'Skipping Delete'
                    continue
                params = {
                    'token': token
                    , 'file': file['id']
                }
                delete_uri = 'https://slack.com/api/files.delete'
                response = requests.get(delete_uri, params=params)
                if not json.loads(response.text)['ok']:
                    print 'Error deleting file:', file['id'], json.loads(response.text)['error']
                else:
                    print count, "/", num_files, " deleted -", file['id']

channeldb = get_channel_ids()
userdb = get_user_ids()
if DEBUG:
    print 'Channels:', channeldb
    print 'Users:', userdb

if restrict_user_name:
    restrict_user_id = reverse_db_lookup(userdb, restrict_user_name)
    if restrict_user_id:
        print 'Restricting results to user:', restrict_user_name
    else:
        print 'Unable to find User:', restrict_user_name
        exit(1)

if restrict_channel_name:
    restrict_channel_id = reverse_db_lookup(channeldb, restrict_channel_name)
    if restrict_channel_id:
        print 'Restricting results to channel:', restrict_channel_name
    else:
        print 'Unable to find channel:', restrict_channel_name
        exit(1)

if download:
    if not os.path.exists(directory):
        print 'Download directory does not exists, creating', directory
        os.makedirs(directory)

files = list_files()
process_files(files)
