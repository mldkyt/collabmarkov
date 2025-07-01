use serde_json::json;

use crate::{conf::{read_instance, read_poster_id}, posts::{get_followers_ids, User, UserFollow}};


mod conf;
mod posts;

fn main() {
    let followers_ids = get_followers_ids();

    println!("{:?}", followers_ids.len());
}
