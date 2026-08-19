#pragma once

#include "app.h"

#include <ftxui/component/component.hpp>
#include <ftxui/component/screen_interactive.hpp>

namespace nw {
namespace ui {

/// Build and run the main TUI application.
/// This function blocks until the user quits.
void run(AppState& state);

} // namespace ui
} // namespace nw
