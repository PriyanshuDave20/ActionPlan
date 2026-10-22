import boto3
import json

lambda_client = boto3.client('lambda', region_name='us-east-2')

# Proper API Gateway HTTP API event format
payload = {
    'version': '2.0',
    'routeKey': 'POST /goals',
    'rawPath': '/goals',
    'rawQueryString': '',
    'headers': {'content-type': 'application/json'},
    'requestContext': {
        'accountId': '123456789012',
        'apiId': 'testapi',
        'domainName': 'testapi.execute-api.us-east-2.amazonaws.com',
        'domainPrefix': 'testapi',
        'http': {
            'method': 'POST',
            'path': '/goals',
            'protocol': 'HTTP/1.1',
            'sourceIp': '203.0.113.1',
            'userAgent': 'curl'
        },
        'requestId': 'test-request',
        'routeKey': 'POST /goals',
        'stage': '$default',
        'time': '15/Sep/2026:00:00:00 +0000',
        'timeEpoch': 0,
    },
    'body': json.dumps({'goal': 'test project', 'people_involved': [{'name': 'Ada', 'role': 'lead'}], 'priority': 'high', 'success_criteria': ['test']}),
    'isBase64Encoded': False
}

response = lambda_client.invoke(FunctionName='ActionPlan', Payload=json.dumps(payload))
print('StatusCode:', response['StatusCode'])
result = json.loads(response['Payload'].read())
print(json.dumps(result, indent=2))