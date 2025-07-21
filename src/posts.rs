use std::{thread::sleep, time::Duration, vec};

use regex::Regex;
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::conf::{
    read_cw_config, read_disable_mfm, read_disable_sanitize_hashtags,
    read_disable_sanitize_mentions, read_disable_sanitize_mfm, read_instance, read_poster_id,
    read_posting_token, read_visibility,
};

#[derive(Serialize, Deserialize)]
pub struct User {
    pub id: String,
    pub name: Option<String>,
    pub username: Option<String>,
    pub host: Option<String>,
    pub description: Option<String>,
}

#[derive(Serialize, Deserialize)]
pub struct UserRelation {
    #[serde(rename = "isFollowing")]
    pub is_following: bool,
    #[serde(rename = "isFollowed")]
    pub is_followed: bool,
    #[serde(rename = "hasPendingFollowRequestFromYou")]
    pub has_pending_follow_request_from_you: bool,
}

#[derive(Serialize, Deserialize)]
pub struct UserFollow {
    pub id: String,
    #[serde(rename = "followeeId")]
    pub followee_id: String,
    #[serde(rename = "followerId")]
    pub follower_id: String,
    pub follower: User,
}

#[derive(Serialize, Deserialize)]
pub struct Post {
    pub id: String,
    pub text: Option<String>,
    pub cw: Option<String>,
    pub user: User,
    pub visibility: Option<String>,
}

#[derive(Serialize, Deserialize)]
struct Posts {
    posts: Vec<Post>,
}

fn get_posts_until_last(user_id: String, last_id: String) -> Vec<Post> {
    println!("{} Getting posts until last id: {}", user_id, last_id);
    let instance = read_instance();

    let out = reqwest::blocking::Client::new()
        .post(format!("https://{}/api/users/notes", instance))
        .bearer_auth(read_posting_token())
        .json(&json!({
            "userId": user_id,
            "limit": 100,
            "untilId": last_id,
            "withRenotes": false,
            "withBots": false,
        }))
        .send()
        .unwrap();

    if out.status() == StatusCode::TOO_MANY_REQUESTS {
        println!("too many requests for {} retrying...", user_id);
        sleep(Duration::from_secs(2));
        return get_posts_until_last(user_id.clone(), last_id.clone());
    }

    let text = match out.text() {
        Ok(txt) => txt,
        Err(error) => {
            println!("{} failed to get text: {}", &user_id, error);

            String::from("")
        }
    };

    let mut out: Vec<Post> = match serde_json::from_str(text.as_str()) {
        Ok(out) => out,
        Err(error) => {
            println!("{} failed to parse json: {}", &user_id, error);
            println!("input string: {}", text);
            vec![]
        }
    };

    match out.last() {
        Some(last_el) => {
            let last_id = last_el.id.clone();
            let mut posts = get_posts_until_last(user_id, last_id);

            out.append(&mut posts);
        }
        None => {
            println!("No posts found");
        }
    }

    out
}

pub fn control_follows_for_user(user_id: &String) {
    println!("checking if {} is followed", user_id);

    let instance = read_instance();
    let token = read_posting_token();

    let req = reqwest::blocking::Client::new()
        .post(format!("https://{}/api/users/relation", instance))
        .bearer_auth(&token)
        .json(&json!({
            "userId": user_id
        }))
        .send();

    let req = match req {
        Ok(a) => a,
        Err(b) => {
            println!("Failed to fetch user information for {}", user_id);
            println!("{:?}", b);
            return;
        }
    };

    if req.status() == StatusCode::TOO_MANY_REQUESTS {
        println!("too many requests, retrying for {}...", user_id);
        sleep(Duration::from_secs(1));
        control_follows_for_user(user_id);
        return;
    }

    let req = match req.json::<Vec<UserRelation>>() {
        Ok(v) => v,
        Err(_) => {
            println!("Failed to parse user data for {}", user_id);
            return;
        }
    };

    let req = match req.get(0) {
        Some(a) => a,
        None => {
            println!("No relations for {}", user_id);
            return;
        }
    };

    if req.is_following {
        println!("{} is already followed", user_id);
    }

    if req.has_pending_follow_request_from_you {
        println!("{} is pending a follow request", user_id);
    }

    if req.is_followed && !req.is_following && !req.has_pending_follow_request_from_you {
        println!("following {}", user_id);

        let req = reqwest::blocking::Client::new()
            .post(format!("https://{}/api/following/create", instance))
            .bearer_auth(token)
            .json(&json!({
                "userId": user_id
            }))
            .send();

        match req {
            Ok(_) => println!("Successfully followed {}", user_id),
            Err(_) => println!("Error following {}", user_id),
        }
    }
}

pub fn get_posts(user_id: String) -> Vec<Post> {
    println!("Getting posts for {}", user_id);

    let mut posts = Vec::new();
    let instance = read_instance();

    let req = reqwest::blocking::Client::new()
        .post(format!("https://{}/api/users/notes", instance))
        .bearer_auth(read_posting_token())
        .json(&json!({
            "userId": user_id,
            "limit": 100,
            "withRenotes": false,
            "withBots": false,
        }))
        .send()
        .unwrap();

    if req.status() == StatusCode::TOO_MANY_REQUESTS {
        println!("too many requests for {} retrying...", user_id);
        sleep(Duration::from_secs(2));
        return get_posts(user_id.clone());
    }

    match req.json::<Vec<Post>>() {
        Ok(v) => v.iter().for_each(|post| {
            posts.push(Post {
                id: post.id.clone(),
                text: post.text.clone(),
                cw: post.cw.clone(),
                user: User {
                    id: post.user.id.clone(),
                    name: post.user.name.clone(),
                    username: post.user.username.clone(),
                    host: post.user.host.clone(),
                    description: post.user.description.clone(),
                },
                visibility: post.visibility.clone(),
            });
        }),
        Err(_) => return vec![],
    }

    if let Some(last_post) = posts.last() {
        let last_id = last_post.id.clone();
        let mut posts_2 = get_posts_until_last(user_id.clone(), last_id);
        posts.append(&mut posts_2);
    }

    println!("Fetched {} posts for {}", &posts.len(), user_id);

    posts
}

pub fn get_followers_ids() -> Vec<String> {
    let mut ids: Vec<UserFollow> = vec![];

    let markov_bot_id = read_poster_id();

    let req = reqwest::blocking::Client::new()
        .post(format!("https://{}/api/users/followers", read_instance()))
        .json(&json!({
            "userId": markov_bot_id,
            "limit": 100
        }))
        .send()
        .unwrap()
        .json::<Vec<UserFollow>>()
        .unwrap();

    for i in req {
        ids.push(i);
    }

    let mut last_id = ids.last().unwrap();
    let mut end_loop = false;
    loop {

        println!(
            "fetched {} followers so far, last id is \"{}\"",
            ids.len(),
            last_id.id
        );

        let req = reqwest::blocking::Client::new()
            .post(format!("https://{}/api/users/followers", read_instance()))
            .json(&json!({
                "userId": markov_bot_id,
                "untilId": last_id.id,
                "limit": 100
            }))
            .send();

        let req = match req {
            Ok(a) => a,
            Err(b) => {
                panic!("request failed: {:?}", b);
            }
        };

        let req = req.text().unwrap_or_else(|b| {
            println!("failed to read response: {:?}", b);
            end_loop = true;
            String::from("")
        });

        let req = serde_json::from_str::<Vec<UserFollow>>(&req).unwrap_or_else(|b| {
            println!("failed to parse json: {:?}", b);
            println!("original JSON was: {:?}", req);
            end_loop = true;
            vec![]
        });

        for i in req {
            ids.push(i);
        }

        if let Some(last_user) = ids.last() {
            last_id = last_user
        } else {
            break;
        }

        if end_loop {
            break;
        }
    }

    let mut ids_filtered: Vec<String> = vec![];

    for i in ids {
        let regex = Regex::new("#[Nn]o[Mm]arkov").unwrap();

        if !regex.is_match(i.follower.description.clone().unwrap_or(String::from("")).as_str()) {
            ids_filtered.push(i.follower_id.clone());
        }
    }

    ids_filtered
}

#[derive(Serialize, Deserialize)]
pub struct CreatedNote {
    #[serde(rename = "createdNote")]
    created_note: Post,
}

pub fn create_post(text: String) {
    let instance = read_instance();
    let posting_token = read_posting_token();

    let mut sanitized = sanitize_mentions(text.clone());
    sanitized = sanitize_formatting(sanitized.clone());
    sanitized = sanitize_hashtags(sanitized.clone());
    sanitized = remove_mfm(sanitized.clone());

    let visibility = read_visibility();

    let cw_config = read_cw_config();

    let mut json = json!({
        "text": sanitized,
        "visibility": visibility
    });

    if cw_config.enable {
        json["cw"] = json!(cw_config.cw);
    }

    let res = reqwest::blocking::Client::new()
        .post(format!("https://{}/api/notes/create", instance))
        .bearer_auth(posting_token)
        .json(&json)
        .send()
        .unwrap()
        .json::<CreatedNote>()
        .unwrap();

    println!("https://{}/notes/{}", instance, res.created_note.id);
}

pub fn remove_mfm(text: String) -> String {
    if !read_disable_mfm() {
        return text;
    }

    let re = Regex::new(r"\$\[\w+ (.*?)\]").unwrap();
    let mut text_process = text;

    for _ in 0..20 {
        text_process = re.replace_all(&text_process, "$1").to_string();
    }

    text_process
}

pub fn sanitize_mentions(text: String) -> String {
    if read_disable_sanitize_mentions() {
        return text;
    }

    let re = Regex::new(r"(@\w+)(@[\w.]+)?").unwrap();
    re.replace_all(&text, "<plain>$1$2</plain>").to_string()
}

pub fn sanitize_hashtags(text: String) -> String {
    if read_disable_sanitize_hashtags() {
        return text;
    }

    let re = Regex::new(r"(#\w+)").unwrap();
    re.replace_all(&text, "<plain>$1</plain>").to_string()
}

pub fn sanitize_formatting(text: String) -> String {
    if read_disable_sanitize_mfm() {
        return text;
    }

    let mut result = String::new();
    let mut chars = text.chars().peekable();

    let mut open_tags = Vec::new();
    let mut open_parentheses = 0;

    let mut processed_closing_tags = Vec::new();

    while let Some(c) = chars.next() {
        match c {
            '$' if chars.peek() == Some(&'[') => {
                chars.next(); // consume '['
                open_tags.push("$[");
                result.push_str("$[");
            }
            '<' if chars.peek() == Some(&'i') => {
                chars.next(); // consume 'i'
                if chars.peek() == Some(&'>') {
                    chars.next(); // consume '>'
                    open_tags.push("<i>");
                    result.push_str("<i>");
                } else {
                    result.push('<');
                    result.push('i');
                }
            }
            '<' if chars.peek() == Some(&'s') => {
                let mut temp = String::new();
                temp.push(c);
                let mut is_small_tag = false;
                while let Some(&next_c) = chars.peek() {
                    chars.next();
                    temp.push(next_c);
                    if temp == "<small>" {
                        open_tags.push("<small>");
                        is_small_tag = true;
                        break;
                    }
                    if next_c == '>' || temp.len() >= 7 {
                        break;
                    }
                }
                if is_small_tag {
                    result.push_str("<small>");
                } else {
                    result.push_str(&temp);
                }
            }
            '*' if chars.peek() == Some(&'*') => {
                chars.next(); // consume second '*'
                if !open_tags.contains(&"**") {
                    open_tags.push("**");
                } else {
                    if let Some(pos) = open_tags.iter().position(|&x| x == "**") {
                        open_tags.remove(pos);
                        processed_closing_tags.push("**");
                    }
                }
                result.push_str("**");
            }
            '(' => {
                open_parentheses += 1;
                result.push(c);
            }
            ')' => {
                if open_parentheses > 0 {
                    open_parentheses -= 1;
                }
                result.push(c);
            }
            ']' => {
                if open_tags.contains(&"$[") {
                    if let Some(pos) = open_tags.iter().position(|&x| x == "$[") {
                        open_tags.remove(pos);
                        processed_closing_tags.push("$[");
                    }
                }
                result.push(']');
            }
            '<' if chars.peek() == Some(&'/') => {
                let mut temp = String::new();
                temp.push(c);
                temp.push(chars.next().unwrap()); // consume '/'

                let mut closing_tag_type = "";
                while let Some(&next_c) = chars.peek() {
                    chars.next();
                    temp.push(next_c);

                    if temp == "</i>" {
                        closing_tag_type = "<i>";
                        break;
                    } else if temp == "</small>" {
                        closing_tag_type = "<small>";
                        break;
                    }

                    if next_c == '>' || temp.len() >= 8 {
                        break;
                    }
                }

                if !closing_tag_type.is_empty() && open_tags.contains(&closing_tag_type) {
                    if let Some(pos) = open_tags.iter().position(|&x| x == closing_tag_type) {
                        open_tags.remove(pos);
                        processed_closing_tags.push(closing_tag_type);
                    }
                }

                result.push_str(&temp);
            }
            _ => result.push(c),
        }
    }

    for tag in open_tags.iter().rev() {
        match *tag {
            "$[" => result.push(']'),
            "<i>" => result.push_str("</i>"),
            "<small>" => result.push_str("</small>"),
            "**" => result.push_str("**"),
            _ => {}
        }
    }

    for _ in 0..open_parentheses {
        result.push(')');
    }

    result
}

#[cfg(test)]
#[serial_test::serial]
mod tests {
    use super::*;

    #[test]
    pub fn test_disable_mfm_basic() {
        let text = "$[x4 Haiiii]".to_string();
        let expected_text = "Haiiii".to_string();

        let sanitized_text = remove_mfm(text);

        assert_eq!(sanitized_text, expected_text);
    }

    #[test]
    pub fn test_disable_mfm_nested() {
        let text = "$[sparkle $[x4 haiii]]".to_string();
        let expected_text = "haiii".to_string();

        let sanitized_text = remove_mfm(text);

        assert_eq!(sanitized_text, expected_text);
    }

    #[test]
    pub fn test_sanitize_mfm() {
        let text = "$[x4 haiii".to_string();
        let expected_text = "$[x4 haiii]".to_string();

        let sanitized_text = sanitize_formatting(text);

        assert_eq!(sanitized_text, expected_text);
    }

    #[test]
    pub fn test_sanitize_mfm_double() {
        let text = "$[sparkle $[x4 haiii".to_string();
        let expected_text = "$[sparkle $[x4 haiii]]".to_string();

        let sanitized_text = sanitize_formatting(text);

        assert_eq!(sanitized_text, expected_text);
    }

    #[test]
    pub fn test_sanitize_mention_local() {
        let text = "@Lunya".to_string();
        let expected_text = "<plain>@Lunya</plain>".to_string();

        let sanitized_text = sanitize_mentions(text);

        assert_eq!(sanitized_text, expected_text);
    }

    #[test]
    pub fn test_sanitize_mention_remote() {
        let text = "@Lunya@fedi.lunya.pet".to_string();
        let expected_text = "<plain>@Lunya@fedi.lunya.pet</plain>".to_string();

        let sanitized_text = sanitize_mentions(text);

        assert_eq!(sanitized_text, expected_text);
    }

    #[test]
    pub fn test_sanitize_hashtags() {
        let text = "#collabmarkov".to_string();
        let expected_text = "<plain>#collabmarkov</plain>".to_string();

        let sanitized_text = sanitize_hashtags(text);

        assert_eq!(sanitized_text, expected_text);
    }
}
