# Collaborative Markov Bot

[![Fedi Account Badge](https://img.shields.io/badge/main%20instance-%40collabmarkov%40fedi.lunya.pet-pink)
](https://fedi.lunya.pet/@collabmarkov)
[![Forgejo Stars](https://img.shields.io/gitea/stars/Lunya/collabmarkov?gitea_url=https%3A%2F%2Fgit.lunya.pet%2F&style=flat)](https://git.lunya.pet/Lunya/collabmarkov/stars)
[![Forgejo Issues](https://img.shields.io/gitea/issues/open/Lunya/collabmarkov?gitea_url=https%3A%2F%2Fgit.lunya.pet)](https://git.lunya.pet/Lunya/collabmarkov/issues)
[![Forgejo Pull Requests](https://img.shields.io/gitea/pull-requests/open/Lunya/collabmarkov?gitea_url=https%3A%2F%2Fgit.lunya.pet)](https://git.lunya.pet/Lunya/collabmarkov/pulls)


oh god no

This bot takes all posts from all the users that follow it and makes a markov post out of that.

## Development

You can register an account on git.lunya.pet if you want to open a pull request here.

1. Clone this repository
2. Make your changes (cargo downloads libraries automatically)
3. Copy `config.example.ini` to `config.ini` and set parameters in that file
4. Test your changes on an account
5. Open a pull request

## Configuration

1. Copy `config.example.ini` to `config.ini`.
2. In the `[posting]` section, set `id`, `token`, `instance` at minimum.

If you want the bot to have content warnings, you can enable them under the `[cw]` section. Set `enable` to `on` and `cw` to your content warning.

You can also configure a blocklist in the bot. Under the `[blocklist]` section, set a comma separate list of words under `keywords` or `hashtags`. Hashtags do **NOT** contain the `#`

Under the `[sanitize]` section, you can configure post processing of Markov text. By default, mentions are made to not mention and all MFM is closed off. However, if you want to change some of these settings, change `mfm` under this section to false to disable fixing of MFM, `mentions` to false to allow mentions, `hashtags` to true to sanitize hashtags and `disable-mfm` to true to disable MFM altogether. Setting `cw` to true will filter out any posts with a CW and setting `visibility-below` to any of `public`, `home` or `followers` will exclude any posts below that visibility. For example setting it to `public` will exclude any posts that are posted to only `home`.

> [!warning] If you want the Remove MFM option to work, please leave sanitize MFM enabled too. It relies on all MFM to be closed.
