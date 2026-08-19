///
/// nano-whale — Lightweight Docker TUI (C++ / FTXUI)
///
/// Entry point: checks Docker availability, bootstraps state, and launches the UI.
///

#include "app.h"
#include "docker.h"
#include "ui.h"
#include "platform.h"

#include <iostream>

int main() {
    // Setup terminal environment (e.g. UTF-8 code page)
    nw::platform::setup_terminal();

    // Initialize application state
    nw::AppState state;

    // Check Docker availability
    state.docker_available = nw::docker::is_available();

    if (state.docker_available) {
        // Initial data load
        nw::refresh_all(state);
    }

    // Launch the TUI
    nw::ui::run(state);

    return 0;
}
