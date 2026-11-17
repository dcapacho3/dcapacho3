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
    def col(x, big, label):
        return (
            f'<text x="{x}" y="90" text-anchor="middle" font-size="34" font-weight="700" fill="#c3e88d">{big}</text>'
            f'<text x="{x}" y="125" text-anchor="middle" font-size="14" fill="#a6accd">{label}</text>'
        )

    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="495" height="195" viewBox="0 0 495 195" '
        'font-family="Segoe UI, Ubuntu, sans-serif">'
        '<rect width="495" height="195" rx="4.5" fill="#292d3e"/>'
        + col(85, total, "Commits, last year")
        + col(247, current, "Current streak")
        + col(410, longest, "Longest streak")
        + f'<text x="247" y="175" text-anchor="middle" font-size="12" fill="#676e95">'
        f"{today:%b} {today.day}, {TZ.key}</text></svg>"
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
