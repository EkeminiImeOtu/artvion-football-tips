import urllib.request, json, ssl

ctx = ssl.create_default_context()
ctx.check_hostname = False
ctx.verify_mode = ssl.CERT_NONE
API_KEY = "9cf573e2f18a33b78b4c5fd008771c86" # Let's see if we have access or if we get matches

# Let's check soccer matches scheduled for today (Aug 19, 2026) across any active soccer sports
print("=== Active Soccer Sports ===")
try:
    url = f'https://api.the-odds-api.com/v4/sports/?apiKey={API_KEY}'
    r = urllib.request.urlopen(url, timeout=10, context=ctx)
    sports = json.loads(r.read())
    active_soccer = [s['key'] for s in sports if s.get('active') and s['key'].startswith('soccer_')]
    print(f"Active Soccer Leagues count: {len(active_soccer)}")
    
    # Check if there are any matches scheduled for today (Aug 19, 2026)
    total_matches = 0
    for lg in active_soccer[:10]: # Check first 10 active leagues
        url2 = f'https://api.the-odds-api.com/v4/sports/{lg}/odds?apiKey={API_KEY}&regions=eu&markets=h2h&commenceTimeFrom=2026-08-19T00:00:00Z&commenceTimeTo=2026-08-19T23:59:59Z'
        try:
            r2 = urllib.request.urlopen(url2, timeout=5, context=ctx)
            matches = json.loads(r2.read())
            if matches:
                print(f"  {lg}: {len(matches)} matches found")
                total_matches += len(matches)
        except Exception as e:
            # If we get 401 OUT_OF_USAGE_CREDITS, print it
            if "401" in str(e):
                print(f"  {lg}: 401 Quota Limit reached")
                break
            else:
                print(f"  {lg}: {e}")
    print(f"Total matches found for today: {total_matches}")
except Exception as ex:
    print("Error:", ex)
