import os.path
import re
import typing
from os import getenv
from time import sleep

import markovify
import bs4
from dotenv import load_dotenv
from mastodon import Mastodon
from sqlalchemy import create_engine, MetaData, Table, Column, VARCHAR, insert, select, BOOLEAN

load_dotenv()

USERNAME = getenv("USERNAME")
PASSWORD = getenv("PASSWORD")
INSTANCE = getenv("INSTANCE")

FILTER_KEYWORDS = [i for i in getenv("FILTER_KEYWORDS", "").split(",") if len(i.strip()) > 0]
FILTER_CW = getenv("FILTER_CW", "0") == "1"
FILTER_VISIBILITY = getenv("FILTER_VISIBILITY", "public")

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

if not os.path.exists("data/pytooter_clientcred.secret"):
    Mastodon.create_app(
        'collabmarkov',
        api_base_url=f'https://{INSTANCE}',
        to_file='data/pytooter_clientcred.secret'
    )

if not os.path.exists("data/pytooter_usercred.secret"):
    mastodon = Mastodon(client_id='data/pytooter_clientcred.secret', api_base_url=f"https://{INSTANCE}")

    mastodon.log_in(
        USERNAME,
        PASSWORD,
        to_file="data/pytooter_usercred.secret"
    )
else:
    mastodon = Mastodon(access_token='data/pytooter_usercred.secret', api_base_url=f"https://{INSTANCE}")

engine = create_engine("sqlite:///data/collabmarkov.db", echo=True)

md_obj = MetaData()

posts_table = Table(
    "posts",
    md_obj,
    Column("id", VARCHAR, primary_key=True),
    Column("text", VARCHAR),
    Column("has_cw", BOOLEAN),
    Column("visibility", VARCHAR)
)

md_obj.create_all(engine, checkfirst=True)

me = mastodon.me()

for i in mastodon.pagination_iterator(mastodon.account_followers(me)):
    print(i.display_name)

    if '#nomarkov' in i.note.lower():
        continue

    rel = mastodon.account_relationships(i)[0]

    if not rel.following:
        while True:
            try:
                mastodon.account_follow(i, reblogs=False)
                sleep(5)
                break
            except Exception as e:
                print(f"failed to follow {i.acct}: {str(e)}")
                sleep(10)
                pass

    with engine.begin() as c:
        try:
            for j in mastodon.pagination_iterator(mastodon.account_statuses(i, exclude_reblogs=True)):
                a = c.execute(
                    select(posts_table.c.id)
                    .where((posts_table.c.id == str(j.id)))
                ).fetchone()
                if a is not None:
                    break

                soup = bs4.BeautifulSoup(j.content)
                text = get_text(soup)

                has_cw = len(j.spoiler_text) > 0

                c.execute(
                    insert(posts_table)
                    .values(id=str(j.id), text=text, has_cw=has_cw, visibility=j.visibility)
                )
        except Exception as e:
            print(f"failed to query posts for {i.acct}: {str(e)}")
            sleep(10)
            pass

    sleep(3)

for i in mastodon.pagination_iterator(mastodon.account_following(me)):
    rel = mastodon.account_relationships(i)[0]

    if not rel.followed_by and rel.following:
        try:
            mastodon.account_unfollow(i) # this is not as important as following users
            # so we can safely unfollow a user on the second hour
            sleep(5)
        except Exception as e:
            print(f"failed to unfollow {i.acct}: {str(e)}")
            sleep(10)
            pass

posts = []

with engine.begin() as c:
    a = c.execute(
        select(posts_table.c.text, posts_table.c.has_cw, posts_table.c.visibility)
    )

    for i in a:
        if FILTER_CW == "1" and i[1]:
            continue

        if FILTER_VISIBILITY == "public" and i[2] not in ["public"]:
            continue
        if FILTER_VISIBILITY == "unlisted" and i[2] not in ["public", "unlisted"]:
            continue
        if FILTER_VISIBILITY == "private" and i[2] not in ["public", "unlisted", "private"]:
            continue

        for j in FILTER_KEYWORDS:
            if j.lower() in i[0].lower():
                continue

        posts.append(i[0])

posts = "\n".join(posts)

markov = markovify.NewlineText(posts)
markov.compile(inplace=True)

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
