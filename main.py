import os.path
from os import getenv

import markovify
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mastodon import Mastodon

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

me = mastodon.me()

# Get all followers
followers = []

posts = []

for i in mastodon.pagination_iterator(mastodon.account_followers(me)):
    print(i.display_name)
    mastodon.account_follow(i)

    for j in mastodon.pagination_iterator(mastodon.account_statuses(i, exclude_reblogs=True)):
        if j.visibility != "public":
            continue

        soup = BeautifulSoup(j.content)
        posts.append(soup.get_text())

posts = "\n".join(posts)

markov = markovify.NewlineText(posts)
markov.compile(inplace=True)

print(markov.make_sentence())
