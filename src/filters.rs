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

pub struct FilterConfiguration {
    keywords: KeywordFilterConfiguration,
    hashtags: HashtagFilterConfiguration,
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

    FilterConfiguration {
        keywords: KeywordFilterConfiguration {
            enabled: keywords.len() != 0,
            words: keywords,
        },
        hashtags: HashtagFilterConfiguration {
            enabled: hashtags.len() != 0,
            hashtags: hashtags,
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

// return true when post is fine
pub fn check_post(filter_config: &FilterConfiguration, post: &Post) -> bool {
    check_post_hashtags(&filter_config.hashtags, post)
        && check_post_keywords(&filter_config.keywords, post)
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
        };

        assert_eq!(check_post(&config, &post_3), true);
        assert_eq!(check_post_keywords(&config.keywords, &post_3), true);
        assert_eq!(check_post_hashtags(&config.hashtags, &post_3), true);
    }
}
