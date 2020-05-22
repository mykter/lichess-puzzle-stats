Performance statistics for lichess

Lichess.org is an amazing free and open source chess site. It has various built-in stats for the performance of players, exposes an API to query their database, and publishes datasets of games played.

This tool extends the built-in statistical analysis of lichess to do:
 1. Puzzle rating distribution
 2. Change in puzzle rating over time across large numbers of users

It is not a 'production quality' tool, but a hacky script written to answer some specific questions.

# Rating distribution
For reasons I'm not familiar with, Lichess doesn't tell you how your puzzle performance compares to other users, like it does for all your other performance scores. We derive it locally by downloading a sample of user's puzzle performance via the API, then comparing a given score against that distribution. To see where a puzzle rating of 2000 falls in a sample, run:

```
$ ./puzzle.py dist 2000 --perffile perf-65k-users-april-2020.json
Read 65528 cached users' performance data
Better than 83.24% of sampled users
```

# Change in puzzle ratings over time
During the start of the lockdown measures in response to the COVID-19 pandemic, I found my puzzle rating plumeted - I presume due to the stress of the situation. I wondered if the same had happened to others, and wrote this tool to try and answer the question.

We need a big sample of user's performance data to answer this. I obtained this by downloading the game database export for a recent month, and extract user IDs from that. Then randomly picked a subset of these users and queried the API to get their performance data. This takes a long time (days) to get a decent sample size.

The list of users active in March 2020 are included in this repo. To build your own list of active users, you can download a game database from https://database.lichess.org then do something like:

```
 bunzip2 --stdout /tmp/lichess_db_standard_rated_2020-03.pgn.bz2 |  grep -P '\[(White|Black) "\K[^"]+' -o > march-users
sort -u march-users
# then turn them into a json array, e.g. with a search/replace in a text editor or sed
```


Performance data for 65k users up to April 2020 is included in this repo. To get your own puzzle performance data for a sample of the users:

```
./puzzle.py -h      # show options (sample size, periods, filenames)
./puzzle.py fetch   # given a users file (such as the one included in the repo), get a sample of their performance data
```

Finally to analyze and visualize that data:

```
./puzzle.py filter  # extract puzzle scores for the given time period from the cached perf data
./puzzle.py stats   # from the cached filtered data, show mean increases, decreases, and a histogram of performance changes
```

So did lots of other people's score also suffer? Not really. The distribution of change in puzzle performance for March is wider than earlier months - i.e. people lost or gained more than usual - but there didn't seem to be an overall downwards trend. This isn't a particular high confidence conclusion - I'm no statistician, and there is at least one confounding factor I'm aware of: the puzzles ratings change in response to people solving them. If there was a widespread reduction in puzzle-solving capability, the rating system would dynamically adjust all puzzle's difficulty rating down, reducing the impact on everyone's performance score.
