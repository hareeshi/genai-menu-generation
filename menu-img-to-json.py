import json
import boto3
import os
from datetime import datetime
import logging
import re

# Configure logging
logger = logging.getLogger()
logger.setLevel(logging.INFO)

# Initialize AWS clients
s3_client = boto3.client('s3')
textract_client = boto3.client('textract')

def extract_price(text):
    """Extract price from text using regex."""
    # Match patterns like $10.99, 10.99, $10, etc.
    price_pattern = r'\$?\d+\.?\d*'
    match = re.search(price_pattern, text)
    return match.group(0) if match else None

def is_price(text):
    """Check if text contains a price."""
    return bool(re.search(r'\$?\d+\.?\d*', text))

def lambda_handler(event, context):
    """
    Lambda function to extract text from menu images using Amazon Textract
    and store the results in S3.
    """
    try:
        # Get the S3 bucket and key from the event
        bucket = event['Records'][0]['s3']['bucket']['name']
        key = event['Records'][0]['s3']['object']['key']
        dest_bucket = '<destination-bucket-name>'
        logger.info(f"Processing image: {key} from bucket: {bucket}")
        
        # Call Textract to analyze the image
        response = textract_client.detect_document_text(
            Document={
                'S3Object': {
                    'Bucket': bucket,
                    'Name': key
                }
            }
        )
        
        # Extract text blocks and organize them
        menu_items = []
        current_item = {}
        current_description = []
        
        for item in response['Blocks']:
            if item['BlockType'] == 'LINE':
                text = item['Text'].strip()
                print (text)
                # Skip empty lines
                if not text:
                    continue
                
                # Check if this line contains a price
                if is_price(text):
                    # If we have a current item, save it
                    if current_item:
                        if current_description:
                            current_item['description'] = ' '.join(current_description)
                        menu_items.append(current_item)
                    
                    # Start a new item
                    price = extract_price(text)
                    item_name = text.replace(price, '').strip()
                    current_item = {
                        'item': item_name,
                        'price': price
                    }
                    current_description = []
                else:
                    # This is likely a description or additional item information
                    if current_item:
                        current_description.append(text)
                    else:
                        # This might be a category or section header
                        menu_items.append({
                            'type': 'header',
                            'text': text
                        })
        
        # Add the last item if exists
        if current_item:
            if current_description:
                current_item['description'] = ' '.join(current_description)
            menu_items.append(current_item)
        
        # Create a structured output
        output = menu_items
        
        # Generate output filename
        output_key = f"extracted_text/{os.path.splitext(key)[0]}.json"
        
        # Save the extracted text to S3
        s3_client.put_object(
            Bucket=bucket,
            Key=output_key,
            Body=json.dumps(output, indent=2),
            ContentType='application/json'
        )
        
        logger.info(f"Successfully processed image and saved results to: {output_key}")
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'message': 'Menu text extraction completed successfully',
                'output_location': f"s3://{bucket}/{output_key}",
                'metadata': output['metadata']
            })
        }
        
    except Exception as e:
        logger.error(f"Error processing image: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({
                'error': str(e)
            })
        }