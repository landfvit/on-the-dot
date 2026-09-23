import os
import requests
from dotenv import load_dotenv

load_dotenv()

API_key = os.getenv("API_FOOTBALL_KEY")
url = "https://v3.football.api-sports.io/leagues"

headers = {
    "x-apisports-key": API_key
}

params = {
    "id": 39
} #PL id

response = requests.get(
    url,
    headers=headers,
    params=params
)

data = response.json()

league = data["response"][0]["league"]
country = data["response"][0]["country"]

print(f"League ID: {league["id"]}")
print(f"League: {league["name"]}")
print(f"Country: {country["name"]}")
print(
    "Remaining: ",
    response.headers.get("x-ratelimit-requests-remaining")
) 