import requests
import json

url = "https://v3.football.api-sports.io/timezone"
headers = {
    'x-apisports-key': "515dac49287f85774d532f095815e90c"
}
response = requests.request("GET", url, headers=headers)
print("api-sports response:", response.status_code)
print(response.text[:200])

url_rapid = "https://api-football-v1.p.rapidapi.com/v3/timezone"
headers_rapid = {
    'x-rapidapi-host': "api-football-v1.p.rapidapi.com",
    'x-rapidapi-key': "515dac49287f85774d532f095815e90c"
}
response_rapid = requests.request("GET", url_rapid, headers=headers_rapid)
print("rapidapi response:", response_rapid.status_code)
print(response_rapid.text[:200])
