from flask import Flask, render_template, request
import urllib.parse, urllib.request, urllib.error, json, logging, base64
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO

app = Flask(__name__)

def pretty(obj):
    return json.dumps(obj, sort_keys=True, indent=2)

class player_record():
    #A Blaseball player, and all the relevant stats except vibes (since those change too frequently to be encapsulated by a static value)
    #Created using dicts returned by Blaseball Reference.
    def __init__(self, dict):
        self.name = dict["player_name"]
        self.team = dict["team"]
        self.ritual = dict["ritual"]
        self.id = dict["player_id"]
        self.cinnamon = float(dict["cinnamon"])
        self.buoyancy = float(dict["buoyancy"])
        self.pressurization = float(dict["pressurization"])
        self.fate = int(dict["fate"])

class player_chronicle():
    #A Blaseball player, and all the relevant stats except vibes (since those change too frequently to be encapsulated by a static value)
    #Created using dicts returned by Chronicler.
    def __init__(self, dict):
        self.fateChange = None
        self.name = dict["data"]["name"]
        self.timestamp = dict["lastSeen"]
        self.date = self.timestamp[0:10]
        self.time = self.timestamp[11:19]
        if "leagueTeamId" in dict["data"]:
            self.teamID = dict["data"]["leagueTeamId"]
        else:
            self.teamID = "NOT YET TRACKED"
        if "ritual" in dict["data"]:
            self.ritual = dict["data"]["ritual"]
        else:
            self.ritual = "NOT YET TRACKED"
        self.id = dict["playerId"]
        if "fate" in dict["data"]:
            if dict["data"]["fate"]:
                self.fate = int(dict["data"]["fate"])
            else:
                self.fate = "none, according to the API. In reality, they likely had one that just wasn't tracked. Chronicler is inconsistent at times"
        else:
            self.fate = "not yet tracked by Chronicler"
        self.modifications = []
        for key in ["gameAttr","permAttr","seasAttr","weekAttr"]:
            if key in dict["data"]:
                for mod in dict["data"][key]:
                    self.modifications.append(mod)
    def __str__(self):
        return f"""{self.name}   ({self.date} at {self.time})
        ID: {self.id}
        Team ID: {self.teamID}
        Pregame ritual: {self.ritual}
        Modifications: {self.modifications}
        Fate: {self.fate}
        Reason for change to Fate: {self.fateChange}\n"""

class team_record():
    #Stores name and ID for a blaseball team or location, as well as if it's a team or location
    def __init__(self, dict, type = 'team'):
        self.name = dict["full_name"]
        self.id = dict["team_id"]
        self.status = dict['team_current_status']
        self.emoji = dict['team_emoji']
        self.type = type
    def __str__(self):
        #Returns team name as string
        return self.name
    def __repr__(self):
        return self.name

def area_record(name, emoji, id):
    #defines a team_record class object for a location (such as the hall of flame)
    area = {"full_name": name, "team_id": id, "team_current_status": None, "team_emoji": emoji}
    return team_record(area, type='area')

def get_player_history(id, page = None):
    try:
        if page:
            paramstr = urllib.parse.urlencode({'player': id, 'count': 1000, 'page': page})
        else: 
            paramstr = urllib.parse.urlencode({'player': id, 'count': 1000})
        baseurl = 'https://api.sibr.dev/chronicler/v1/players/updates'
        request = baseurl+'?'+paramstr
        requeststr = urllib.request.urlopen(request).read()
        data = json.loads(requeststr)
    except urllib.error.URLError as e:
        if hasattr(e,"code"):
            print("The server couldn't fulfill the request.")
            print("Error code: ", e.code)
        elif hasattr(e,'reason'):
            print("We failed to reach a server")
            print("Reason: ", e.reason)
    else:
        return data

def roster_swap_doublecheck(player):
    try:
        paramstr1 = urllib.parse.urlencode({'player': player.id, 'count': 1, 'before': player.timestamp})
        paramstr2 = urllib.parse.urlencode({'player': player.id, 'count': 1, 'after': player.timestamp})
        baseurl = 'https://api.sibr.dev/chronicler/v1/roster/updates'
        request1 = baseurl+'?'+paramstr1
        requeststr1 = urllib.request.urlopen(request1).read()
        data1 = json.loads(requeststr1)
        request2 = baseurl+'?'+paramstr2
        requeststr2 = urllib.request.urlopen(request2).read()
        data2 = json.loads(requeststr2)
    except urllib.error.URLError as e:
        if hasattr(e,"code"):
            print("The server couldn't fulfill the request.")
            print("Error code: ", e.code)
        elif hasattr(e,'reason'):
            print("We failed to reach a server")
            print("Reason: ", e.reason)
    else:
        if data1['data'] and data2['data']:
            if data1['data'][0]['teamId'] != data2['data'][0]['teamId']:
                return True
            else:
                return False

def get_full_player_history(id):
    output = []
    loop = True
    page = None
    while loop:
        data = get_player_history(id, page)
        if page == data["nextPage"] or data["nextPage"] == None:
            loop = False
            print("Looping done!")
        else:
            page = data["nextPage"]
            output.append(data["data"])
            print(f"Appended page. Calling {page} next.")
    flatput = []
    for lst in output:
        for dic in lst:
            #print(pretty(dic))
            flatput.append(dic)
    cleanput = [player_chronicle(entry) for entry in flatput]
    return cleanput

def fate_filtered_history(input):
    output = []
    last_entry = None
    for entry in input:
        if entry.fate not in ['not yet tracked by Chronicler','none, according to the API. In reality, they likely had one that just wasn\'t tracked. Chronicler is inconsistent at times']:
            if last_entry != None:
                if last_entry.fate != entry.fate and last_entry.fate != "NONE":
                    if output[-1].timestamp != last_entry.timestamp:
                        output.append(last_entry)
                    if 'ALTERNATE' in entry.modifications and 'ALTERNATE' not in last_entry.modifications:
                        entry.fateChange = "due to becoming an Alternate."
                    elif entry.teamID != last_entry.teamID:
                        entry.fateChange = "due to a Feedback swap."
                    else:
                        feedback_doublecheck = roster_swap_doublecheck(entry)
                        if feedback_doublecheck:
                            entry.fateChange = "due to a Feedback swap."
                        else:
                            if entry.name in ['Axel Trololol','Lachlan Shelton','Antonio Wallace','Hobbs Cain']:
                                entry.fateChange = "due to a Feedback swap."
                            else:
                                entry.fateChange = "due to... some other cause. (If you're seeing this, odds are that there's been an error.)"
                    output.append(entry)
            else:
                output.append(entry)
            last_entry = entry
    #people's names change and I'd like to make sure I use the most recent name.
    output[0].name = input[-1].name
    return output

def get_players_seasonal(season = 23):
    #This defaults to getting all dead players.
    try:
        paramstr = paramstr = urllib.parse.urlencode({'season': season})
        baseurl = 'https://api.blaseball-reference.com/v2/players'
        request = baseurl+'?'+paramstr
        requeststr = urllib.request.urlopen(request).read()
        data = json.loads(requeststr)
    except urllib.error.URLError as e:
        if hasattr(e,"code"):
            print("The server couldn't fulfill the request.")
            print("Error code: ", e.code)
        elif hasattr(e,'reason'):
            print("We failed to reach a server")
            print("Reason: ", e.reason)
    else:
        return data

def get_pooled_players(pool = 'deceased'):
    #This defaults to getting all dead players.
    try:
        paramstr = paramstr = urllib.parse.urlencode({'playerPool': pool})
        baseurl = 'https://api.blaseball-reference.com/v2/players'
        request = baseurl+'?'+paramstr
        requeststr = urllib.request.urlopen(request).read()
        data = json.loads(requeststr)
    except urllib.error.URLError as e:
        if hasattr(e,"code"):
            print("The server couldn't fulfill the request.")
            print("Error code: ", e.code)
        elif hasattr(e,'reason'):
            print("We failed to reach a server")
            print("Reason: ", e.reason)
    else:
        return data

def get_player(id = None):
    #This gets EVERY player if it doesn't get an ID.
    try:
        paramstr = id
        baseurl = 'https://api.blaseball-reference.com/v2/players/'
        request = baseurl+str(paramstr or '')
        requeststr = urllib.request.urlopen(request).read()
        data = json.loads(requeststr)
    except urllib.error.URLError as e:
        if hasattr(e,"code"):
            print("The server couldn't fulfill the request.")
            print("Error code: ", e.code)
        elif hasattr(e,'reason'):
            print("We failed to reach a server")
            print("Reason: ", e.reason)
    else:
        return data

def get_team_roster(id, includeShadows = True):
    #includeShadows sets whether or not to return reserve ("shadowed") players
    try:
        paramstr = urllib.parse.urlencode({'teamId': id, 'includeShadows': includeShadows})
        baseurl = 'https://api.blaseball-reference.com/v1/currentRoster'
        request = baseurl+'?'+paramstr
        requeststr = urllib.request.urlopen(request).read()
        data = json.loads(requeststr)
    except urllib.error.URLError as e:
        if hasattr(e,"code"):
            print("The server couldn't fulfill the request.")
            print("Error code: ", e.code)
        elif hasattr(e,'reason'):
            print("We failed to reach a server")
            print("Reason: ", e.reason)
    else:
        return data

def get_teams(season = 23):
    try:
        paramstr = urllib.parse.urlencode({'season': season})
        baseurl = 'https://api.blaseball-reference.com/v2/teams'
        request = baseurl+'?'+paramstr
        requeststr = urllib.request.urlopen(request).read()
        data = json.loads(requeststr)
    except urllib.error.URLError as e:
        if hasattr(e,"code"):
            print("The server couldn't fulfill the request.")
            print("Error code: ", e.code)
        elif hasattr(e,'reason'):
            print("We failed to reach a server")
            print("Reason: ", e.reason)
    else:
        return data

def clean_team_list(season = 23):
    team_list = get_teams(season)
    clean_list = [team_record(team) for team in team_list]
    return clean_list

def get_player_stats(category, season, players):
    playerIds = ''
    for player in players:
        playerIds = playerIds+str(player['player_id'])+','
    try:
        paramstr = urllib.parse.urlencode({'category':category, 'season':season, 'playerIds':playerIds})
        baseurl = 'https://api.blaseball-reference.com/v1/playerStats'
        request = baseurl+'?'+paramstr
        requeststr = urllib.request.urlopen(request).read()
        data = json.loads(requeststr)
    except urllib.error.URLError as e:
        if hasattr(e,"code"):
            print("The server couldn't fulfill the request.")
            print("Error code: ", e.code)
        elif hasattr(e,'reason'):
            print("We failed to reach a server")
            print("Reason: ", e.reason)
    else:
        return data

def season_mapping():
    try:
        request = 'https://api.sibr.dev/chronicler/v1/time/seasons'
        requeststr = urllib.request.urlopen(request).read()
        data = json.loads(requeststr)
    except urllib.error.URLError as e:
        if hasattr(e,"code"):
            print("The server couldn't fulfill the request.")
            print("Error code: ", e.code)
        elif hasattr(e,'reason'):
            print("We failed to reach a server")
            print("Reason: ", e.reason)
    else:
        del data['data'][-2:]
        return data['data']

"""
def summarize_player(player):
    if float(player['batting_stars']) >= 5.0:
        print(pretty(player))
        return f'----------------------------\nName: {player["player_name"]}\nTeam: {player["team"]}\nPregame Ritual: {player["ritual"]}\nBatting Stars: {player["batting_stars"]}\n'


with open("batters.txt", "w") as text_file:
    idlist = clean_team_list()
    for team in idlist:
        roster = get_team_roster(team)
        for player in roster:
            summary = summarize_player(player)
            if summary != None:
                print(summary)
                text_file.write(summary)
"""
@app.route("/")
def landing():
    app.logger.info("On Main Page!")
    title = 'HCDE 310 Final: Blaseball Vibes & Fate'
    return render_template('origin.html',title=title)

@app.route("/vteam")
def vleague_list():
    title = 'Vibe Analysis Tool'
    #desc goes here
    data = clean_team_list()
    outdata = []
    for team in data:
        if team.name == "The Hall Stars":
            team.name = "Hall Stars"
            app.logger.info(f"***Editing the Hall Stars!")
        if team.name != "Hall Stars" and team.status != 'active':
            app.logger.info(f"***Removing {team} from roster")
        else:
            app.logger.info(f"***{team} remains. They are {team.status}")
            outdata.append(team)
    outdata.append(area_record("Vault", "0x1F947", '698cfc6d-e95e-4391-b754-b87337e4d2a9'))
    outdata.append(area_record("Hall of Flame", "0x1f480", id = 'Hell'))
    return render_template('vteam_select.html',title=title,data=outdata)

@app.route("/vroster")
def vroster_printer():
    team = request.args.get("selected_team")
    print(team)
    app.logger.info(f"Getting roster for the {team}")
    if team == "Hell":
        raw_roster = get_pooled_players()
        for player in raw_roster:
            if player['team'] != 'null':
                raw_roster.remove(player)
    else:
        raw_roster = get_team_roster(team, includeShadows=True)
    clean_roster = [player_record(player) for player in raw_roster]
    return render_template('vroster_return.html',title=f"Roster for the {team}",roster=clean_roster,team=team)

@app.route("/gvibes")
def vibe_charts():
    id = request.args.get("selected_player")
    player = player_record(get_player(id))
    #Vibes aren't stored on any accessible APIs, but its formula is visible on the front-end of the Blaseball website.
    #We can use this to recreate a player's vibes using stats that we do have access to.
    frequency = 6 + round(10 * player.buoyancy)
    range = 0.5 * (player.pressurization + player.cinnamon)
    x = np.arange(99)
    y = (range * np.sin(np.pi * ((2 / frequency) * x + 0.5))) - (0.5 * player.pressurization) + (0.5 * player.cinnamon)
    plt.plot(x, y)
    plt.xlabel('Day')
    plt.ylabel('Vibes')
    plt.xlim(0, 100)
    plt.ylim(-2.0, 2.0)
    #We can't simply save the image to the server then call it by local url, since that'd be a security risk.
    #This necessitates that I instead convert the image to a base64 string, which can be fed directly to the jinja template and be turned back into an image.
    #Utter clownery.
    #Code adapted from https://stackoverflow.com/questions/38061267/matplotlib-graphic-image-to-base64
    #Corresponding HTML adapted from https://stackoverflow.com/questions/31492525/converting-matplotlib-png-to-base64-for-viewing-in-html-template
    chart_bytes = BytesIO()
    plt.savefig(chart_bytes, format='jpg')
    plt.close()
    chart_bytes.seek(0)
    chart_base64 = base64.b64encode(chart_bytes.read())
    chart_bytes.close()
    return render_template('vibechart_template.html',title=f"Summary of {player.name}",player=player, graph=chart_base64.decode('utf8'))

@app.route("/fteam")
def fleague_list():
    title = 'Fate Summary Tool'
    #desc goes here
    data = clean_team_list()
    outdata = []
    for team in data:
        if team.name == "The Hall Stars":
            team.name = "Hall Stars"
            app.logger.info(f"***Editing the Hall Stars!")
        if team.name != "Hall Stars" and team.status != 'active':
            app.logger.info(f"***Removing {team} from roster")
        else:
            app.logger.info(f"***{team} remains. They are {team.status}")
            outdata.append(team)
    outdata.append(area_record("Vault", "0x1F947", '698cfc6d-e95e-4391-b754-b87337e4d2a9'))
    outdata.append(area_record("Hall of Flame", "0x1f480", id = 'Underworld'))
    return render_template('fteam_select.html',title=title,data=outdata)

@app.route("/froster")
def froster_printer():
    team = request.args.get("selected_team")
    print(team)
    app.logger.info(f"Getting roster for the {team}")
    if team == "Underworld":
        raw_roster = get_pooled_players()
        for player in raw_roster:
            if player['team'] != 'null':
                raw_roster.remove(player)
    else:
        raw_roster = get_team_roster(team, includeShadows=True)
    clean_roster = [player_record(player) for player in raw_roster]
    return render_template('froster_return.html',title=f"Roster for the {team}",roster=clean_roster,team=team)

@app.route("/fhist")
def fate_summary():
    player_id = request.args.get("selected_player")
    hist = get_full_player_history(player_id)
    fate_hist = fate_filtered_history(hist)
    return render_template('fate_history.html',title=f"Vibe summary for {fate_hist[0].name}",history=fate_hist, length = len(fate_hist))

@app.route("/fseason")
def scatter_definer():
    batter_stats = ['doubles','triples','home_runs','runs_batted_in','walks', 'strikeouts', 'batting_average', 'on_base_percentage', 'batting_average_risp', 'slugging', 'on_base_slugging']
    pitcher_stats = ["win_pct","earned_run_average","walks_per_9","hits_per_9","strikeouts_per_9","home_runs_per_9","whip","strikeouts_per_walk"]
    return render_template('scatter_definer.html',title=f"Fate Comparison Tool",batter_stats=batter_stats,pitcher_stats=pitcher_stats)

@app.route("/fscatter")
def fate_scatter():
    #get all players, filter out to only include players in correct position for stat, get stats for all players
    batter_stats = ['doubles','triples','home_runs','runs_batted_in','walks', 'strikeouts', 'batting_average', 'on_base_percentage', 'batting_average_risp', 'slugging', 'on_base_slugging']
    statistic = request.args.get("selected_stat")
    season = int(request.args.get("season"))-1
    league = get_players_seasonal(season)
    playersfate = []
    if statistic in batter_stats:
        category = 'batting'
        for player in league:
            if player['position_type'] == 'BATTER' and player["current_location"] == "main_roster":
                playersfate.append(player)
    else:
        category = 'pitching'
        for player in league:
            if player['position_type'] == 'PITCHER' and player["current_location"] == "main_roster":
                playersfate.append(player)
    playerstats = get_player_stats(category, season, playersfate)
    playersfate = sorted(playersfate, key = lambda i: i['player_id'])
    playerstats = sorted(playerstats, key = lambda i: (i['player_id'], float(i[statistic]or 0.0)))
    graph_inputs = {'fate':[], 'stat':[]}
    for player in playersfate:
        graph_inputs['fate'].append(player['fate'])
    last_player = None
    for player in playerstats:
        app.logger.info(player['player_name'])
        if last_player == player['player_name']:
            graph_inputs['stat'][-1]+=(float(player[statistic] or 0.0))
        else:
            graph_inputs['stat'].append(float(player[statistic] or 0.0))
        last_player = player['player_name']
    plt.scatter(x=graph_inputs['fate'], y=graph_inputs['stat'])
    plt.xlabel('Fate')
    plt.ylabel(statistic)
    chart_bytes = BytesIO()
    plt.savefig(chart_bytes, format='jpg')
    plt.close()
    chart_bytes.seek(0)
    chart_base64 = base64.b64encode(chart_bytes.read())
    chart_bytes.close()
    return render_template('fate_scatter.html',title=f"{statistic} compared to Fate in season {season+1}", graph=chart_base64.decode('utf8'))

#@app.route("/review")

#MalikID = '1301ee81-406e-43d9-b2bb-55ca6e0f7765'
#hist = get_full_player_history(MalikID)
#fate_hist = fate_filtered_history(hist)
#for entry in fate_hist:
#    print(entry)


#league_fate = []
#idlist = get_player()
#for player in idlist:
#    print(player["player_name"])
#    hist = get_full_player_history(player["player_id"])
#    fate_hist = fate_filtered_history(hist)
#    if len(fate_hist) > 1:
#        for entry in fate_hist:
#            league_fate.append(entry)

#with open("fate.txt", "w") as text_file:
#    for entry in league_fate:
#        text_file.write(str(entry))


if __name__ == "__main__":
    # Used when running locally only.
    # When deploying to Google AppEngine, a webserver process will
    # serve your app.
    app.run(host="localhost", port=8080, debug=True)
