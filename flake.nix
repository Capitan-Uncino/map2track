{
  description = "Procedural Track Generator Environment";

  inputs = {
    nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";
    flake-utils.url = "github:numtide/flake-utils";
  };

  outputs = { self, nixpkgs, flake-utils }:
    flake-utils.lib.eachDefaultSystem (system:
      let
        pkgs = nixpkgs.legacyPackages.${system};
      in
      {
        devShells.default = pkgs.mkShell {
          # Bring in base Python, the venv hook, and system libraries
          buildInputs = [
            pkgs.python3
            pkgs.python3Packages.venvShellHook
            pkgs.blender
            
            # Libraries required for PyPI wheels (build123d/OpenCASCADE)
            pkgs.stdenv.cc.cc.lib 
            pkgs.libGL            
            pkgs.xorg.libX11
            pkgs.zlib
          ];

          # Define the local virtual environment directory
          venvDir = "./.venv";

          # This block ONLY runs once, right after the .venv is created
          postVenvCreation = ''
            unset SOURCE_DATE_EPOCH
            echo "Installing Python dependencies into local .venv..."
            pip install numpy scipy requests pyproj osmnx build123d
          '';

          # This block runs every time you enter the shell (`nix develop`)
          postShellHook = ''
            # Fix dynamic linking for pre-compiled Python wheels
            export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath [ 
              pkgs.stdenv.cc.cc.lib 
              pkgs.libGL 
              pkgs.xorg.libX11
              pkgs.zlib
            ]}:$LD_LIBRARY_PATH"

            unset SOURCE_DATE_EPOCH
            
            echo "==========================================="
            echo "🏎️  Track Generator Environment Activated"
            echo "==========================================="
            echo "Available commands:"
            echo "  python track_builder.py   -> Run the pipeline"
            echo "  blender                   -> Open headless/GUI Blender"
          '';
        };
      }
    );
}
