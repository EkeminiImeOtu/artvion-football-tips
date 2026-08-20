import urllib.request
import json
import time

API_KEY = "9cf573e2f18a33b78b4c5fd008771c86"
LEAGUES = [
  'soccer_epl', 'soccer_england_championship', 'soccer_spain_la_liga',
  'soccer_italy_serie_a', 'soccer_france_ligue_one', 'soccer_germany_bundesliga',
  'soccer_netherlands_eredivisie', 'soccer_portugal_primeira_liga',
  'soccer_turkey_super_league', 'soccer_scotland_premiership',
  'soccer_belgium_first_div', 'soccer_brazil_campeonato',
  'soccer_argentina_primera_division', 'soccer_poland_ekstraklasa',
  'soccer_austria_bundesliga', 'soccer_greece_super_league',
  'soccer_denmark_superliga', 'soccer_norway_eliteserien',
  'soccer_sweden_allsvenskan', 'soccer_chile_campeonato',
  'soccer_colombia_primera_a', 'soccer_mexico_ligamx',
  'soccer_usa_mls', 'soccer_uefa_champs_league',
  'soccer_uefa_europa_league', 'soccer_south_africa_premier_division'
]

results = []
print("Starting scan for Aug 15 and Aug 16...")

for date_str in ["2026-08-15", "2026-08-16"]:
    from_time = f"{date_str}T00:00:00Z"
    to_time = f"{date_str}T23:59:59Z"
    
    for league in LEAGUES:
        url = f"https://api.the-odds-api.com/v4/sports/{league}/odds/?apiKey={API_KEY}&regions=eu&markets=h2h&dateFormat=iso&oddsFormat=decimal&commenceTimeFrom={from_time}&commenceTimeTo={to_time}"
        try:
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req) as response:
                data = json.loads(response.read().decode())
                
                for match in data:
                    h2h = None
                    for bm in match.get('bookmakers', []):
                        for mkt in bm.get('markets', []):
                            if mkt['key'] == 'h2h':
                                h2h = mkt
                                break
                        if h2h: break
                    
                    if not h2h: continue
                    
                    oc = {o['name']: o['price'] for o in h2h.get('outcomes', [])}
                    ho = oc.get(match['home_team'])
                    ao = oc.get(match['away_team'])
                    
                    if not ho or not ao: continue
                    
                    fav_odds, und_odds = (ho, ao) if ho <= ao else (ao, ho)
                    fav_team, und_team = (match['home_team'], match['away_team']) if ho <= ao else (match['away_team'], match['home_team'])
                    
                    if fav_odds <= 1.35 and und_odds >= 5.00:
                        results.append({
                            'date': date_str,
                            'league': league,
                            'fav': fav_team,
                            'und': und_team,
                            'fav_odds': fav_odds,
                            'und_odds': und_odds,
                            'start': match['commence_time']
                        })
                        print(f"Found: {fav_team} vs {und_team} ({fav_odds} / {und_odds})")
        except urllib.error.HTTPError as e:
            if e.code != 422: # 422 means no odds for that sport right now
                print(f"Error {e.code} for {league}")
        except Exception as e:
            print(f"Error for {league}: {e}")
        time.sleep(0.2)

with open("C:/Users/user/Documents/Zoom/sportybet-agent/live_results.json", "w", encoding="utf-8") as f:
    json.dump(results, f, indent=2)

print(f"Scan complete. Found {len(results)} matches.")
