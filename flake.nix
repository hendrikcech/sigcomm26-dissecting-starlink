{
  description = "Dissecting StarLink plotting environment";

  inputs = {
    nixpkgs.url = "github:nixos/nixpkgs/nixos-26.05";
    utils.url = "github:numtide/flake-utils";
    pcap-match.url = "github:hendrikcech/pcap-match";
    pcap-match.inputs.nixpkgs.follows = "nixpkgs";
  };

  outputs = { self, nixpkgs, utils, pcap-match }:
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

        packages = [ pythonEnv pkgs.coreutils pkgs.go-task pcap-match.packages.${system}.default ];
      in
      {
        # Interactive Development Shell: use with `nix develop` for an
        # interactive shell or `nix develop -c <CMD>` for a one-off command
        devShells.default = pkgs.mkShell {
          inherit packages;

          shellHook = ''
            echo "Research environment loaded!"
          '';
        };
      }
    );
}
