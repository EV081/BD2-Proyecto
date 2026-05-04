{
  description = "BD2-Proyecto development shell";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-24.11";

  outputs = { self, nixpkgs }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = f: nixpkgs.lib.genAttrs systems (system: f system);
    in {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python311;
        in {
          default = pkgs.mkShell {
            packages = [
              python
              pkgs.git
            ];

            shellHook = ''
              export PYTHONPATH="$PWD:$PYTHONPATH"

              if [ ! -d .venv ]; then
                python -m venv .venv
              fi

              . .venv/bin/activate

              if [ ! -f .venv/.requirements-installed ] || [ requirements.txt -nt .venv/.requirements-installed ]; then
                python -m pip install --upgrade pip
                python -m pip install -r requirements.txt
                touch .venv/.requirements-installed
              fi

              echo "BD2-Proyecto listo. Usa: uvicorn main:app --reload"
            '';
          };
        });
    };
}