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
        self.fateChange = "Pre-change."
        self.name = dict["data"]["name"]
        self.time = dict["lastSeen"]
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
                self.fate = float(dict["data"]["fate"])
            else:
                self.fate = "NONE"
        else:
            self.fate = "NOT YET TRACKED"
        self.modifications = []
        for key in ["gameAttr","permAttr","seasAttr","weekAttr"]:
            if key in dict["data"]:
                for mod in dict["data"][key]:
                    self.modifications.append(mod)
    def __str__(self):
        return f"""{self.name}   ({self.time})
        ID: {self.id}
        Team ID: {self.teamID}
        Pregame ritual: {self.ritual}
        Modifications: {self.modifications}
        Fate: {self.fate}
        Reason for change to Fate: {self.fateChange}\n"""

class team_record():
    #A Blaseball team. Stores name & ID.
    def __init__(self, dict):
        self.name = dict["full_name"]
        self.id = dict["team_id"]
    def __str__(self):
        #Returns team name as string
        return self.name
    def __repr__(self):
        return self.name

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
        paramstr1 = urllib.parse.urlencode({'player': player.id, 'count': 1, 'before': player.time})
        paramstr2 = urllib.parse.urlencode({'player': player.id, 'count': 1, 'after': player.time})
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

def fate_filtered_history(list):
    output = []
    last_entry = None
    for entry in list:
        if entry.fate != "NOT YET TRACKED":
            if last_entry != None:
                if last_entry.fate != entry.fate:
                    if output == [] or output[-1].time != last_entry.time:
                        output.append(last_entry)
                    if 'ALTERNATE' in entry.modifications and 'ALTERNATE' not in last_entry.modifications:
                        entry.fateChange = "Stat randomization due to becoming an Alternate."
                    elif entry.teamID != last_entry.teamID:
                        entry.fateChange = "Fate reroll due to Feedback swap."
                    else:
                        feedback_doublecheck = roster_swap_doublecheck(entry)
                        if feedback_doublecheck:
                            entry.fateChange = "Fate reroll due to Feedback swap."
                        else:
                            entry.fateChange = "Outlier. Cause cannot be clearly determined."
                    output.append(entry)
            last_entry = entry
    return output

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

def summarize_player(player):
    if float(player['batting_stars']) >= 5.0:
        print(pretty(player))
        return f'----------------------------\nName: {player["player_name"]}\nTeam: {player["team"]}\nPregame Ritual: {player["ritual"]}\nBatting Stars: {player["batting_stars"]}\n'


"""
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
def league_list():
    app.logger.info("On Main Page!")
    title = 'Team IDs'
    #pulls team list for season 13, manually removes the Hall Stars and THE PODS as they're not active teams.
    #season 13 is used rather than the latest season to avoid unnecessarily pulling pre-historical teams.
    data = clean_team_list(13)
    for team in data:
        if team.name == "THE SHELLED ONE'S PODS" or team.name == "The Hall Stars":
            app.logger.info(f"***Removing {team} from roster")
            data.remove(team)
    return render_template('base_page.html',title=title,data=data)

@app.route("/groster")
def roster_printer():
    team = request.args.get("selected_team")
    print(team)
    app.logger.info(f"Getting roster for {team}")
    raw_roster = get_team_roster(team, includeShadows=True)
    clean_roster = [player_record(player) for player in raw_roster]
    return render_template('roster_return.html',title=f"Roster for the {team}",roster=clean_roster,team=team)

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
"""
MalikID = '1301ee81-406e-43d9-b2bb-55ca6e0f7765'
hist = get_full_player_history(MalikID)
fate_hist = fate_filtered_history(hist)
for entry in fate_hist:
    print(entry)
"""

league_fate = []
idlist = clean_team_list(13)
print("Got team list!")
for team in idlist:
    print(team.name)
    roster = get_team_roster(team.id)
    for player in roster:
        print(player["player_name"])
        hist = get_full_player_history(player["player_id"])
        fate_hist = fate_filtered_history(hist)
        if len(fate_hist) > 1:
            for entry in fate_hist:
                league_fate.append(entry)

with open("fate.txt", "w") as text_file:
    for entry in league_fate:
        text_file.write(str(entry))

"""
if __name__ == "__main__":
    # Used when running locally only.
    # When deploying to Google AppEngine, a webserver process will
    # serve your app.
    app.run(host="localhost", port=8080, debug=True)
"""
