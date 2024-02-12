import logging
import base64
import json
import zlib
import os
import traceback
import re
import ast

from datetime import datetime, timedelta, timezone
from slack_sender import SlackInfo, SlackSender
from secrets_manager_accessor import SecretsManagerAccessor
from log_utils import convert_to_jst, create_log_stream_url

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

is_local = os.environ.get('IS_LOCAL') == 'True'
slack_sender = SlackSender(is_local)

def load_secret_keys():

    sm_accessor = SecretsManagerAccessor()
    # 同じSlack API (CMMレポーター)のBOTトークンなので使い回す。
    ret = sm_accessor.get_secret('cmm3-conversation-summary')

    return ret

def check_keys_in_awslogs_data(data):
    '''
        必須のキーを確認し、欠けているキーのリストを返却する

        event['awslogs']['data']を解凍したデータの構成
        {
            'messageType': 'DATA_MESSAGE',
            'owner': {{ ACCOUNT_ID }},
            'logGroup': '/aws/lambda/cmm-service-site-api',
            'logStream': '2023/05/04/[$LATEST]14aa2621196d4249b25285b86ce2f14f',
            'subscriptionFilters': ['error-log'],
            'logEvents': [
                {
                    'id': '37536922055805962068900291500381884339199803225701220358',
                    'timestamp': 1683213799433,
                    'message': '[ERROR]\t2023-05-06T01:55:50.034Z\td54e41d2-9ee3-43c4-9c55-af5a99365edc\tDynamoDB存在確認中に想定外のエラーが発生した。バケット名=cmm-subscribers-users'
                },,,
            ]
        }
        
        サブスクリプションフィルターにマッチした以外のログもlogEventsに含まれる事がある
            EC2内のログは、CloudWatch Agentを通じて定期的にCloudWatchへと送信される。
            これらのログは数ミリ秒ごとにまとめられ、一括でCloudWatchに送られる。
            その結果、CloudWatchには同じタイムスタンプを持つ複数のログが存在することになる。
            その複数のログが一つの塊としてlogEventsに格納され、Lambda関数に送られる。
    '''
    missing_keys = []  # 欠けているキーを追跡するリスト

    # 必要なトップレベルキーの存在を確認
    required_top_level_keys = ['messageType', 'owner', 'logGroup', 'logStream', 'subscriptionFilters', 'logEvents']
    for key in required_top_level_keys:
        if key not in data:
            missing_keys.append(f'data.{key}')

    # 'logEvents' 内の各エントリに必要なキーが存在するか確認
    if 'logEvents' in data:
        for i, log_event in enumerate(data['logEvents']):
            log_event_keys = ['id', 'timestamp', 'message']
            for key in log_event_keys:
                if key not in log_event:
                    missing_keys.append(f'data.logEvents[{i}].{key}')

    return missing_keys


def lambda_handler(event, context):
    logger.info(json.dumps(event, ensure_ascii=False, indent=2))
    logger.info(context)

    try:
        secrets = load_secret_keys()

        if 'awslogs' not in event or 'data' not in event['awslogs']:
            raise f'awslogsフォーマット不正 event.awslogs.dataは必須です'
            
        data = zlib.decompress(base64.b64decode(event['awslogs']['data']), 16+zlib.MAX_WBITS)
        data_json = json.loads(data)
        logger.info(f'data_json: {data_json}')
        
        missing_keys = check_keys_in_awslogs_data(data_json)
        if len(missing_keys) > 0:
            raise f'awslogsフォーマット不正 不足しているKey: {missing_keys}'

        log_events = data_json.get("logEvents")
        if len(log_events) < 1:
            raise 'log_eventsがありません。'

        # timestampはdataのトップレベルにはなくlog_events配列内にあり、かつ、配列内のtimestampは全部同じなので1つ目から取得する
        timestamp = log_events[0].get('timestamp')

        # 通知用スレッドを立てる。対象のURLだけ入れて詳細は後からスレッドにぶら下げる
        slack_sender = SlackSender(is_local)
        # CloudWatchで設定しているサブスクリプションフィルタ名（配列だけど基本要素は１つ。どんなときに複数個になるのか不明）
        slack_info = SlackInfo(text=', '.join(data_json.get('subscriptionFilters')))
        # 該当のログストリームページのURLを生成。その際、該当ログのtimestampの前後10秒でフィルター
        log_stream_url = create_log_stream_url(data_json.get('logGroup'), data_json.get('logStream'), timestamp, 10000)

        # スレッドのルートメッセージには、タイムスタンプを除いた最初のログの内容を80文字で表示し、エラーの内容を一目で確認できるようにする。（読みにくいのでANSIエスケープコードも削除）
        description = re.sub(r'\x1b\[\d+m', '', log_events[0]['message'])[26:106]
        slack_info.add_info(title='LogStream URL', value=log_stream_url, type='button', description=description)
        sender_res = slack_sender.send(
            token=secrets['SLACK_TOKEN'],
            channel=os.environ.get('CANNEL_ID'),
            info=slack_info
        )

        # ログメッセージを1件ずつスレッドにぶら下げる。
        log_messages = []
        for index, log_event in enumerate(log_events):

            # 前回のslack送信結果をチェックする
            logger.info(f'message {index}, status: {sender_res.status}, headers: {sender_res.headers}')
            byte_str = sender_res.read()
            res_str = byte_str.decode('utf-8')
            logger.info(res_str)
            res_json = json.loads(res_str)
            if res_json['ok'] == False:
                try:
                    slack_info = SlackInfo(text='slack通知に失敗しました')
                    slack_info.add_info(title='メッセージ', value='詳細はCloudWatchログを確認してください。')
                    slack_info.add_info(title='発生時間', value=convert_to_jst(timestamp))
                    sender_res = slack_sender.send(
                        token=secrets['SLACK_TOKEN'],
                        channel=os.environ.get('CANNEL_ID'),
                        info=slack_info
                    )
                except Exception as e:
                    logger.error(f'Slack通知失敗の通知に失敗しました: {e}')
                    return

            if 'message' not in res_json or  'ts' not in res_json['message']:
                raise 'Slack APIからのレスポンスが異常です。message.tsは必須です。'

            '''
            前回SlackAPI結果のチェック完了。次のログメッセージをスレッドにぶら下げる形で送信する。
            '''
            
            logger.info(f'log_event: {index} {log_event}')
            # 読みにくいのでANSIエスケープコードを削除
            message = re.sub(r'\x1b\[\d+m', '', log_event['message'])

            # Slack APIの文字数上限がある
            if len(message) > 1000:
                message = message[:1000] + '...'

            if index == 0:
                slack_info.add_info(title='ロググループ名', value=data_json.get('logGroup'))
                slack_info.add_info(title='ログストリーム名', value=data_json.get('logStream'))

            slack_info.add_info(title=f'ログメッセージ {index + 1}', value=message)

            sender_res = slack_sender.send(
                token=secrets['SLACK_TOKEN'],
                channel=os.environ.get('CANNEL_ID'),
                info=slack_info,
                # ぶら下げたいスレッドのthread_tsを指定する
                thread_ts=res_json['message']['ts']
            )

    except Exception as e:
        logger.info(f'error: {e}')
        logger.info(traceback.format_exc())
