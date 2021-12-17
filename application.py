from flask import Flask, render_template, request
import urllib.parse, urllib.request, urllib.error, json, logging, base64
import matplotlib.pyplot as plt
import numpy as np
from io import BytesIO

app = Flask(__name__)

def pretty(obj):
    #I stole this! (Thank you for making this it is very useful)
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
    #A Blaseball player, and all the relevant stats except vibes (since those change too frequently to be encapsulated by a static value) at a given time period.
    #Created using dicts returned by Chronicler.
    #placeholder fate values are wordy so that they can be directly read in the HTML and still flow well.
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
    #Stores name and ID for a blaseball team or location, as well as if it's a team or location.
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
    #Defines a team_record class object for a location (such as the hall of flame)
    area = {"full_name": name, "team_id": id, "team_current_status": None, "team_emoji": emoji}
    return team_record(area, type='area')

def get_player_history(id, page = None):
    #Get a page of player history updates from Chronicler.
    #Returns the pagination token for the next page alongside the data,
    #which can be fed back to the function as page to get the next page of updates.
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
    #Call chronicler records for before and after the Fate change and checks if there was a team change.
    #Chronicler doesn't track team as part of player records for earlier seasons,
    #But it DOES still have roster updates for those seasons.
    #So, cross-reference the roster-updates.
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
    #gets every page of stat updates for the player of the given ID.
    #Returns a flat list of dictionaries, as opposed to the nested mess directly returned by get_player_history.
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
    #Takes a player's stat updates as a list of dictionaries (as returned by get_full_player_history())
    #Returns a list with only the updates where Fate changed, as well as why said changes occured.
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
                                #Chronicler doesn't have proper records for feedback swaps involving these players.
                                #I have manually verified that all of their Fate changes coincide with a feedback swap.
                                entry.fateChange = "due to a Feedback swap."
                            else:
                                entry.fateChange = "due to... some other cause. (If you're seeing this, odds are that there's been an error.)"
                    output.append(entry)
            else:
                #Always append the first entry, to represent debut state
                output.append(entry)
            last_entry = entry
    #people's names change and I'd like to make sure I use the most recent name.
    output[0].name = input[-1].name
    return output

def get_players_seasonal(season = 23):
    #Gets the Blaseball Reference records for all players in a given season.
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
    #Gets the Blaseball Reference records for all players in a specific 'playerPool' category.
    #This defaults to getting all dead players, and that's all I use it for.
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
    #Gets the Blaseball Reference records for a given player.
    #This gets EVERY player if it doesn't get an ID. I don't use this in the final program, but it was helpful for testing.
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
    #Get the Blaseball Reference records for all the players on a specific team.
    #includeShadows sets whether or not to return reserve ("shadowed") players.
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
    #Returns the Blaseball Reference records for all the teams as of a specific season.
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
    #Returns the Blaseball Reference records for all the teams as of a specific season,
    #formatted as team_record objects.
    team_list = get_teams(season)
    clean_list = [team_record(team) for team in team_list]
    return clean_list

def get_player_stats(category, season, players):
    #Takes a type of stat (pitching or batting), a season, and a list of dictionaries of player stats as returned by Blaseball Reference.
    #Returns the corresponding performance stats for that season for all players inputted as a list of dictionaries.
    playerIds = ''
    i = 0
    for player in players:
        i+=1
        playerIds = playerIds+str(player['player_id'])+','
    try:
        app.logger.info(i)
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

@app.route("/")
def landing():
    #Home page
    title = 'HCDE 310 Final: Blaseball Vibes & Fate'
    return render_template('origin.html',title=title)

@app.route("/vteam")
def vleague_list():
    #Grab and display the teams in the league for user selection.
    title = 'Vibe Analysis Tool'
    data = clean_team_list()
    outdata = []
    for team in data:
        if team.name == "The Hall Stars":
            #The Hall Stars name has 'The' in it, unlike every other team. This fixes that so it fits into the templates right.
            team.name = "Hall Stars"
            app.logger.info(f"***Editing the Hall Stars!")
        if team.name != "Hall Stars" and team.status != 'active':
            #Only active teams from the list are displayed.
            #The Hall Stars are an exception to this, as their roster has seen actual play, unlike other inactive teams.
            app.logger.info(f"***Removing {team} from roster")
        else:
            app.logger.info(f"***{team} remains. They are {team.status}")
            outdata.append(team)
    #The Vault and the Hall of Flame are not proper teams, but I'd like the option to analyze players from them.
    #As such, area-type records for both are generated and added.
    outdata.append(area_record("Vault", "0x1F947", '698cfc6d-e95e-4391-b754-b87337e4d2a9'))
    outdata.append(area_record("Hall of Flame", "0x1f480", 'Underworld'))
    return render_template('vteam_select.html',title=title,data=outdata)

@app.route("/vroster")
def vroster_printer():
    #Gets the roster for the selected team/area and returns it for user selection.
    team = request.args.get("selected_team")
    app.logger.info(f"Getting roster for the {team}")
    if team == "Underworld":
        raw_roster = get_pooled_players()
        filter_roster = []
        for player in raw_roster:
            if player['team'] == 'null' or player['team'] == None:
                filter_roster.append(player)
        team = "Hall of Flame"
    else:
        #You can get the roster for all the other teams, including the Vault, by directly feeding it to Blaseball Reference. Convenient.
        filter_roster = get_team_roster(team, includeShadows=True)
    clean_roster = [player_record(player) for player in filter_roster]
    return render_template('vroster_return.html',title=f"Roster for the {team}",roster=clean_roster,team=team)

@app.route("/gvibes")
def vibe_charts():
    #Generates the chart of the selected player's vibes over the course of a hypothetical season.
    id = request.args.get("selected_player")
    player = player_record(get_player(id))
    #Vibes aren't stored on any accessible APIs, but its formula is visible on the front-end of the Blaseball website.
    #We can use this to recreate a player's vibes using stats that actually are stored.
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
    #This necessitates that I instead convert the image to a base64 string, which can be fed directly to the jinja template and then turned back into an image there.
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
    #Grab and display the teams in the league for user selection.
    title = 'Fate History Tool'
    data = clean_team_list()
    outdata = []
    for team in data:
        if team.name == "The Hall Stars":
            team.name = "Hall Stars"
            #The Hall Stars name has 'The' in it, unlike every other team. This fixes that so it fits into the templates right.
            app.logger.info(f"***Editing the Hall Stars!")
        if team.name != "Hall Stars" and team.status != 'active':
            #Only active teams from the list are displayed.
            #The Hall Stars are an exception to this, as their roster has seen actual play, unlike other inactive teams.
            app.logger.info(f"***Removing {team} from roster")
        else:
            app.logger.info(f"***{team} remains. They are {team.status}")
            outdata.append(team)
    #The Vault and the Hall of Flame are not proper teams, but I'd like the option to analyze players from them.
    #As such, area-type records for both are generated and added.
    outdata.append(area_record("Vault", "0x1F947", '698cfc6d-e95e-4391-b754-b87337e4d2a9'))
    outdata.append(area_record("Hall of Flame", "0x1f480", id = 'Underworld'))
    return render_template('fteam_select.html',title=title,data=outdata)

@app.route("/froster")
def froster_printer():
    #Gets the roster for the selected team/area and returns it for user selection.
    team = request.args.get("selected_team")
    print(team)
    app.logger.info(f"Getting roster for the {team}")
    #The Hall of Flame is not and never was a team. It does not have a roster that can be called.
    #Since it's just where dead players hang out, we instead just get a list of all deceased players without a proper team affiliation.
    #Yes, that's an issue. There are dead players who are still playing actively. It makes this rather annoying.
    if team == "Underworld":
        raw_roster = get_pooled_players()
        filter_roster = []
        for player in raw_roster:
            if player['team'] == 'null' or player['team'] == None:
                filter_roster.append(player)
        team = "Hall of Flame"
    else:
        #You can get the roster for all the other teams, including the Vault, by directly feeding it to Blaseball Reference. Convenient.
        filter_roster = get_team_roster(team, includeShadows=True)
    clean_roster = [player_record(player) for player in filter_roster]
    return render_template('froster_return.html',title=f"Roster for the {team}",roster=clean_roster,team=team)

@app.route("/fhist")
def fate_summary():
    #Get the selected player's history of Fate changes, and display the summary.
    player_id = request.args.get("selected_player")
    hist = get_full_player_history(player_id)
    fate_hist = fate_filtered_history(hist)
    return render_template('fate_history.html',title=f"Vibe summary for {fate_hist[0].name}",history=fate_hist, length = len(fate_hist))

@app.route("/fseason")
def scatter_definer():
    #Prompt the user to select a performance stat to analyze against and a season to draw data from.
    batter_stats = [('doubles', 'Doubles'),
    ('triples','Triples'),
    ('home_runs','Home Runs (HR)'),
    ('runs_batted_in','Runs batted in (RBI)'),
    ('walks','Walks (Bases on Balls)'),
    ('strikeouts','Strikeouts'),
    ('batting_average','Batting Average (BA)'),
    ('on_base_percentage','On Base Percentage (OBP)'),
    ('batting_average_risp','Batting Average with runners in scoring position (BA/RISP)'),
    ('slugging','Slugging Percentage (SLG)'),
    ('on_base_slugging','On Base plus Slugging Percentage (OPS)')]
    pitcher_stats = [("win_pct", 'Winning percentage (W-L%)'),
    ("earned_run_average",'Earned Run Average (ERA)'),
    ("walks_per_9",'Walks per 9 innings'),
    ("hits_per_9",'Hits per 9 innings'),
    ("strikeouts_per_9",'Strikeouts per 9 innings'),
    ("home_runs_per_9",'Home Runs per 9 innings'),
    ("whip",'Walks and Hits per inning pitched (WHIP)'),
    ("strikeouts_per_walk",'Strikeout-to-Walk ratio')]
    return render_template('scatter_definer.html',title=f"Fate Comparison Tool",batter_stats=batter_stats,pitcher_stats=pitcher_stats)

@app.route("/fscatter")
def fate_scatter():
    #get all players, filter out to only include players in correct position for stat, get stats for all players
    batter_stats = [('doubles', 'Doubles'),
    ('triples','Triples'),
    ('home_runs','Home Runs (HR)'),
    ('runs_batted_in','Runs batted in (RBI)'),
    ('walks','Walks (Bases on Balls)'),
    ('strikeouts','Strikeouts'),
    ('batting_average','Batting Average (BA)'),
    ('on_base_percentage','On Base Percentage (OBP)'),
    ('batting_average_risp','Batting Average with runners in scoring position (BA/RISP)'),
    ('slugging','Slugging Percentage (SLG)'),
    ('on_base_slugging','On Base plus Slugging Percentage (OPS)')]
    pitcher_stats = [("win_pct", 'Winning percentage (W-L%)'),
    ("earned_run_average",'Earned Run Average (ERA)'),
    ("walks_per_9",'Walks per 9 innings'),
    ("hits_per_9",'Hits per 9 innings'),
    ("strikeouts_per_9",'Strikeouts per 9 innings'),
    ("home_runs_per_9",'Home Runs per 9 innings'),
    ("whip",'Walks and Hits per inning pitched (WHIP)'),
    ("strikeouts_per_walk",'Strikeout-to-Walk ratio')]
    raw_batter_stats = ['doubles','triples','home_runs','runs_batted_in','walks', 'strikeouts', 'batting_average', 'on_base_percentage', 'batting_average_risp', 'slugging', 'on_base_slugging']
    statistic = request.args.get("selected_stat")
    season = int(request.args.get("season"))-1
    #get all players for the chosen season
    league = get_players_seasonal(season)
    playersfate = []
    #Go over the list of players. Only keep those who are in the correct position on the main roster.
    if statistic in raw_batter_stats:
        category = 'batting'
        for player in league:
            if player['position_type'] == 'BATTER' and player["current_location"] == "main_roster":
                playersfate.append(player)
        for term in batter_stats:
            if term[0] == statistic:
                cleanstat = term[1]
    else:
        category = 'pitching'
        for player in league:
            if player['position_type'] == 'PITCHER' and player["current_location"] == "main_roster":
                playersfate.append(player)
        for term in pitcher_stats:
            if term[0] == statistic:
                cleanstat = term[1]
    #Get the stats for all remaining players.
    playerstats = get_player_stats(category, season, playersfate)
    #Sort both lists by player id to ensure that the right values are paired together.
    playersfate = sorted(playersfate, key = lambda i: i['player_id'], reverse=True)
    playerstats = sorted(playerstats, key = lambda i: (i['player_id'], float(i[statistic]or 0.0)), reverse=True)
    #matplotlib can't handle lists of dictionaries, so convert both of them into a dictionary of lists.
    graph_inputs = {'fate':[], 'stat':[]}
    active = []
    last_player = None
    
    for player in playerstats:
        #the stat list includes records for all the teams a player played for separate from each other. Only the highest stat is kept.
        if last_player == player['player_id']:
            graph_inputs['stat'][-1]=(float(player[statistic] or 0.0))
        else:
            graph_inputs['stat'].append(float(player[statistic] or 0.0))
        last_player = player['player_id']
        active.append(player['player_id'])
    for player in playersfate:
        if player['player_id'] in active:
            graph_inputs['fate'].append(player['fate'])
    app.logger.info(len(playerstats))
    app.logger.info(len(graph_inputs['stat']))
    with open("test.txt", "w") as text_file:
        text_file.write(pretty(graph_inputs))
    #Finally graph the thing and feed it to the template.
    plt.scatter(x=graph_inputs['fate'], y=graph_inputs['stat'])
    plt.xlabel('Fate')
    plt.ylabel(cleanstat)
    chart_bytes = BytesIO()
    plt.savefig(chart_bytes, format='jpg')
    plt.close()
    chart_bytes.seek(0)
    chart_base64 = base64.b64encode(chart_bytes.read())
    chart_bytes.close()
    return render_template('fate_scatter.html',title=f"{statistic} compared to Fate in season {season+1}", graph=chart_base64.decode('utf8'))

if __name__ == "__main__":
    app.run(host="localhost", port=8080, debug=True)
