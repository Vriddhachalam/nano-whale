#include "platform.h"

#include <algorithm>
#include <array>
#include <cstdio>
#include <cstdlib>
#include <sstream>
#include <stdexcept>

#ifdef _WIN32
#include <windows.h>
#else
#include <unistd.h>
#include <limits.h>
#include <sys/wait.h>
#endif

namespace nw {
namespace platform {

bool is_windows() {
#ifdef _WIN32
    return true;
#else
    return false;
#endif
}

void setup_terminal() {
#ifdef _WIN32
    SetConsoleOutputCP(CP_UTF8);
    SetConsoleCP(CP_UTF8);
#endif
}

std::string get_hostname() {
#ifdef _WIN32
    char buf[256];
    DWORD size = sizeof(buf);
    if (GetComputerNameA(buf, &size)) {
        return std::string(buf, size);
    }
    return "unknown";
#else
    char buf[256];
    if (gethostname(buf, sizeof(buf)) == 0) {
        return std::string(buf);
    }
    return "unknown";
#endif
}

std::string get_docker_cmd() {
    static std::string cmd = "";
    if (!cmd.empty()) {
        return cmd;
    }

    if (const char* env_p = std::getenv("DOCKER_CMD")) {
        cmd = env_p;
        return cmd;
    }

#ifdef _WIN32
    if (std::system("docker --version >nul 2>&1") == 0) {
        cmd = "docker";
    } else if (std::system("wsl docker --version >nul 2>&1") == 0) {
        cmd = "wsl docker";
    } else {
        cmd = "docker"; // Fallback
    }
#else
    cmd = "docker";
#endif

    return cmd;
}

std::optional<std::string> exec_command(const std::string& cmd, int /*timeout_ms*/) {
    // Note: timeout_ms is accepted for API compatibility but basic implementation
    // does not enforce timeouts. For production use, consider platform-specific
    // async process APIs.
    std::string result;
    std::array<char, 4096> buffer;

    std::string full_cmd = cmd;
#ifdef _WIN32
    full_cmd += " 2>nul";
    FILE* pipe = _popen(full_cmd.c_str(), "r");
#else
    full_cmd += " 2>/dev/null";
    FILE* pipe = popen(full_cmd.c_str(), "r");
#endif

    if (!pipe) {
        return std::nullopt;
    }

    while (fgets(buffer.data(), static_cast<int>(buffer.size()), pipe) != nullptr) {
        result += buffer.data();
    }

#ifdef _WIN32
    int status = _pclose(pipe);
#else
    int status = pclose(pipe);
#endif

    if (status != 0 && result.empty()) {
        return std::nullopt;
    }

    return trim(result);
}

void spawn_new_window(const std::string& cmd, const std::string& label) {
#ifdef _WIN32
    // Try Windows Terminal first, fallback to cmd
    std::string wt_cmd = "wt new-tab --title \"" + label + "\" cmd /k " + cmd;
    std::string fallback = "start cmd /k " + cmd;

    if (std::system(("where wt >nul 2>&1")) == 0) {
        std::system(wt_cmd.c_str());
    } else {
        std::system(fallback.c_str());
    }
#elif defined(__APPLE__)
    std::string osa = "osascript -e 'tell application \"Terminal\" to do script \"" + cmd + "\"'";
    std::system(osa.c_str());
#else
    // Linux: try common terminal emulators
    const char* terminals[] = {
        "x-terminal-emulator",
        "gnome-terminal",
        "xterm",
        "konsole",
    };

    for (const auto& term : terminals) {
        std::string check = std::string("which ") + term + " >/dev/null 2>&1";
        if (std::system(check.c_str()) == 0) {
            std::string spawn_cmd;
            if (std::string(term) == "gnome-terminal") {
                spawn_cmd = std::string(term) + " -- " + cmd + " &";
            } else {
                spawn_cmd = std::string(term) + " -e " + cmd + " &";
            }
            std::system(spawn_cmd.c_str());
            return;
        }
    }
#endif
}

std::vector<std::string> split(const std::string& str, char delimiter) {
    std::vector<std::string> tokens;
    std::string token;
    std::istringstream stream(str);
    while (std::getline(stream, token, delimiter)) {
        tokens.push_back(token);
    }
    return tokens;
}

std::string trim(const std::string& str) {
    const auto strBegin = str.find_first_not_of(" \t\n\r");
    if (strBegin == std::string::npos) return "";

    const auto strEnd = str.find_last_not_of(" \t\n\r");
    return str.substr(strBegin, strEnd - strBegin + 1);
}

void open_url(const std::string& url) {
    if (url.empty()) return;
#ifdef _WIN32
    std::string cmd = "start \"\" \"" + url + "\"";
#elif defined(__APPLE__)
    std::string cmd = "open \"" + url + "\"";
#else
    std::string cmd = "xdg-open \"" + url + "\" &";
#endif
    std::system(cmd.c_str());
}

} // namespace platform
} // namespace nw
