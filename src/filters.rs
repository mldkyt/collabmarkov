use configparser::ini::Ini;
use regex::Regex;

use crate::posts::Post;

pub struct KeywordFilterConfiguration {
    enabled: bool,
    words: Vec<String>,
}

pub struct HashtagFilterConfiguration {
    enabled: bool,
    hashtags: Vec<String>,
}

pub struct CWConfigruration {
    enabled: bool,
}

pub struct VisibilityConfiguration {
    enabled: bool,
    visibility: String,
}

pub struct FilterConfiguration {
    keywords: KeywordFilterConfiguration,
    hashtags: HashtagFilterConfiguration,
    cw: CWConfigruration,
    visibility: VisibilityConfiguration,
}

pub fn get_filter_configuration() -> FilterConfiguration {
    let mut config = Ini::new();
    config.load("./config.ini").unwrap();

    // Keyword filters
    let keywords: Vec<String> = config
        .get("blocklist", "keywords")
        .unwrap_or("".to_string())
        .split(',')
        .map(|f| f.trim().to_string())
        .collect();

    // Hashtag filters
    let hashtags: Vec<String> = config
        .get("blocklist", "hashtags")
        .unwrap_or("".to_string())
        .split(',')
        .map(|f| f.trim().to_string())
        .collect();

    // CW configuration
    let cw = config
        .getboolcoerce("blocklist", "cw")
        .unwrap_or(Some(false))
        .unwrap_or(false);

    // Visibility configuration
    let visibility = config
        .get("blocklist", "visibility-below")
        .unwrap_or("home".to_string());

    FilterConfiguration {
        keywords: KeywordFilterConfiguration {
            enabled: keywords.len() != 0,
            words: keywords,
        },
        hashtags: HashtagFilterConfiguration {
            enabled: hashtags.len() != 0,
            hashtags: hashtags,
        },
        cw: CWConfigruration { enabled: cw },
        visibility: VisibilityConfiguration {
            enabled: visibility != "followers",
            visibility: visibility,
        },
    }
}

fn check_post_hashtags(hashtag_configuration: &HashtagFilterConfiguration, post: &Post) -> bool {
    if !&hashtag_configuration.enabled {
        return true;
    }

    let post_hashtags = post.text.clone().unwrap_or("".to_string());
    let re = Regex::new(r"#(\w+)").unwrap();

    for capture in re.captures_iter(&post_hashtags) {
        for blocked_hashtag in &hashtag_configuration.hashtags {
            if &capture[1] == blocked_hashtag {
                return false;
            }
        }
    }

    true
}

fn check_post_keywords(keyword_configuration: &KeywordFilterConfiguration, post: &Post) -> bool {
    if !&keyword_configuration.enabled {
        return true;
    }

    for keyword in &keyword_configuration.words {
        if post
            .text
            .clone()
            .unwrap_or("".to_string())
            .contains(keyword)
        {
            return false;
        }
    }

    true
}

pub fn check_exclude_below_visiblity(config: &VisibilityConfiguration, post: &Post) -> bool {
    if !config.enabled {
        return true;
    }

    match &post.visibility {
        Some(post_visibility) => match post_visibility.as_str() {
            "public" => return true,                         // keep any public posts
            "home" => return &config.visibility != "public", // remove home posts if the configuration is for public
            "followers" => return &config.visibility != "public" && &config.visibility != "home", // remove followers only posts if the configuration is below public or below home
            _ => return true, // keep any other visibility posts
        },
        None => return true, // if the post doesn't have a visibility for some reason, keep it as well
    }
}

pub fn check_exclude_with_cw(config: &CWConfigruration, post: &Post) -> bool {
    if !config.enabled {
        return true; // keep cw posts when the cw filter is disabled
    }

    post.cw.clone().unwrap_or("".to_string()).trim().len() == 0 // keep cw posts if there's no cw or the cw is empty
}

// return true when post is fine
pub fn check_post(filter_config: &FilterConfiguration, post: &Post) -> bool {
    check_post_hashtags(&filter_config.hashtags, post)
        && check_post_keywords(&filter_config.keywords, post)
        && check_exclude_below_visiblity(&filter_config.visibility, &post)
        && check_exclude_with_cw(&filter_config.cw, &post)
}

#[cfg(test)]
#[serial_test::serial]
mod tests {
    use crate::{conf, posts::User};

    use super::*;

    #[test]
    fn test_configuration() {
        let config = get_filter_configuration();

        assert_eq!(config.hashtags.enabled, true);
        assert_eq!(config.hashtags.hashtags, vec!["mutualaid"]);

        assert_eq!(config.keywords.enabled, true);
        assert_eq!(config.keywords.words, vec!["block", "these", "keywords"]);
    }

    #[test]
    fn test_filtering_on_posts() {
        let config = get_filter_configuration();

        let post_1 = Post {
            cw: None,
            id: "a".to_string(),
            text: Some("this is a blocked post".to_string()),
            user: User {
                description: None,
                host: None,
                id: "a".to_string(),
                name: None,
                username: None,
            },
            visibility: Some("public".to_string()),
        };

        assert_eq!(check_post(&config, &post_1), false);
        assert_eq!(check_post_keywords(&config.keywords, &post_1), false);
        assert_eq!(check_post_hashtags(&config.hashtags, &post_1), true);

        let post_2 = Post {
            cw: None,
            id: "a".to_string(),
            text: Some("#mutualaid please donate to me...".to_string()),
            user: User {
                description: None,
                host: None,
                id: "a".to_string(),
                name: None,
                username: None,
            },
            visibility: Some("public".to_string()),
        };

        assert_eq!(check_post(&config, &post_2), false);
        assert_eq!(check_post_keywords(&config.keywords, &post_2), true);
        assert_eq!(check_post_hashtags(&config.hashtags, &post_2), false);

        let post_3 = Post {
            cw: None,
            id: "a".to_string(),
            text: Some("this is a normal post".to_string()),
            user: User {
                description: None,
                host: None,
                id: "a".to_string(),
                name: None,
                username: None,
            },
            visibility: Some("public".to_string()),
        };

        assert_eq!(check_post(&config, &post_3), true);
        assert_eq!(check_post_keywords(&config.keywords, &post_3), true);
        assert_eq!(check_post_hashtags(&config.hashtags, &post_3), true);
    }

    #[test]
    pub fn test_exclude_public_post() {
        let config = VisibilityConfiguration {
            enabled: true,
            visibility: "public".to_string(),
        };

        let post = Post {
            cw: None,
            id: "a".to_string(),
            text: Some("b".to_string()),
            user: User {
                description: None,
                host: None,
                id: "a".to_string(),
                name: None,
                username: None,
            },
            visibility: Some("public".to_string()),
        };

        let check_status = check_exclude_below_visiblity(&config, &post);

        assert_eq!(check_status, true);
    }

    #[test]
    pub fn test_exclude_home_post() {
        let config = VisibilityConfiguration {
            enabled: true,
            visibility: "public".to_string(),
        };

        let post = Post {
            cw: None,
            id: "a".to_string(),
            text: Some("b".to_string()),
            user: User {
                description: None,
                host: None,
                id: "a".to_string(),
                name: None,
                username: None,
            },
            visibility: Some("home".to_string()),
        };

        let check_status = check_exclude_below_visiblity(&config, &post);

        assert_eq!(check_status, false);
    }

    #[test]
    pub fn test_exclude_followers_post() {
        let config = VisibilityConfiguration {
            enabled: true,
            visibility: "public".to_string(),
        };

        let post = Post {
            cw: None,
            id: "a".to_string(),
            text: Some("b".to_string()),
            user: User {
                description: None,
                host: None,
                id: "a".to_string(),
                name: None,
                username: None,
            },
            visibility: Some("followers".to_string()),
        };

        let check_status = check_exclude_below_visiblity(&config, &post);

        assert_eq!(check_status, false);
    }

    #[test]
    pub fn test_exclude_with_cw() {
        let configuration = CWConfigruration { enabled: true };

        let post = Post {
            cw: Some("c".to_string()),
            id: "a".to_string(),
            text: Some("b".to_string()),
            user: User {
                description: None,
                host: None,
                id: "a".to_string(),
                name: None,
                username: None,
            },
            visibility: Some("followers".to_string()),
        };

        let check_status = check_exclude_with_cw(&configuration, &post);

        assert_eq!(check_status, false);
    }

    #[test]
    pub fn test_exclude_without_cw() {
        let configuration = CWConfigruration { enabled: true };

        let post = Post {
            cw: None,
            id: "a".to_string(),
            text: Some("b".to_string()),
            user: User {
                description: None,
                host: None,
                id: "a".to_string(),
                name: None,
                username: None,
            },
            visibility: Some("followers".to_string()),
        };

        let check_status = check_exclude_with_cw(&configuration, &post);

        assert_eq!(check_status, true);
    }
}
