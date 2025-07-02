
use std::ops::Index;

use markov::Chain;

use crate::posts::{get_followers_ids, get_posts, Post};


mod conf;
mod posts;

fn main() {
    println!("collabmarkov  Copyright (C) 2025  Lunya
This program comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it under certain conditions. Please check LICENSE for more infomation.");

    let followers_ids = get_followers_ids();

    let mut all_posts: Vec<Post> = vec![];

    for i in 0..followers_ids.len() {
        let follower_i = followers_ids[i].clone();
        println!("processing {} ({}/{})", follower_i, i + 1, followers_ids.len());

        let mut posts = get_posts(follower_i);
        all_posts.append(&mut posts);
    }

    let mut chain = Chain::new();

    for post in all_posts {
        if post.text.is_none() {
            continue;
        }

        chain.feed_str(post.text.unwrap().as_str());
    }

    let mut str = String::new();

    for _ in 0..conf::read_multiplier() {
        let chunk = chain.generate_str();
        str.push_str(&chunk);
        str.push_str(" ");
    }

    println!("{}", &str);

    posts::create_post(str);
}
