import json

import boto3
from botocore.exceptions import ClientError


class SecretsManagerAccessor():

    def __init__(self, profile_name=None) -> None:
        session = boto3.Session(profile_name=profile_name)
        self.client = session.client(
            service_name='secretsmanager'
        )

    def get_secret(self, secret_name, jsonize=True):

        try:
            get_secret_value_response = self.client.get_secret_value(
                SecretId=secret_name
            )
        except ClientError as e:
            raise e
        secret = get_secret_value_response['SecretString']

        if jsonize:
            return json.loads(secret)
        else:
            return secret




