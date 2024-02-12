import boto3
import json
import urllib.request

class SlackInfo():
    def __init__(self, text:str):
        self.info = {
            "blocks": [
                {
        			"type": "section",
        			"text": {
        				"type": "plain_text",
        				"text": text
        			}
                }
            ]
        }

    def add_info(self, title : str, value: str, type='text', description="|"):
        if title is None or value is None or title == '' or value == '':
            return
        
        if type == 'text':
            self.info["blocks"].append({
    			"type": "rich_text",
    			"elements": [
    				{
    					"type": "rich_text_section",
    					"elements": [
    						{
    							"type": "text",
    							"text": f'{title} : \n',
    							"style": {
    								"bold": True
    							}
    						},
    						{
    							"type": "text",
    							"text": value
    						}
    					]
    				}
    			]
            })
        elif type == 'button':
            self.info["blocks"].append({
    			"type": "section",
    			"text": {
    				"type": "mrkdwn",
    				"text": description
    			},
    			"accessory": {
    				"type": "button",
    				"text": {
					    "type": "plain_text",
    					"text": title
    				},
    				"url": value
    			}
            })

    def to_blocks(self):
        blocks = self.info['blocks']
        return blocks
    
    def reset(self):
        self.info = {
            'blocks': []
        }

class SlackSender():

    def __init__(self, is_local: bool) -> None:

        if is_local:
            self._send = send_mock
        else:
            self._send = urllib.request.Request

    def send(self, token: str, channel: str, info: SlackInfo, thread_ts=None):
        json_data = self.__create_slack_args(channel, info, thread_ts)
        print('json_data: ', json_data)

        url = 'https://slack.com/api/chat.postMessage'
        headers = {
            'Authorization': 'Bearer ' + token,
            'Content-Type': 'application/json; charset=utf-8'
        }
        method = 'POST'
        req = self._send(
            url=url, data=json_data, headers=headers, method=method)
        res = urllib.request.urlopen(req, timeout=5)
        
        info.reset()

        return res

    def __create_slack_args(self, channel: str, info: SlackInfo, thread_ts=None):

        blocks = info.to_blocks()

        data = {
            'channel': channel,
            'blocks': blocks,
        }
        
        # thread_tsがある場合はdataに追加する(tsが一致するスレッドにぶら下げる)
        if (thread_ts):
            data['thread_ts'] = thread_ts
        json_data = json.dumps(data).encode('utf-8')

        return json_data


def send_mock(url, data, headers, method):
    print('url: ', url)
    print('data: ', data)
    print('headers: ', headers)
    print('method: ', method)
