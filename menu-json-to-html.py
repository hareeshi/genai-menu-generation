import os
import json
import boto3
import base64
import random
import tempfile

# ENVIRONMENT VARIABLES
MENU_JSON_BUCKET = '<json-bucket-name>'
MENU_JSON_KEY = 'menu.json'
OUTPUT_BUCKET = '<output-bucket-name>'

# AWS clients
s3 = boto3.client('s3')
bedrock = boto3.client('bedrock-runtime')

NOVA_TEXT_MODEL = "us.amazon.nova-lite-v1:0"
NOVA_IMAGE_MODEL = "amazon.nova-canvas-v1:0"

def generate_description(item_name):
    prompt = f"Write a concise description for a menu item called '{item_name}'. This is to display in an online ordering webpage. Dont add the item_name again in the beginning of the description"
    messages = [
            {
                "role": "user",
                "content": [
                    {
                        "text": prompt
                    }
                ]
            }
    ]
    response = bedrock.converse(
        modelId=NOVA_TEXT_MODEL,
        messages=messages
    )
    print("\\n[Full Response]")
    print(json.dumps(response, indent=2))
    # Claude/Nova returns: {'content': {'text': ...}}
    return response["output"]["message"]["content"][0]["text"]


def generate_image(item_name):
    prompt = f"A studio-quality photo of {item_name}, restaurant menu style."
    seed = random.randint(0, 858993460)
    native_request = {
        "taskType": "TEXT_IMAGE",
        "textToImageParams": {"text": prompt},
        "imageGenerationConfig": {
            "seed": seed,
            "quality": "standard",
            "height": 512,
            "width": 512,
            "numberOfImages": 1
        }
    }
    response = bedrock.invoke_model(
        modelId=NOVA_IMAGE_MODEL,
        body=json.dumps(native_request)
    )
    model_response = json.loads(response["body"].read())
    base64_image = model_response["images"][0]
    # Save image to /tmp for Lambda
    filename = f"/tmp/{item_name.replace(' ', '_')}.png"
    with open(filename, "wb") as img_file:
        img_file.write(base64.b64decode(base64_image))
    return filename

def build_html(menu_items_with_assets):
    html = """
    <html>
    <head>
        <title>Our Menu</title>
        <meta name="viewport" content="width=device-width, initial-scale=1">
        <style>
            body {
                font-family: 'Segoe UI', Arial, sans-serif;
                background: #f9f9f9;
                margin: 0;
                padding: 0;
            }
            header {
                background: #22223b;
                color: #fff;
                padding: 32px 0 16px 0;
                text-align: center;
                letter-spacing: 2px;
                box-shadow: 0 2px 8px rgba(0,0,0,0.08);
            }
            h1 {
                margin: 0;
                font-size: 2.5rem;
                letter-spacing: 2px;
            }
            .menu-container {
                display: flex;
                flex-wrap: wrap;
                justify-content: center;
                gap: 32px;
                padding: 40px 10vw;
            }
            .menu-card {
                background: #fff;
                border-radius: 18px;
                box-shadow: 0 4px 16px rgba(34,34,59,0.10);
                width: 320px;
                margin-bottom: 24px;
                display: flex;
                flex-direction: column;
                align-items: center;
                transition: transform 0.15s, box-shadow 0.15s;
            }
            .menu-card:hover {
                transform: translateY(-4px) scale(1.02);
                box-shadow: 0 8px 24px rgba(34,34,59,0.16);
            }
            .menu-img {
                width: 100%;
                height: 220px;
                object-fit: cover;
                border-top-left-radius: 18px;
                border-top-right-radius: 18px;
            }
            .menu-content {
                padding: 18px 24px 24px 24px;
                width: 100%;
                box-sizing: border-box;
            }
            .menu-title {
                font-size: 1.3rem;
                font-weight: 600;
                color: #22223b;
                margin: 0 0 8px 0;
                letter-spacing: 1px;
            }
            .menu-price {
                font-size: 1.1rem;
                color: #4a4e69;
                font-weight: 500;
                margin-bottom: 10px;
            }
            .menu-desc {
                font-size: 1rem;
                color: #555;
                margin-bottom: 0;
            }
            @media (max-width: 700px) {
                .menu-container {
                    flex-direction: column;
                    align-items: center;
                    padding: 20px 2vw;
                }
                .menu-card {
                    width: 95vw;
                    max-width: 380px;
                }
            }
        </style>
    </head>
    <body>
        <header>
            <h1>Our Menu</h1>
        </header>
        <div class="menu-container">
    """
    for item in menu_items_with_assets:
        # Construct S3 public URL (adjust as needed)
        image_url = f"{https://{OUTPUT_BUCKET}.s3.amazonaws.com/item['image_s3_key']}"
        html += f"""
            <div class="menu-card">
                <img src="{image_url}" class="menu-img" alt="{item['item']}"/>
                <div class="menu-content">
                    <div class="menu-title">{item['item']}</div>
                    <div class="menu-price">{item['price']}</div>
                    <div class="menu-desc">{item['description']}</div>
                </div>
            </div>
        """
    html += """
        </div>
    </body>
    </html>
    """
    html_file = "/tmp/menu.html"
    with open(html_file, "w") as f:
        f.write(html)
    return html_file


def lambda_handler(event, context):
    # Step 1: Read menu JSON from S3
    response = s3.get_object(Bucket=MENU_JSON_BUCKET, Key=MENU_JSON_KEY)
    menu_items = json.loads(response['Body'].read().decode('utf-8'))

    menu_items_with_assets = []

    # Step 2: For each menu item, generate description and image
    for entry in menu_items:
        item_name = entry['item']
        price = entry['price']
        description = generate_description(item_name)
        image_path = generate_image(item_name)
        image_s3_key = f"images/{os.path.basename(image_path)}"
        # Upload image to S3
        s3.upload_file(image_path, OUTPUT_BUCKET, image_s3_key, ExtraArgs={'ContentType': 'image/png'})
        menu_items_with_assets.append({
            "item": item_name,
            "price": price,
            "description": description,
            "image_s3_key": image_s3_key
        })

    # Step 3: Build HTML
    html_file = build_html(menu_items_with_assets)
    s3.upload_file(html_file, OUTPUT_BUCKET, "menu.html", ExtraArgs={'ContentType': 'text/html'})

    return {
        "statusCode": 200,
        "body": json.dumps({
            "message": "Menu generated and uploaded.",
            "html_s3_key": "menu.html",
            "image_keys": [item['image_s3_key'] for item in menu_items_with_assets]
        })
    }
