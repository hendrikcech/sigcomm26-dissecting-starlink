{
  description = "Network namespace emulation model environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-unstable";
    utils.url = "github:numtide/flake-utils";
    pcap-match.url = "github:hendrikcech/pcap-match";
    netmeas = {
      type = "gitlab";
      owner = "cm%2Fstarlink";
      repo = "netmeas";
      host = "gitlab.lrz.de";
    };
  };

  outputs = { self, nixpkgs, utils, pcap-match, netmeas }:
    utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        pythonEnv = pkgs.python313.withPackages (ps: with ps; [
          matplotlib
          pandas
          scipy
          tqdm
          numba
        ]);

        # Create a wrapper for sudo that preserves the Nix environment's PATH
        # and correctly parses sudo options (like -u) so they aren't passed to `env`.
        sudoWrapper = pkgs.writeShellScriptBin "sudo" ''
          opts=()
          while [[ $# -gt 0 ]]; do
            case "$1" in
              -u|-g|-C|-p|-R|-U|-A|-a|-c|-h|-t|-T)
                if [[ -n "$2" ]]; then
                  opts+=("$1" "$2")
                  shift 2
                else
                  opts+=("$1")
                  shift
                fi
                ;;
              -*)
                opts+=("$1")
                shift
                ;;
              *=*)
                opts+=("$1")
                shift
                ;;
              *)
                break
                ;;
            esac
          done
          exec /usr/bin/sudo "''${opts[@]}" env PATH="$PATH" "$@"
        '';

        packages = with pkgs; [
          pcap-match.packages.${system}.default
          netmeas.packages.${system}.default
          pythonEnv
          sudoWrapper
          coreutils
          go-task
          iproute2
          ethtool
          procps
          nftables
          bpftrace
          tcpdump
          gawk
          gnugrep
          uv
          bash
        ];

        envRunner = pkgs.writeShellApplication {
          name = "run-env";
          runtimeInputs = packages;
          text = ''
            # Restrict to the nix-defined packages
            export PATH="${pkgs.lib.makeBinPath packages}"

            if [ $# -eq 0 ]; then
              echo "Error: No command provided."
              echo "Usage: nix run . -- <command> [args...]"
              exit 1
            fi
            
            exec "$@"
          '';
        };
      in
      {
        # Interactive Development Shell (`nix develop`)
        devShells.default = pkgs.mkShell {
          inherit packages;

          shellHook = ''
            echo "netns_model environment loaded!"
            echo "You can now run tasks defined in Taskfile.yml using 'task <task_name>'"
          '';
        };

        # Package definition
        packages.default = envRunner;

        # Direct execution via `nix run`
        apps.default = {
          type = "app";
          description = "Run a command in the custom environment";
          program = "${envRunner}/bin/run-env";
        };
      }
    );
}
