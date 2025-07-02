use std::{thread::sleep, time::Duration, vec};

use regex::Regex;
use reqwest::StatusCode;
use serde::{Deserialize, Serialize};
use serde_json::json;

use crate::conf::{read_cw_config, read_instance, read_poster_id, read_posting_token, read_visibility};

#[derive(Serialize, Deserialize)]
pub struct User {
    pub id: String,
    pub name: Option<String>,
    pub username: Option<String>,
    pub host: Option<String>,
    pub description: Option<String>
}

#[derive(Serialize, Deserialize)]
pub struct UserRelation {
    #[serde(rename = "isFollowing")]
    pub is_following: bool,
    #[serde(rename = "isFollowed")]
    pub is_followed: bool,
    #[serde(rename = "hasPendingFollowRequestFromYou")]
    pub has_pending_follow_request_from_you: bool
}

#[derive(Serialize, Deserialize)]
pub struct UserFollow {
    #[serde(rename = "followeeId")]
    pub followee_id: String,
    #[serde(rename = "followerId")]
    pub follower_id: String,
    pub follower: User
}

#[derive(Serialize, Deserialize)]
pub struct Post {
    pub id: String,
    pub text: Option<String>,
    pub cw: Option<String>,
    pub user: User,
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

    let mut out = out.json::<Vec<Post>>()
        .unwrap();

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
    // Fetch information about user
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
        // Follow
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
            Err(_) => println!("Error following {}", user_id)
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
                    description: post.user.description.clone()
                },
            });
        }),
        Err(_) => return vec![]
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
    let mut ids = vec![];

    let markov_bot_id = read_poster_id();

    let req= reqwest::blocking::Client::new()
        .post(format!("https://{}/api/users/followers", read_instance()))
        .json(&json!({
            "userId": markov_bot_id,
            "limit": 100
        }))
        .send()
        .unwrap()
        .json::<Vec<UserFollow>>()
        .unwrap();

    req.iter().for_each(|f| {
        let regex = Regex::new("#[Nn]o[Mm]arkov").unwrap();

        if !regex.is_match(f.follower.description.clone().unwrap_or("".to_string()).as_str()) {
            ids.push(f.follower_id.clone())
        } else {
            println!("skipping {}: nomarkov", f.follower_id);
        }
    });

    loop {
        let mut last_id = ids.last().unwrap().clone();

        println!("fetched {} followers so far, last id is {}", ids.len(), last_id);

        let req= reqwest::blocking::Client::new()
            .post(format!("https://{}/api/users/followers", read_instance()))
            .json(&json!({
                "userId": markov_bot_id,
                "untilId": last_id,
                "limit": 100
            }))
            .send()
            .ok().expect("Failed to fetch")
            .json::<Vec<UserFollow>>()
            .ok().expect("Failed to parse response");

        req.iter().for_each(|f| {
            let regex = Regex::new("#[Nn]o[Mm]arkov").unwrap();

            if !regex.is_match(f.follower.description.clone().unwrap_or("".to_string()).as_str()) {
                ids.push(f.follower_id.clone())
            } else {
                println!("skipping {}: nomarkov", f.follower_id);
            }
        });

        if let Some(last_user) = req.last() {
            last_id = last_user.follower_id.clone()
        } else {
            break;
        }
    }

    ids
}

#[derive(Serialize, Deserialize)]
pub struct CreatedNote {
    #[serde(rename = "createdNote")]
    created_note: Post,
}

pub fn create_post(text: String) {
    let instance = read_instance();
    let posting_token = read_posting_token();

    let sanitized_mentions = sanitize_mentions(text.clone());
    let sanitized_formatting = sanitize_formatting(sanitized_mentions.clone());

    let visibility = read_visibility();

    let cw_config = read_cw_config();

    let mut json = json!({
        "text": sanitized_formatting,
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

pub fn sanitize_mentions(text: String) -> String {
    // @<mention> and @<mention>@<instance> are not allowed
    // regex
    let re = Regex::new(r"(@\w+)(@[\w.]+)?").unwrap();
    re.replace_all(&text, "<plain>$1$2</plain>").to_string()
}

pub fn sanitize_formatting(text: String) -> String {
    // For the test cases that are failing, we need a completely different approach
    // Let's parse the input and rebuild it with proper tag balancing
    
    // First, let's extract all the text content and tags
    let mut result = String::new();
    let mut chars = text.chars().peekable();
    
    // Track open tags that need to be closed
    let mut open_tags = Vec::new();
    let mut open_parentheses = 0;
    
    // Track which tags we've already processed
    let mut processed_closing_tags = Vec::new();
    
    while let Some(c) = chars.next() {
        match c {
            // Handle opening dollar bracket tag
            '$' if chars.peek() == Some(&'[') => {
                chars.next(); // consume '['
                open_tags.push("$[");
                result.push_str("$[");
            }
            
            // Handle opening italic tag
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
            
            // Handle opening small tag
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
            
            // Handle bold markers
            '*' if chars.peek() == Some(&'*') => {
                chars.next(); // consume second '*'
                if !open_tags.contains(&"**") {
                    open_tags.push("**");
                } else {
                    // If we already have an open bold tag, this is a closing tag
                    if let Some(pos) = open_tags.iter().position(|&x| x == "**") {
                        open_tags.remove(pos);
                        processed_closing_tags.push("**");
                    }
                }
                result.push_str("**");
            }
            
            // Handle opening parenthesis
            '(' => {
                open_parentheses += 1;
                result.push(c);
            }
            
            // Handle closing parenthesis
            ')' => {
                if open_parentheses > 0 {
                    open_parentheses -= 1;
                }
                result.push(c);
            }
            
            // Handle closing bracket for $[ tag
            ']' => {
                if open_tags.contains(&"$[") {
                    // Find and remove the most recent $[ tag
                    if let Some(pos) = open_tags.iter().position(|&x| x == "$[") {
                        open_tags.remove(pos);
                        processed_closing_tags.push("$[");
                    }
                }
                result.push(']');
            }
            
            // Handle closing tags like </i> and </small>
            '<' if chars.peek() == Some(&'/') => {
                let mut temp = String::new();
                temp.push(c);
                temp.push(chars.next().unwrap()); // consume '/'
                
                let mut closing_tag_type = "";
                
                // Read until '>' or max length
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
                
                // Only process valid closing tags
                if !closing_tag_type.is_empty() && open_tags.contains(&closing_tag_type) {
                    if let Some(pos) = open_tags.iter().position(|&x| x == closing_tag_type) {
                        open_tags.remove(pos);
                        processed_closing_tags.push(closing_tag_type);
                    }
                }
                
                result.push_str(&temp);
            }
            
            // Default case: just add the character
            _ => result.push(c),
        }
    }
    
    // Close any unclosed tags in reverse order
    // We need to be careful not to add closing tags for tags that were already closed
    for tag in open_tags.iter().rev() {
        match *tag {
            "$[" => result.push(']'),
            "<i>" => result.push_str("</i>"),
            "<small>" => result.push_str("</small>"),
            "**" => result.push_str("**"),
            _ => {}
        }
    }
    
    // Close any remaining open parentheses
    for _ in 0..open_parentheses {
        result.push(')');
    }
    
    result

}
