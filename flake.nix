{
  description = "Development environment for the Taiwan stock report widget";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs = { nixpkgs, ... }:
    let
      systems = [ "x86_64-linux" "aarch64-linux" ];
      forAllSystems = nixpkgs.lib.genAttrs systems;
    in
    {
      devShells = forAllSystems (system:
        let
          pkgs = import nixpkgs { inherit system; };
          python = pkgs.python3.withPackages (ps: [ ps.pyside6 ]);
          stock-report = pkgs.writeShellScriptBin "stock-report" ''
            exec ${python}/bin/python -m stock_report "$@"
          '';
        in
        {
          default = pkgs.mkShell {
            packages = [ python stock-report pkgs.just pkgs.uv ];

            # Use Nix's Qt bindings instead of binary wheels from .venv.
            STOCK_REPORT_PYTHON = "${python}/bin/python";
            QT_PLUGIN_PATH = pkgs.lib.makeSearchPath pkgs.qt6.qtbase.qtPluginPrefix [
              pkgs.qt6.qtbase
              pkgs.qt6.qtwayland
            ];
          };
        });
    };
}
