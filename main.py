import os.path
from os import getenv

import markovify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mastodon import Mastodon
from sqlalchemy import create_engine, MetaData, Table, Column, VARCHAR, insert, select

load_dotenv()

USERNAME = getenv("USERNAME")
PASSWORD = getenv("PASSWORD")
INSTANCE = getenv("INSTANCE")

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
    Column("text", VARCHAR)
)

md_obj.create_all(engine, checkfirst=True)

me = mastodon.me()

for i in mastodon.pagination_iterator(mastodon.account_followers(me)):
    print(i.display_name)
    mastodon.account_follow(i)

    with engine.begin() as c:
        for j in mastodon.pagination_iterator(mastodon.account_statuses(i, exclude_reblogs=True)):
            if j.visibility != "public":
                continue

            a = c.execute(
                select(posts_table.c.id)
                    .where((posts_table.c.id == str(j.id)))
            ).fetchone()
            if a is not None:
                break

            soup = BeautifulSoup(j.content)
            text = soup.get_text()

            c.execute(
                insert(posts_table)
                    .values(id=str(j.id), text=text)
            )

posts = []

with engine.begin() as c:
    a = c.execute(
        select(posts_table.c.text)
    )

    for i in a:
        posts.append(i[0])

posts = "\n".join(posts)

markov = markovify.NewlineText(posts)
markov.compile(inplace=True)

print(markov.make_sentence())
