{
  description = "Dissecting StarLink environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-26.05";
    utils.url = "github:numtide/flake-utils";
    pcap-match.url = "github:hendrikcech/pcap-match";
    pcap-match.inputs.nixpkgs.follows = "nixpkgs";
    netscalpel.url = "github:hendrikcech/netscalpel";
  };

  outputs = { self, nixpkgs, utils, pcap-match, netscalpel }:
    utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        pythonEnv = pkgs.python313.withPackages (ps: with ps; [
          matplotlib
          pandas
          scipy
          tqdm
          pyarrow
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
          netscalpel.packages.${system}.default
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

      in
      {
        # Interactive Development Shell: use with `nix develop` for an
        # interactive shell or `nix develop -c <CMD>` for a one-off command
        devShells.default = pkgs.mkShell {
          inherit packages;

          shellHook = ''
            echo "Environment loaded! You can now run Taskfile.yml tasks using 'task <task_name>'"
          '';
        };
      }
    );
}
