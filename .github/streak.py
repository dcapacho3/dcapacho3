"""Write a commit streak card that counts days in the owner's timezone."""

import json
import os
import sys
import urllib.request
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

TZ = ZoneInfo(os.environ.get("STREAK_TZ", "America/Bogota"))
# Looks back one year only, so a streak longer than that shows as one year.
DAYS_BACK = 365
QUERY = """
query($cursor: String, $since: GitTimestamp!) {
  viewer {
    id
    repositories(first: 50, after: $cursor, ownerAffiliations: [OWNER, COLLABORATOR]) {
      pageInfo { hasNextPage endCursor }
      nodes { defaultBranchRef { target { ... on Commit {
        history(first: 100, since: $since, author: {id: "%s"}) { nodes { committedDate } }
      } } } }
    }
  }
}
"""


def graphql(query, variables):
    req = urllib.request.Request(
        "https://api.github.com/graphql",
        json.dumps({"query": query, "variables": variables}).encode(),
        {"Authorization": f"bearer {os.environ['GH_TOKEN']}"},
    )
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.load(resp)
    if "errors" in data:
        sys.exit(f"GitHub API error: {data['errors']}")
    return data["data"]["viewer"]


def commit_days(since):
    viewer_id = graphql("{ viewer { id } }", {})["id"]
    days, total, cursor = set(), 0, None
    while True:
        page = graphql(QUERY % viewer_id, {"cursor": cursor, "since": since})["repositories"]
        for repo in page["nodes"]:
            branch = repo["defaultBranchRef"]
            if not branch:
                continue
            for node in branch["target"]["history"]["nodes"]:
                utc = datetime.fromisoformat(node["committedDate"].replace("Z", "+00:00"))
                days.add(utc.astimezone(TZ).date())
                total += 1
        if not page["pageInfo"]["hasNextPage"]:
            return days, total
        cursor = page["pageInfo"]["endCursor"]


def streaks(days, today):
    # Today without a commit yet does not break the current streak.
    day = today if today in days else today - timedelta(days=1)
    current = 0
    while day in days:
        current += 1
        day -= timedelta(days=1)
    longest = run = 0
    prev = None
    for d in sorted(days):
        run = run + 1 if prev and d - prev == timedelta(days=1) else 1
        longest = max(longest, run)
        prev = d
    return current, longest


def card(total, current, longest, today):
    ring = 2 * 3.14159 * 42
    fill = ring * min(current / longest, 1) if longest else 0

    def side(x, big, label):
        return (
            f'<text x="{x}" y="92" text-anchor="middle" font-size="32" font-weight="700" fill="#e6edf3">{big}</text>'
            f'<text x="{x}" y="118" text-anchor="middle" font-size="13" fill="#8b949e">{label}</text>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" '
        'font-family="Segoe UI, Ubuntu, Helvetica, sans-serif">'
        '<defs><linearGradient id="g" x1="0" y1="0" x2="1" y2="1">'
        '<stop offset="0" stop-color="#00f7ff"/><stop offset="1" stop-color="#a371f7"/></linearGradient></defs>'
        '<rect x="0.5" y="0.5" width="494" height="194" rx="10" fill="#0d1117" stroke="#30363d"/>'
        '<line x1="165" y1="40" x2="165" y2="140" stroke="#21262d"/>'
        '<line x1="330" y1="40" x2="330" y2="140" stroke="#21262d"/>'
        + side(82, total, "Commits, last year")
        + '<circle cx="247" cy="82" r="42" fill="none" stroke="#21262d" stroke-width="7"/>'
        f'<circle cx="247" cy="82" r="42" fill="none" stroke="url(#g)" stroke-width="7" stroke-linecap="round" '
        f'stroke-dasharray="{fill:.1f} {ring:.1f}" transform="rotate(-90 247 82)"/>'
        f'<text x="247" y="94" text-anchor="middle" font-size="34" font-weight="700" fill="#e6edf3">{current}</text>'
        '<text x="247" y="148" text-anchor="middle" font-size="13" font-weight="600" fill="#00f7ff">Current streak</text>'
        + side(412, longest, "Longest streak")
        + f'<text x="247" y="180" text-anchor="middle" font-size="11" fill="#6e7681">'
        f"{today:%b} {today.day} - counted in {TZ.key}</text></svg>"
    )


if __name__ == "__main__":
    now = datetime.now(timezone.utc)
    since = (now - timedelta(days=DAYS_BACK)).strftime("%Y-%m-%dT%H:%M:%SZ")
    found, count = commit_days(since)
    today = now.astimezone(TZ).date()
    cur, best = streaks(found, today)
    with open(sys.argv[1], "w", encoding="utf-8") as out:
        out.write(card(count, cur, best, today))
    print(f"commits={count} current={cur} longest={best}")
