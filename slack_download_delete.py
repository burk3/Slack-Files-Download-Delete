import json
import os
import re
import time
from argparse import ArgumentParser
from sys import exit

import requests


class DownloadDeleteTask(object):
    def __init__(self, token, debug=False):
        self.token: str = token
        self.debug: bool = debug
        self._user_db = None
        self._channel_db = None

    @property
    def channel_db(self):
        if self._channel_db:
            return self._channel_db

        params = {
            'token': self.token
        }
        uri = 'https://slack.com/api/channels.list'
        response = requests.get(uri, params=params)
        channel_list = json.loads(response.text)['channels']
        with open('metadata_channels.json', 'wb') as f:
                f.write(response.text)
        db = {}
        for c in channel_list:
            db[c['id']] = c['name']
        self._channel_db = db
        return db

    @property
    def user_db(self):
        if self._user_db:
            return self._user_db

        params = {
            'token': self.token
        }
        uri = 'https://slack.com/api/users.list'
        response = requests.get(uri, params=params)
        users_list = json.loads(response.text)['members']
        with open('metadata_users.json', 'wb') as f:
                f.write(response.text)
        db = {}
        for u in users_list:
            db[u['id']] = u['name']
        self._user_db = db
        return db

    @staticmethod
    def reverse_db_lookup(db, check):
        for key in db:
            if db[key] == check:
                return key

    def list_files(self, minimum_age, restrict_user_name=None, restrict_channel_name=None):
        ts_to = int(time.time()) - minimum_age * 24 * 60 * 60
        params = {
            "token": self.token,
            "ts_to": ts_to,
            "count": 1000,
            "page": 1,
        }
        if restrict_channel_name:
            params["channel"] = self.reverse_db_lookup(self.channel_db, restrict_channel_name)
        if restrict_user_name:
            params["user"] = self.reverse_db_lookup(self.user_db, restrict_user_name)
        if self.debug:
            print("files.list params:", params),

        uri = "https://slack.com/api/files.list",
        response = requests.get(uri, params=params)
        ret = json.loads(response.text)["files"]
        page_info = json.loads(response.text)["paging"]
        if self.debug:
            print(page_info)
        while params["page"] < page_info["pages"]:
            params['page'] += 1
            print('Loading page', params['page'], 'of', page_info['pages'])
            response = requests.get(uri, params=params)
            ret += json.loads(response.text)['files']
        return ret

    def process_files(self, files, download: str=None, delete=False):
        count = 0
        num_files = len(files)
        with open(os.path.join('metadata_files.json'), 'w') as f:
            f.write(json.dumps(files))

        for file in files:
            count += 1

            header = {
                'Authorization': ('Bearer ' + self.token)
            }

            if 'url_private_download' in file:
                print(count, "/", num_files, "-", self.user_db[file['user']], '-', file['title'])
                print(file['url_private_download'])
                skip_delete = True
                if download:
                    r = requests.get(file['url_private_download'], headers=header, stream=True)
                    if r.status_code == 200:
                        filename = "{}_{}_{}_{}".format(
                            self.user_db[file["user"]],
                            str(file["created"]),
                            file["id"],
                            file["name"],
                        )
                        filename = re.sub(r"[^\w\-_. ']", "_", filename)  # TODO: this looks jank.
                        with open(os.path.join(download, filename), 'wb') as f:
                            for chunk in r:
                                f.write(chunk)
                        print('Successfully Downloaded', filename)
                        skip_delete = False
                    else:
                        print('Download Failed!')
                        skip_delete = True
                if delete:
                    if download and skip_delete:
                        print('Skipping Delete')
                        continue
                    params = {
                        'token': self.token,
                        'file': file['id'],
                    }
                    delete_uri = 'https://slack.com/api/files.delete'
                    response = requests.get(delete_uri, params=params)
                    if not json.loads(response.text)['ok']:
                        print('Error deleting file:', file['id'], json.loads(response.text)['error'])
                    else:
                        print(count, "/", num_files, " deleted -", file['id'])


def main():
    parser = ArgumentParser(
        description=("A slack file downloader/deleter for you poor folks out there without thicc wads of VC money to "
                     "drop on a slack sub."),
        epilog="You need to set the env var SFDD_SLACK_TOKEN to a legacy token you generate.",
    )

    parser.add_argument("--download", "-d", type=str, default=".",
                        help="download files to the specified directory.")
    parser.add_argument("--delete", "-x", action="store_true",
                        help="Delete files too. From the server. To save space.")
    parser.add_argument("--min-age", "-m", type=int, default="5",
                        help="Number of days in the past to operate on.")
    parser.add_argument("--user", "-u", type=str,
                        help="Specify a username (not nick). Only operate on their files.")
    parser.add_argument("--chan", "-c", type=str,
                        help="Specify a channel name. Only operate on it's files.")
    parser.add_argument("--debug", "-D", action="store_true",
                        help="Debug mode (print a bunch of shit idk).")

    args = parser.parse_args()
    token = os.environ.get("SFDD_SLACK_TOKEN")

    if args.download:
        if not os.path.exists(args.download):
            print('Download directory does not exist.')
            exit(1)

    task = DownloadDeleteTask(token, debug=args.debug)
    files = task.list_files(minimum_age=args.min_age, restrict_user_name=args.user, restrict_channel_name=args.chan)
    task.process_files(files, download=args.download, delete=args.delete)


if __name__ == "__main__":
    main()
