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
        
        # Provision Python and the natively packaged heavy GIS/Math libraries
        pythonEnv = pkgs.python3.withPackages (ps: with ps; [
          numpy
          scipy
          requests
          pyproj
          osmnx
          pip
          venvShellHook
        ]);
      in
      {
        devShells.default = pkgs.mkShell {
          # Define standard packages to bring into the shell
          buildInputs = [
            pythonEnv
            pkgs.blender
            
            # Libraries required for PyPI wheels (like build123d/OpenCASCADE) to run on Nix
            pkgs.stdenv.cc.cc.lib 
            pkgs.libGL            
            pkgs.xorg.libX11
          ];

          # Create a local venv directory so pip doesn't complain about read-only Nix store
          venvDir = "./.venv";

          shellHook = ''
            # Fix dynamic linking for pre-compiled Python wheels downloaded via pip
            export LD_LIBRARY_PATH="${pkgs.lib.makeLibraryPath [ 
              pkgs.stdenv.cc.cc.lib 
              pkgs.libGL 
              pkgs.xorg.libX11 
            ]}:$LD_LIBRARY_PATH"

            echo "==========================================="
            echo "🏎️  Track Generator Environment Activated"
            echo "==========================================="
            
            # Check if build123d is installed in the local venv, install if missing
            if ! python -c "import build123d" &> /dev/null; then
                echo "Installing build123d CAD library..."
                pip install build123d --quiet
            fi

            echo ""
            echo "Available commands:"
            echo "  python track_builder.py   -> Run the pipeline"
            echo "  blender                   -> Open headless/GUI Blender"
          '';
        };
      }
    );
}
