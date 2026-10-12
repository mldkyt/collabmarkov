{
  pkgs,
  lib,
  config,
  inputs,
  ...
}:

{

    languages.python = {
        enable = true;
        uv.enable = true;
        uv.sync.enable = true;
    };

    dotenv.enable = true;

}
