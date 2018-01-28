import csv
import json
import requests
from os.path import isfile
import pandas as pd

#url = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event=400947324"
TEST_GAME_URL = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event=400986636"
GAME_URL_TEMPLATE = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/summary?event=%s"
# date_url = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&dates=20161111&limit=300"
DATE_URL_TEMPLATE = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=50&dates=%s%s%s&limit=300"
TOURNEY_DATE_URL_TEMPLATE = "http://site.api.espn.com/apis/site/v2/sports/basketball/mens-college-basketball/scoreboard?groups=100&dates=%s%s%s&limit=300"
# output_file = "Data/testfile.csv"

TEST_NBA_GAME_URL = 'http://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=400975049'
NBA_GAME_URL_TEMPLATE = 'http://site.api.espn.com/apis/site/v2/sports/basketball/nba/summary?event=%s'
NBA_DATE_URL_TEMPLATE = "http://site.api.espn.com/apis/site/v2/sports/basketball/nba/scoreboard?dates=%s%s%s&limit=30"


# Function for getting home and away scores by quarter
def get_quarter_scores(play_list):
    current_quarter = 1
    current_score = (0,0)
    home_quarters = []
    away_quarters = []
    for p in play_list:
        if p['period']['number'] != current_quarter and p['period']['number'] <= 4:
            away_quarters.append(str(current_score[0]))
            home_quarters.append(str(current_score[1]))
            current_quarter = p['period']['number']
        current_score = (p['awayScore'], p['homeScore'])
    return ",".join(home_quarters)+",", ",".join(away_quarters)+","


# Reformatting dates to be compatible with ESPN URL formats, then putting in template
def format_date(day, month, year, tournament=False, nba=False):
    if len(str(day)) < 2:
        day = "0%d" % day
    if len(str(month)) < 2:
        month = "0%d" % month
    if nba:
        date_url = NBA_DATE_URL_TEMPLATE % (year, month, day)
    elif not tournament:
        date_url = DATE_URL_TEMPLATE % (year, month, day)
    else:
        date_url = TOURNEY_DATE_URL_TEMPLATE % (year, month, day)
    return date_url


# Get a list of game summary urls to pass to individual game scraper from a date
def get_urls_from_date(day, month, year, show=False, nba=False):
    date_url = format_date(day, month, year, tournament=False, nba=nba)
    r = requests.get(date_url)
    try:
        game_url_template = NBA_GAME_URL_TEMPLATE if nba else GAME_URL_TEMPLATE
        game_urls = [game_url_template % e['id'] for e in r.json()['events']]
        if month == 3 or month == 4:  # March Madness Final Four can spill into April
            t_date_url = format_date(day, month, year, tournament=True, nba=nba)
            r = requests.get(t_date_url)
            game_urls += [game_url_template % e['id'] for e in r.json()['events']]
        if show:
            "%d games found for %s-%s-%s" % (len(game_urls), month, day, year)
    except json.decoder.JSONDecodeError:
        print("JSONDecodeError for %s-%s-%s" % (month, day, year))
        game_urls = []
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
def generate_header(stat_list, nba=False):
    header_string = "Name,id,Rank,FinalScore,"  # List of columns gathered for home and away teams
    if nba:
        spread = "Spread,"
        header_string += "1stQ,2ndQ,3rdQ,"
    else:
        spread = "Spread,OverUnder,"
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
    return_string += "Neutral,Conference,Venue,City,State,Zip,Capacity,Attendance,AttendanceRatio,Referees"  # Extra columns not specific to home or away team but specific to game
    return "GameID,Date," + spread + return_string+"\n"


# Function for getting additional game details from json
def get_game_info_extras(data_dict, show=False):
    try:
        venue = data_dict['gameInfo']['venue']['shortName']
        city = data_dict['gameInfo']['venue']['address']['city']
        state = data_dict['gameInfo']['venue']['address']['state']
        try:
            zip_code = str(data_dict['gameInfo']['venue']['address']['zipCode'])
        except KeyError:
            zip_code = "NaN"
        capacity = data_dict['gameInfo']['venue']['capacity']
        attendance = data_dict['gameInfo']['attendance']
        try:
            attendance_ratio = "%.4f" % (attendance / float(capacity))
        except ZeroDivisionError:
            attendance_ratio = "0.0"
        ref_string = ""
        for o in data_dict['gameInfo']['officials']:  # Not sure if this is variable length, so treating all refs as one hyphenated entry
            ref_string += "%s-" % (o['displayName'].replace(",", ""))
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


def _get_rank(team):
    try:
        rank = team['rank']
    except KeyError:
        rank = "0"
    return str(rank)+","


def _get_team_ranks(game_json):
    """Return the away and home rankings of the competing teams"""
    try:
        home = game_json['header']['competitions'][0]['competitors'][0]
        away = game_json['header']['competitions'][0]['competitors'][1]
        home_rank = _get_rank(home)
        away_rank = _get_rank(away)
        return home_rank, away_rank
    except KeyError:
        return '-1', '-1'
    except IndexError:
        return '-1', '-1'


def _get_neutral(game_json):
    try:
        neutral = game_json['header']['competitions'][0]['neutralSite']
        return str(neutral) + ","
    except KeyError:
        return "NaN,"
    except IndexError:
        return "NaN,"


def _get_conf_game(game_json):
    try:
        conf = game_json['header']['competitions'][0]['conferenceCompetition']
        return str(conf) +","
    except KeyError:
        return "NaN,"
    except IndexError:
        return "NaN,"


def _get_betting_info(game_json):
    try:
        spread = game_json['pickcenter'][0]['spread']
        over_under = game_json['pickcenter'][0]['overUnder']
        return str(spread)+",", str(over_under)+","
    except KeyError:
        return "NaN,", "NaN,"
    except IndexError:
        return "NaN,", "NaN,"


# Wrapper which takes game event url from espn api and returns output string
def convert_game_to_string(url, date_string, show=False, nba=False):
    try:
        r = requests.get(url)
        game_id = r.json()['header']['id'] + ","
        home_info = get_team_info(r.json()['boxscore']['teams'][1]['team'])
        away_info = get_team_info(r.json()['boxscore']['teams'][0]['team'])

        home_stats_dict, home_stats_str = get_team_statistics(r.json()['boxscore']['teams'][1]['statistics'], show=show)
        away_stats_dict, away_stats_str = get_team_statistics(r.json()['boxscore']['teams'][0]['statistics'], show=show)

        home_score = calculate_score_from_dict(home_stats_dict) + ","
        away_score = calculate_score_from_dict(away_stats_dict) + ","

        if nba:
            try:
                spread = str(r.json()['pickcenter'][0]['spread']) + ","
            except KeyError:
                spread = "NaN,"
            except IndexError:
                spread = "NaN,"
            home_cumulative_quarters, away_cumulative_quarters = get_quarter_scores(r.json()['plays'])
            output_string = game_id + date_string + spread \
                            + home_info + home_score + home_cumulative_quarters + home_stats_str \
                            + away_info + away_score + away_cumulative_quarters + away_stats_str
        else:
            home_rank, away_rank = _get_team_ranks(r.json())
            neutral_site = _get_neutral(r.json())
            conference_game = _get_conf_game(r.json())
            home_spread, over_under = _get_betting_info(r.json())
            output_string = game_id + date_string + home_spread + over_under + home_info + home_rank + home_score + \
                            home_stats_str + away_info + away_rank + away_score + away_stats_str + \
                            neutral_site + conference_game
        output_string += get_game_info_extras(r.json(), show=show) + "\n"

        if home_stats_str == "" or away_stats_str == "":
            output_string = "INVALID"
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
        return False, None
    else:
        with open(output_filename, 'r') as ofile:
            header = ofile.readline()
            if len(header.split(",")) > 1 and header.split(",")[0] == "GameID":
                return True, header
            else:
                return False, None


def write_game_data_for_date_range(start_day, end_day, month, year, output_filename, show=False, nba=False):
    header_exists, header = detect_header(output_filename)
    last_date = "None"
    with open(output_filename, 'a') as f:
        if not header_exists:
            test_game_url = TEST_NBA_GAME_URL if nba else TEST_GAME_URL
            header = generate_header(requests.get(test_game_url).json()['boxscore']['teams'][1]['statistics'], nba=nba)
            f.write(header)
        for day in range(start_day, end_day + 1):  # Looping through days in range for the month
            date_game_urls = get_urls_from_date(day=day, month=month, year=year, show=show, nba=nba)  # Getting all game_urls for date
            for game_url in date_game_urls:  # Looping through all extracted game_urls
                output_string = convert_game_to_string(url=game_url,
                                                       date_string="%d-%d-%d," % (month, day, year),
                                                       show=show,
                                                       nba=nba)  # Getting data for each game_url
                if output_string != "INVALID":
                    f.write(output_string)  # Write the data from the game
                    last_date = "%d-%d-%d" % (month, day, year)
            if show:
                print("Finished %d-%d-%d" % (month, day, year))
    return last_date

if __name__ == "__main__":
    # Arguments for looping through dates
    start_year = 2017
    leap_year = 0  # set to 1 if (start_year + 1) is a leap year, 0 otherwise
    nba = False
    show = True

    # Should not need to change anything below this comment
    nba_date_tuples = [(start_year, 10, 24, 31),  # Typically NBA Only, set start_day to after preseason ends
                   (start_year, 11, 1, 30),
                   (start_year, 12, 1, 31),
                   (start_year+1, 1, 1, 31),
                   (start_year+1, 2, 1, 28 + leap_year),
                   (start_year+1, 3, 1, 31),
                   (start_year+1, 4, 1, 30),
                   (start_year+1, 5, 1, 31),  # NBA Only
                   (start_year+1, 6, 1, 30)]  # NBA Only

    # ncaa_date_tuples = [(start_year, 11, 1, 30),
    #                (start_year, 12, 1, 31),
    #                (start_year+1, 1, 1, 31),
    #                (start_year+1, 2, 1, 28 + leap_year),
    #                (start_year+1, 3, 1, 31),
    #                (start_year+1, 4, 1, 10)]

    ncaa_date_tuples = [(start_year+1, 1, 23, 27)]

    league_string = "NBA" if nba else "NCAABB"
    date_tuples = nba_date_tuples if nba else ncaa_date_tuples
    date_string = "%s%s" % (str(start_year)[-2:], str(start_year+1)[-2:])
    output_file = "C:/Users/robsc/Documents/Data and Stats/ScrapedData/%s/%s%s_ESPN.csv" % (league_string, league_string, date_string)

    for date_tuple in date_tuples:
        year = date_tuple[0]
        month = date_tuple[1]
        start_day = date_tuple[2]
        end_day = date_tuple[3]
        last_date_scraped = write_game_data_for_date_range(start_day=start_day,
                                                           end_day=end_day,
                                                           month=month,
                                                           year=year,
                                                           output_filename=output_file,
                                                           show=show,
                                                           nba=nba)
        if show:
            print("Last date scraped %s" % last_date_scraped)

    # Checking for and removing duplicates
    data = pd.read_csv(output_file)
    data = data.drop_duplicates(subset=['GameID'])
    data.to_csv(output_file, index=False)
