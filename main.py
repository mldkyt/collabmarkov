import datetime
import os.path
import re
import typing
from os import getenv

import bs4
import markovify
from dotenv import load_dotenv
from mastodon import Mastodon
from sqlalchemy import select, insert, delete, update

from database import engine, posts_table, get_setting, follows_table, last_scan_table

load_dotenv()

FILTER_KEYWORDS = [i for i in getenv("FILTER_KEYWORDS", "").split(",") if len(i.strip()) > 0]

SANITIZE_MENTIONS = getenv("SANITIZE_MENTIONS", "1") == "1"
SANITIZE_HASHTAGS = getenv("SANITIZE_HASHTAGS", "1") == "1"

REMOVE_MENTIONS = getenv("REMOVE_MENTIONS", "0") == "1"
REMOVE_HASHTAGS = getenv("REMOVE_HASHTAGS", "0") == "1"

DEBUG = getenv("DEBUG", "0") == "1"

# borrowed from https://stackoverflow.com/questions/30337528/make-beautifulsoup-handle-line-breaks-as-a-browser-would
def get_text(tag: bs4.Tag) -> str:
    _inline_elements = {"a","span","em","strong","u","i","font","mark","label",
    "s","sub","sup","tt","bdo","button","cite","del","b","a","font",}

    def _get_text(tag: bs4.Tag) -> typing.Generator:
        for child in tag.children:
            if isinstance(child, bs4.Tag):
                # if the tag is a block type tag then yield new lines before after
                is_block_element = child.name not in _inline_elements
                if is_block_element:
                    yield "\n"
                yield from ["\n"] if child.name == "br" else _get_text(child)
                if is_block_element:
                    yield "\n"
            elif isinstance(child, bs4.NavigableString):
                yield child.string

    return "".join(_get_text(tag))

if not os.path.exists("data"):
    os.mkdir("data")

mastodon = Mastodon(access_token='data/pytooter_usercred.secret')

me = mastodon.me()

for i in mastodon.pagination_iterator(mastodon.account_followers(me)):
    print(i.display_name)

    if '#nomarkov' in i.note.lower():
        continue

    with engine.begin() as c:
        rel = mastodon.account_relationships(i)[0]

        if not rel.following and not rel.requested:
            while True:
                try:
                    mastodon.account_follow(i, reblogs=False)
                    c.execute(
                        insert(follows_table)
                        .values(id=i.id, acct=i.acct)
                    )
                    mastodon.status_post(f"@{i.acct} Welcome to Collaborative Markov Bot!"
                                         f"This bot will now use your posts for the corpus. "
                                         f"**Only posts that are public and don't have CW are used.** "
                                         f"The behaviour of this can be changed by replying to this post with `help`.",
                                         visibility='direct')
                    break
                except Exception as e:
                    print(f"failed to follow {i.acct}: {str(e)}")
                    pass

        try:
            a = c.execute(
                select(last_scan_table.c.last_scan)
                .where((last_scan_table.c.id == i.id))
            ).fetchone()
            if a is None:
                c.execute(
                    insert(last_scan_table)
                    .values(id=i.id, last_scan=datetime.datetime.now())
                )

                do_full_scan = False
            else:
                if (datetime.datetime.now() - a[0]).total_seconds() > 1209600:
                    do_full_scan = True
                    c.execute(
                        update(last_scan_table)
                        .where((last_scan_table.c.id == i.id))
                        .values(last_scan=datetime.datetime.now())
                    )

            for j in mastodon.pagination_iterator(mastodon.account_statuses(i, exclude_reblogs=True)):
                a = c.execute(
                    select(posts_table.c.id)
                    .where((posts_table.c.id == str(j.id)))
                ).fetchone()
                if a is not None:
                    if do_full_scan:
                        continue
                    else:
                        break

                soup = bs4.BeautifulSoup(j.content)
                text = get_text(soup)

                has_cw = len(j.spoiler_text) > 0

                c.execute(
                    insert(posts_table)
                    .values(id=str(j.id), text=text, has_cw=has_cw, visibility=j.visibility, author=i.acct)
                )
        except Exception as e:
            print(f"failed to query posts for {i.acct}: {str(e)}")
            pass

with engine.begin() as c:
    a = c.execute(
        select(follows_table.c.id, follows_table.c.acct)
    ).all()

    for i in a:
        rel = mastodon.account_relationships(i[0])[0]

        if not rel.followed_by:
            try:
                if rel.following:
                    mastodon.account_unfollow(i[0]) # this is not as important as following users
                    # so we can safely unfollow a user on the second hour

                with engine.begin() as c:
                    c.execute(
                        delete(posts_table)
                        .where((posts_table.c.author == i[1]))
                    )
                    c.execute(
                        delete(follows_table)
                        .where((follows_table.c.id == i[0]))
                    )

            except Exception as e:
                print(f"failed to unfollow {i[0]}: {str(e)}")
                pass

posts = []

with engine.begin() as c:
    a = c.execute(
        select(posts_table.c.text, posts_table.c.has_cw, posts_table.c.visibility, posts_table.c.author)
    ).all()

    settings_cache = {}

    for i in a:
        if f"{i[3]}:cw" not in settings_cache:
            settings_cache[f"{i[3]}:cw"] = get_setting(c, i[3], "cw", "0") == "0"

        if f"{i[3]}:vis" not in settings_cache:
            settings_cache[f"{i[3]}:vis"] = get_setting(c, i[3], "unlisted", "0")

        if settings_cache[f"{i[3]}:cw"] and i[1]:
            continue

        vis = settings_cache[f"{i[3]}:vis"]
        if vis == "0" and i[2] != "public":
            continue
        elif vis == "1" and i[2] not in ["public", "unlisted"]:
            continue

        for j in FILTER_KEYWORDS:
            if j.lower() in i[0].lower():
                continue

        posts.append(i[0])

if len(posts) == 0:
    print("No posts")
    exit(0)

posts = "\n".join(posts)

markov = markovify.NewlineText(posts)
markov.compile(inplace=True)

output = None
while output is None:
    output = markov.make_sentence()

if SANITIZE_MENTIONS:
    output = re.sub(r"@(\S)", r"@ \1", output) # breaks all mentions, both local and remote
elif REMOVE_MENTIONS:
    output = re.sub(r"@[a-zA-Z.\-_]+", "", output) # removes mentions

if SANITIZE_HASHTAGS:
    output = re.sub(r"@(\S)", r"# \1", output) # breaks all hashtags
elif REMOVE_HASHTAGS:
    output = re.sub(r"#\w+", "", output) # removes hashtags

if DEBUG:
    print(output)
else:
    mastodon.toot(output)
