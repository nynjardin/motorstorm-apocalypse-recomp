fn main() {
    // The exe's icon in Explorer: the game's own (icons\game.ico, made from the player's ICON0.PNG
    // by scripts\make_game_icon.ps1, never in Git) when it is there, else ours (icons\icon.ico).
    println!("cargo:rerun-if-changed=icons/game.ico");
    let mut attributes = tauri_build::Attributes::new();
    if std::path::Path::new("icons/game.ico").exists() {
        attributes = attributes.windows_attributes(tauri_build::WindowsAttributes::new().window_icon_path("icons/game.ico"));
    }
    tauri_build::try_build(attributes).expect("tauri-build");
}
