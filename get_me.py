from mastodon import Mastodon

mastodon = Mastodon(access_token="data/pytooter_usercred.secret")

me = mastodon.me()
print("logged in as", me.acct, me.display_name)
