{pkgs, ...}: {
  # https://devenv.sh/packages/
  packages = with pkgs; [
    git
    pre-commit
    curl
    wget
    age
    sops
    git
  ];

  dotenv.enable = true;
  languages.python = {
    enable = true;
    package = pkgs.python312; # find the relevant version of python for uv to run on https://search.nixos.org
    venv.enable = true;
    uv.enable = true;
    uv.sync.enable = true;
  };
  scripts.exec-from-repo-root.exec = ''
    repo_root=$(git rev-parse --show-toplevel)
    pushd $repo_root 1>/dev/null
    eval $@
    popd 1>/dev/null
  '';

  scripts.updatekeys.exec = ''
    exec-from-repo-root sops updatekeys secrets.env
  '';

  scripts.editsecrets.exec = ''
    exec-from-repo-root sops secrets.env
  '';

  scripts.run.exec = ''
    exec-from-repo-root uv run python run_eval.py
  '';
  scripts.view.exec = ''
    exec-from-repo-root uv run inspect view
  '';
  scripts.cleanup-vms.exec = ''
    exec-from-repo-root uv run inspect sandbox cleanup proxmox
  '';
  scripts.setup-age-key.exec = ''
    echo -e "\033[33mSetting up age key for sops...\033[0m"
    mkdir -p ~/.config/sops/age/

    # Backup existing keys.txt if it exists
    if [ -f ~/.config/sops/age/keys.txt ]; then
      echo -e "\033[33mBacking up existing age key to keys.txt.bkp\033[0m"
      mv ~/.config/sops/age/keys.txt ~/.config/sops/age/keys.txt.bkp.$(date +"%Y-%m-%d_%H-%M-%S")
    fi

    echo -e "\033[33mGenerating new age key...\033[0m"
    age-keygen -o ~/.config/sops/age/keys.txt
    echo -e "\033[32mAge key generated successfully!\033[0m"
    echo -e "\033[33mPlease save your public key and add it to .sops.yaml:\033[0m"
    grep "public key:" ~/.config/sops/age/keys.txt
  '';

  scripts.banner.exec = ''
    echo -e "\033[35m"
    echo "   ___        _        __    ___            _             _ "
    echo "  / _ \ _   _| |_    __\ \  / __\___  _ __ | |_ _ __ ___ | |"
    echo " | | | | | | | __|  /___\ \| /  / _ \| '_ \| __| '__/ _ \| |"
    echo " | |_| | |_| | |_  //___/\/| \_( (_) | | | | |_| | | (_) | |"
    echo "  \___/ \__,_|\__|/_/     \_\__/\___/|_| |_|\__|_|  \___/|_|"
    echo -e "\033[36m            ⊂(◉‿◉)つ  offense ⚔  vs  🛡 defense\033[0m"
    echo -e "\033[90m         ~ agents on VMs, monitors on watch ~\033[0m"
    echo ""
  '';

  scripts.menu.exec = ''
    banner
    echo -e '\033[32mtype `\033[31mmenu\033[32m` print this menu.\033[0m'
    echo ""
    echo -e '\033[32mEval Scripts\033[0m'
    echo -e '\033[32m-----------\033[0m'
    echo -e '\033[32mtype `\033[31mrun\033[32m` run the eval (HONEST + ATTACK) via run_eval.py.\033[0m'
    echo -e '\033[32mtype `\033[31mview\033[32m` open the Inspect log viewer.\033[0m'
    echo -e '\033[32mtype `\033[31mcleanup-vms\033[32m` delete inspect-tagged Proxmox VMs/SDNs.\033[0m'
    echo ""
    echo -e '\033[32mUtility\033[0m'
    echo -e '\033[32m----\033[0m'
    echo -e '\033[32mtype `\033[31mcz\033[32m` Commitizen - format commits and create changelogs\033[0m'
    echo -e '\033[32mtype `\033[31meditsecrets\033[32m` edit secrets.env (OPENROUTER_API_KEY + PROXMOX_*) via sops.\033[0m'
    echo ""
    echo -e '\033[32mMisc\033[0m'
    echo -e '\033[32m----\033[0m'
    echo -e '\033[32mtype `\033[31msetup-hooks\033[32m` Reinstall githooks.\033[0m'
    echo -e '\033[32mtype `\033[31mupdatekeys\033[32m` add new users to allowed list of sops.\033[0m'
    echo -e '\033[32mtype `\033[31msetup-age-key\033[32m` generate age key for sops encryption. (backs up existing key to .bkp)\033[0m'
    echo -e '\033[32mtype `\033[31msetup-personal-env\033[32m` Sets up personal environment file with snowflake passwords and DAGSTER_HOME. (backs up existing .env to .bkp)\033[0m'
    echo -e '\033[32mtype `\033[31mreload\033[32m` reload the environment\033[0m'
  '';
  scripts.setup-hooks.exec = ''
    echo -e "\033[33mSetting up pre-commit hooks...\033[0m"
    pre-commit install
    pre-commit install --hook-type commit-msg
    echo -e "\033[32mPre-commit hooks installed successfully!\033[0m"
  '';
  scripts.reload.exec = "direnv allow";

  enterShell = ''
    uv --version | grep --color=auto "${pkgs.uv.version}"
    python --version | grep --color=auto "${pkgs.python312.version}"
    echo -e "\033[32mWelcome ⊂(◉‿◉)þ!\033[0m"

    # Setup pre-commit hooks
    if [ ! -f .git/hooks/pre-commit ] || [ ! -f .git/hooks/commit-msg ]; then
     setup-hooks
    else
      echo -e "\033[32mPre-commit hooks already installed ✓\033[0m"
    fi

    menu
  '';
  enterTest = ''
    echo "Running tests"
    ci-checks
  '';
}
