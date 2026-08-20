import os
import re

file_path = r"D:\Zoom\sportybet-agent\index.html"
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# 1. Checkbox
content = content.replace(
'''        <div class="control-group">
          <label>Min Odds Filter</label>
          <input type="number" id="min-odds" value="1.20" step="0.01" min="1.01">
        </div>''',
'''        <div class="control-group">
          <label>Min Odds Filter</label>
          <input type="number" id="min-odds" value="1.20" step="0.01" min="1.01">
        </div>
        <div class="control-group">
          <label>Options</label>
          <label class="checkbox-label"><input type="checkbox" id="m-hide-empty" checked> Hide matches with no recommendations</label>
        </div>'''
)

# 2. CSS classes
css_add = '''
    .match-card.rejected {
      opacity: 0.65;
      border: 1px dashed var(--border);
    }
    .rejections-details {
      display: none;
      margin-top: 1rem;
      background: rgba(255, 82, 82, 0.05);
      border-radius: 8px;
      padding: 1rem;
      font-size: 0.85rem;
      border: 1px solid rgba(255, 82, 82, 0.3);
    }
    .rejections-details.open {
      display: block;
    }
    .rejections-details ul {
      list-style-type: none;
      display: flex;
      flex-direction: column;
      gap: 0.5rem;
    }
    .rejections-details li {
      position: relative;
      padding-left: 1.2rem;
      color: #ff8a80;
    }
    .rejections-details li::before {
      content: '•';
      position: absolute;
      left: 0;
      color: var(--red);
    }
'''
content = content.replace("    /* Matches Container */", css_add + "\n    /* Matches Container */")

# 3. LEAGUES to let
content = content.replace("const LEAGUES = [", "let LEAGUES = [")

# 4. getEspnSlug function
espn_slug_code = '''
const getEspnSlug = (oddsKey) => {
  if (ESPN_SLUGS[oddsKey]) return ESPN_SLUGS[oddsKey];
  if (oddsKey === 'soccer_club_friendlies') return 'club.friendly';
  if (oddsKey === 'soccer_international_friendlies') return 'intl.friendly';
  if (oddsKey === 'soccer_uefa_champs_league_qualification') return 'uefa.champions';
  if (oddsKey === 'soccer_uefa_europa_league_qualification') return 'uefa.europa';
  if (oddsKey === 'soccer_uefa_europa_conference_league_qualification') return 'uefa.europa.conf';
  if (oddsKey === 'soccer_conmebol_copa_libertadores') return 'conmebol.libertadores';
  return null;
};
'''
content = content.replace("const CACHE = {", espn_slug_code + "\nconst CACHE = {")

# 5. mainScan API discovery
main_scan_old = '''const mainScan = async () => {
  const apiKey = qs('#api-key').value.trim();
  if (!apiKey) { alert("Please enter your The Odds API key"); return; }
  
  const startD = qs('#start-date').value;'''

main_scan_new = '''const mainScan = async () => {
  const apiKey = qs('#api-key').value.trim();
  if (!apiKey) { alert("Please enter your The Odds API key"); return; }
  
  try {
    const sportsRes = await fetch(`https://api.the-odds-api.com/v4/sports/?apiKey=${apiKey}`);
    if (!sportsRes.ok) throw new Error("Failed to fetch active sports");
    const sportsData = await sportsRes.json();
    const dynamicLeagues = sportsData.filter(s => s.key.startsWith('soccer_') && s.active);
    if (dynamicLeagues.length > 0) {
      LEAGUES = dynamicLeagues.map(s => ({ key: s.key, name: s.title, flag: '⚽' }));
    }
  } catch(e) {
    alert("Odds API Error: Failed to fetch active sports. Check your API key.");
    return;
  }
  
  const startD = qs('#start-date').value;'''
content = content.replace(main_scan_old, main_scan_new)

content = content.replace("let espnSlug = ESPN_SLUGS[lg.key];", "let espnSlug = getEspnSlug(lg.key);")

# Update analyzeMatch invocation in mainScan
analyze_call_old = '''        const picks = analyzeMatch(match, homeForm, awayForm, filters);
        
        if (picks.length > 0) {
          stats.picks += picks.length;
          stats.high += picks.filter(p => p.conf === 'high').length;
          updateStats(null, null, null, stats.picks, stats.high);
          
          let mObj = { raw: match, homeForm, awayForm, picks };
          
          // Result verification
          await resolveMatchResult(mObj, espnSlug, homeEspnId, awayEspnId);
          
          globalMatches.push(mObj);
        }'''

analyze_call_new = '''        const { picks, rejections } = analyzeMatch(match, homeForm, awayForm, filters);
        
        stats.picks += picks.length;
        stats.high += picks.filter(p => p.conf === 'high').length;
        updateStats(null, null, null, stats.picks, stats.high);
        
        let mObj = { raw: match, homeForm, awayForm, picks, rejections };
        await resolveMatchResult(mObj, espnSlug, homeEspnId, awayEspnId);
        globalMatches.push(mObj);'''

content = content.replace(analyze_call_old, analyze_call_new)

# 7. Change renderMatches
render_picks_old = '''    const filteredPicks = m.picks.filter(p => currentBetTypeFilter === 'all' || p.betType === currentBetTypeFilter);
    if (filteredPicks.length === 0) return;'''
render_picks_new = '''    const filteredPicks = m.picks.filter(p => currentBetTypeFilter === 'all' || p.betType === currentBetTypeFilter);
    
    if (filteredPicks.length === 0) {
      const hideEmpty = document.getElementById('m-hide-empty')?.checked;
      if (hideEmpty) return;
    }'''
content = content.replace(render_picks_old, render_picks_new)

card_gen_old = '''      <div class="match-card ${hasHigh ? 'has-high' : ''}">'''
card_gen_new = '''      <div class="match-card ${hasHigh ? 'has-high' : ''} ${filteredPicks.length === 0 ? 'rejected' : ''}">'''
content = content.replace(card_gen_old, card_gen_new)

picks_title_old = '''<div class="picks-title">AI Recommendations (${m.picks.length})</div>'''
picks_title_new = '''<div class="picks-title">AI Recommendations (${filteredPicks.length})</div>
            ${filteredPicks.length === 0 ? '<span style="background:var(--muted);color:#fff;padding:2px 6px;border-radius:4px;margin-left:6px;font-size:0.7rem;">⚠️ No Picks Met Safety Thresholds</span>' : ''}
            ${m.rejections && m.rejections.length > 0 ? `
              <div style="margin-top: 1rem;">
                <button class="analysis-toggle" onclick="document.getElementById('rejections-${idx}').classList.toggle('open')">📋 View Scan Rejections (${m.rejections.length})</button>
                <div class="rejections-details" id="rejections-${idx}">
                  <ul>${m.rejections.map(r => `<li>${r}</li>`).join('')}</ul>
                </div>
              </div>
            ` : ''}'''
content = content.replace(picks_title_old, picks_title_new)

# 8. Modify exportCsv
export_csv_old = '''  globalMatches.forEach(m => {'''
export_csv_new = '''  globalMatches.forEach(m => {
    if (!m.picks || m.picks.length === 0) return;'''
content = content.replace(export_csv_old, export_csv_new)

# Add event listener for checkbox
event_listener_old = '''if(qs('#btn-export')) qs('#btn-export').addEventListener('click', exportCsv);'''
event_listener_new = '''if(qs('#btn-export')) qs('#btn-export').addEventListener('click', exportCsv);
if(qs('#m-hide-empty')) qs('#m-hide-empty').addEventListener('change', renderMatches);'''
content = content.replace(event_listener_old, event_listener_new)

# 9. Replace analyzeMatch entirely
new_analyze = '''const analyzeMatch = (match, homeForm, awayForm, filters) => {
  const picks = [];
  const rejections = [];
  const bookmaker = match.bookmakers?.[0];
  if (!bookmaker) return { picks, rejections };
  
  const h2h = bookmaker.markets.find(m => m.key === 'h2h');
  const totals = bookmaker.markets.find(m => m.key === 'totals');
  const btts = bookmaker.markets.find(m => m.key === 'btts');
  if (!h2h) return { picks, rejections };
  
  let homeOdds = 0, drawOdds = 0, awayOdds = 0;
  h2h.outcomes.forEach(o => {
    if (o.name === match.home_team) homeOdds = o.price;
    else if (o.name === 'Draw') drawOdds = o.price;
    else awayOdds = o.price;
  });

  if (!homeOdds || !awayOdds) return { picks, rejections };

  let over25Odds = 0, over35Odds = 0;
  if (totals) {
    totals.outcomes.forEach(o => {
      if (o.name === 'Over' && o.point === 2.5) over25Odds = o.price;
      if (o.name === 'Over' && o.point === 3.5) over35Odds = o.price;
    });
  }

  let bttsYesOdds = 0;
  if (btts) {
    btts.outcomes.forEach(o => {
      if (o.name === 'Yes') bttsYesOdds = o.price;
    });
  }

  const hasForm = homeForm && awayForm;
  const minOdds = filters.minOdds || 1.20;

  if (!hasForm) {
    if (filters.matchWinner) rejections.push("Match Winner: Skipped because ESPN form data is missing");
    if (filters.draw) rejections.push("Draw: Skipped because ESPN form data is missing");
    if (filters.gg) rejections.push("Both Teams to Score (GG): Skipped because ESPN form data is missing");
    if (filters.ggOver25) rejections.push("GG & Over 2.5: Skipped because ESPN form data is missing");
    if (filters.over25) rejections.push("Over 2.5: Skipped because ESPN form data is missing");
    if (filters.over35) rejections.push("Over 3.5: Skipped because ESPN form data is missing");
    if (filters.teamOver15) rejections.push("Team Over 1.5: Skipped because ESPN form data is missing");
    if (filters.teamOver25) rejections.push("Team Over 2.5: Skipped because ESPN form data is missing");
    if (filters.handicap) rejections.push("Handicap: Skipped because ESPN form data is missing");
    if (filters.doubleChance) rejections.push("Double Chance: Skipped because ESPN form data is missing");
    if (filters.teamOver05) rejections.push("Team to Score (Over 0.5): Skipped because ESPN form data is missing");
    if (filters.corners) rejections.push("Corners: Skipped because ESPN form data is missing");
    return { picks, rejections };
  }

  // A. Match Winner (1-2)
  if (filters.matchWinner) {
    let picked = false;
    [{ t: match.home_team, f: homeForm, oppF: awayForm, odds: homeOdds }, 
     { t: match.away_team, f: awayForm, oppF: homeForm, odds: awayOdds }].forEach(team => {
      if (team.f.winRate >= 0.50 && team.oppF.winRate <= 0.33 && parseFloat(team.f.avgScored) >= 1.4 && parseFloat(team.oppF.avgConceded) >= 1.2) {
        if (team.odds >= minOdds && team.odds <= 2.50) {
          let conf = (team.f.winRate >= 0.80 && parseFloat(team.f.avgScored) >= 1.8) ? 'high' : 'medium';
          picks.push({ 
            market: 'Match Winner', 
            display: `${team.t} to Win`, 
            conf, 
            odds: team.odds,
            betType: team.odds >= 1.80 ? 'single' : 'acca',
            reasons: [`Win rate: ${Math.round(team.f.winRate * 100)}% (Won ${Math.round(team.f.winRate*team.f.played)}/${team.f.played})`, `Opponent win rate: ${Math.round(team.oppF.winRate * 100)}%`, `Odds: ${team.odds}`] 
          });
          picked = true;
        } else {
          rejections.push(`Match Winner: ${team.t} odds (${team.odds}) out of range (${minOdds} - 2.50)`);
        }
      }
    });
    if (!picked && rejections.filter(r => r.startsWith("Match Winner")).length === 0) {
      rejections.push(`Match Winner: Win rate or scoring form criteria not met for either team`);
    }
  }

  // B. Draw (X)
  if (filters.draw) {
    const combinedAvg = parseFloat(homeForm.avgScored) + parseFloat(homeForm.avgConceded) + parseFloat(awayForm.avgScored) + parseFloat(awayForm.avgConceded);
    const avgMatchGoals = combinedAvg / 2;
    const underdogAvgConceded = homeOdds < awayOdds ? parseFloat(awayForm.avgConceded) : parseFloat(homeForm.avgConceded);
    const favoriteAvgScored = homeOdds < awayOdds ? parseFloat(homeForm.avgScored) : parseFloat(awayForm.avgScored);
    
    if (homeForm.record.filter(r => r === 'D').length >= 2 && awayForm.record.filter(r => r === 'D').length >= 2) {
      if (avgMatchGoals <= 2.2 && underdogAvgConceded <= 1.2 && favoriteAvgScored <= 1.8) {
        if (drawOdds >= minOdds) {
          let conf = (homeForm.record.filter(r => r === 'D').length >= 3 && awayForm.record.filter(r => r === 'D').length >= 3) ? 'high' : 'medium';
          picks.push({
            market: 'Draw',
            display: `Draw (X)`,
            conf,
            odds: drawOdds,
            betType: 'single',
            reasons: [`Both teams have high draw rates`, `Low scoring match expected (combined avg: ${avgMatchGoals.toFixed(2)})`, `Odds: ${drawOdds}`]
          });
        } else {
          rejections.push(`Draw: Odds (${drawOdds}) below minimum (${minOdds})`);
        }
      } else {
        rejections.push(`Draw: Match average goals (${avgMatchGoals.toFixed(2)}) too high or team defenses not tight enough`);
      }
    } else {
      rejections.push(`Draw: Draw rates too low for one or both teams`);
    }
  }

  // C. Both Teams to Score (GG)
  if (filters.gg) {
    if (homeForm.scoringRate >= 0.66 && awayForm.scoringRate >= 0.66 && parseFloat(homeForm.avgConceded) >= 1.0 && parseFloat(awayForm.avgConceded) >= 1.0 && homeForm.cleanSheets <= 1 && awayForm.cleanSheets <= 1) {
      let conf = (homeForm.scoringRate >= 0.83 && awayForm.scoringRate >= 0.83 && parseFloat(homeForm.avgConceded) >= 1.2 && parseFloat(awayForm.avgConceded) >= 1.2) ? 'high' : 'medium';
      picks.push({
        market: 'Both Teams to Score',
        display: `GG (Both to Score)`,
        conf,
        odds: bttsYesOdds || null,
        betType: bttsYesOdds >= 1.80 ? 'single' : 'acca',
        reasons: [`Both teams score consistently (>= 66%)`, `Both teams concede >= 1.0 goals/game`]
      });
    } else {
      rejections.push(`Both Teams to Score (GG): Scoring rates too low or too many clean sheets`);
    }
  }

  // D. GG & Over 2.5 Goals
  if (filters.ggOver25) {
    const combinedAvg = parseFloat(homeForm.avgScored) + parseFloat(homeForm.avgConceded) + parseFloat(awayForm.avgScored) + parseFloat(awayForm.avgConceded);
    const avgMatchGoals = combinedAvg / 2;
    
    if (avgMatchGoals >= 2.8 && homeForm.scoringRate >= 0.83 && awayForm.scoringRate >= 0.83 && parseFloat(homeForm.avgConceded) >= 1.0 && parseFloat(awayForm.avgConceded) >= 1.0 && homeForm.cleanSheets <= 1 && awayForm.cleanSheets <= 1) {
      let conf = avgMatchGoals >= 3.4 ? 'high' : 'medium';
      picks.push({
        market: 'GG & Over 2.5',
        display: `GG & Over 2.5 Goals`,
        conf,
        odds: null,
        betType: 'single',
        reasons: [`Combined average match goals: ${avgMatchGoals.toFixed(2)}`, `Both teams scoring rate >= 83%`]
      });
    } else {
      rejections.push(`GG & Over 2.5: Combined avg goals (${avgMatchGoals.toFixed(2)}) too low or scoring rates below 83%`);
    }
  }

  // E. Over 3.5 Total Goals
  if (filters.over35) {
    const combinedAvg = parseFloat(homeForm.avgScored) + parseFloat(homeForm.avgConceded) + parseFloat(awayForm.avgScored) + parseFloat(awayForm.avgConceded);
    const avgMatchGoals = combinedAvg / 2;
    
    if (avgMatchGoals >= 3.2 && parseFloat(homeForm.avgScored) >= 1.8 && parseFloat(awayForm.avgScored) >= 1.8 && homeForm.scoringRate >= 0.66 && awayForm.scoringRate >= 0.66) {
      if (!over35Odds || over35Odds >= minOdds) {
        let conf = avgMatchGoals >= 3.8 ? 'high' : 'medium';
        picks.push({
          market: 'Over 3.5 Total Goals',
          display: `Over 3.5 Goals`,
          conf,
          odds: over35Odds || null,
          betType: 'single',
          reasons: [`Combined average match goals: ${avgMatchGoals.toFixed(2)}`, `Both teams avg scored >= 1.8`]
        });
      } else {
        rejections.push(`Over 3.5: Odds (${over35Odds}) below minimum (${minOdds})`);
      }
    } else {
      rejections.push(`Over 3.5: Avg match goals (${avgMatchGoals.toFixed(2)}) too low or teams don't score enough`);
    }
  }
  
  // F. Handicap
  if (filters.handicap) {
    let fav = homeOdds <= awayOdds ? {t: match.home_team, odds: homeOdds, f: homeForm} : {t: match.away_team, odds: awayOdds, f: awayForm};
    let dog = homeOdds > awayOdds ? {t: match.home_team, odds: homeOdds, f: homeForm} : {t: match.away_team, odds: awayOdds, f: awayForm};
    
    if (fav.odds <= 1.35 && dog.odds >= 5.00 && parseFloat(dog.f.avgConceded) <= 1.8) {
      let line = '+3.0';
      if (fav.odds <= 1.10) line = '+4.0';
      else if (fav.odds <= 1.25) line = '+3.5';
      else if (fav.odds <= 1.32) line = '+3.5'; 
      
      let conf = 'low';
      if (parseFloat(dog.f.avgConceded) <= 1.0 && parseFloat(fav.f.avgScored) <= 2.5) conf = 'high';
      else if (parseFloat(dog.f.avgConceded) <= 1.5) conf = 'medium';
      
      picks.push({
        market: 'Handicap',
        display: `${dog.t} Handicap ${line}`,
        conf,
        odds: null,
        betType: 'acca',
        reasons: [`Underdog defense is decent (avg conceded ${dog.f.avgConceded})`, `Favorite odds are low (${fav.odds})`]
      });
    } else {
      rejections.push(`Handicap: Favorite odds (${fav.odds}) too high or Underdog odds (${dog.odds}) too low`);
    }
  }

  // Over 2.5 Total Goals
  if (filters.over25) {
    const combinedAvg = parseFloat(homeForm.avgScored) + parseFloat(homeForm.avgConceded) + parseFloat(awayForm.avgScored) + parseFloat(awayForm.avgConceded);
    const avgMatchGoals = combinedAvg / 2;
    
    if (avgMatchGoals >= 2.6 && homeForm.scoringRate >= 0.66 && awayForm.scoringRate >= 0.66) {
      if (!over25Odds || over25Odds >= minOdds) {
        let conf = avgMatchGoals >= 3.2 ? 'high' : 'medium';
        picks.push({ 
          market: 'Over 2.5 Total Goals', 
          display: `Over 2.5 Goals`, 
          conf, 
          odds: over25Odds || null,
          betType: over25Odds >= 1.80 ? 'single' : 'acca',
          reasons: [`Combined average match goals: ${avgMatchGoals.toFixed(2)}`, `Both teams score reliably (>66% scoring rate)`] 
        });
      } else {
        rejections.push(`Over 2.5: Odds (${over25Odds}) below minimum (${minOdds})`);
      }
    } else {
      rejections.push(`Over 2.5: Avg match goals (${avgMatchGoals.toFixed(2)}) too low or scoring rate below 66%`);
    }
  }

  // Team Over 1.5 Goals
  if (filters.teamOver15) {
    let picked = false;
    [{ t: match.home_team, f: homeForm, oppF: awayForm }, 
     { t: match.away_team, f: awayForm, oppF: homeForm }].forEach(team => {
      if (team.oppF.cleanSheets >= 2 || parseFloat(team.oppF.avgConceded) <= 0.8) {
        rejections.push(`Team Over 1.5: Opponent defense too strong (clean sheets: ${team.oppF.cleanSheets}) for ${team.t}`);
        return; 
      }
      if (parseFloat(team.f.avgScored) >= 1.6 && parseFloat(team.oppF.avgConceded) >= 1.2) {
        let conf = (parseFloat(team.f.avgScored) >= 2.0 && parseFloat(team.oppF.avgConceded) >= 1.6) ? 'high' : 'medium';
        picks.push({ 
          market: 'Team Over 1.5 Goals', 
          display: `${team.t} Over 1.5 Goals`, 
          conf, 
          odds: null,
          betType: 'acca',
          reasons: [`Team averages ${team.f.avgScored} goals scored/game`, `Opponent averages ${team.oppF.avgConceded} goals conceded/game`] 
        });
        picked = true;
      } else {
        rejections.push(`Team Over 1.5: Avg scored too low (${team.f.avgScored}) for ${team.t}`);
      }
    });
    if (!picked && rejections.filter(r => r.startsWith("Team Over 1.5")).length === 0) {
      rejections.push(`Team Over 1.5: Criteria not met for either team`);
    }
  }

  // Team Over 2.5 Goals
  if (filters.teamOver25) {
    let picked = false;
    [{ t: match.home_team, f: homeForm, oppF: awayForm }, 
     { t: match.away_team, f: awayForm, oppF: homeForm }].forEach(team => {
      if (team.oppF.cleanSheets >= 1 || parseFloat(team.oppF.avgConceded) <= 1.0) {
        rejections.push(`Team Over 2.5: Opponent defense too strong for ${team.t}`);
        return; 
      }
      if (parseFloat(team.f.avgScored) >= 2.2 && parseFloat(team.oppF.avgConceded) >= 1.6) {
        let conf = (parseFloat(team.f.avgScored) >= 2.7 && parseFloat(team.oppF.avgConceded) >= 2.0) ? 'high' : 'medium';
        picks.push({ 
          market: 'Team Over 2.5 Goals', 
          display: `${team.t} Over 2.5 Goals`, 
          conf, 
          odds: null,
          betType: 'single',
          reasons: [`Team averages ${team.f.avgScored} goals scored/game`, `Opponent averages ${team.oppF.avgConceded} goals conceded/game`] 
        });
        picked = true;
      } else {
        rejections.push(`Team Over 2.5: Avg scored too low (${team.f.avgScored}) for ${team.t}`);
      }
    });
    if (!picked && rejections.filter(r => r.startsWith("Team Over 2.5")).length === 0) {
      rejections.push(`Team Over 2.5: Criteria not met for either team`);
    }
  }

  // G. Double Chance (1X, X2, 12)
  if (filters.doubleChance) {
    let picked = false;
    if (homeForm.record.filter(r => r === 'L').length <= 1 && awayForm.record.filter(r => r === 'W').length <= 1) {
      let conf = (homeForm.winRate >= 0.5 && awayForm.winRate <= 0.33) ? 'high' : 'medium';
      picks.push({
        market: 'Double Chance 1X', display: `Double Chance 1X (Home/Draw)`, conf, odds: null, betType: 'acca',
        reasons: [`Home lost <= 1 of last 6`, `Away won <= 1 of last 6`]
      });
      picked = true;
    }
    if (awayForm.record.filter(r => r === 'L').length <= 1 && homeForm.record.filter(r => r === 'W').length <= 1) {
      let conf = (awayForm.winRate >= 0.5 && homeForm.winRate <= 0.33) ? 'high' : 'medium';
      picks.push({
        market: 'Double Chance X2', display: `Double Chance X2 (Away/Draw)`, conf, odds: null, betType: 'acca',
        reasons: [`Away lost <= 1 of last 6`, `Home won <= 1 of last 6`]
      });
      picked = true;
    }
    const combinedAvg = parseFloat(homeForm.avgScored) + parseFloat(homeForm.avgConceded) + parseFloat(awayForm.avgScored) + parseFloat(awayForm.avgConceded);
    const avgMatchGoals = combinedAvg / 2;
    if (homeForm.record.filter(r => r === 'D').length <= 1 && awayForm.record.filter(r => r === 'D').length <= 1 && avgMatchGoals >= 2.6 && homeForm.scoringRate >= 0.66 && awayForm.scoringRate >= 0.66) {
      let conf = (homeForm.record.filter(r => r === 'D').length === 0 && awayForm.record.filter(r => r === 'D').length === 0) ? 'high' : 'medium';
      picks.push({
        market: 'Double Chance 12', display: `Double Chance 12 (Home/Away)`, conf, odds: null, betType: 'acca',
        reasons: [`Both teams draw <= 1 of last 6`, `Combined avg goals >= 2.6`, `Both scoring rate >= 66%`]
      });
      picked = true;
    }
    if (!picked) {
      rejections.push(`Double Chance: Form doesn't match 1X, X2, or 12 criteria`);
    }
  }

  // H. Team to Score (Over 0.5 Goals)
  if (filters.teamOver05) {
    let picked = false;
    [{ t: match.home_team, f: homeForm, oppF: awayForm },
     { t: match.away_team, f: awayForm, oppF: homeForm }].forEach(team => {
      if (team.oppF.cleanSheets >= 3 || parseFloat(team.oppF.avgConceded) <= 0.5) {
        rejections.push(`Team to Score (Over 0.5): Opponent defense too strong for ${team.t}`);
        return;
      }
      if (team.f.scoringRate >= 0.83 && parseFloat(team.f.avgScored) >= 1.2) {
        let conf = (team.f.scoringRate === 1) ? 'high' : 'medium';
        picks.push({
          market: 'Team to Score (Over 0.5)', display: `${team.t} to Score (Over 0.5)`, conf, odds: null, betType: 'acca',
          reasons: [`Team scored in >= 83% of last 6 matches`, `Team averages ${team.f.avgScored} goals scored/game`, `Opponent defense allows ${team.oppF.avgConceded} goals/game`]
        });
        picked = true;
      } else {
        rejections.push(`Team to Score (Over 0.5): Scoring rate too low for ${team.t}`);
      }
    });
    if (!picked && rejections.filter(r => r.startsWith("Team to Score")).length === 0) {
      rejections.push(`Team to Score (Over 0.5): Criteria not met for either team`);
    }
  }

  // I. Corners
  if (filters.corners) {
    let picked = false;
    const combinedAvg = parseFloat(homeForm.avgScored) + parseFloat(homeForm.avgConceded) + parseFloat(awayForm.avgScored) + parseFloat(awayForm.avgConceded);
    const avgMatchGoals = combinedAvg / 2;

    [{ t: match.home_team, f: homeForm, oppF: awayForm },
     { t: match.away_team, f: awayForm, oppF: homeForm }].forEach(team => {
      if (parseFloat(team.f.avgScored) >= 1.8 && parseFloat(team.oppF.avgScored) <= 1.0) {
        picks.push({
          market: 'Corners Winner', display: `${team.t} to win Corners`, conf: 'medium', odds: null, betType: 'acca',
          reasons: [`Attacking Proxy Model (high attacking pressure, avg scored: ${team.f.avgScored} vs opponent avg scored: ${team.oppF.avgScored})`]
        });
        picked = true;
      }
    });

    if (avgMatchGoals >= 3.0 && homeForm.scoringRate >= 0.66 && awayForm.scoringRate >= 0.66) {
      picks.push({
        market: 'Over 9.5 Corners', display: `Over 9.5 Corners`, conf: 'medium', odds: null, betType: 'single',
        reasons: [`Attacking Proxy Model (high shooting frequency, combined goals avg: ${avgMatchGoals.toFixed(2)})`]
      });
      picked = true;
    }
    
    if (!picked) {
      rejections.push(`Corners: Attacking metrics below corner threshold`);
    }
  }

  return { picks, rejections };
};'''

old_analyze = re.search(r"const analyzeMatch = \(match, homeForm, awayForm, filters\) => \{.*?\n  return picks;\n\};\n", content, re.DOTALL)
if old_analyze:
    content = content.replace(old_analyze.group(0), new_analyze + "\\n")
else:
    print("Could not find analyzeMatch to replace.")

with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)
print("Updated successfully!")
