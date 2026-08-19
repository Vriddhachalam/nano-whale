#pragma once

#include "docker.h"

#include <deque>
#include <map>
#include <set>
#include <string>
#include <vector>
#include <mutex>
#include <atomic>
#include <nlohmann/json.hpp>

namespace nw {

struct FileExplorerState {
    bool show = false;
    std::string container;
    std::string current_path = "/";
    std::vector<struct docker::FileEntry> files;
    int selected = 0;
};

/// Maximum number of data points to keep in CPU/memory history.
constexpr int MAX_HISTORY = 80;

/// Tab identifiers.
enum class Tab { Logs = 0, Stats, Env, Config, Top, Compose, About };
constexpr const char* TAB_NAMES[] = {"Logs", "Stats", "Env", "Config", "Top", "Compose", "About"};
constexpr int TAB_COUNT = 7;

/// Which left-panel list is focused.
enum class FocusedList { Containers = 0, Images, Volumes, Networks };

/// Global application state.
struct AppState {
    // Docker data
    std::vector<Container> containers;
    std::vector<Image> images;
    std::vector<Volume> volumes;
    std::vector<Network> networks;

    // Stats
    std::map<std::string, ContainerStats> stats;
    std::map<std::string, std::deque<double>> cpu_history;
    std::map<std::string, std::deque<double>> mem_history;

    // Cache for env/config/top (keyed by container name)
    std::map<std::string, std::vector<std::string>> env_cache;
    std::map<std::string, nlohmann::json> config_cache;
    std::map<std::string, std::string> top_cache;

    // Selection state
    int selected_container = 0;
    int selected_image = 0;
    int selected_volume = 0;
    int selected_network = 0;

    // Marks for batch operations
    std::set<std::string> marked_containers;
    std::set<std::string> marked_images;
    std::set<std::string> marked_volumes;

    // UI state
    Tab current_tab = Tab::Logs;
    FocusedList focused_list = FocusedList::Containers;

    // Logs
    std::string logs_content;
    bool logs_auto_scroll = true;

    // Help
    bool show_help = false;

    // Inspect
    bool show_inspect = false;
    std::string inspect_content;

    // File Explorer
    FileExplorerState file_explorer;

    // Notification
    std::string notification;
    std::string notification_color;

    // Compose
    bool compose_available = false;
    bool compose_running = false;
    std::string compose_logs;

    // Confirm dialog
    bool show_confirm = false;
    std::string confirm_message;

    // Thread safety
    std::mutex mtx;

    // Running flag
    std::atomic<bool> running{true};

    // Docker available
    bool docker_available = false;
};

/// Refresh all Docker data in the state.
void refresh_all(AppState& state);

/// Refresh just containers and stats.
void refresh_containers(AppState& state);

/// Refresh images, volumes, networks.
void refresh_misc(AppState& state);

/// Get the currently selected container (or nullptr).
const Container* get_selected_container(const AppState& state);

} // namespace nw
