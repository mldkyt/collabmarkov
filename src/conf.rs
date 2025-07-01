use std::cmp::min;

use configparser::ini::Ini;

pub struct ReturnedCWConfiguration {
    pub enable: bool,
    pub cw: String
}

fn read_config() -> Ini {
    // Read from file
    let mut config = Ini::new();
    config.load("./config.ini").unwrap();
    
    return config;
}

pub fn read_posting_token() -> String {
    let config = read_config();

    config.get("posting", "token").unwrap()
}

pub fn read_instance() -> String {
    let config = read_config();

    config.get("posting", "instance").unwrap()
}

pub fn read_cw_config() -> ReturnedCWConfiguration {
    let config = read_config();

    let cw_enabled = config.get("cw", "enable");
    let cw = config.get("cw", "cw");

    match cw_enabled {
        Some(v) => {
            if v == "yes" || v == "on" || v == "true" {
                return ReturnedCWConfiguration {
                    enable: true,
                    cw: cw.unwrap_or("Markov Generated Post".to_string())
                };
            } else {
                return ReturnedCWConfiguration {
                    enable: false,
                    cw: cw.unwrap_or("Markov Generated Post".to_string())
                };
            }
        }
        None => {
            return ReturnedCWConfiguration {
                enable: false,
                cw: cw.unwrap_or("Markov Generated Post".to_string())
            };
        }
    }
}

pub fn read_multiplier() -> i64 {
    let config = read_config();

    let mult = config.getint("posting", "multiplier");

    match mult {
        Ok(Some(v)) => {
            return min(1, v);
        }
        Ok(None) => return 1,
        Err(_) => return 1
    }

}

pub fn read_visibility() -> String {
    let config = read_config();
    let visibility = config.get("posting", "visibility").unwrap_or("public".to_string());

    if visibility == "public" || visibility == "home" || visibility == "followers" {
        return visibility;
    }

    "public".to_string()
}

pub fn read_poster_id() -> String {
    let config = read_config();
    let id = config.get("posting", "id").unwrap();

    id
}

#[cfg(test)]
#[serial_test::serial]
mod tests {
    use super::*;

    #[test]
    fn test_read_config() {

        let posting_token = read_posting_token();
        assert_eq!(posting_token, "token");

        let instance = read_instance();
        assert_eq!(instance, "misskey.io");
        
        let cw_config = read_cw_config();
        assert_eq!(cw_config.enable, true);
        assert_eq!(cw_config.cw, "Markov Generated Post");

        let multiplier = read_multiplier();
        assert_eq!(multiplier, 2);

        let visibility = read_visibility();
        assert_eq!(visibility, "home");

        let poster_id = read_poster_id();
        assert_eq!(poster_id, "123456abcd");

    }
}
