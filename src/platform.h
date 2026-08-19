#pragma once

#include <string>
#include <vector>
#include <optional>

namespace nw {
namespace platform {

/// Returns true if running on Windows.
bool is_windows();

/// Setup terminal environment (e.g. set UTF-8 code page on Windows)
void setup_terminal();

/// Returns the machine hostname.
std::string get_hostname();

/// Returns the docker command prefix ("wsl docker" on Windows, "docker" elsewhere).
std::string get_docker_cmd();

/// Execute a shell command and capture its stdout. Returns nullopt on failure.
std::optional<std::string> exec_command(const std::string& cmd, int timeout_ms = 5000);

/// Open a new terminal window with the given command.
void spawn_new_window(const std::string& cmd, const std::string& label);

/// Split a string by a delimiter.
std::vector<std::string> split(const std::string& str, char delimiter);

/// Trim whitespace from both ends of a string.
std::string trim(const std::string& str);

/// Open a URL in the default browser.
void open_url(const std::string& url);

} // namespace platform
} // namespace nw
