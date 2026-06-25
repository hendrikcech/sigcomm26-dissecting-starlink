{
  description = "Dissecting StarLink plotting environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-26.05";
    utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, utils }:
    utils.lib.eachDefaultSystem (system:
      let
        pkgs = import nixpkgs { inherit system; };

        pythonEnv = pkgs.python313.withPackages (ps: with ps; [
          matplotlib
          pandas
          scipy
          tqdm
          pyarrow
        ]);

        packages = [ pythonEnv pkgs.coreutils pkgs.go-task ];

        envRunner = pkgs.writeShellApplication {
          name = "run-env";
          runtimeInputs = packages;
          text = ''
            # Only make the nix-defined packages available
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
            echo "Research environment loaded!"
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
