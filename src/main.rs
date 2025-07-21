
use markov::Chain;

use crate::{
    filters::{check_post, get_filter_configuration},
    posts::{Post, control_follows_for_user, get_followers_ids, get_posts},
};

mod conf;
mod filters;
mod posts;

fn main() {
    println!("collabmarkov  Copyright (C) 2025  Lunya
This program comes with ABSOLUTELY NO WARRANTY.
This is free software, and you are welcome to redistribute it under certain conditions. Please check LICENSE for more infomation.");

    let followers_ids = get_followers_ids();

    for i in &followers_ids {
        control_follows_for_user(i);
    }

    let mut all_posts: Vec<Post> = vec![];

    for i in 0..followers_ids.len() {
        let follower_i = followers_ids[i].clone();
        println!(
            "processing {} ({}/{})",
            follower_i,
            i + 1,
            followers_ids.len()
        );

        let mut posts = get_posts(follower_i);
        all_posts.append(&mut posts);
    }

    let mut total_corpus_length = 0;
    let mut total_post_count = 0;

    let mut chain = Chain::new();

    let filter_config = get_filter_configuration();

    for post in all_posts {
        if post.text.is_none() {
            continue;
        }

        if !check_post(&filter_config, &post) {
            continue;
        }

        total_corpus_length += post.text.clone().unwrap().len();
        total_post_count += 1;
        chain.feed_str(post.text.unwrap().as_str());
    }

    println!("total users: {}", followers_ids.len());
    println!("total posts: {}", total_post_count);
    println!("total corpus length: {}", total_corpus_length);

    let mut str = String::new();

    for _ in 0..conf::read_multiplier() {
        let chunk = chain.generate_str();
        str.push_str(&chunk);
        str.push_str(" ");
    }

    println!("{}", &str);

    posts::create_post(str);
}
