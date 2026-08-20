import urllib.request, json, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

url = 'https://site.api.espn.com/apis/site/v2/sports/soccer/teams/432' # Galatasaray
print(f"Querying: {url}")
try:
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    r = urllib.request.urlopen(req, timeout=5, context=ctx)
    data = json.loads(r.read())
    team = data.get('team', {})
    print("Galatasaray Default League Name:", team.get('defaultLeague', {}).get('name'))
    print("Galatasaray Default League Link:", team.get('defaultLeague', {}).get('links', [{}])[0].get('href'))
except Exception as ex:
    print("Error:", ex)
