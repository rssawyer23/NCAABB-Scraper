import requests
import unicodedata
import pathlib
from bs4 import BeautifulSoup
from shutil import copyfile

URL_TEST = "https://www.sportsbookreview.com/betting-odds/nba-basketball/1st-half/?date=20171203"
URL_TEMPLATE = "https://www.sportsbookreview.com/betting-odds/nba-basketball/1st-half/?date=%s%s%s"

NCAAB_URL_TEST = "https://www.sportsbookreview.com/betting-odds/ncaa-basketball/?date=20180102"
NCAAB_URL_TEMPLATE = "https://www.sportsbookreview.com/betting-odds/ncaa-basketball/?date=%s%s%s"


# Getting a team's scoreline of "Final,1stQ,2ndQ,3rdQ,4thQ," or "Final,1stH,2ndH" for ncaab=True
def parse_scores(score_div, ncaab=False):
    q_scores = score_div.find_all(name="span")
    max_length = 3 if ncaab else 5  # two halves plus ot for NCAAB, four quarters plus ot for NBA
    if len(q_scores) >= max_length:
        output_string = ",".join([e.get_text() for e in q_scores[:max_length]])
    else:
        print("Incorrect length or unexpected arguments for quarter scores")
        output_string = ",".join(["-1"] * max_length)
    return output_string


# Converts a specific book cell into a [home line, home payout] list
def convert_line(line):
    spreads = line.find_all(name="div")
    if len(spreads) != 2:
        print("Line Parse Error")
        home_spread = [0.1,0.1]
    else:
        try:
            text = unicodedata.normalize("NFKD", spreads[1].get_text())
            line = text.split(" ")[0]
            line = line.replace("1%s2" % u'\u2044', '.5')
            payout = text.split(" ")[1]
            try:
                line = float(line)
                payout = float(payout)
            except ValueError:
                line, payout = 0.1, 0.1
        except IndexError:
            line, payout = 0.1, 0.1

        home_spread = [line, payout]
    return home_spread


# Among the 10 books, determine which line most favors the home team
#  Uses the raw line value as 1st preference, i.e. -4 is preferred to -5 and +3 is preferred to +2.5
#  Uses payout for tie-breakers
#  Using 0.1 as an error code, ignoring these values
def _best_line(lines):
    best_line = [-999,-999]
    for line in lines:
        if line[0] > best_line[0] and line[0] != 0.1:
            best_line = list(line)
        elif line[0] == best_line[0] and line[1] > best_line[1] and line[1] != 0.1:
            best_line = list(line)
    return [str(e) for e in best_line]


# Same as _best_line but for the worst line for the home team
def _worst_line(lines):
    worst_line = [999,999]
    for line in lines:
        if line[0] < worst_line[0] and line[0] != 0.1:
            worst_line = list(line)
        elif line[0] == worst_line[0] and line[1] < worst_line[1] and line[1] != 0.1:
            worst_line = list(line)
    return [str(e) for e in worst_line]


# Convert each book cell into optimistic, bovada, and pessimistic lines
def parse_lines(line_list):
    lines = [convert_line(line) for line in line_list]
    optimistic_line = _best_line(lines)
    bovada_line = [str(e) for e in lines[4]]     # Bovada is always the 5th book listed (index = 4)
    if bovada_line[0] == "0.1":
        bovada_line = [str(e) for e in lines[3]]
    pessimistic_line = _worst_line(lines)
    line_string = "%s,%s,%s" % (",".join(optimistic_line), ",".join(bovada_line), ",".join(pessimistic_line))
    return line_string


def _parse_team(cell_text, ncaab=False):
    """Returns name of away or home team with rank separated for ncaab games"""
    return_name, return_rank = cell_text, "0"
    if ncaab:
        if "(" in cell_text.split(" ")[0]:
            return_name = cell_text[cell_text.index(")")+2:]
            rank_str = cell_text.split(" ")[0]
            return_rank = rank_str[rank_str.index("(")+1:rank_str.index(")")]
    return return_name, return_rank


# Given the game row, return the useful data in a csv string for output
def parse_game(game_div, ncaab=False):
    score_div = game_div.find(name="div", class_="scorebox odd")
    if score_div is None:
        score_div = game_div.find(name="div", class_="scorebox")
    try:
        scores = score_div.find_all(name="div", class_="score-periods")
        away_scores = parse_scores(scores[0], ncaab)
        home_scores = parse_scores(scores[1], ncaab)
    except AttributeError:
        away_scores = "-1,-1,-1,-1,-1"
        home_scores = "-1,-1,-1,-1,-1"

    team_div = game_div.find(name="div", class_="el-div eventLine-team")
    try:
        teams = team_div.find_all(name="div", class_="eventLine-value")
        away_team, away_rank = _parse_team(teams[0].get_text(), ncaab)
        home_team, home_rank = _parse_team(teams[1].get_text(), ncaab)
    except AttributeError:
        away_team, away_rank = "NaN", "NaN"
        home_team, home_rank = "NaN", "NaN"

    lines = game_div.find_all(name="div", class_="el-div eventLine-book")
    try:
        line_string = parse_lines(lines)
    except AttributeError:
        line_string = "0.1,0.1,0.1,0.1,0.1,0.1"
    if not ncaab:
        game_string = "%s,%s,%s,%s,%s" % (away_team, away_scores, home_team, home_scores, line_string)
    else:
        game_string = "%s,%s,%s,%s,%s,%s,%s" % \
                      (away_team, away_rank, away_scores, home_team, home_rank, home_scores, line_string)
    return game_string, away_team, home_team


# Converting a numerical date into the url and string date
def format_date(day, month, year, ncaab=False):
    if len(str(day)) < 2:
        day = "0%d" % day
    if len(str(month)) < 2:
        month = "0%d" % month
    if not ncaab:
        date_url = URL_TEMPLATE % (year, month, day)
    else:
        date_url = NCAAB_URL_TEMPLATE % (year, month, day)
    return date_url, "%s-%s-%s" % (month, day, year)


# Given a date, write all csv-lines of game spreads
def get_date_lines(day, month, year, output_filepath, prev_teams, ncaab=False, show=False):
    url, string_date = format_date(day, month, year, ncaab)
    todays_teams = []
    with open(output_filepath, 'a') as ofile:
        r = requests.get(url)
        bs = BeautifulSoup(r.content)
        event_table = bs.find_all(name="div", class_="eventLines")
        if len(event_table) >= 1:
            games = event_table[0].find_all(name="div", class_="event-holder holder-complete")
            for game in games:
                game_string, away_team, home_team = parse_game(game, ncaab)
                away_b2b_indicator = int(away_team in prev_teams)
                todays_teams.append(away_team)
                todays_teams.append(home_team)
                output_string = "%s,%s,%d\n" % (string_date, game_string, away_b2b_indicator)
                if show:
                    print(output_string.replace("\n", ""))
                ofile.write(output_string)
        else:
            print("Error with url from date: %s" % string_date)
    return todays_teams


if __name__ == "__main__":
    ncaab = True
    start_year = 2011
    leap_year = 1  # Set this to 1 if start_year+1 is a leap year
    output_filepath = "C:/Users/robsc/Documents/Data and Stats/ScrapedData/NCAABB/SBRLines/GameSpreads%s%s.csv" % (str(start_year)[-2:], str(start_year+1)[-2:])

    # If the data file is not detected, write a header for a new file
    if not pathlib.Path(output_filepath).is_file():
        with open(output_filepath, 'w') as ofile:
            if not ncaab:
                ofile.write("Date,Away-Name,Away-FinalScore,Away-1stQuarter,Away-2ndQuarter,Away-3rdQuarter,Away-4thQuarter,"
                            "Home-Name,Home-FinalScore,Home-1stQuarter,Home-2ndQuarter,Home-3rdQuarter,Home4thQuarter,"
                            "OptLine,OptPayout,BovLine,BovPayout,PesLine,PesPayout,Away-B2B-Indicator\n")
            else:
                ofile.write(
                    "Date,Away-Name,Away-APRank,Away-FinalScore,Away-1stHalf,Away-2ndHalf,"
                    "Home-Name,Home-APRank,Home-FinalScore,Home-1stHalf,Home-2ndHalf,"
                    "OptLine,OptPayout,BovLine,BovPayout,PesLine,PesPayout,Away-B2B-Indicator\n")

    # Dates to loop through for the nba, each tuple is a month of the NBA season
    # nba_date_tuples = [(start_year, 10, 30, 31),  # Typically NBA Only, set start_day to after preseason ends
    #                (start_year, 11, 1, 30),
    #                (start_year, 12, 1, 31),
    #                (start_year+1, 1, 1, 31),
    #                (start_year+1, 2, 1, 28 + leap_year),
    #                (start_year+1, 3, 1, 31),
    #                (start_year+1, 4, 1, 30),
    #                (start_year+1, 5, 1, 31),  # NBA Only
    #                (start_year+1, 6, 1, 30)]  # NBA Only

    nba_date_tuples = [(start_year, 10, 17, 31),  # Typically NBA Only, set start_day to after preseason ends
                   (start_year, 11, 1, 30),
                   (start_year, 12, 1, 6)]  # NBA Only

    ncaab_date_tuples = [(start_year, 11, 1, 30),
                    (start_year, 12, 1, 31),
                    (start_year+1, 1, 1, 31),
                    (start_year+1, 2, 1, 28 + leap_year),
                    (start_year+1, 3, 1, 31),
                    (start_year+1, 4, 1, 10)]

    days_teams = []
    date_tuples = ncaab_date_tuples if ncaab else nba_date_tuples

    for date_tuple in date_tuples:
        year = date_tuple[0]
        month = date_tuple[1]
        start_day = date_tuple[2]
        end_day = date_tuple[3]
        for day in range(start_day, end_day+1):
            days_teams = get_date_lines(day, month, year, output_filepath, days_teams, ncaab, show=True)

