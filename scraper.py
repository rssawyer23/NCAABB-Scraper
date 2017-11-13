import csv
import json
import requests

url = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event=400947324"
output_file = "Data/testfile.csv"


# Getting general info regarding the team for identification
def get_team_info(team):
    return_string = "%s,%s," % (team['shortDisplayName'], team['id'])
    return return_string


# Getting values of stat categories and returning as dictionary and list
def get_team_statistics(stat_list):
    return_dict = dict()
    return_string = ""
    for s in stat_list:
        if "Made-Attempted" not in s['label']:
            return_dict[s['label']] = s['displayValue']
            return_string += "%s," % s['displayValue']
        else:
            prefix = s['label'].split(' ')[0]
            made, attempted = s['displayValue'].split("-")
            return_dict["%s-Made" % prefix] = made
            return_dict["%s-Attempted" % prefix] = attempted
            return_string += "%s,%s," % (made, attempted)
    return return_dict, return_string


# Generating header from the stat list labels using splits on made-attempted
def generate_header(stat_list):
    header_string = "Name,id,FinalScore,"
    for s in stat_list:
        if "Made-Attempted" not in s['label']:
            header_string += "%s," % s['label']
        else:
            prefix = s['label'].split(" ")[0]
            header_string += "%s-Made,%s-Attempted," % (prefix, prefix)
    return_string = ""
    for loc in ["Home","Away"]:
        for s in header_string[:-1].split(","):
            return_string += "%s-%s," % (loc, s)
    return_string += "Venue,City,State,Zip,Attendance,Referees"
    return "GameID," + return_string+"\n"


# Function for getting additional game details from json fail
def get_game_info_extras(data_dict):
    try:
        venue = data_dict['gameInfo']['venue']['shortName']
        city = data_dict['gameInfo']['venue']['address']['city']
        state = data_dict['gameInfo']['venue']['address']['state']
        zip_code = str(data_dict['gameInfo']['venue']['address']['zipCode'])
        attendance = str(data_dict['gameInfo']['attendance'])
        ref_string = ""
        for o in data_dict['gameInfo']['officials']:
            ref_string += "%s-" % (o['displayName'])
        extra_string = "%s,%s,%s,%s,%s,%s" % (venue, city, state, zip_code, attendance, ref_string)
    except KeyError:
        extra_string = "NaN,NaN,NaN,NaN,NaN,NaN"
    return extra_string[:-1]


# Wrapper which takes game event url from espn api and returns output string
def convert_game_to_string(url, get_header=False):
    r = requests.get(url)
    game_id = r.json()['header']['id'] + ","
    if get_header:
        header = generate_header(r.json()['boxscore']['teams'][1]['statistics'])
    else:
        header = None
    home_info = get_team_info(r.json()['boxscore']['teams'][1]['team'])
    home_stats_dict, home_stats_str = get_team_statistics(r.json()['boxscore']['teams'][1]['statistics'])
    home_score = str(r.json()['plays'][-1]['homeScore']) + ","
    away_info = get_team_info(r.json()['boxscore']['teams'][0]['team'])
    away_stats_dict, away_stats_str = get_team_statistics(r.json()['boxscore']['teams'][0]['statistics'])
    away_score = str(r.json()['plays'][-1]['awayScore']) + ","
    output_string = game_id + home_info + home_score + home_stats_str + away_info + away_score + away_stats_str
    output_string += get_game_info_extras(r.json()) + "\n"
    return output_string, header

if __name__ == "__main__":
    output_string, header = convert_game_to_string(url, get_header=True)
    with open(output_file, 'w') as f:
        f.write(header)
        f.write(output_string)
