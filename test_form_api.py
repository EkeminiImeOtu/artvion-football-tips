import urllib.request, json, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE

print("=== Test 1: ESPN Teams API ===")
try:
    url = 'https://site.api.espn.com/apis/site/v2/sports/soccer/tur.1/teams'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    r = urllib.request.urlopen(req, timeout=10, context=ctx)
    
    # Check CORS headers
    print(f"Status: {r.status}")
    cors = r.headers.get('Access-Control-Allow-Origin', 'NOT SET')
    print(f"CORS Header (Access-Control-Allow-Origin): {cors}")
    
    d = json.loads(r.read())
    teams = d.get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', [])
    print(f"Teams found: {len(teams)}")
    if teams:
        print(f"First team: {teams[0]['team']['displayName']} (ID: {teams[0]['team']['id']})")
except Exception as ex:
    print(f"Error: {ex}")

print("\n=== Test 2: ESPN Schedule ===")
try:
    url = 'https://site.api.espn.com/apis/site/v2/sports/soccer/tur.1/teams/436/schedule?season=2025'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    r = urllib.request.urlopen(req, timeout=10, context=ctx)
    print(f"Status: {r.status}")
    cors = r.headers.get('Access-Control-Allow-Origin', 'NOT SET')
    print(f"CORS Header: {cors}")
    d = json.loads(r.read())
    events = d.get('events', [])
    print(f"Events: {len(events)}")
    completed = [e for e in events if 'FULL_TIME' in (e.get('competitions', [{}])[0].get('status', {}).get('type', {}).get('name', '') or '')]
    print(f"Completed: {len(completed)}")
except Exception as ex:
    print(f"Error: {ex}")

print("\n=== Test 3: CORS Proxy ===")
try:
    target = 'https://site.api.espn.com/apis/site/v2/sports/soccer/tur.1/teams'
    url = f'https://corsproxy.io/?{urllib.request.quote(target, safe="")}'
    req = urllib.request.Request(url)
    req.add_header('User-Agent', 'Mozilla/5.0')
    r = urllib.request.urlopen(req, timeout=10, context=ctx)
    print(f"Proxy Status: {r.status}")
    d = json.loads(r.read())
    teams = d.get('sports', [{}])[0].get('leagues', [{}])[0].get('teams', [])
    print(f"Teams via proxy: {len(teams)}")
except Exception as ex:
    print(f"Proxy Error: {ex}")
