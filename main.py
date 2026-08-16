import datetime
import os.path
import re
import typing
from asyncio import gather, run, sleep
from os import getenv

import bs4
import markovify
import requests
import sentry_sdk
from dotenv import load_dotenv
from mastodon import Mastodon
from sentry_sdk import capture_exception
from sqlalchemy import delete, insert, select, text, update

from database import (
    engine,
    follows_table,
    get_setting,
    last_scan_table,
    posts_table,
    responded_dms_table,
    set_setting,
)

load_dotenv()

FILTER_KEYWORDS = [
    i for i in getenv("FILTER_KEYWORDS", "").split(",") if len(i.strip()) > 0
]

SANITIZE_MENTIONS = getenv("SANITIZE_MENTIONS", "1") == "1"
SANITIZE_HASHTAGS = getenv("SANITIZE_HASHTAGS", "1") == "1"

REMOVE_MENTIONS = getenv("REMOVE_MENTIONS", "0") == "1"
REMOVE_HASHTAGS = getenv("REMOVE_HASHTAGS", "0") == "1"

DEBUG = getenv("DEBUG", "0") == "1"

SENTRY_SDK = getenv("SENTRY_SDK")

if SENTRY_SDK is not None:
    sentry_sdk.init(
        dsn=SENTRY_SDK,
        auto_session_tracking=False,
        send_default_pii=True,
        # enable_logs=True,  # Opt-in: send logs to GlitchTip (uses disk space)
    )


# borrowed from https://stackoverflow.com/questions/30337528/make-beautifulsoup-handle-line-breaks-as-a-browser-would
def get_text(tag: bs4.Tag) -> str:
    _inline_elements = {
        "a",
        "span",
        "em",
        "strong",
        "u",
        "i",
        "font",
        "mark",
        "label",
        "s",
        "sub",
        "sup",
        "tt",
        "bdo",
        "button",
        "cite",
        "del",
        "b",
        "a",
        "font",
    }

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

mastodon = Mastodon(access_token="data/pytooter_usercred.secret")

me = mastodon.me()


async def commands():
    while True:
        try:
            notifications = mastodon.notifications(types=["mention"], limit=10)

            with engine.begin() as c:
                for i in notifications:
                    if i.status is None or i.account is None:
                        continue

                    if i.status.in_reply_to_id is not None:
                        post_that_was_replied_to = mastodon.status(
                            i.status.in_reply_to_id
                        )
                        if (
                            post_that_was_replied_to.visibility != "direct"
                            and post_that_was_replied_to.account.id != me.id
                        ):
                            continue
                    if i.status.visibility != "direct":
                        continue

                    is_replied = (
                        c.execute(
                            select(responded_dms_table).where(
                                (responded_dms_table.c.id == str(i.status.id))
                            )
                        ).fetchone()
                        is not None
                    )

                    if is_replied:
                        continue

                    print(i.status.visibility, i.account.acct, i.status.id)

                    text = get_text(
                        bs4.BeautifulSoup(i.status.content, features="html.parser")
                    ).strip()

                    if not text.startswith(f"@{me.acct}"):
                        print(text)
                        print("skipping: not mentioning collabmarkov")
                        continue

                    reply = ""

                    for command_candidate in text.splitlines():
                        command = command_candidate.strip()
                        if command.startswith("@"):
                            command = " ".join(command.split(" ")[1:])
                        command = " ".join(
                            [
                                part
                                for part in command.split(" ")
                                if len(part.strip()) > 0
                            ]
                        )
                        if len(command) == 0:
                            continue

                        if command == "help":
                            print("sending help command test")
                            reply += (
                                f"Available commands\n"
                                f"- `include CWd posts` - send this to allow posts under a content warning\n"
                                f"- `don't include CWd posts` - send this to disallow posts under a content warning\n"
                                f"- `include unlisted posts` - send this to allow unlisted (private) posts\n"
                                f"- `don't include unlisted posts` - send this to disallow unlisted (private) posts\n"
                                f"- `get/list settings` - get current settings\n\n"
                                f"To use any of the commands, copy and paste them to a reply to this post.\n"
                                f"\n"
                                f"<small>[Donate](https://donate.mldkyt.com) to help run collabmarkov! -[mldkyt](https://soc.mldkyt.com/@mldkyt)</small>"
                                f"\n\n"
                            )

                        elif (
                            re.match(r"^includes? CW'?d? (posts?|notes?)$", command)
                            is not None
                        ):
                            set_setting(c, i.account.acct, "cw", "1")
                            reply += f"Now including CW'd posts in the corpus\n\n"

                        elif (
                            re.match(
                                r"^don'?t includes? CW'?d? (posts?|notes?)$", command
                            )
                            is not None
                        ):
                            set_setting(c, i.account.acct, "cw", "0")
                            reply += f"No longer including CW'd posts in the corpus\n\n"

                        elif (
                            re.match(
                                r"^includes? (unlisted|home) (posts?|notes?)$", command
                            )
                            is not None
                        ):
                            set_setting(c, i.account.acct, "unlisted", "1")
                            reply += f"Now including unlisted posts in the corpus\n\n"

                        elif (
                            re.match(
                                r"^don'?t includes? (unlisted|home) (posts?|notes?)$",
                                command,
                            )
                            is not None
                        ):
                            set_setting(c, i.account.acct, "unlisted", "0")
                            reply += f"No longer using unlisted posts in the corpus\n\n"

                        elif re.match("^(get|list)( settings)?", command) is not None:
                            cw = get_setting(c, i.account.acct, "cw", "0")
                            unlisted = get_setting(c, i.account.acct, "unlisted", "0")

                            reply += f"""Current settings:
- Include CW'd posts in the corpus: {"yes" if cw == "1" else "no"}
- Include unlisted posts in the corpus: {"yes" if unlisted == "1" else "no"}

You can change these by asking for help\n\n"""

                    if len(reply.strip()) == 0:
                        reply = "Unknown command(s). Please use `help` to get a list of available commands."

                    mastodon.status_post(
                        f"@{i.account.acct} {reply.strip()}",
                        content_type="text/markdown",
                        in_reply_to_id=i.status,
                        visibility="direct",
                    )

                    c.execute(insert(responded_dms_table).values(id=str(i.status.id)))

            await sleep(10)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await sleep(300)
            continue


async def followers():
    while True:
        try:
            for account in mastodon.pagination_iterator(mastodon.account_followers(me)):
                print(account.display_name)

                if "#nomarkov" in account.note.lower():
                    continue

                with engine.begin() as c:
                    should_scan = False
                    rel = mastodon.account_relationships(account)[0]

                    if not rel.following and not rel.requested and not rel.blocked_by:
                        if (
                            c.execute(
                                select(follows_table).where(
                                    follows_table.c.id == str(account.id)
                                )
                            ).fetchone()
                            is not None
                        ):
                            print(
                                f"Unfollowing {account.display_name}: inside the followers table but not following"
                            )
                            # This likely only happens if the user is following the account and rejects the follow request
                            # (rel.following=False, rel.requested=False, rel.blockedby=False)
                            mastodon.account_remove_from_followers(account)
                            c.execute(
                                delete(follows_table).where(
                                    follows_table.c.id == str(account.id)
                                )
                            )
                            c.execute(
                                delete(posts_table).where(
                                    (posts_table.c.author == account.acct)
                                )
                            )
                            continue

                        # Account Move
                        if account.moved is not None:
                            try:
                                new_account = account.moved
                                while True:
                                    if new_account.moved is None:
                                        break

                                    new_account = new_account.moved

                                print(
                                    "Account migrated",
                                    account.acct,
                                    "to",
                                    new_account.acct,
                                )
                                mastodon.account_remove_from_followers(account)

                                if (
                                    c.execute(
                                        select(follows_table).where(
                                            follows_table.c.acct == new_account.acct
                                        )
                                    ).fetchone()
                                    is None
                                ):
                                    print(
                                        "New account is not following collabmarkov, begging for follow"
                                    )
                                    mastodon.status_post(
                                        f"Hi @{new_account.acct}! It looks like you moved from {account.acct}. In order for the bot to interact with you, you have to consent by following the bot on your new account.",
                                        visibility="private",
                                    )
                            except Exception as e:
                                capture_exception(e)

                            continue

                        try:
                            mastodon.account_follow(account, reblogs=False)
                            c.execute(
                                insert(follows_table).values(
                                    id=account.id, acct=account.acct
                                )
                            )
                            mastodon.status_post(
                                f"@{account.acct} Welcome to Collaborative Markov Bot!"
                                f"This bot will now use your posts for the corpus. "
                                f"**Only posts that are public and don't have CW are used.** "
                                f"The behaviour of this can be changed by replying to this post with `help`.",
                                visibility="direct",
                            )
                            should_scan = True
                        except Exception as e:
                            sentry_sdk.capture_exception(e)
                            print(f"failed to follow {account.acct}: {str(e)}")
                            print(
                                f"rel.following={rel.following} rel.requested={rel.requested} rel.blocked_by={rel.blocked_by}"
                            )

                    if not should_scan:
                        print(f"skipping account {account.acct}")
                        continue

                    try:
                        a = c.execute(
                            select(last_scan_table.c.last_scan).where(
                                (last_scan_table.c.id == account.id)
                            )
                        ).fetchone()
                        do_full_scan = False
                        if a is None:
                            c.execute(
                                insert(last_scan_table).values(
                                    id=account.id, last_scan=datetime.datetime.now()
                                )
                            )

                        else:
                            if (
                                datetime.datetime.now() - a[0]
                            ).total_seconds() > 1209600:
                                do_full_scan = True
                                c.execute(
                                    update(last_scan_table)
                                    .where((last_scan_table.c.id == account.id))
                                    .values(last_scan=datetime.datetime.now())
                                )

                        for status in mastodon.pagination_iterator(
                            mastodon.account_statuses(account, exclude_reblogs=True)
                        ):
                            a = c.execute(
                                select(posts_table.c.id).where(
                                    (posts_table.c.id == str(status.id))
                                )
                            ).fetchone()
                            if a is not None:
                                if do_full_scan:
                                    continue
                                else:
                                    break

                            soup = bs4.BeautifulSoup(
                                status.content, features="html.parser"
                            )
                            text = get_text(soup)

                            has_cw = len(status.spoiler_text) > 0

                            c.execute(
                                insert(posts_table).values(
                                    id=str(status.id),
                                    text=text,
                                    has_cw=has_cw,
                                    visibility=status.visibility,
                                    author=account.acct,
                                )
                            )
                    except Exception as e:
                        sentry_sdk.capture_exception(e)
                        print(f"failed to query posts for {account.acct}: {str(e)}")
                        pass

            with engine.begin() as c:
                a = c.execute(select(follows_table.c.id, follows_table.c.acct)).all()

                for i in a:
                    rel = mastodon.account_relationships(i[0])[0]

                    if not rel.followed_by:
                        try:
                            if rel.following:
                                mastodon.account_unfollow(
                                    i[0]
                                )  # this is not as important as following users
                                # so we can safely unfollow a user on the second hour

                            with engine.begin() as c:
                                c.execute(
                                    delete(posts_table).where(
                                        (posts_table.c.author == i[1])
                                    )
                                )
                                c.execute(
                                    delete(follows_table).where(
                                        (follows_table.c.id == i[0])
                                    )
                                )

                        except Exception as e:
                            sentry_sdk.capture_exception(e)
                            print(f"failed to unfollow {i[0]}: {str(e)}")
                            pass

            print("followers: Finished managing followers, waiting an hour")
            await sleep(300)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await sleep(300)
            continue


async def post():
    while True:
        try:
            posts = []

            with engine.begin() as c:
                a = c.execute(
                    select(
                        posts_table.c.text,
                        posts_table.c.has_cw,
                        posts_table.c.visibility,
                        posts_table.c.author,
                    )
                ).all()

                settings_cache = {}

                for i in a:
                    if f"{i[3]}:cw" not in settings_cache:
                        settings_cache[f"{i[3]}:cw"] = (
                            get_setting(c, i[3], "cw", "0") == "0"
                        )

                    if f"{i[3]}:vis" not in settings_cache:
                        settings_cache[f"{i[3]}:vis"] = get_setting(
                            c, i[3], "unlisted", "0"
                        )

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
                print("No posts, waiting...")
                await sleep(60)
                continue

            posts = "\n".join(posts)

            markov = markovify.NewlineText(posts)
            markov.compile(inplace=True)

            output = None
            for attempt in range(10000):
                output = markov.make_sentence()

            if output is None:
                print("After 10000 attempts no output was made, skipping")
                continue

            if SANITIZE_MENTIONS:
                output = re.sub(
                    r"@(\S)", r"@ \1", output
                )  # breaks all mentions, both local and remote
            elif REMOVE_MENTIONS:
                output = re.sub(r"@[a-zA-Z.\-_]+", "", output)  # removes mentions

            if SANITIZE_HASHTAGS:
                output = re.sub(r"#(\S)", r"# \1", output)  # breaks all hashtags
            elif REMOVE_HASHTAGS:
                output = re.sub(r"#\w+", "", output)  # removes hashtags

            if DEBUG:
                print(output)
            else:
                a = mastodon.status_post(output, visibility="unlisted")
                print("shitposted: ", a.url)

            await sleep(3600)
        except Exception as e:
            sentry_sdk.capture_exception(e)
            await sleep(300)
            continue


async def update_bio():
    while True:
        with engine.begin() as c:
            stats = c.execute(
                text("SELECT COUNT(id), SUM(LENGTH(text)) FROM posts")
            ).fetchone()

            stats_2 = c.execute(text("SELECT COUNT(id) FROM follows")).fetchone()

        posts = stats[0]
        corpus_size = stats[1]
        users = stats_2[0]

        bio_text = f"""Follow this account to include your posts in its corpus.

Please report any posts that should have a CW or are bad, either through the instance or by DMing @mldkyt :3

This bot and the server it is on is running purely on donations, if you are enjoying the posts by this bot, please donate! https://donate.mldkyt.com

:collabmarkov_88x31:

Corpus stats:
Posts: {posts}
Corpus size: {corpus_size}
Contributors to the corpus: {users}"""

        mastodon.account_update_credentials(note=bio_text)

        await sleep(3600 * 12)


async def heartbeat():
    while True:
        HEARTBEAT_URL = getenv("HEARTBEAT_URL", "")

        if len(HEARTBEAT_URL.strip()) == 0:
            return

        requests.post(HEARTBEAT_URL)
        await sleep(60)


async def main():
    tasks = [heartbeat(), followers(), post(), commands(), update_bio()]

    await gather(*tasks)


if __name__ == "__main__":
    run(main())
