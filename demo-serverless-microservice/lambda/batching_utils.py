import boto3
from botocore.exceptions import ClientError

MAX_RETRIES = 3
BATCH_SIZE = 25

def batch_get_items(table, keys):
    """
    Batch multiple get requests to DynamoDB
    """
    responses = []
    for i in range(0, len(keys), BATCH_SIZE):
        batch_keys = keys[i:i+BATCH_SIZE]
        retries = 0
        while retries < MAX_RETRIES:
            try:
                response = table.batch_get_item(RequestItems={table.name: {'Keys': batch_keys}})
                responses.extend(response['Responses'][table.name])
                break
            except ClientError as e:
                print(f"Error: {e.response['Error']['Message']}")
                retries += 1
    return responses

def batch_write_items(table, items, operation):
    """
    Batch multiple write requests (put or delete) to DynamoDB
    """
    responses = []
    for i in range(0, len(items), BATCH_SIZE):
        batch_items = items[i:i+BATCH_SIZE]
        request_items = {table.name: []}
        for item in batch_items:
            request_items[table.name].append({operation: item})
        retries = 0
        while retries < MAX_RETRIES:
            try:
                response = table.batch_write_item(RequestItems=request_items)
                responses.append(response)
                break
            except ClientError as e:
                print(f"Error: {e.response['Error']['Message']}")
                retries += 1
    return responses
