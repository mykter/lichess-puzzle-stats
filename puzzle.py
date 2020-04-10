#!/use/bin/env python3

import sys
import os
import logging
import json
import time
import argparse
import datetime
import random

import numpy
import matplotlib.pyplot as plt
from boltons.fileutils import atomic_save
import berserk
from berserk import exceptions

client = berserk.Client()
logger = logging.Logger(__name__)
logger.addHandler(logging.StreamHandler())


def save(path, data):
    with atomic_save(path, text_mode=True) as f:
        json.dump(data, f)


def retry(f):
    try:
        return f()
    except exceptions.ResponseError as err:
        if err.status_code == 429:
            logger.info("Got rate limited response, sleeping for 1 minute")
            time.sleep(61)
            return f()
        else:
            raise err


def get_tournament_users():
    logger.debug("Fetching tournaments")
    tournaments = retry(lambda: client.tournaments.get())
    users = set()
    for tstate in tournaments.values():
        for t in tstate:
            results = retry(lambda:
                            client.tournaments.stream_results(t['id']))
            users = users.union(set([r["username"] for r in results]))
            logger.debug(f"Got {len(users)} unique users...")

    return list(users)


def get_users(filename, cached_only):
    try:  # if we have it saved locally, just return that
        with open(filename, "r") as f:
            users = json.load(f)
            logger.info(f"Read {len(users)} cached users")
            return users
    except:
        if cached_only:
            raise
        return fetch_tournament_users(filename)


def fetch_tournament_users(filename):
    users = get_tournament_users()
    save(users)
    logger.info(f"Saved {len(users)} users")

    return users


def fetch_perf(data,  users, num, filename):
    checked = 0
    cached = 0
    withdata = 0
    for user in users:
        if checked >= num:
            break
        checked += 1

        # See if we already have this user's data from a previous run
        for (u, p) in data:
            if u == user:
                got = True
                cached += 1
                if p:
                    withdata += 1
                break
        else:
            h = get_puzzle_history(user)
            if h:
                withdata += 1
            # save this data even if the user doesn't have any puzzle history, so we don't check them again
            data.append((user, h))
            save(filename, data)

        if checked % 10 == 0:
            logger.debug(
                f"Checked {checked} users, got puzzle data for {withdata} of them ({cached} from cache; cache has {len(data)} users in total)")

    logger.info(f"Saved puzzle performance for {len(data)} users")

    return json.loads(json.dumps(data))  # ditch the class information


def parse_perf(data):
    # remove users without perf data and parse the date into a date type
    # note the month offset! From the API docs: "month starts at zero (January)."
    return [(user, [(datetime.date(d[0], d[1] + 1, d[2]), d[3]) for d in perf]) for (user, perf) in data if perf]


def get_puzzle_history(user):
    try:
        history = client.users.get_rating_history(user)
    except exceptions.ResponseError as err:
        if err.status_code == 404:
            logger.warning(f"User {user} doesn't exist, skipping")
            return None
        elif err.status_code == 429:
            logger.info("Got rate limited response, sleeping for 1 minute")
            time.sleep(61)
            history = client.users.get_rating_history(user)
        else:
            logger.fatal(f"Error retrieving data for {user}")
            raise err
    except Exception as err:
        logger.warning(f"Error retrieving data for {user}, skipping: {err}")
        return None

    perf = list(filter(lambda h: h['name'] == "Puzzles", history))
    if len(perf) == 0:
        return None
    return perf[0]['points']


def analyze(values, start, end, tolerance, ref_start, ref_end, ref_tolerance):
    deltas = [s-e for (s, e, _, _) in values]
    ref_deltas = [s-e for (_, _, s, e) in values]
    save("deltas.json", (start.isoformat(), end.isoformat(), tolerance.days, ref_start.isoformat(),
                         ref_end.isoformat(), ref_tolerance.days, deltas, ref_deltas))

    def period(ds):
        total = increased = decreased = inc_sum = dec_sum = 0
        for d in ds:
            total += d
            if d > 0:
                increased += 1
                inc_sum += d
            elif d < 0:
                decreased += 1
                dec_sum += d
        return int(total/len(ds)), increased/len(ds), int(inc_sum/increased), decreased/len(ds), int(dec_sum/decreased)

    for (label, ds) in [("period", deltas), ("reference period", ref_deltas)]:
        mean, inc, inc_mean, dec, dec_mean = period(ds)
        print(f"In {label} {inc:.0%} improved with a mean improvement of {inc_mean}, {dec:.0%} regressed with a mean decrease of {dec_mean}")
        print(f"Overall mean delta of {mean}")

    fig, (ax1, ax2) = plt.subplots(2, sharex=True, sharey=True)
    hist(ax1, deltas, 200, start, end)
    hist(ax2, ref_deltas, 200, ref_start, ref_end)
    plt.show()


def hist(ax, deltas, limit, start, end):
    d = list(filter(lambda v: abs(v) <= limit, deltas))
    n, bins, patches = ax.hist(x=d, bins=20, color='#0504aa',
                               rwidth=0.85)
    ax.grid(axis='y', alpha=0.75)
    ax.set_title(
        f'Change in puzzle performance from {start.isoformat()} to {end.isoformat()}')
    maxfreq = n.max()
    # Set a clean upper y-axis limit.
    ax.set_ylim(ymax=numpy.ceil(maxfreq / 10) *
                10 if maxfreq % 10 else maxfreq + 10)


def filter_perf(data, start, end, tolerance, ref_start, ref_end, ref_tolerance):
    """ extract puzzle scores with the specified tolerances for the (ref)start and (ref) end dates
    returns [(start score,end score, ref start score, ref end score)]
    """

    values = []
    for user, perf in data:
        closest_start = closest_ref_start = closest_end = closest_ref_end = (
            datetime.date.min, None)

        # Gather the scores that are closest to the date boundaries
        for day, score in perf:
            if abs(day - start) < abs(start - closest_start[0]):
                closest_start = (day, score)
            if abs(day - ref_start) < abs(ref_start - closest_ref_start[0]):
                closest_ref_start = (day, score)
            if abs(day - end) < abs(end - closest_end[0]):
                closest_end = (day, score)
            if abs(day - ref_end) < abs(ref_end - closest_ref_end[0]):
                closest_ref_end = (day, score)

        # Check these are within tolerance
        if closest_start[1] and (abs(closest_start[0]-start) <= tolerance) and \
                closest_ref_start[1] and (abs(closest_ref_start[0]-ref_start) <= tolerance) and \
                closest_end[1] and (abs(closest_end[0]-end) <= ref_tolerance) and \
                closest_ref_end[1] and (abs(closest_ref_end[0]-ref_end) <= ref_tolerance):
            values.append((closest_start[1], closest_end[1],
                           closest_ref_start[1], closest_ref_end[1]))

    logger.info(
        f"Saved {len(values)} users that meet the criteria to sample.json")
    save("sample.json", values)
    return values


def parseargs():
    parser = argparse.ArgumentParser(
        description='Analyze lichess puzzle performance change over time')

    parser.add_argument('command', choices=["fetch", "filter", "stats"])
    parser.add_argument('--userfile', default="users.json",
                        help='Filename for cached (json) usernames')
    parser.add_argument('--perffile', default="perf.json",
                        help='Filename for cached (json) user puzzle performance')
    parser.add_argument('--num-users', default=10000, type=int,
                        help='Number of users to process')

    parser.add_argument(
        '--start', type=datetime.date.fromisoformat, default="2020-03-05")
    parser.add_argument(
        '--end', type=datetime.date.fromisoformat, default="2020-04-05")
    parser.add_argument(
        '--ref_start', type=datetime.date.fromisoformat, default="2020-02-01")
    parser.add_argument(
        '--ref_end', type=datetime.date.fromisoformat, default="2020-03-01")

    return parser.parse_args()


if __name__ == "__main__":
    sys.excepthook = sys.__excepthook__  # disable apport
    logger.setLevel(logging.DEBUG)
    args = parseargs()

    tolerance = datetime.timedelta(days=7)
    ref_tolerance = datetime.timedelta(days=7)

    perf = None
    with open(args.perffile, "r") as f:
        perf = json.load(f)
        logger.info(f"Read {len(perf)} cached users' performance data")

    if args.command == "fetch":
        users = get_users(args.userfile)
        random.shuffle(users)
        perf = fetch_perf(perf, users, args.num_users,
                          args.perffile)
    elif args.command == "filter":
        values = filter_perf(parse_perf(perf), args.start, args.end, tolerance,
                             args.ref_start, args.ref_end, ref_tolerance)
    elif args.command == "stats":
        with open("sample.json", "r") as f:
            values = json.load(f)
        deltas = analyze(values, args.start, args.end, tolerance,
                         args.ref_start, args.ref_end, ref_tolerance)
