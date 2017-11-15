import csv
import json
import requests
from os.path import isfile

#url = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event=400947324"
TEST_GAME_URL = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event=400986636"
GAME_URL_TEMPLATE = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event=%s"
# date_url = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&dates=20161111&limit=300"
DATE_URL_TEMPLATE = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&dates=%s%s%s&limit=300"
# output_file = "Data/testfile.csv"


# Reformatting dates to be compatible with ESPN URL formats, then putting in template
def format_date(day, month, year):
    if len(str(day)) < 2:
        day = "0%d" % day
    if len(str(month)) < 2:
        month = "0%d" % month
    return DATE_URL_TEMPLATE % (year, month, day)


# Get a list of game summary urls to pass to individual game scraper from a date
def get_urls_from_date(day, month, year, show=False):
    date_url = format_date(day, month, year)
    r = requests.get(date_url)
    game_urls = [GAME_URL_TEMPLATE % e['id'] for e in r.json()['events']]
    if show:
        "%d games found for %s-%s-%s" % (len(game_urls), month, day, year)
    return game_urls


# Getting general info regarding the team for identification
def get_team_info(team):
    return_string = "%s,%s," % (team['shortDisplayName'], team['id'])
    return return_string


# Getting values of stat categories and returning as dictionary and list
def get_team_statistics(stat_list, show=False):
    return_dict = dict()
    return_string = ""
    for s in stat_list:
        if "Made-Attempted" not in s['label']:  # Label is the official public ESPN category name for statistic
            return_dict[s['label']] = s['displayValue']  # displayValue is the value for the category shown in espn tables
            return_string += "%s," % s['displayValue']
        else:  # Made-Attempted recorded as an x-y pair, want these in separate columns
            prefix = s['label'].split(' ')[0]   # Formatted where type of Make-Attempt is given in characters before space
            made, attempted = s['displayValue'].split("-")
            return_dict["%s-Made" % prefix] = made
            return_dict["%s-Attempted" % prefix] = attempted
            return_string += "%s,%s," % (made, attempted)
    return return_dict, return_string


# Generating header from the stat list labels using splits on made-attempted
def generate_header(stat_list):
    header_string = "Name,id,FinalScore,"  # List of columns gathered for home and away teams
    for s in stat_list:  # Automatically determine what column names are from a statistics list
        if "Made-Attempted" not in s['label']:
            header_string += "%s," % s['label']
        else:
            prefix = s['label'].split(" ")[0]
            header_string += "%s-Made,%s-Attempted," % (prefix, prefix)
    return_string = ""  # Need statistics for both home and away teams
    for loc in ["Home","Away"]:
        for s in header_string[:-1].split(","):
            return_string += "%s-%s," % (loc, s)
    return_string += "Venue,City,State,Zip,Capacity,Attendance,AttendanceRatio,Referees"  # Extra columns not specific to home or away team but specific to game
    return "GameID,Date," + return_string+"\n"


# Function for getting additional game details from json
def get_game_info_extras(data_dict, show=False):
    try:
        venue = data_dict['gameInfo']['venue']['shortName']
        city = data_dict['gameInfo']['venue']['address']['city']
        state = data_dict['gameInfo']['venue']['address']['state']
        zip_code = str(data_dict['gameInfo']['venue']['address']['zipCode'])
        capacity = data_dict['gameInfo']['venue']['capacity']
        attendance = data_dict['gameInfo']['attendance']
        try:
            attendance_ratio = "%.4f" % (attendance / float(capacity))
        except ZeroDivisionError:
            attendance_ratio = "0.0"
        ref_string = ""
        for o in data_dict['gameInfo']['officials']:  # Not sure if this is variable length, so treating all refs as one hyphenated entry
            ref_string += "%s-" % (o['displayName'])
        extra_string = "%s,%s,%s,%s,%s,%s,%s,%s" % (venue, city, state, zip_code, str(capacity), str(attendance), attendance_ratio, ref_string)
    except KeyError:
        extra_string = "NaN,NaN,NaN,NaN,NaN,NaN,NaN,NaNx"
        if show:
            print("Error retrieving gameInfo for game")
    return extra_string[:-1]


# Function to calculate team score from box score data (if no play-by-play data this is necessary,
# cannot find final score in the json()
def calculate_score_from_dict(data_dict):
    try:
        threes = int(data_dict["3PT-Made"])
        twos = int(data_dict["FG-Made"]) - threes
        ones = int(data_dict["FT-Made"])
        score = threes * 3 + twos * 2 + ones * 1
    except KeyError:
        score = 0
    return str(score)


# Wrapper which takes game event url from espn api and returns output string
def convert_game_to_string(url, date_string, show=False):
    try:
        r = requests.get(url)
        game_id = r.json()['header']['id'] + ","
        home_info = get_team_info(r.json()['boxscore']['teams'][1]['team'])
        away_info = get_team_info(r.json()['boxscore']['teams'][0]['team'])

        home_stats_dict, home_stats_str = get_team_statistics(r.json()['boxscore']['teams'][1]['statistics'], show=show)
        away_stats_dict, away_stats_str = get_team_statistics(r.json()['boxscore']['teams'][0]['statistics'], show=show)

        home_score = calculate_score_from_dict(home_stats_dict) + ","
        away_score = calculate_score_from_dict(away_stats_dict) + ","

        output_string = game_id + date_string + home_info + home_score + home_stats_str + away_info + away_score + away_stats_str
        output_string += get_game_info_extras(r.json(), show=show) + "\n"
        if show:
            print(output_string)
    except KeyError:
        if show:
            print("KeyError experienced")
        output_string = "INVALID"
    except requests.exceptions.ConnectionError:
        if show:
            print("ConnectionError experienced")
        output_string = "INVALID"
    except json.decoder.JSONDecodeError:
        if show:
            print("JSON Decode Error")
        output_string = "INVALID"
    return output_string


# Function that determines if output file exists and first line matches proper header start
def detect_header(output_filename):
    if not isfile(output_filename):
        return False
    else:
        with open(output_filename, 'r') as ofile:
            header = ofile.readline()
            if len(header.split(",")) > 1 and header.split(",")[0] == "GameID":
                return True
            else:
                return False


def write_game_data_for_date_range(start_day, end_day, month, year, output_filename, show=False):
    header_exists = detect_header(output_filename)
    last_date = "None"
    with open(output_filename, 'a') as f:
        if not header_exists:
            header = generate_header(requests.get(TEST_GAME_URL).json()['boxscore']['teams'][1]['statistics'])
            f.write(header)
        for day in range(start_day, end_day + 1):  # Looping through days in range for the month
            date_game_urls = get_urls_from_date(day=day, month=month, year=year, show=show)  # Getting all game_urls for date
            for game_url in date_game_urls:  # Looping through all extracted game_urls
                output_string = convert_game_to_string(url=game_url,
                                                       date_string="%d-%d-%d," % (day, month, year),
                                                       show=show)  # Getting data for each game_url
                if output_string != "INVALID":
                    f.write(output_string)  # Write the data from the game
                    last_date = "%d-%d-%d" % (day, month, year)
            if show:
                print("Finished %d-%d-%d" % (day, month, year))
    return last_date

if __name__ == "__main__":
    # Arguments for looping through dates
    start_day = 1
    end_day = 31
    month = 1
    year = 2017
    show = True
    output_file = "Data/NCAABB1617_FullScores.csv"

    last_date_scraped = write_game_data_for_date_range(start_day=start_day,
                                                       end_day=end_day,
                                                       month=month,
                                                       year=year,
                                                       output_filename=output_file,
                                                       show=show)
    if show:
        print("Last date scraped %s" % last_date_scraped)
