from datetime import datetime, timedelta, timezone
from urllib.parse import quote


def convert_to_jst(unix_timestamp_ms):
    # タイムスタンプを秒単位に
    unix_timestamp = unix_timestamp_ms / 1000

    # 日本時間 (UTC+9) のdatetimeオブジェクトに変換
    jst_datetime = datetime.fromtimestamp(unix_timestamp, timezone(timedelta(hours=9)))

    # 指定されたフォーマットで日本時間を出力
    formatted_jst_datetime = jst_datetime.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + jst_datetime.strftime("%z")
    formatted_timezone = formatted_jst_datetime[-5:-2] + ':' + formatted_jst_datetime[-2:]
    formatted_jst_datetime = formatted_jst_datetime[:-5] + formatted_timezone
    return formatted_jst_datetime

def create_log_stream_url(log_group_name, log_stream_name, timestamp=None, width_ms=None):
    """
    AWS CloudWatch Logsの特定のログストリームのURLを生成します。

    Args:
        log_group_name (str): ロググループの名前。
        log_stream_name (str): ログストリームの名前。
        timestamp (int, optional): タイムスタンプ（ミリ秒単位）。Noneの場合、現在の時刻が使用されます。
        width_ms (int, optional): タイムスタンプを中心とした時間幅（ミリ秒単位）。Noneの場合、時間範囲はURLに含まれません。

    Returns:
        str: 生成されたURL。
    """
    # timestampがNoneの場合、現在のUTC時刻を使用
    if timestamp is None:
        utc_dt = datetime.utcnow()
    else:
        # UTCのdatetimeオブジェクトを取得
        utc_dt = datetime.utcfromtimestamp(timestamp/1000)

    # JSTに変換（UTC+9時間）
    jst_dt = utc_dt + timedelta(hours=9)

    # width_msが指定されている場合、開始と終了の時間を計算
    if width_ms is not None:
        start_dt = jst_dt - timedelta(milliseconds=width_ms)
        end_dt = jst_dt + timedelta(milliseconds=width_ms)
        # datetimeオブジェクトをミリ秒単位のタイムスタンプに変換
        start_timestamp = int(start_dt.timestamp() * 1000)
        end_timestamp = int(end_dt.timestamp() * 1000)
        time_query = f'$3Fend$3D{end_timestamp}$26filterPattern$3D$26start$3D{start_timestamp}'
    else:
        time_query = ''

    # URLを生成
    url = ''.join([
        "https://",
        'ap-northeast-1',
        ".console.aws.amazon.com/cloudwatch/home?region=",
        'ap-northeast-1',
        "#logsV2:log-groups/log-group/",
        quote(log_group_name, safe=''),
        '/log-events/',
        quote(log_stream_name, safe=''),
        time_query
    ])

    return url
