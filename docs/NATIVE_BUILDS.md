Native builds
=============

This project includes optional native components (a WPF/C# overlay and a small Rust audio streamer) that are not built by the Python packaging step.

Requirements (Windows):
- .NET SDK 6.0+ (for WPF overlay build)
- Visual Studio (recommended) for building the WPF project
- Rust toolchain (rustc/cargo) for the audio streamer

High-level steps:
1. Build WPF overlay: open the Visual Studio solution in `native/overlay` (if present) and build the Release configuration.
2. Build Rust audio streamer: cd into `native/audio_streamer` and run `cargo build --release`.
3. Copy the produced binaries into the `build/PCController` folder before running PyInstaller packaging so the exe can include them.

If you want, I can create CI scripts that build these components and produce an installer.
