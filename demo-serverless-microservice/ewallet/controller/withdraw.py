import json
import logging
import os
import boto3
import re

from ewallet.repository.dynamodb_wallet_repository import DynamoDbWalletRepository
from ewallet.repository.dynamodb_transaction_repository import DynamoDbTransactionRepository
from ewallet.repository.transaction_repository import TransactionRepository
from ewallet.repository.base_repository import BaseRepository
from ewallet.model.wallet import Wallet
from ewallet.model.transaction import Transaction

logger = logging.getLogger()
logger.setLevel(logging.INFO)

def get_wallet_repository(dynamodb_client, table_name) -> BaseRepository:
    return DynamoDbWalletRepository(dynamodb_client, table_name)

def get_transaction_repository(dynamodb_client, table_name) -> TransactionRepository:
    return DynamoDbTransactionRepository(dynamodb_client, table_name)

def find_wallet(dynamodb_client, wallet_table_name, id) -> Wallet:
    wallet_repository = get_wallet_repository(dynamodb_client, wallet_table_name)
    return wallet_repository.find(id)

def save_transaction(dynamodb_client, transaction_table_name, transaction) -> Transaction:
    transaction_repository = get_transaction_repository(dynamodb_client, transaction_table_name)
    return transaction_repository.save(transaction)


validation_rules = {
  "iban": {"required": True},
  "amount": {"required": True, 
             "type": float,
             "min": 0},
  "currency": {"required": True,
               "values": ["USD", "EUR"]}  
}

def validate_payload(payload):
  errors = []
  
  for field, rules in validation_rules.items():
    value = payload.get(field)
    
    if rules.get("required") and not value:
      errors.append(f"{field} is required")
      
    if "type" in rules:
      type_check = isinstance(value, rules["type"])  
      if not type_check:
        errors.append(f"{field} must be a {rules['type']}")
        
    if "min" in rules and type(value) == float:
      if value < rules["min"]:
        errors.append(f"{field} must be greater than {rules['min']}")  
        
    if "values" in rules and value not in rules["values"]:
      errors.append(f"{field} must be one of {rules['values']}")
      
  return errors



def send_withdrawal_order_to_sns(sns_topic, target_iban, currency, amount):
    """
    Sends a message to SNS to process withdrawal.
    :param sns_topic: The SNS topic to send the message to.
    :param target_iban: The IBAN of the recipient.
    :param currency: The ISO 4217 currency code.
    :param amount: The amount to withdraw.
    :return: The response from SNS.
    :rtype: dict
    """
    sns = boto3.client('sns')
    return sns.publish(
        TopicArn=sns_topic,
        Message=json.dumps({
            'target_iban': target_iban,
            'currency': currency,
            'amount': amount
        })
    )

def lambda_handler(event, context):
    try:
        logger.info('Event: {}'.format(event))
        logger.info('Context: {}'.format(context))

        wallet_table_name = os.getenv('WALLETS_TABLE')
        if (not wallet_table_name):
            raise Exception('Wallet table name missing') 
        
        wallet_table_name = os.getenv('TRANSACTIONS_TABLE')
        if (not wallet_table_name):
            raise Exception('Transactions table name missing') 
        
        withdrawal_sns_topic = os.getenv('WITHDRAWAL_SNS_TOPIC')
        if (not withdrawal_sns_topic):
            raise Exception('SNS topic missing') 

        # secret_key = os.getenv('AWS_SECRET_ACCESS_KEY')
        # logger.info(secret_key)

        try:
            payload = json.loads(event['body'])
        except Exception as error:
            return {
                'statusCode': 400,
                'body': json.dumps({'message': 'Bad Request'})
            }
        
        errors = validate_payload(payload)
        if (errors):
            return {
                'statusCode': 400,
                'body': json.dumps({'message': errors})
            }
        
        try:
            id = event['pathParameters']['id']
        except Exception as error:
            logger.info('Error: {}'.format(error))
            return {
                'statusCode': 400,
                'body': json.dumps({'message': 'Bad Request'})
            }
        
        dynamodb = boto3.client('dynamodb')

        wallet = find_wallet(dynamodb, wallet_table_name, id)
        if not Wallet:
            return {
                'statusCode': 404,
                'body': json.dumps({'message': 'Wallet not found'})
            }
        
        try:
            withdrawal_transaction = wallet.withdraw(payload['amount'], payload['currency'])
        except ValueError as error:
            return {
                'statusCode': 400,
                'body': json.dumps({'message': error})
            }
        
        save_transaction(dynamodb, wallet_table_name, withdrawal_transaction)

        send_withdrawal_order_to_sns(withdrawal_sns_topic, payload['iban'], payload['currency'], payload['amount'])

        response = {
            'statusCode': 200,

            'body': json.dumps(withdrawal_transaction.__dict__)
        }
        logger.info("Response: %s", response)

        return response

    except Exception as error: 
        logger.info('Error: {}'.format(error))
        return {
            'statusCode': 500,
            'body': {'message': error}
        }
