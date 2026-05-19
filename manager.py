import os
import re
import typing
from time import sleep

import bs4
from bs4 import BeautifulSoup
from dotenv import load_dotenv
from mastodon import Mastodon
from sqlalchemy import select, insert

from database import engine, responded_dms_table, set_setting, get_setting


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

load_dotenv()

USERNAME = os.getenv("USERNAME")
PASSWORD = os.getenv("PASSWORD")
INSTANCE = os.getenv("INSTANCE")

if not os.path.exists("data/pytooter_clientcred.secret"):
    Mastodon.create_app(
        'collabmarkov',
        api_base_url=f'https://{INSTANCE}',
        to_file='data/pytooter_clientcred.secret'
    )

if not os.path.exists("data/pytooter_usercred.secret"):
    mastodon = Mastodon(client_id='data/pytooter_clientcred.secret')

    mastodon.log_in(
        USERNAME,
        PASSWORD,
        to_file="data/pytooter_usercred.secret"
    )
else:
    mastodon = Mastodon(access_token='data/pytooter_usercred.secret')

me = mastodon.me()

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

            text = get_text(BeautifulSoup(i.status.content, features="html.parser")).strip()

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
    sleep(5)
