import json
import random

with open('predictions.json', encoding='utf-8') as f:
    data = json.load(f)

all_urls = list(data.keys())
print(random.choice(all_urls))