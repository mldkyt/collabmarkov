import asyncio
import datetime
import os.path
import re
import typing
from asyncio import sleep
from os import getenv

import bs4
import markovify
import requests
from dotenv import load_dotenv
from mastodon import Mastodon
from sqlalchemy import select, insert, delete, update

from database import engine, posts_table, follows_table, last_scan_table, responded_dms_table, set_setting, get_setting

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

async def commands():
    while True:
        notifications = mastodon.notifications(types=["mention"], limit=10)

        with engine.begin() as c:
            for i in notifications:
                if i.status is None or i.account is None:
                    continue

                if i.status.in_reply_to_id is not None:
                    post_that_was_replied_to = mastodon.status(i.status.in_reply_to_id)
                    if post_that_was_replied_to.visibility != 'direct' and post_that_was_replied_to.account.id != me.id:
                        continue
                if i.status.visibility != 'direct':
                    continue

                is_replied = c.execute(
                    select(responded_dms_table)
                    .where((responded_dms_table.c.id == str(i.status.id)))
                ).fetchone() is not None

                if is_replied:
                    continue

                print(i.status.visibility, i.account.acct, i.status.id)

                text = get_text(bs4.BeautifulSoup(i.status.content, features="html.parser")).strip()

                if not text.startswith(f"@{me.acct}"):
                    print(text)
                    print("skipping: not mentioning collabmarkov")
                    continue

                command = (" ".join(text.split(" ")[1:])).strip()

                if command == 'help':
                    print("sending help command test")
                    mastodon.status_post(f"@{i.account.acct} Available commands\n"
                                         f"- `include CWd posts` - send this to allow posts under a content warning\n"
                                         f"- `don't include CWd posts` - send this to disallow posts under a content warning\n"
                                         f"- `include unlisted posts` - send this to allow unlisted (private) posts\n"
                                         f"- `don't include unlisted posts` - send this to disallow unlisted (private) posts\n"
                                         f"- `get/list settings` - get current settings\n\n"
                                         f"To use any of the commands, copy and paste them to a reply to this post.\n"
                                         f"\n"
                                         f"<small>[Donate](https://ko-fi.com/lunyauwu) to help run collabmarkov! No pressure, thanks :3 -[Lunya](https://sk.lunya.pet/@lunya)</small>", content_type="text/markdown", in_reply_to_id=i.status, visibility='direct')



                elif re.match(r"^includes? CW'?d? (posts?|notes?)$", command) is not None:
                    set_setting(c, i.account.acct, "cw", "1")
                    mastodon.status_post(f"@{i.account.acct} The bot will now take posts under CW's and use them", in_reply_to_id=i.status, visibility='direct')

                elif re.match(r"^don'?t includes? CW'?d? (posts?|notes?)$", command) is not None:
                    set_setting(c, i.account.acct, "cw", "0")
                    mastodon.status_post(f"@{i.account.acct} The bot will no longer use posts under CW's", in_reply_to_id=i.status, visibility='direct')

                elif re.match(r"^includes? (unlisted|home) (posts?|notes?)$", command) is not None:
                    set_setting(c, i.account.acct, "unlisted", "1")
                    mastodon.status_post(f"@{i.account.acct} The bot will now take unlisted posts and use them", in_reply_to_id=i.status, visibility='direct')

                elif re.match(r"^don'?t includes? (unlisted|home) (posts?|notes?)$", command) is not None:
                    set_setting(c, i.account.acct, "unlisted", "0")
                    mastodon.status_post(f"@{i.account.acct} The bot will no longer use unlisted posts", in_reply_to_id=i.status, visibility='direct')

                elif re.match("^(get|list)( settings)?", command) is not None:
                    cw = get_setting(c, i.account.acct, "cw", "0")
                    unlisted = get_setting(c, i.account.acct, "unlisted", "0")

                    mastodon.status_post(f"""@{i.account.acct} Current settings:
    - Use CW'd posts: {"yes" if cw == "1" else "no"}
    - Use unlisted posts: {"yes" if unlisted == "1" else "no"}
    You can change these by asking for help""", in_reply_to_id=i.status, visibility='direct')

                else:
                    mastodon.status_post(f"@{i.account.acct} Unrecognized command. Please reply to this post with `help` to get help.", in_reply_to_id=i.status, visibility='direct')


                if not is_replied:
                    c.execute(
                        insert(responded_dms_table)
                        .values(id=str(i.status.id))
                    )

        await sleep(10)


async def followers():
    while True:
        for i in mastodon.pagination_iterator(mastodon.account_followers(me)):
            print(i.display_name)

            if '#nomarkov' in i.note.lower():
                continue

            with engine.begin() as c:
                rel = mastodon.account_relationships(i)[0]

                if not rel.following and not rel.requested and not rel.blocked_by:
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
                            print(
                                f"rel.following={rel.following} rel.requested={rel.requested} rel.blocked_by={rel.blocked_by}")
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
                        else:
                            do_full_scan = False

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

async def post():
    while True:
        with engine.begin() as c:
            a = c.execute(
                select(follows_table.c.id, follows_table.c.acct)
            ).all()

            for i in a:
                rel = mastodon.account_relationships(i[0])[0]

                if not rel.followed_by:
                    try:
                        if rel.following:
                            mastodon.account_unfollow(i[0])  # this is not as important as following users
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
            output = re.sub(r"@(\S)", r"@ \1", output)  # breaks all mentions, both local and remote
        elif REMOVE_MENTIONS:
            output = re.sub(r"@[a-zA-Z.\-_]+", "", output)  # removes mentions

        if SANITIZE_HASHTAGS:
            output = re.sub(r"#(\S)", r"# \1", output)  # breaks all hashtags
        elif REMOVE_HASHTAGS:
            output = re.sub(r"#\w+", "", output)  # removes hashtags

        if DEBUG:
            print(output)
        else:
            mastodon.status_post(output, spoiler_text="Collabmarkov generated post", visibility="unlisted")

        await sleep(3600)


async def heartbeat():
    while True:
        HEARTBEAT_URL = getenv("HEARTBEAT_URL", "")

        if len(HEARTBEAT_URL.strip()) == 0:
            exit(0)

        requests.post(HEARTBEAT_URL)


if __name__ == '__main__':
    tasks = [
        heartbeat(),
        followers(),
        post()
    ]

    asyncio.get_event_loop().run_until_complete(asyncio.gather(*tasks))
